"""Budgets: how much model work an instance may do, in tokens as the providers count them, so
a run that loops, or a busy day, can't run up the bill unseen.

Each release sets two (definitions.Budget): one for a single run, and one for each person an
instance acts for, each day, in their own time zone. A fifth of each person's day is kept for
what they owe and what they asked to be reminded of: chases and reminders may use all of it,
and other work, such as answers and reports, stops short of that share. Crossing four fifths
is recorded as a warning. The core checks before it opens a run and before each model call.
Once a budget is spent, the work waits: a report for the next day, and someone asking is
told so, in a5s's own words, with who to ask.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import psycopg

from a5s.contract import Scenario
from a5s.core import groups
from a5s.core.obligations import local
from a5s.definitions import KEPT, Budget

WARN = 0.8  # of each person's day, when a warning is recorded
OWED = ("obligation", "reminder")  # the work that may use the share kept for it


def split(usage: object) -> tuple[int, int]:
    """The tokens a call took in and out, in either API's words, as providers price them."""
    if not isinstance(usage, dict):
        return 0, 0
    tokens_in = usage.get("prompt_tokens", usage.get("input_tokens"))
    tokens_out = usage.get("completion_tokens", usage.get("output_tokens"))
    return (tokens_in if isinstance(tokens_in, int) else 0,
            tokens_out if isinstance(tokens_out, int) else 0)


def tokens_of(usage: object) -> int:
    """The tokens a provider says a call took, in either API's words."""
    if not isinstance(usage, dict):
        return 0
    if isinstance(usage.get("total_tokens"), int):
        return usage["total_tokens"]
    return sum(v for k, v in usage.items()
               if k in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens")
               and isinstance(v, int))


def day_of(scenario: Scenario, person: str, now: datetime) -> date:
    """The day it is for someone, in their own time zone."""
    who = scenario.person(person) if person else None
    return local(who, now).date() if who else now.date()


def payer(acts_for: list[str], trigger: dict | None) -> str | None:
    """Whose day's budget a run uses: the one person it acts for, or in a group chat,
    whoever asked (core/groups.py), or for a run that answers another agent's question, whoever
    the run that asked was paid for by. None for a run for several people nobody asked for."""
    if (trigger or {}).get("payer"):
        return str(trigger["payer"])
    return groups.asker({"acts_for": acts_for, "trigger": trigger or {}})


def refused(conn: psycopg.Connection, scenario: Scenario, budget: Budget, instance: str,
            acts_for: list[str], kind: str, tokens: int, now: datetime,
            trigger: dict | None = None) -> str | None:
    """Why a run, or its next model call, would go past its budgets, if it would."""
    if tokens >= budget.per_run:
        return f"this run has used its budget of {budget.per_run:,} tokens"
    if (person := payer(acts_for, trigger)) is None:
        return None
    row = conn.execute("select tokens from spend where instance_id = %s and person = %s and day = %s",
                       (instance, person, day_of(scenario, person, now))).fetchone()
    may = budget.per_person_per_day if kind in OWED else int(budget.per_person_per_day * (1 - KEPT))
    if row and row["tokens"] >= may:
        return f"{instance} has used its budget for {person} today"
    return None


def spent(conn: psycopg.Connection, scenario: Scenario, budget: Budget, run: dict, tokens: int,
          now: datetime, usage: object = None, model: str | None = None) -> dict | None:
    """Count a model call's tokens against its run, in and out apart, with the model it
    called, and against its person's day, letting go of their days before yesterday, which no
    budget needs. The day's use, if this call took it past four fifths of the budget, for a
    warning."""
    tokens_in, tokens_out = split(usage)
    conn.execute("update runs set tokens = tokens + %s, tokens_in = tokens_in + %s, "
                 "tokens_out = tokens_out + %s, model = coalesce(%s, model) where id = %s",
                 (tokens, tokens_in, tokens_out, model, run["run"]))
    person = payer(list(run["acts_for"]), run.get("trigger")) or ""
    conn.execute("delete from spend where person = %s and day < %s",
                 (person, day_of(scenario, person, now) - timedelta(days=1)))
    row = conn.execute(
        "insert into spend (instance_id, person, day, tokens) values (%s, %s, %s, %s) "
        "on conflict (instance_id, person, day) do update set tokens = spend.tokens + excluded.tokens "
        "returning tokens, warned_at", (run["id"], person, day_of(scenario, person, now), tokens)
    ).fetchone()
    if not person or row["warned_at"] or row["tokens"] < WARN * budget.per_person_per_day:
        return None
    conn.execute("update spend set warned_at = %s where instance_id = %s and person = %s "
                 "and day = %s", (now, run["id"], person, day_of(scenario, person, now)))
    return {"person": person, "used": row["tokens"], "budget": budget.per_person_per_day}
