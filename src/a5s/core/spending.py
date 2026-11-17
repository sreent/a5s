"""Spending: what agents' model calls cost each calendar month, at the prices models.yaml gives
them, by part, by agent and by instance, against the monthly budgets the signed settings set
(contract.Spending), with a forecast to the month's end and what each message answered cost
(docs/studio.md).

- A run costs what its tokens do at its model's prices, as the measures price runs
  (measures.priced). Runs on a model whose prices models.yaml doesn't give are counted apart,
  never as costing nothing.
- A run's cost goes to the parts its instance works in now: shared equally among those of the
  records it handled, or among all of them if it handled none there. An instance in no part
  spends in none.
- The month is a calendar month in UTC, by the database's clock, which stamps each run. Its
  forecast is what it has cost so far, and the rest of the month at the pace of the last seven
  days.
- What a message answered cost is all an instance's runs cost over the month, its reports and
  chases too, over the messages they answered: what the work people asked for costs, all in. A
  part counts each message whose run's cost it shares, at its share of the cost.
- A budget is a guide, never a stop: the token budgets each release sets stop a run, and a
  person's day. a5s shows the month against it, and tells its owners, on their home page, once
  the month is forecast to pass it.
- Each sees what's theirs to watch, as the studio's pages show them (core/studio.py): the
  instances they may watch; a part's totals if they own it, decide for it or approve instances;
  an agent's if they own it or approve instances. Spending names nobody: it's the instances'.
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
    Scenario,
    Spending,
)
from a5s.core import measures, studio, words
from a5s.core.releases import agent_owner

PACE = 7  # days: the forecast goes on at the pace of the last week
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
KINDS = ("parts", "agents")


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


def totals(conn: db.Connection, scenario: Scenario, models: dict[str, ModelConfig],
           insts: list[dict], start: datetime, end: datetime, now: datetime) -> dict[str, dict]:
    """What each instance, agent and part spent from `start` to `end`, and over the PACE days
    to `now`, for the pace: each run's cost at its model's prices, its tokens, and whether it
    answered a message, a part's share of a run as its records say (the module's doc)."""
    found: dict[str, dict[str, dict]] = {k: defaultdict(_blank)
                                         for k in ("instances", "agents", "parts")}
    by_id = {i["id"]: i for i in insts}
    recent = now - timedelta(days=PACE)
    parts_of: dict[str, str | None] = {}  # each record's part, worked out once
    rows = conn.execute(
        "select r.instance_id as instance, coalesce(r.model, i.model) as model, r.opened_at, "
        "r.tokens, r.tokens_in, r.tokens_out, r.tokens_cached, r.tokens_cache_written, "
        "coalesce(r.trigger->>'kind' = 'message' and r.outcome like 'done%%', false) as answered, "
        "array(select rr.record from run_records rr where rr.run_id = r.id) as records "
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
        works = studio.parts_of(inst)
        for record in r["records"] or ():
            if record not in parts_of:
                parts_of[record] = scenario.part_of(record)
        handled = sorted({p for k in r["records"] or () if (p := parts_of[k]) in works})
        shares = handled or works
        into = [(found["instances"][inst["id"]], 1.0), (found["agents"][inst["definition"]], 1.0),
                *((found["parts"][p], 1 / len(shares)) for p in shares)]
        for spend, share in into:
            if r["opened_at"] >= recent and r["opened_at"] <= now:
                spend["recent"] += (cost or 0.0) * share
            if r["opened_at"] < start:
                continue
            spend["spent"] += (cost or 0.0) * share
            spend["tokens"] += round(r["tokens"] * share)
            spend["runs"] += 1 if r["tokens"] else 0
            spend["unpriced"] += 1 if cost is None else 0
            spend["answered"] += 1 if r["answered"] else 0
    return found


def _shown(key: str, spend: dict, budget: float | None, left: float | None) -> dict:
    """One instance's, agent's or part's month, with its forecast if the month isn't over."""
    pace = spend["recent"] / PACE if left is not None else None
    return {"key": key, "spent": spend["spent"], "budget": budget, "pace": pace,
            "forecast": None if pace is None or left is None else spend["spent"] + pace * left,
            "runs": spend["runs"], "unpriced": spend["unpriced"],
            "answered": spend["answered"], "tokens": spend["tokens"],
            "per_answer": spend["spent"] / spend["answered"] if spend["answered"] else None}


def sees_any(url: str, person: Person) -> bool:
    """Whether someone has spending to see: they own a part or an agent, decide for a part,
    approve instances, or run an instance, as its owner or deputy."""
    roles = set(person.roles)
    if INSTANCE_APPROVER in roles or any(r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:",
                                                       f"{AGENT_OWNER}:")) for r in roles):
        return True
    with db.transaction(url) as conn:
        return conn.execute("select 1 from instances where %s in (owner, deputy) limit 1",
                            (person.id,)).fetchone() is not None


def sees(viewer: Person, kind: str, key: str) -> bool:
    """Whether someone may see a part's or an agent's totals: they own it, decide for a part,
    or approve instances, and so may watch every instance that spends there."""
    roles = set(viewer.roles)
    if INSTANCE_APPROVER in roles:
        return True
    if kind == "parts":
        return f"{PART_OWNER}:{key}" in roles or f"{PART_DELEGATE}:{key}" in roles
    return agent_owner(key) in roles


def _now(conn: db.Connection) -> datetime:
    """The database's time, which stamps each run."""
    row = conn.execute("select now() as t").fetchone()
    assert row is not None  # a select of a value always has its row
    return row["t"]


def compared(spending: Spending, currency: str | None) -> bool:
    """Whether the budgets are in the currency models.yaml prices models in, so a5s compares
    what's spent with them: one the settings don't name is."""
    return spending.currency is None or spending.currency == currency


def report(conn: db.Connection, scenario: Scenario, models: dict[str, ModelConfig],
           spending: Spending, viewer: Person, now: datetime | None = None,
           month: str | None = None, currency: str | None = None) -> dict:
    """A month's spending as someone may see it, as of `now`, or the database's time: each
    part's and agent's against its budget, with its forecast to the month's end while it lasts,
    and each instance they may watch, with what each message it answered cost: with no budget
    where the budgets are in a currency models.yaml doesn't price models in. Refused if the
    month isn't one."""
    now = now or _now(conn)
    start, end = month_of(now, month)
    current = start <= now < end
    insts = studio.instances(conn, retired=True)
    found = totals(conn, scenario, models, insts, start, end, now)
    left = (end - now).total_seconds() / 86400 if current else None
    shown: dict[str, list[dict]] = {}
    same = compared(spending, currency)
    for kind in KINDS:
        budgets = getattr(spending, kind)
        keys = sorted({k for k in set(found[kind]) | set(budgets) if sees(viewer, kind, k)})
        shown[kind] = [_shown(k, found[kind][k] if k in found[kind] else _blank(),
                              budgets.get(k) if same else None, left) for k in keys]
    watched = [i for i in insts if studio.watches(i, viewer)
               and (i["id"] in found["instances"] or i["status"] in studio.SERVING)]
    shown["instances"] = [{**_shown(i["id"], found["instances"][i["id"]] if i["id"] in
                                    found["instances"] else _blank(), None, left),
                           "agent": i["definition"], "parts": studio.parts_of(i)}
                          for i in watched]
    return {"month": start.strftime("%Y-%m"), "current": current, "currency": currency,
            "budget_currency": spending.currency, "compared": same,
            "starts": start.isoformat(), "ends": end.isoformat(),
            "days": (end - start).days,
            "day": min((end - start).days, (now - start).days + 1) if current else (end - start).days,
            **shown}


def said(amount: float, currency: str | None) -> str:
    """An amount, as people read it: 520.40, or GBP 520.40 where models.yaml names a currency."""
    return f"{currency} {amount:,.2f}" if currency else f"{amount:,.2f}"


def over(conn: db.Connection, scenario: Scenario, models: dict[str, ModelConfig],
         spending: Spending, person: Person, now: datetime | None = None,
         currency: str | None = None, language: str = "en") -> list[dict]:
    """The budgets someone owns that this month has passed, or is forecast to pass, as of
    `now`, or the database's time, for their home page: each part they own and agent they own
    with a budget, in words; and those whose runs this month were on a model whose prices
    aren't known, which count for nothing against it. Budgets in a currency models.yaml doesn't
    price models in, a5s compares with nothing, and says so once."""
    roles = set(person.roles)
    mine = [(kind, key) for kind in KINDS for key in getattr(spending, kind)
            if (f"{PART_OWNER}:{key}" if kind == "parts" else agent_owner(key)) in roles]
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
    found = totals(conn, scenario, models, studio.instances(conn, retired=True), start, end, now)
    left = (end - now).total_seconds() / 86400
    items = []
    for kind, key in mine:
        budget = getattr(spending, kind)[key]
        month = _shown(key, found[kind][key] if key in found[kind] else _blank(), budget, left)
        whose = key if kind == "parts" or language == words.THAI else f"The {key}"
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
        why = [words.say(language, "you own {what}", what=key if kind == "parts"
                         or language == words.THAI else "the " + key)]
        go = f"/studio/spending#{kind[:-1]}-{key}"
        if what:
            items.append({"kind": "spending", "what": what, "why": why, "go": go})
        if month["unpriced"]:  # which counted for nothing against it
            items.append({"kind": "spending", "what": words.say(
                language, "{whose} ran {n} times this month on a model whose prices aren't known, "
                "which count for nothing against its budget", whose=whose, n=month["unpriced"]),
                "why": why, "go": go})
    return items
