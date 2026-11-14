"""Counts: how many changes of a type one piece of work, and each person, may ask for before
the rest wait for a person, whatever the level.

The scenario's settings give its limits for each type of action: how many one run may make,
and how many for each person a run acts for, in 30 days, across every agent. A run for
nobody counts against its instance, as a person would. Code decides what a piece of work is:
a run. Each record a change names counts, so a change to three records counts three. The
gateway counts in the transaction that decides each call, under a lock for its type of
action, so calls made at once can't each squeeze under a limit, and a change past one waits
for its decider, even at level 2. Only changes count, held or made, never reads or drafts,
and never a change the records system didn't take.

The same change made again in the same run, to the same records, is counted once and made
once: a5s answers it with what became of it, and never makes it again. A tool gets a key for
each change, from the run and the change, so a system that knows keys makes it once too.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from a5s import db
from a5s.core.ledger import canonical

WINDOW = timedelta(days=30)
KEPT = timedelta(days=31)  # counts go once nothing weighs them


def change(action: str, records: list[str], args: dict) -> str:
    """A digest of a change: its type, its records and its arguments."""
    return hashlib.sha256(canonical({"action": action, "records": sorted(records),
                                     "args": args}).encode()).hexdigest()


def work(run: dict) -> str:
    """The piece of work a run's changes are part of: for a slice of a task, the task's tree,
    its root and the parts it split into, so a change a later slice or a part asks for again,
    such as after its last one stopped part way, is the same change (core/tasking.py), and the
    scenario's limit for a piece of work counts all of their changes; for any other run, the
    run."""
    trigger = run.get("trigger") or {}
    if trigger.get("kind") == "task" and trigger.get("task"):
        return str(trigger.get("root") or trigger["task"])
    return str(run["run"])


_OF_WORK = "coalesce(r.trigger ->> 'root', r.trigger ->> 'task')"  # a task run's piece of work


def key(work: str, change_digest: str) -> str:
    """The key a tool gets for a change, so a system that knows keys makes it once: for the
    piece of work it's part of, a run or a task (`work`)."""
    return hashlib.sha256(f"a5s {work} {change_digest}".encode()).hexdigest()


def before(conn: db.Connection, run: dict, action: str, change_digest: str) -> dict | None:
    """The same change asked for already in this run, or for a slice of a task, in any run of
    the task, if it was: whether it was held or made, or is being made now, the last most of
    all. Taken under the type's lock, held until the transaction ends."""
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"a5s counts {action}",))
    if (whole := work(run)) != str(run["run"]):  # its task's: any of its runs
        return conn.execute(
            "select a.state, a.over from action_counts a join runs r on r.id = a.run_id "
            f"where a.change = %s and r.trigger ->> 'kind' = 'task' and {_OF_WORK} = %s "
            "order by a.state = 'held', a.id limit 1", (change_digest, whole)).fetchone()
    return conn.execute("select state, over from action_counts where run_id = %s and change = %s",
                        (run["run"], change_digest)).fetchone()


def over(conn: db.Connection, run: dict, action: str, weight: int,
         limits: dict[str, dict], now: datetime) -> str | None:
    """Why a change of `weight` records goes past the scenario's limits for its type, if it
    does, in words for its decider. Call `before` first, in the same transaction."""
    limit = limits.get(action) or {}
    if (most := limit.get("per_run")) is not None:
        if (whole := work(run)) != str(run["run"]):  # a task's slices and parts share it
            made = conn.execute(
                "select coalesce(sum(a.records), 0) as n from action_counts a join runs r on "
                f"r.id = a.run_id where a.action = %s and r.trigger ->> 'kind' = 'task' and "
                f"{_OF_WORK} = %s", (action, whole)).fetchone()["n"]
            asked = "this task, in its runs and its parts', asked"
        else:
            made = conn.execute("select coalesce(sum(records), 0) as n from action_counts "
                                "where run_id = %s and action = %s",
                                (run["run"], action)).fetchone()["n"]
            asked = "this run asked"
        if made + weight > most:
            return (f"it's past the scenario's limit of {most} {action} a run, which a task's "
                    f"runs share: {asked} for {made} already, and this one changes {weight}")
    if (most := limit.get("per_person_30_days")) is not None:
        for person in run["acts_for"]:
            made = conn.execute("select coalesce(sum(records), 0) as n from action_counts "
                                "where action = %s and %s = any(acts_for) and at > %s",
                                (action, person, now - WINDOW)).fetchone()["n"]
            if made + weight > most:
                return (f"it's past the scenario's limit of {most} {action} in 30 days for "
                        f"each person: {person} has had {made} already")
        if not run["acts_for"]:  # a run for nobody counts against its instance
            made = conn.execute("select coalesce(sum(records), 0) as n from action_counts "
                                "where action = %s and instance_id = %s and acts_for = '{}' "
                                "and at > %s", (action, run["id"], now - WINDOW)).fetchone()["n"]
            if made + weight > most:
                return (f"it's past the scenario's limit of {most} {action} in 30 days, which "
                        f"{run['id']} has for runs that act for nobody: it's had {made} already")
    return None


def count(conn: db.Connection, run: dict, action: str, change_digest: str, weight: int,
          was_over: bool, state: str, now: datetime) -> None:
    """Count a change that's held, or being made, once."""
    conn.execute("insert into action_counts (run_id, instance_id, action, change, acts_for, at, "
                 "over, records, state) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                 "on conflict (run_id, change) do nothing",
                 (run["run"], run["id"], action, change_digest, list(run["acts_for"]), now,
                  was_over, weight, state))


def made(conn: db.Connection, run: str, change_digest: str) -> None:
    conn.execute("update action_counts set state = 'made' where run_id = %s and change = %s",
                 (run, change_digest))


def failed(conn: db.Connection, run: str, change_digest: str) -> None:
    """A change the records system didn't take: it doesn't count, and may be asked for again."""
    conn.execute("delete from action_counts where run_id = %s and change = %s and state = 'making'",
                 (run, change_digest))
