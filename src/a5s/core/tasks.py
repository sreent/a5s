"""Durable tasks, with checkpoints, leases, fresh-worker resume and ledger evidence."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
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


class TaskService:
    def __init__(self, database_url: str, lease_seconds: float = 60):
        self.url = database_url
        self.lease_seconds = lease_seconds
        self.clock = lambda: datetime.now(UTC)

    def create(self, spec: TaskSpec) -> str:
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
        with db.transaction(self.url) as conn:
            depth = 0
            if spec.parent:
                parent = self._get(conn, spec.parent, lock=True)
                if parent is None or parent["status"] in ("done", "cancelled", "failed"):
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
                if deadline > parent["deadline"]:
                    raise TaskError("the child's deadline may not outlast its parent's")
                depth = parent["depth"] + 1
            conn.execute(
                "insert into tasks (id, instance_id, owner, audience, task, token_budget, "
                "deadline, parent, depth) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (task_id, spec.instance, spec.owner, list(audience), spec.task,
                 spec.token_budget, deadline, spec.parent, depth))
            self._record(conn, task_id, "start", instance=spec.instance, acts_for=list(audience),
                         args={"task": spec.task, "token_budget": spec.token_budget,
                               "deadline": deadline.isoformat(), "parent": spec.parent})
        return task_id

    @staticmethod
    def _public(row: dict | None) -> dict | None:
        if row is None:
            return None
        return {**row, **{key: str(row[key]) for key in ("id", "parent", "lease_id")
                          if row.get(key) is not None}}

    def get(self, task_id: str) -> dict | None:
        with db.transaction(self.url) as conn:
            return self._get(conn, task_id)

    def list_for(self, owner: str) -> list[dict]:
        with db.transaction(self.url) as conn:
            return [self._public(r) for r in conn.execute(
                "select * from tasks where owner = %s order by created_at, id", (owner,)).fetchall()]

    def due(self, now: datetime | None = None) -> list[str]:
        now = now or self.clock()
        with db.transaction(self.url) as conn:
            return [str(r["id"]) for r in conn.execute(
                "select id from tasks where status in ('queued', 'waiting') "
                "or (status = 'running' and lease_expires_at <= %s) order by created_at, id",
                (now,)).fetchall()]

    def cancel(self, task_id: str, by: str) -> dict:
        with db.transaction(self.url) as conn:
            row = self._owned(conn, task_id, by)
            if row["status"] in ("done", "cancelled", "failed"):
                raise TaskError(f"a {row['status']} task can't be cancelled")
            row = self._status(conn, row, "cancelled")
            self._record(conn, task_id, "cancel", instance=row["instance_id"],
                         acts_for=row["audience"], args={"by": by})
            return row

    def resume(self, task_id: str, by: str) -> dict:
        with db.transaction(self.url) as conn:
            row = self._owned(conn, task_id, by)
            if row["status"] not in ("blocked", "failed", "waiting"):
                raise TaskError("only a blocked, failed or waiting task resumes")
            row = self._status(conn, row, "waiting", error=None)
            self._record(conn, task_id, "resume", instance=row["instance_id"],
                         acts_for=row["audience"], args={"by": by})
            return row

    def run_next(self, task_id: str, worker: Callable[[dict, Callable[[dict], None]], dict]) -> dict:
        with db.transaction(self.url) as conn:
            row = self._get(conn, task_id, lock=True)
            if row is None:
                raise TaskError("no such task")
            now = self.clock()
            if row["status"] in ("done", "cancelled", "blocked", "failed"):
                raise TaskError(f"a {row['status']} task can't run")
            if row["status"] == "running" and row["lease_expires_at"] > now:
                raise TaskError("the task's current worker still holds its lease")
            if row["deadline"] <= now or row["tokens"] >= row["token_budget"]:
                reason = "its deadline passed" if row["deadline"] <= now else "its token budget is spent"
                row = self._status(conn, row, "failed", error=reason)
                self._record(conn, task_id, "stop", instance=row["instance_id"],
                             acts_for=row["audience"], args={"why": reason})
                return row
            lease = str(uuid.uuid4())
            conn.execute("update tasks set status = 'running', lease_id = %s, "
                         "lease_expires_at = %s, last_heartbeat_at = %s, attempts = attempts + 1, "
                         "last_error = null, updated_at = %s where id = %s",
                         (lease, now + timedelta(seconds=self.lease_seconds), now, now, task_id))
            self._record(conn, task_id, "slice", instance=row["instance_id"],
                         acts_for=row["audience"], args={"attempt": row["attempts"] + 1})
        execution = self.get(task_id)
        stop = threading.Event()
        heart = threading.Thread(target=self._heartbeat, args=(task_id, lease, stop),
                                 name="a5s-task-heartbeat", daemon=True)
        heart.start()
        try:
            result = worker(execution, lambda change: self.checkpoint(task_id, lease, change))
        except TaskStopped:
            result = None
        except Exception as exc:  # noqa: BLE001 - a failed slice waits with its checkpoints
            result = {"status": "waiting", "error": str(exc)}
        finally:
            stop.set()
            heart.join()
        return self._finish(task_id, lease, result)

    def checkpoint(self, task_id: str, lease: str, change: dict) -> None:
        with db.transaction(self.url) as conn:
            row = self._leased(conn, task_id, lease)
            now = self.clock()
            if row["deadline"] <= now:
                raise TaskStopped("the task's deadline passed")
            tokens = self._tokens(row, change)
            if tokens > row["token_budget"]:
                raise TaskStopped("the task's token budget is spent")
            step = int(change.get("step", row["step"]))
            progress = float(change.get("progress", row["progress"]))
            if step < row["step"] or not 0 <= progress <= 1 or progress < row["progress"]:
                raise TaskError("a checkpoint may only move a task forward")
            partial = change.get("partial", row["partial"])
            plan = planned(row["plan"], change["plan"]) if "plan" in change else row["plan"]
            conn.execute("update tasks set step = %s, progress = %s, partial = %s, plan = %s, "
                         "tokens = %s, last_heartbeat_at = %s, lease_expires_at = %s, "
                         "updated_at = %s where id = %s",
                         (step, progress, Jsonb(partial), Jsonb(plan), tokens, now,
                          now + timedelta(seconds=self.lease_seconds), now, task_id))
            self._record(conn, task_id, "checkpoint", instance=row["instance_id"],
                         acts_for=row["audience"], args={"step": step, "progress": progress,
                                                          "partial": partial, "tokens": tokens,
                                                          **_planned(plan)})

    def heartbeat(self, task_id: str, lease: str) -> bool:
        with db.transaction(self.url) as conn:
            row = self._leased(conn, task_id, lease)
            now = self.clock()
            if row["deadline"] <= now:
                return False
            conn.execute("update tasks set last_heartbeat_at = %s, lease_expires_at = %s, "
                         "updated_at = %s where id = %s", (now, now + timedelta(
                             seconds=self.lease_seconds), now, task_id))
            return True

    def _heartbeat(self, task_id: str, lease: str, stop: threading.Event) -> None:
        while not stop.wait(max(0.01, self.lease_seconds / 3)):
            try:
                if not self.heartbeat(task_id, lease):
                    return
            except psycopg.Error:
                log.exception("couldn't renew task %s's lease", task_id)
                return

    def _finish(self, task_id: str, lease: str, result: dict | None) -> dict:
        with db.transaction(self.url) as conn:
            row = self._get(conn, task_id, lock=True)
            if row is None:
                raise TaskError("no such task")
            if result is None:
                if row["status"] == "running":
                    row = self._status(conn, row, "waiting", error="the slice stopped")
                    self._record(conn, task_id, "stop", instance=row["instance_id"],
                                 acts_for=row["audience"], args={"why": "the slice stopped"})
                return row
            if row["status"] in ("cancelled", "done", "failed"):
                return row
            row = self._leased(conn, task_id, lease)
            now = self.clock()
            status = result.get("status", "waiting")
            if status not in ("waiting", "blocked", "done", "failed"):
                raise TaskError(f"a worker returned an unknown task status: {status}")
            if status == "blocked" and not result.get("reason"):
                raise TaskError("a blocked task needs a reason")
            if row["deadline"] <= now:
                status = "failed"
                result = {**result, "error": "its deadline passed"}
            tokens = self._tokens(row, result)
            if tokens > row["token_budget"]:
                status = "failed"
                result = {**result, "error": "its token budget is spent"}
            step = int(result.get("step", row["step"]))
            progress = 1.0 if status == "done" else float(result.get("progress", row["progress"]))
            if step < row["step"] or not 0 <= progress <= 1 or progress < row["progress"]:
                raise TaskError("a result may only move a task forward")
            partial = result.get("partial", row["partial"])
            plan = planned(row["plan"], result["plan"]) if "plan" in result else row["plan"]
            error = result.get("error") or result.get("reason")
            conn.execute("update tasks set status = %s, step = %s, progress = %s, partial = %s, "
                         "plan = %s, result = %s, tokens = %s, lease_id = null, "
                         "lease_expires_at = null, last_error = %s, updated_at = %s where id = %s",
                         (status, step, progress, Jsonb(partial), Jsonb(plan),
                          Jsonb(result.get("result")), tokens, error, now, task_id))
            self._record(conn, task_id, status, instance=row["instance_id"],
                         acts_for=row["audience"], args={"step": step, "progress": progress,
                                                          "partial": partial, "tokens": tokens,
                                                          "error": error, **_planned(plan)})
            return self._get(conn, task_id)

    def _tokens(self, row: dict, result: dict) -> int:
        used = int(result.get("tokens", 0))
        if used < 0:
            raise TaskError("a slice may not use a negative number of tokens")
        return row["tokens"] + used

    @staticmethod
    def _get(conn, task_id: str, lock: bool = False) -> dict | None:
        found = conn.execute("select * from tasks where id = %s" + (" for update" if lock else ""),
                             (task_id,)).fetchone()
        return TaskService._public(found)

    def _owned(self, conn, task_id: str, by: str) -> dict:
        row = self._get(conn, task_id, lock=True)
        if row is None:
            raise TaskError("no such task")
        if row["owner"] != by:
            raise TaskError("only the task's owner may change it")
        return row

    def _leased(self, conn, task_id: str, lease: str) -> dict:
        row = self._get(conn, task_id, lock=True)
        if row is None or row["status"] != "running" or row["lease_id"] != lease:
            raise TaskStopped("the task is no longer running under this lease")
        return row

    @staticmethod
    def _status(conn, row: dict, status: str, error: str | None = None) -> dict:
        conn.execute("update tasks set status = %s, lease_id = null, lease_expires_at = null, "
                     "last_error = %s, updated_at = now() where id = %s",
                     (status, error, row["id"]))
        return {**row, "status": status, "lease_id": None, "last_error": error}

    @staticmethod
    def _record(conn, task_id: str, action: str, **entry: Any) -> None:
        args = entry.pop("args", {})
        ledger.append(conn, {"kind": "task", "action": action, "task": task_id,
                             "decision": "record", **entry, "args": ledger.mask(args)})


def _planned(plan: list[dict]) -> dict[str, Any]:
    """How far a plan has come, for the ledger: its steps by hash, and how many are completed."""
    return {"plan": plan, "steps": len(plan),
            "completed": sum(s["status"] == "completed" for s in plan)}
