"""Counts: how many changes of a type one piece of work, and each person, may ask for before
the rest wait for a person, whatever the level.

The scenario's settings give its limits for each type of action: how many one run may take,
and how many for each person a run acts for, in 30 days, across every agent. Code decides
what a piece of work is: a run. The gateway counts in the transaction that decides each
call, under a lock for its type of action, so calls made at once can't each squeeze under a
limit, and a change past one waits for its decider, even at level 2. Only changes count, held
or made, never reads or drafts. A call made again in the same run, the same change to the
same records, is counted once, and keeps the verdict it had.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import psycopg

from a5s.core.ledger import canonical

WINDOW = timedelta(days=30)


def change(action: str, records: list[str], args: dict) -> str:
    """A digest of a change: its type, its records and its arguments."""
    return hashlib.sha256(canonical({"action": action, "records": sorted(records),
                                     "args": args}).encode()).hexdigest()


def over(conn: psycopg.Connection, run: dict, action: str, key: str, limits: dict[str, dict],
         now: datetime) -> bool:
    """Whether a change would go past the scenario's limits for its type, in the caller's
    transaction, holding the type's lock until it ends."""
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"a5s counts {action}",))
    again = conn.execute("select over from action_counts where run_id = %s and change = %s",
                         (run["run"], key)).fetchone()
    if again is not None:
        return again["over"]
    limit = limits.get(action) or {}
    if (most := limit.get("per_run")) is not None and conn.execute(
            "select count(*) as n from action_counts where run_id = %s and action = %s",
            (run["run"], action)).fetchone()["n"] >= most:
        return True
    if (most := limit.get("per_person_30_days")) is not None:
        for person in run["acts_for"]:
            if conn.execute("select count(*) as n from action_counts where action = %s "
                            "and %s = any(acts_for) and at > %s",
                            (action, person, now - WINDOW)).fetchone()["n"] >= most:
                return True
    return False


def count(conn: psycopg.Connection, run: dict, action: str, key: str, was_over: bool,
          now: datetime) -> None:
    """Count a change that's made or held, once."""
    conn.execute("insert into action_counts (run_id, instance_id, action, change, acts_for, at, "
                 "over) values (%s, %s, %s, %s, %s, %s, %s) on conflict (run_id, change) do nothing",
                 (run["run"], run["id"], action, key, list(run["acts_for"]), now, was_over))
