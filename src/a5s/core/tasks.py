"""Durable tasks, with checkpoints, leases, fresh-worker resume and ledger evidence.

A task and the children it makes are a tree, which shares its root's budget: each task's own
budget is the most it may spend, and the tree together spends no more than its root's. Every
token a slice reports counts, past a budget too, and a report past one ends the task at once;
a slice is told what's left, the most it may spend. A slice that fails, or loses its lease,
leaves its task waiting a little longer each time, and after MAX_FAILURES in a row the task
fails. A result the core refuses blocks the task, for a person to decide, rather than leave
it to be done again. Cancelling a task cancels its children too, and what the slice at work
did meanwhile is kept. Only the core writes a task (migration 0045_round9.sql).

A slice runs either here, on a worker given to run_next, with a heartbeat renewing its lease,
or as one of a5s's runs (core/tasking.py), with begin and end: then its lease lasts as long as
the run may, and what it spent is the run's own count of its tokens. A task someone asked for
waits as offered until they say yes. Each method works in a transaction of its own, or in the
caller's, `within`.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import ledger

log = logging.getLogger(__name__)
MAX_DEPTH = 3
MAX_CHILDREN = 8
# A task's plan, as its runs keep it: a short list of named steps, each pending, in progress
# or completed, in the shape of LangChain's todos (`write_todos`), which models know, but kept
# by the core with the task, so a fresh worker's run is shown it and the task's owner sees it.
# Deep Agents' own `write_todos` stays off: it would live in one run's state, and go with it.
PLAN_STEPS = 20  # the most steps a plan names
PLAN_CHARS = 200  # the most characters a step says
PLANNED = ("pending", "in_progress", "completed")
ENDED = ("done", "cancelled", "failed")
OFFERED = "offered"  # asked for, and waiting for its owner's yes
MAX_FAILURES = 5  # slices in a row that fail or lose their lease, before the task fails [TBC]
BACKOFF = timedelta(seconds=30)  # how long a task waits after a slice fails, doubling [TBC]
BACKOFF_MOST = timedelta(hours=1)
PUT_OFF = timedelta(minutes=30)  # how long a task waits when its slice's run can't open [TBC]


class TaskError(RuntimeError):
    pass


def planned(before: list[dict], plan: Any) -> list[dict]:
    """A task's plan as a run would have it, checked: its steps, each with its content and
    whether it's pending, in_progress or completed, at most one in progress, and every step
    that was completed still completed, in its words, so a plan moves forward as its task does.
    Otherwise, TaskError."""
    if not isinstance(plan, list) or len(plan) > PLAN_STEPS:
        raise TaskError(f"a task's plan is a list of at most {PLAN_STEPS} steps")
    steps = []
    for item in plan:
        said = " ".join(str(item.get("content", "")).split()) if isinstance(item, dict) else ""
        status = item.get("status") if isinstance(item, dict) else None
        if not said or len(said) > PLAN_CHARS or status not in PLANNED:
            raise TaskError(f"each step of a plan says what it is, in at most {PLAN_CHARS} "
                            "characters, as its content, and whether it's pending, in_progress "
                            "or completed")
        steps.append({"content": said, "status": status})
    if sum(s["status"] == "in_progress" for s in steps) > 1:
        raise TaskError("a plan has at most one step in progress at a time")
    now_done = iter(s["content"] for s in steps if s["status"] == "completed")
    if not all(any(step == d for d in now_done)
               for step in (s["content"] for s in before if s["status"] == "completed")):
        raise TaskError("a plan keeps every step it had completed, completed, in its words")
    return steps


def backoff(failures: int) -> timedelta:
    """How long a task waits after this many slices in a row failed."""
    return min(BACKOFF * 2 ** max(0, failures - 1), BACKOFF_MOST)


class TaskStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskSpec:
    instance: str
    owner: str
    task: str
    audience: tuple[str, ...] = ()
    token_budget: int = 100_000
    deadline: datetime | None = None
    parent: str | None = None


@dataclass
class _Moved:
    """What a slice's report would set, once checked: or why it's refused."""
    step: int
    progress: float
    partial: Any
    plan: list[dict]
    refused: str | None = None


class TaskService:
    def __init__(self, database_url: str, lease_seconds: float = 60):
        self.url = database_url
        self.lease_seconds = lease_seconds
        self.clock = lambda: datetime.now(UTC)

    @contextmanager
    def _tx(self, within: psycopg.Connection | None) -> Iterator[psycopg.Connection]:
        if within is not None:
            yield within
            return
        with db.transaction(self.url) as own:
            yield own

    def create(self, spec: TaskSpec, *, offered_run: str | None = None,
               asked_at: datetime | None = None,
               within: psycopg.Connection | None = None) -> str:
        """A new task, queued, or, with `offered_run`, the run that offered it, waiting for its
        owner's yes to a message that came after `asked_at`."""
        now = self.clock()
        deadline = spec.deadline or now + timedelta(days=1)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if not spec.task.strip() or len(spec.task) > 10_000:
            raise TaskError("a task needs a task of 1 to 10,000 characters")
        if spec.token_budget <= 0 or deadline <= now:
            raise TaskError("a task needs a positive token budget and a future deadline")
        audience = spec.audience or (spec.owner,)
        if spec.owner not in audience:
            raise TaskError("the task's owner is in its audience")
        task_id = str(uuid.uuid4())
        with self._tx(within) as conn:
            depth, root = 0, task_id
            if spec.parent:
                parent = self._locked(conn, spec.parent)
                if parent is None or parent["status"] in ENDED:
                    raise TaskError("a parent task must be open")
                if spec.instance != parent["instance_id"] or spec.owner != parent["owner"]:
                    raise TaskError("a child keeps its parent's instance and owner")
                if not set(audience) <= set(parent["audience"]):
                    raise TaskError("a child's audience may only narrow its parent's")
                if parent["depth"] >= MAX_DEPTH:
                    raise TaskError("the task's child depth is exhausted")
                children = conn.execute("select count(*) as n from tasks where parent = %s",
                                        (spec.parent,)).fetchone()["n"]
                if children >= MAX_CHILDREN:
                    raise TaskError("the parent task's child count is exhausted")
                used = conn.execute("select coalesce(sum(token_budget), 0) as n from tasks "
                                    "where parent = %s", (spec.parent,)).fetchone()["n"]
                if parent["tokens"] + used + spec.token_budget > parent["token_budget"]:
                    raise TaskError("the child doesn't fit the parent's total token budget")
                if spec.token_budget > self._tree_left(conn, parent):
                    raise TaskError("the child doesn't fit what's left of its tree's budget")
                if deadline > parent["deadline"]:
                    raise TaskError("the child's deadline may not outlast its parent's")
                depth, root = parent["depth"] + 1, parent["root"]
            conn.execute(
                "insert into tasks (id, instance_id, owner, audience, task, token_budget, "
                "deadline, parent, depth, root, status, offered_run, asked_at) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (task_id, spec.instance, spec.owner, list(audience), spec.task,
                 spec.token_budget, deadline, spec.parent, depth, root,
                 OFFERED if offered_run else "queued", offered_run, asked_at))
            self._record(conn, task_id, "offer" if offered_run else "start",
                         instance=spec.instance, acts_for=list(audience),
                         args={"task": spec.task, "token_budget": spec.token_budget,
                               "deadline": deadline.isoformat(), "parent": spec.parent})
        return task_id

    def confirm(self, task_id: str, by: str, within: psycopg.Connection | None = None) -> dict:
        """Start a task its owner said yes to."""
        with self._tx(within) as conn:
            row = self._owned(conn, task_id, by)
            if row["status"] != OFFERED:
                raise TaskError(f"a {row['status']} task isn't waiting for a yes")
            row = self._status(conn, row, "queued")
            self._record(conn, task_id, "start", instance=row["instance_id"],
                         acts_for=row["audience"], args={"by": by})
            return self._get(conn, task_id)

    @staticmethod
    def _public(row: dict | None) -> dict | None:
        if row is None:
            return None
        return {**row, **{key: str(row[key]) for key in ("id", "parent", "lease_id", "root")
                          if row.get(key) is not None}}

    def get(self, task_id: str, within: psycopg.Connection | None = None) -> dict | None:
        with self._tx(within) as conn:
            return self._get(conn, task_id)

    def list_for(self, owner: str) -> list[dict]:
        with db.transaction(self.url) as conn:
            return [self._public(r) for r in conn.execute(
                "select * from tasks where owner = %s order by created_at, id", (owner,)).fetchall()]

    def due(self, now: datetime | None = None,
            within: psycopg.Connection | None = None) -> list[str]:
        """The tasks a worker may take up now: queued, or waiting and not waiting longer after
        a failed slice, or running under a lease that lapsed."""
        now = now or self.clock()
        with self._tx(within) as conn:
            return [str(r["id"]) for r in conn.execute(
                "select id from tasks where (status in ('queued', 'waiting') and "
                "(not_before is null or not_before <= %s)) "
                "or (status = 'running' and lease_expires_at <= %s) order by created_at, id",
                (now, now)).fetchall()]

    def cancel(self, task_id: str, by: str, within: psycopg.Connection | None = None) -> dict:
        """Cancel a task, and every child of it still open, at its owner's request. A slice at
        work keeps its lease, so what it did meanwhile still counts, but can do no more."""
        with self._tx(within) as conn:
            row = self._owned(conn, task_id, by)
            if row["status"] in ENDED:
                raise TaskError(f"a {row['status']} task can't be cancelled")
            stopped = conn.execute(
                "with recursive tree as (select id from tasks where id = %s union all "
                "select t.id from tasks t join tree on t.parent = tree.id) "
                "update tasks set status = 'cancelled', lease_expires_at = null, "
                "last_error = null, not_before = null, updated_at = %s "
                "where id in (select id from tree) and status not in "
                "('done', 'cancelled', 'failed') returning id::text as id, instance_id, audience",
                (task_id, self.clock())).fetchall()
            for t in stopped:
                self._record(conn, t["id"], "cancel", instance=t["instance_id"],
                             acts_for=t["audience"],
                             args={"by": by, **({"with": task_id} if t["id"] != task_id else {})})
            return self._get(conn, task_id)

    def resume(self, task_id: str, by: str, within: psycopg.Connection | None = None) -> dict:
        with self._tx(within) as conn:
            row = self._owned(conn, task_id, by)
            if row["status"] not in ("blocked", "failed", "waiting"):
                raise TaskError("only a blocked, failed or waiting task resumes")
            row = self._status(conn, row, "waiting", error=None, failures=0)
            self._record(conn, task_id, "resume", instance=row["instance_id"],
                         acts_for=row["audience"], args={"by": by})
            return row

    def begin(self, task_id: str, *, lease_seconds: float | None = None,
              within: psycopg.Connection | None = None) -> tuple[str | None, dict]:
        """Begin a task's next slice, under a lease of its own for `lease_seconds`: the lease
        and the task as it then stands, with `tokens_left`, the most the slice may spend. Or
        None and the task, ended, if it can't go on: past its deadline, its budget or its tree's
        spent, or its slices failed too often (its `last_error` says which). TaskError if it
        can't run at all, such as when it's done, or another worker holds its lease."""
        with self._tx(within) as conn:
            row = self._locked(conn, task_id)
            if row is None:
                raise TaskError("no such task")
            now = self.clock()
            if row["status"] in (OFFERED, "done", "cancelled", "blocked", "failed"):
                raise TaskError(f"a {row['status']} task can't run")
            if row["status"] == "running" and row["lease_expires_at"] > now:
                raise TaskError("the task's current worker still holds its lease")
            lapsed = row["status"] == "running"  # its last worker stopped, and said nothing
            failures = row["failures"] + lapsed
            left = min(row["token_budget"] - row["tokens"], self._tree_left(conn, row))
            reason = ("its deadline passed" if row["deadline"] <= now
                      else "its token budget is spent" if row["tokens"] >= row["token_budget"]
                      else "the budget its tree shares is spent" if left <= 0
                      else f"its slices failed {MAX_FAILURES} times in a row"
                      if failures >= MAX_FAILURES else None)
            if reason:
                self._status(conn, row, "failed", error=reason, failures=failures)
                self._record(conn, task_id, "stop", instance=row["instance_id"],
                             acts_for=row["audience"], args={"why": reason})
                return None, self._get(conn, task_id)
            lease = str(uuid.uuid4())
            conn.execute("update tasks set status = 'running', lease_id = %s, "
                         "lease_expires_at = %s, last_heartbeat_at = %s, attempts = attempts + 1, "
                         "failures = %s, not_before = null, last_error = null, updated_at = %s "
                         "where id = %s",
                         (lease, now + timedelta(seconds=lease_seconds or self.lease_seconds),
                          now, failures, now, task_id))
            self._record(conn, task_id, "slice", instance=row["instance_id"],
                         acts_for=row["audience"], args={"attempt": row["attempts"] + 1,
                                                          "tokens_left": left,
                                                          **({"lapsed": True} if lapsed else {})})
            return lease, {**self._get(conn, task_id), "tokens_left": left}

    def put_off(self, task_id: str, why: str, *,
                within: psycopg.Connection | None = None) -> dict | None:
        """Put a task's next slice off for PUT_OFF, when its run can't open now for a reason
        outside the task, such as its owner's budget for the day being spent, so the task
        isn't asked for again at every sweep. It isn't a failed slice, since nothing ran,
        unless its last worker's lease lapsed. Past its deadline, the task fails instead. The
        task as it then stands, or None if it's gone."""
        with self._tx(within) as conn:
            row = self._locked(conn, task_id)
            if row is None:
                return None
            now = self.clock()
            lapsed = row["status"] == "running" and row["lease_expires_at"] <= now
            if row["status"] not in ("queued", "waiting") and not lapsed:
                return self._get(conn, task_id)  # ended, or at work under a live lease
            if row["deadline"] <= now:
                reason = "its deadline passed"
                self._status(conn, row, "failed", error=reason, failures=row["failures"] + lapsed)
                self._record(conn, task_id, "stop", instance=row["instance_id"],
                             acts_for=row["audience"], args={"why": reason})
            else:
                self._status(conn, row, "waiting" if lapsed else row["status"], error=why[:200],
                             failures=row["failures"] + lapsed, not_before=now + PUT_OFF)
            return self._get(conn, task_id)

    def run_next(self, task_id: str, worker: Callable[[dict, Callable[[dict], None]], dict]) -> dict:
        """Run a task's next slice on `worker`, under a lease of its own, which a heartbeat
        renews while it works: the task as it then stands. The worker is given the task, with
        `tokens_left`, the most its slice may spend, and a way to keep a checkpoint."""
        lease, execution = self.begin(task_id)
        if lease is None:
            return execution
        stop = threading.Event()
        heart = threading.Thread(target=self._heartbeat, args=(task_id, lease, stop),
                                 name="a5s-task-heartbeat", daemon=True)
        heart.start()
        failed = None
        try:
            result = worker(execution, lambda change: self.checkpoint(task_id, lease, change))
        except TaskStopped:
            result = None
        except Exception as exc:  # noqa: BLE001 - a failed slice waits with its checkpoints
            result, failed = None, str(exc)[:500] or type(exc).__name__
        finally:
            stop.set()
            heart.join()
        return self._finish(task_id, lease, result, failed)

    def checkpoint(self, task_id: str, lease: str, change: dict) -> None:
        """Keep what a slice did so far. Its tokens count whatever else happens. TaskStopped if
        the slice may do no more: its task was cancelled, or ended at its deadline or budget,
        or another worker has it; TaskError if what it says doesn't move the task forward."""
        with db.transaction(self.url) as conn:
            stopped, refused = self.kept(conn, task_id, lease, change)
        if stopped:
            raise TaskStopped(stopped)
        if refused:
            raise TaskError(refused)

    def kept(self, conn: psycopg.Connection, task_id: str, lease: str,
             change: dict) -> tuple[str | None, str | None]:
        """A checkpoint, in the caller's transaction: why the slice must stop, if it must, and
        why what it said is refused, if it is. What it spent counts either way."""
        stopped = refused = None
        row = self._locked(conn, task_id)
        if row is None:
            return "the task is gone", None
        used, bad = self._used(change)
        tokens = row["tokens"] + used
        if row["lease_id"] != lease:  # taken over, or never this slice's: it counts, and stops
            self._spend(conn, row, tokens, "late", used)
            stopped = "the task is no longer running under this lease"
        elif row["status"] != "running":  # cancelled as it worked: what it did is kept
            moved = self._moved(row, change)
            self._keep(conn, row, tokens, moved if moved.refused is None else None,
                       row["status"], row["last_error"], lease=lease)
            stopped = f"the task was {row['status']}"
        else:
            reason = self._over(conn, row, tokens)
            moved = self._moved(row, change)
            if reason:  # it counts, and ends the task, before anything more is spent
                self._keep(conn, row, tokens, moved if moved.refused is None else None,
                           "failed", reason)
                stopped = reason
            elif bad or moved.refused:  # its tokens count; the rest is refused
                self._spend(conn, row, tokens, "refused", used, why=bad or moved.refused)
                refused = bad or moved.refused
            else:
                now = self.clock()
                conn.execute("update tasks set step = %s, progress = %s, partial = %s, "
                             "plan = %s, tokens = %s, last_heartbeat_at = %s, "
                             "lease_expires_at = %s, updated_at = %s where id = %s",
                             (moved.step, moved.progress, Jsonb(moved.partial),
                              Jsonb(moved.plan), tokens, now,
                              now + timedelta(seconds=self.lease_seconds), now, task_id))
                self._record(conn, task_id, "checkpoint", instance=row["instance_id"],
                             acts_for=row["audience"],
                             args={"step": moved.step, "progress": moved.progress,
                                   "partial": moved.partial, "tokens": tokens,
                                   **_planned(moved.plan)})
        return stopped, refused

    def heartbeat(self, task_id: str, lease: str) -> bool:
        """Renew a slice's lease: False once the slice should stop, as its task is no longer
        running under it, or its deadline has passed."""
        with db.transaction(self.url) as conn:
            row = self._get(conn, task_id, lock=True)
            if row is None or row["status"] != "running" or row["lease_id"] != lease:
                return False
            now = self.clock()
            if row["deadline"] <= now:
                return False
            conn.execute("update tasks set last_heartbeat_at = %s, lease_expires_at = %s, "
                         "updated_at = %s where id = %s", (now, now + timedelta(
                             seconds=self.lease_seconds), now, task_id))
            return True

    def _heartbeat(self, task_id: str, lease: str, stop: threading.Event) -> None:
        """Renew the lease while the slice works. A database that fails for a moment, such as
        in a failover, is tried again at the next beat, and said once: only a lease left
        unrenewed for its whole time lapses."""
        failing = False
        while not stop.wait(max(0.01, self.lease_seconds / 3)):
            try:
                if not self.heartbeat(task_id, lease):
                    return
            except psycopg.Error as exc:
                if not failing:
                    log.warning("couldn't renew task %s's lease, trying again: %s",
                                task_id, type(exc).__name__)
                failing = True
                continue
            if failing:
                log.info("renewed task %s's lease again", task_id)
                failing = False

    def end(self, task_id: str, lease: str, result: dict | None, failed: str | None = None, *,
            spent: int = 0, within: psycopg.Connection | None = None) -> dict:
        """End a slice begun with begin: with its result, or None if it stopped or `failed`,
        and `spent`, the tokens its run used, which count whatever it came to."""
        return self._finish(task_id, lease, result, failed, spent=spent, within=within)

    def _finish(self, task_id: str, lease: str, result: dict | None,
                failed: str | None = None, *, spent: int = 0,
                within: psycopg.Connection | None = None) -> dict:
        """What a slice ended with: its result, or None if it stopped or `failed`."""
        with self._tx(within) as conn:
            row = self._locked(conn, task_id)
            if row is None:
                raise TaskError("no such task")
            ours = row["lease_id"] == lease
            now = self.clock()
            if result is None and spent:  # what its run spent counts, whatever came of it
                self._spend(conn, row, row["tokens"] + spent, "spent", spent)
                row = self._locked(conn, task_id)
            if result is None:
                if ours and row["status"] == "running":  # it failed, or stopped: it waits
                    failures = row["failures"] + 1
                    why = failed or "the slice stopped"
                    if failures >= MAX_FAILURES:
                        why = f"its slices failed {MAX_FAILURES} times in a row: {why}"
                    status = "failed" if failures >= MAX_FAILURES else "waiting"
                    row = self._status(conn, row, status, error=why, failures=failures,
                                       not_before=now + backoff(failures)
                                       if status == "waiting" else None)
                    self._record(conn, task_id, "stop", instance=row["instance_id"],
                                 acts_for=row["audience"], args={"why": why})
                elif ours:  # cancelled under it: the lease goes with the slice
                    conn.execute("update tasks set lease_id = null where id = %s", (task_id,))
                return self._get(conn, task_id)
            used, bad = self._used(result)
            used += spent
            tokens = row["tokens"] + used
            if not ours:  # a stale slice's, whose lease another took: what it spent counts
                self._spend(conn, row, tokens, "late", used)
                return self._get(conn, task_id)
            moved = self._moved(row, result)
            if row["status"] != "running":  # cancelled as it worked: what it did is kept
                self._keep(conn, row, tokens, moved if moved.refused is None and not bad else None,
                           row["status"], row["last_error"],
                           result=result.get("result"), lease=lease)
                return self._get(conn, task_id)
            status = result.get("status", "waiting")
            refused = bad or moved.refused or (
                f"a worker returned an unknown task status: {status}"
                if status not in ("waiting", "blocked", "done", "failed")
                else "a blocked task needs a reason"
                if status == "blocked" and not result.get("reason") else None)
            if refused:  # done again, it might repeat what it did: a person decides
                self._keep(conn, row, tokens, None, "blocked", f"a5s refused its result: {refused}")
                return self._get(conn, task_id)
            error = result.get("error") or result.get("reason")
            reason = self._over(conn, row, tokens)
            if reason:
                status, error = "failed", reason
            if status == "done":
                moved.progress = 1.0
            self._keep(conn, row, tokens, moved, status, error, result=result.get("result"))
            return self._get(conn, task_id)

    # What a slice reports, checked

    @staticmethod
    def _used(said: dict) -> tuple[int, str | None]:
        """The tokens a slice says it used, and why that's refused, if it is."""
        try:
            used = int(said.get("tokens", 0))
        except (TypeError, ValueError):
            return 0, "a slice says how many tokens it used as a number"
        if used < 0:
            return 0, "a slice may not use a negative number of tokens"
        return used, None

    @staticmethod
    def _moved(row: dict, said: dict) -> _Moved:
        """Where a slice's report would take its task, if it moves it forward."""
        try:
            step = int(said.get("step", row["step"]))
            progress = float(said.get("progress", row["progress"]))
        except (TypeError, ValueError):
            return _Moved(row["step"], row["progress"], row["partial"], row["plan"],
                          "a step and progress are numbers")
        partial = said.get("partial", row["partial"])
        if step < row["step"] or not 0 <= progress <= 1 or progress < row["progress"]:
            return _Moved(row["step"], row["progress"], row["partial"], row["plan"],
                          "a checkpoint may only move a task forward")
        try:
            plan = planned(row["plan"], said["plan"]) if "plan" in said else row["plan"]
        except TaskError as exc:
            return _Moved(row["step"], row["progress"], row["partial"], row["plan"], str(exc))
        return _Moved(step, progress, partial, plan)

    def _over(self, conn: psycopg.Connection, row: dict, tokens: int) -> str | None:
        """Why a task must end now, with `tokens` spent: its deadline, or a budget."""
        if row["deadline"] <= self.clock():
            return "its deadline passed"
        if tokens > row["token_budget"]:
            return "its token budget is spent"
        if self._tree_left(conn, row) - (tokens - row["tokens"]) < 0:
            return "the budget its tree shares is spent"
        return None

    def _keep(self, conn: psycopg.Connection, row: dict, tokens: int, moved: _Moved | None,
              status: str, error: str | None, *, result: Any = None,
              lease: str | None = None) -> None:
        """Keep what a slice did, as `moved`, or only what it spent, and end its lease."""
        moved = moved or _Moved(row["step"], row["progress"], row["partial"], row["plan"])
        conn.execute("update tasks set status = %s, step = %s, progress = %s, partial = %s, "
                     "plan = %s, result = coalesce(%s, result), tokens = %s, lease_id = null, "
                     "lease_expires_at = null, last_error = %s, failures = 0, "
                     "not_before = null, updated_at = %s where id = %s and "
                     "(%s::uuid is null or lease_id = %s::uuid)",
                     (status, moved.step, moved.progress, Jsonb(moved.partial), Jsonb(moved.plan),
                      Jsonb(result) if result is not None else None, tokens, error, self.clock(),
                      row["id"], lease, lease))
        self._record(conn, row["id"], status, instance=row["instance_id"],
                     acts_for=row["audience"], args={"step": moved.step,
                                                     "progress": moved.progress,
                                                     "partial": moved.partial, "tokens": tokens,
                                                     "error": error, **_planned(moved.plan)})

    def _spend(self, conn: psycopg.Connection, row: dict, tokens: int, action: str, used: int,
               why: str | None = None) -> None:
        """Count what a slice spent, and nothing else of what it said."""
        if not used and why is None:
            return
        conn.execute("update tasks set tokens = %s, updated_at = %s where id = %s",
                     (tokens, self.clock(), row["id"]))
        self._record(conn, row["id"], action, instance=row["instance_id"],
                     acts_for=row["audience"], args={"tokens": tokens, "used": used,
                                                     **({"why": why} if why else {})})

    @staticmethod
    def _tree_left(conn: psycopg.Connection, row: dict) -> int:
        """What's left of the budget a task's tree shares: its root's, less all it spent."""
        found = conn.execute(
            "select r.token_budget - coalesce((select sum(t.tokens) from tasks t "
            "where t.root = r.id), 0) as n from tasks r where r.id = %s",
            (row["root"],)).fetchone()
        return int(found["n"]) if found else 0

    @staticmethod
    def _get(conn, task_id: str, lock: bool = False) -> dict | None:
        found = conn.execute("select * from tasks where id = %s" + (" for update" if lock else ""),
                             (task_id,)).fetchone()
        return TaskService._public(found)

    @staticmethod
    def _locked(conn, task_id: str) -> dict | None:
        """A task, locked, after its tree's root, so what its tree spends is counted once."""
        found = conn.execute("select root from tasks where id = %s", (task_id,)).fetchone()
        if found is None:
            return None
        if str(found["root"]) != str(task_id):
            conn.execute("select 1 from tasks where id = %s for update", (found["root"],))
        return TaskService._get(conn, task_id, lock=True)

    def _owned(self, conn, task_id: str, by: str) -> dict:
        row = self._locked(conn, task_id)
        if row is None:
            raise TaskError("no such task")
        if row["owner"] != by:
            raise TaskError("only the task's owner may change it")
        return row

    @staticmethod
    def _status(conn, row: dict, status: str, error: str | None = None, *,
                failures: int | None = None, not_before: datetime | None = None) -> dict:
        conn.execute("update tasks set status = %s, lease_id = null, lease_expires_at = null, "
                     "last_error = %s, failures = coalesce(%s, failures), not_before = %s, "
                     "updated_at = now() where id = %s",
                     (status, error, failures, not_before, row["id"]))
        return {**row, "status": status, "lease_id": None, "last_error": error,
                "failures": row["failures"] if failures is None else failures,
                "not_before": not_before}

    @staticmethod
    def _record(conn, task_id: str, action: str, **entry: Any) -> None:
        args = entry.pop("args", {})
        ledger.append(conn, {"kind": "task", "action": action, "task": task_id,
                             "decision": "record", **entry, "args": ledger.mask(args)})


def _planned(plan: list[dict]) -> dict[str, Any]:
    """How far a plan has come, for the ledger: its steps by hash, and how many are completed."""
    return {"plan": plan, "steps": len(plan),
            "completed": sum(s["status"] == "completed" for s in plan)}
