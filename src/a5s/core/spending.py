"""Spending: what agents' model calls cost each calendar month, at the prices models.yaml gives
them, by agent and by instance, against the monthly budgets the signed settings set each agent
(contract.Spending), with a forecast to the month's end and what each message answered cost
(docs/studio.md).

- A run costs what its tokens do at its model's prices, as the measures price runs
  (measures.priced). Runs on a model whose prices models.yaml doesn't give are counted apart,
  never as costing nothing.
- A run's cost is its instance's and its agent's, whole. a5s shares it out among no parts: a
  part's share of a run that handled records in several, or none, is a figure few could check,
  and an agent's and its instances' totals answer what the work costs and who pays for it.
- The month is a calendar month in UTC, by the database's clock, which stamps each run. Its
  forecast is what it has cost so far, and the rest of the month at the pace of the last seven
  days.
- What a message answered cost is all an instance's or agent's runs cost over the month, their
  reports and chases too, over the messages they answered: what the work people asked for
  costs, all in.
- A budget is a guide, never a stop: the token budgets each release sets stop a run, and a
  person's day. a5s shows the month against it, and tells the agent's owners, on their home
  page, once the month is forecast to pass it.
- Each sees what's theirs to watch, as the studio's pages show them (core/studio.py): the
  instances they may watch, such as those at work in a part they own; and an agent's totals if
  they own it or approve instances. Spending names nobody: it's the instances'.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from a5s import db
from a5s.config import ModelConfig
from a5s.contract import (
    AGENT_OWNER,
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    Person,
    Spending,
)
from a5s.core import measures, studio, words
from a5s.core.releases import agent_owner

PACE = 7  # days: the forecast goes on at the pace of the last week
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class Refused(ValueError):
    """Why a month's spending can't be shown, in words."""


def month_of(now: datetime, month: str | None = None) -> tuple[datetime, datetime]:
    """The calendar month, in UTC, that `now` is in, or the one named, such as 2026-11: when
    it begins, and when the next one does."""
    if month is None:
        start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        found = MONTH.match(month)
        if found is None or int(found[1]) < 1:  # the year 0000 is none
            raise Refused("a month is written as its year and its number, such as 2026-11")
        start = datetime(int(found[1]), int(found[2]), 1, tzinfo=UTC)
        if start > now:
            raise Refused(f"{month} hasn't begun")
    return start, (start + timedelta(days=32)).replace(day=1)


def _blank() -> dict[str, Any]:
    return {"spent": 0.0, "recent": 0.0, "runs": 0, "unpriced": 0, "answered": 0, "tokens": 0}


def totals(conn: db.Connection, models: dict[str, ModelConfig], insts: list[dict],
           start: datetime, end: datetime, now: datetime) -> dict[str, dict]:
    """What each instance and agent spent from `start` to `end`, and over the PACE days to
    `now`, for the pace: each run's cost at its model's prices, its tokens, and whether it
    answered a message, each run whole (the module's doc)."""
    found: dict[str, dict[str, dict]] = {k: defaultdict(_blank) for k in ("instances", "agents")}
    by_id = {i["id"]: i for i in insts}
    recent = now - timedelta(days=PACE)
    rows = conn.execute(
        "select r.instance_id as instance, coalesce(r.model, i.model) as model, r.opened_at, "
        "r.tokens, r.tokens_in, r.tokens_out, r.tokens_cached, r.tokens_cache_written, "
        "coalesce(r.trigger->>'kind' = 'message' and r.outcome like 'done%%', false) as answered "
        "from runs r join instances i on i.id = r.instance_id "
        "where r.opened_at >= %s and r.opened_at < %s "
        "and (r.tokens > 0 or r.trigger->>'kind' = 'message')",
        (min(start, recent), end)).fetchall()
    for r in rows:
        inst = by_id.get(r["instance"])
        if inst is None:
            continue
        cost = measures.priced(models.get(r["model"] or ""), r["tokens_in"], r["tokens_out"],
                               r["tokens_cached"], r["tokens_cache_written"]) if r["tokens"] else 0.0
        for spend in (found["instances"][inst["id"]], found["agents"][inst["definition"]]):
            if recent <= r["opened_at"] <= now:
                spend["recent"] += cost or 0.0
            if r["opened_at"] < start:
                continue
            spend["spent"] += cost or 0.0
            spend["tokens"] += r["tokens"]
            spend["runs"] += 1 if r["tokens"] else 0
            spend["unpriced"] += 1 if cost is None else 0
            spend["answered"] += 1 if r["answered"] else 0
    return found


def _shown(key: str, spend: dict, budget: float | None, left: float | None) -> dict:
    """One instance's or agent's month, with its forecast if the month isn't over."""
    pace = spend["recent"] / PACE if left is not None else None
    return {"key": key, "spent": spend["spent"], "budget": budget, "pace": pace,
            "forecast": None if pace is None or left is None else spend["spent"] + pace * left,
            "runs": spend["runs"], "unpriced": spend["unpriced"],
            "answered": spend["answered"], "tokens": spend["tokens"],
            # what each message cost, only where every run's cost is known (round 14)
            "per_answer": spend["spent"] / spend["answered"]
            if spend["answered"] and not spend["unpriced"] else None}


def sees_any(url: str, person: Person) -> bool:
    """Whether someone has spending to see: they own an agent, approve instances, may watch
    the instances at work in a part they own or decide for, or run an instance, as its owner
    or deputy."""
    roles = set(person.roles)
    if INSTANCE_APPROVER in roles or any(r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:",
                                                       f"{AGENT_OWNER}:")) for r in roles):
        return True
    with db.transaction(url) as conn:
        return conn.execute("select 1 from instances where %s in (owner, deputy) limit 1",
                            (person.id,)).fetchone() is not None


def sees(viewer: Person, agent: str) -> bool:
    """Whether someone may see an agent's totals: they own it, or approve instances, and so may
    watch every instance of it."""
    return INSTANCE_APPROVER in viewer.roles or agent_owner(agent) in viewer.roles


def _now(conn: db.Connection) -> datetime:
    """The database's time, which stamps each run."""
    row = conn.execute("select now() as t").fetchone()
    assert row is not None  # a select of a value always has its row
    return row["t"]


def compared(spending: Spending, currency: str | None) -> bool:
    """Whether the budgets are in the currency models.yaml prices models in, so a5s compares
    what's spent with them: one the settings don't name is."""
    return spending.currency is None or spending.currency == currency


def report(conn: db.Connection, models: dict[str, ModelConfig], spending: Spending,
           viewer: Person, now: datetime | None = None, month: str | None = None,
           currency: str | None = None) -> dict:
    """A month's spending as someone may see it, as of `now`, or the database's time: each
    agent's against its budget, with its forecast to the month's end while it lasts, and each
    instance they may watch, with what each message it answered cost: with no budget where the
    budgets are in a currency models.yaml doesn't price models in. Refused if the month isn't
    one."""
    now = now or _now(conn)
    start, end = month_of(now, month)
    current = start <= now < end
    insts = studio.instances(conn, retired=True)
    found = totals(conn, models, insts, start, end, now)
    left = (end - now).total_seconds() / 86400 if current else None
    same = compared(spending, currency)
    agents = sorted({a for a in set(found["agents"]) | set(spending.agents) if sees(viewer, a)})
    watched = [i for i in insts if studio.watches(i, viewer)
               and (i["id"] in found["instances"] or i["status"] in studio.SERVING)]
    return {"month": start.strftime("%Y-%m"), "current": current, "currency": currency,
            "budget_currency": spending.currency, "compared": same,
            "starts": start.isoformat(), "ends": end.isoformat(),
            "days": (end - start).days,
            "day": min((end - start).days, (now - start).days + 1) if current else (end - start).days,
            "agents": [_shown(a, found["agents"][a] if a in found["agents"] else _blank(),
                              spending.agents.get(a) if same else None, left) for a in agents],
            "instances": [{**_shown(i["id"], found["instances"][i["id"]] if i["id"] in
                                    found["instances"] else _blank(), None, left),
                           "agent": i["definition"], "parts": studio.parts_of(i)}
                          for i in watched]}


def said(amount: float, currency: str | None) -> str:
    """An amount, as people read it: 520.40, or GBP 520.40 where models.yaml names a currency."""
    return f"{currency} {amount:,.2f}" if currency else f"{amount:,.2f}"


def over(conn: db.Connection, models: dict[str, ModelConfig], spending: Spending,
         person: Person, now: datetime | None = None, currency: str | None = None,
         language: str = "en") -> list[dict]:
    """The budgets someone owns that this month has passed, or is forecast to pass, as of
    `now`, or the database's time, for their home page: each agent they own with a budget, in
    words; and those whose runs this month were on a model whose prices aren't known, which
    count for nothing against it. Budgets in a currency models.yaml doesn't price models in,
    a5s compares with nothing, and says so once."""
    mine = [a for a in spending.agents if agent_owner(a) in person.roles]
    if not mine:
        return []
    if not compared(spending, currency):
        return [{"kind": "spending", "what": words.say(
                     language, "Budgets are in {theirs}, and models.yaml prices models in "
                     "{prices}, so a5s compares neither", theirs=spending.currency or "",
                     prices=currency or words.say(language, "no currency it names")),
                 "why": [words.say(language, "you own a budget")], "go": "/studio/settings"}]
    now = now or _now(conn)
    start, end = month_of(now)
    found = totals(conn, models, studio.instances(conn, retired=True), start, end, now)
    left = (end - now).total_seconds() / 86400
    items = []
    for agent in mine:
        budget = spending.agents[agent]
        month = _shown(agent, found["agents"][agent] if agent in found["agents"] else _blank(),
                       budget, left)
        whose = agent if language == words.THAI else f"The {agent}"
        if month["spent"] > budget:
            what = words.say(language, "{whose} has spent {amount} this month, past its budget of "
                             "{budget}", whose=whose, amount=said(month["spent"], currency),
                             budget=said(budget, currency))
        elif (month["forecast"] or 0) > budget:
            what = words.say(language, "{whose} is on course to spend {amount} this month, past "
                             "its budget of {budget}", whose=whose,
                             amount=said(month["forecast"] or 0, currency),
                             budget=said(budget, currency))
        else:
            what = None
        why = [words.say(language, "you own {what}",
                         what=agent if language == words.THAI else "the " + agent)]
        go = f"/studio/spending#agent-{agent}"
        if what:
            items.append({"kind": "spending", "what": what, "why": why, "go": go})
        if month["unpriced"]:  # which counted for nothing against it
            items.append({"kind": "spending", "what": words.say(
                language, "{whose} ran {n} times this month on a model whose prices aren't known, "
                "which count for nothing against its budget", whose=whose, n=month["unpriced"]),
                "why": why, "go": go})
    return items
