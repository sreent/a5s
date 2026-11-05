"""Measures: how a5s is doing for the people it serves, worked out from its own records, for
the baseline phase 1 asks of its first users (docs/phase-1.md), and for what each later stage
of the pilot shows (docs/pilot.md).

- Nothing lapses unnoticed: of what people owed that fell due, how much was done by when it
  was due, and how much an agent chased or took up the line, and of the reminders they asked
  for that fell due, how many came on time.
- People spend less time chasing: how long after it fell due what was done late was done.
- People keep using the agents: of those who wrote to an agent in the window before this one,
  how many wrote to it again in this one, and how often people mentioned one in a group chat.
- What it costs: tokens for each run that called a model, and for a model whose prices its
  approved list gives, what such a run costs.
- Held changes: how many their deciders approved and how long deciding took, and of the
  samples graders graded, how many were right.
- Agents together: the questions agents asked each other and how many were answered, and the
  notes each kept, had refused, gave its runs and let go.

Each is over the last `days` days, by the core's clock, and counts people, never names them.
What people owed, held changes and samples are the scenario's now, so a deployment that
changed scenarios counts only the new one's. Someone who has left isn't counted as not coming
back, once a5s has archived what it kept for them (core/departures.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from a5s.config import ModelConfig
from a5s.core import notebook

GRACE = "1 hour"  # a reminder for a particular time is on time within this of it [TBC]
APPROVED = ("making", "made", "not made", "stopped")  # a held change its deciders approved


def report(conn: psycopg.Connection, scenario: str, models: dict[str, ModelConfig],
           days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    """The measures over the last `days` days, at least one, to `now`, the core's clock, or
    else the database's, for the scenario named."""
    days = max(1, int(days))
    at = {"scenario": scenario, "window": f"{days} days", "grace": GRACE,
          "now": now or conn.execute("select now() as t").fetchone()["t"],
          "approved": list(APPROVED), "note": notebook.NOTE}
    since = "%(now)s::timestamptz - %(window)s::interval"
    owed = conn.execute(
        "select count(*) as due, "
        "count(*) filter (where done_at <= due_at) as on_time, "
        "count(*) filter (where done_at > due_at) as late, "
        "count(*) filter (where done_at is null) as open, "
        "count(*) filter (where chased_at is not null) as chased, "
        "count(*) filter (where escalations > 0) as escalated, "
        "percentile_cont(0.5) within group (order by extract(epoch from done_at - due_at)) "
        "  filter (where done_at > due_at) as late_p50, "
        "percentile_cont(0.9) within group (order by extract(epoch from done_at - due_at)) "
        "  filter (where done_at > due_at) as late_p90 "
        f"from obligations where scenario = %(scenario)s and due_at > {since} "
        "and due_at <= %(now)s", at).fetchone()
    by = "due_at + case when in_digest then interval '1 day' else %(grace)s::interval end"
    reminded = conn.execute(  # one for a day comes in that day's digest, at its own time, so
        "select count(*) as due, "  # it's counted once that day is over
        f"count(*) filter (where reminded_at <= {by}) as on_time, "
        "count(*) filter (where reminded_at is null) as missed "
        "from reminders where confirmed_at is not null and cancelled_at is null "
        f"and due_at > {since} and {by} <= %(now)s", at).fetchone()
    returning = conn.execute(
        "with before as (select distinct agent, person from inbound where "
        f"  received_at > {since} - %(window)s::interval and received_at <= {since} "
        "  and person not like 'former:%%'), "
        f"since as (select distinct agent, person from inbound where received_at > {since}) "
        "select b.agent, count(*) as wrote_before, count(s.person) as came_back "
        "from before b left join since s on s.agent = b.agent and s.person = b.person "
        "group by b.agent order by b.agent", at).fetchall()
    mentioned = conn.execute(  # in a group chat, an agent hears only what mentions it
        "select agent, count(*) as messages, count(distinct conversation) as chats, "
        "count(distinct person) as people from inbound "
        f"where conversation is not null and received_at > {since} "
        "group by agent order by agent", at).fetchall()
    runs = conn.execute(  # by the model each called, or, before runs said, their instance's
        "select r.instance_id, coalesce(r.model, i.model) as model, count(*) as runs, "
        "sum(r.tokens)::bigint as tokens, "
        "sum(r.tokens_in)::bigint as tokens_in, sum(r.tokens_out)::bigint as tokens_out, "
        "sum(r.tokens_cached)::bigint as cached, "
        "sum(r.tokens_cache_written)::bigint as cache_written, "
        "percentile_cont(0.9) within group (order by r.tokens) as p90 "
        "from runs r join instances i on i.id = r.instance_id "
        f"where r.opened_at > {since} and r.tokens > 0 "
        "group by 1, 2 order by 1", at).fetchall()
    decided = "extract(epoch from coalesce(decided_at, ended_at) - proposed_at)"
    held = conn.execute(  # a rejection ends as it's decided, and an approval is made after it
        "select count(*) as held, "
        "count(*) filter (where status = any(%(approved)s)) as approved, "
        "count(*) filter (where status = 'rejected') as rejected, "
        "count(*) filter (where status = 'lapsed') as lapsed, "
        "count(*) filter (where status = 'waiting') as waiting, "
        f"percentile_cont(0.5) within group (order by {decided}) "
        "  filter (where status not in ('waiting', 'lapsed')) as decided_p50, "
        f"percentile_cont(0.9) within group (order by {decided}) "
        "  filter (where status not in ('waiting', 'lapsed')) as decided_p90 "
        f"from proposals where scenario = %(scenario)s and proposed_at > {since}",
        at).fetchone()
    graded = conn.execute(
        f"select count(*) filter (where graded_at > {since}) as graded, "
        f"count(*) filter (where graded_at > {since} and grade = 'right') as right, "
        f"count(*) filter (where graded_at > {since} and grade = 'wrong') as wrong, "
        f"count(*) filter (where graded_at > {since} and grade = 'critical') as critical, "
        f"count(*) filter (where lapsed_at > {since}) as lapsed "
        "from samples where scenario = %(scenario)s", at).fetchone()
    asked = conn.execute(  # by the instance asked
        "select asked as instance, count(*) as questions, "
        "count(*) filter (where answered_at is not null) as answered, "
        "count(*) filter (where problem is not null) as unanswered, "
        "percentile_cont(0.9) within group (order by extract(epoch from answered_at - asked_at)) "
        "  filter (where answered_at is not null) as p90 "
        f"from questions where asked_at > {since} group by asked order by asked", at).fetchall()
    noted = {r["instance"]: r for r in conn.execute(  # each note offered, as the ledger has it
        "select instance_id as instance, "
        "count(*) filter (where kind = 'tool' and e #>> '{outcome,status}' = 'ok') as kept, "
        "count(*) filter (where kind = 'tool' and e #>> '{outcome,status}' = 'refused') "
        "  as refused, count(*) filter (where kind = 'notebook') as let_go "
        "from (select kind, instance_id, entry::jsonb as e from ledger "
        "  where kind = 'tool' and action = %(note)s and decision = 'record' "
        "  or kind = 'notebook' and action in ('lapse', 'remove')) said "
        f"where (e ->> 'at')::timestamptz > {since} group by 1", at)}
    notes = {r["instance_id"]: r["n"] for r in conn.execute(
        "select instance_id, count(*) as n from notebook group by 1")}
    given = {r["instance_id"]: r for r in conn.execute(
        "select instance_id, count(*) as runs, sum(notes_given)::bigint as given from runs "
        f"where opened_at > {since} and notes_given > 0 group by 1", at)}
    return {
        "days": days,
        "obligations": {"due": owed["due"], "on_time": owed["on_time"], "late": owed["late"],
                        "open": owed["open"], "chased": owed["chased"],
                        "escalated": owed["escalated"],
                        "on_time_share": _share(owed["on_time"], owed["due"]),
                        "late_hours_p50": _hours(owed["late_p50"]),
                        "late_hours_p90": _hours(owed["late_p90"])},
        "reminders": {"due": reminded["due"], "on_time": reminded["on_time"],
                      "missed": reminded["missed"],
                      "on_time_share": _share(reminded["on_time"], reminded["due"])},
        "returning": [{"agent": r["agent"], "wrote_before": r["wrote_before"],
                       "came_back": r["came_back"],
                       "share": _share(r["came_back"], r["wrote_before"])} for r in returning],
        "groups": [{"agent": r["agent"], "messages": r["messages"], "chats": r["chats"],
                    "people": r["people"]} for r in mentioned],
        "runs": [{"instance": r["instance_id"], "model": r["model"], "runs": r["runs"],
                  "tokens_per_run": round(r["tokens"] / r["runs"]),
                  "tokens_p90": round(float(r["p90"])),
                  "cached_share": _share(r["cached"], r["tokens_in"]),
                  "cost_per_run": _cost(models.get(r["model"]), r)} for r in runs],
        "held": {"held": held["held"], "approved": held["approved"],
                 "rejected": held["rejected"], "lapsed": held["lapsed"],
                 "waiting": held["waiting"],
                 "approved_share": _share(held["approved"], held["approved"] + held["rejected"]),
                 "decided_hours_p50": _hours(held["decided_p50"]),
                 "decided_hours_p90": _hours(held["decided_p90"])},
        "samples": {"graded": graded["graded"], "right": graded["right"],
                    "wrong": graded["wrong"], "critical": graded["critical"],
                    "lapsed": graded["lapsed"],
                    "right_share": _share(graded["right"], graded["graded"])},
        "questions": [{"instance": r["instance"], "asked": r["questions"],
                       "answered": r["answered"], "unanswered": r["unanswered"],
                       "answered_seconds_p90": None if r["p90"] is None else float(r["p90"])}
                      for r in asked],
        "notebook": [{"instance": i, "notes": notes.get(i, 0),
                      "kept": noted[i]["kept"] if i in noted else 0,
                      "refused": noted[i]["refused"] if i in noted else 0,
                      "let_go": noted[i]["let_go"] if i in noted else 0,
                      "given": given[i]["given"] if i in given else 0,
                      "runs_given": given[i]["runs"] if i in given else 0}
                     for i in sorted({*noted, *notes, *given})],
    }


def told(m: dict[str, Any]) -> str:
    """The measures in words, for the command line."""
    o, r, h, s = m["obligations"], m["reminders"], m["held"], m["samples"]
    lines = [
        f"a5s over the last {m['days']} days:",
        "  What people owed that fell due: " + (
            f"{o['due']}, {_percent(o['on_time_share'])} done by when it was due, "
            f"{o['late']} done late, {o['open']} still open"
            + (f"; done late, half within {o['late_hours_p50']:.0f} hours of falling due, "
               f"nine in ten within {o['late_hours_p90']:.0f}" if o["late"] else "")
            + f"; an agent chased {o['chased']} and took {o['escalated']} up the line"
            if o["due"] else "nothing") + ".",
        "  Reminders people asked for that fell due: " + (
            f"{r['due']}, {_percent(r['on_time_share'])} on time, {r['missed']} never sent"
            if r["due"] else "none") + ".",
        "  People who came back to an agent, of those who wrote to it the window before: " + (
            "; ".join(f"the {x['agent']}, {x['came_back']} of {x['wrote_before']}"
                      for x in m["returning"]) or "nobody wrote to one before") + ".",
        "  Group chats that mentioned an agent: " + ("; ".join(
            f"the {x['agent']}, {_many(x['messages'], 'time')} in {_many(x['chats'], 'chat')}, "
            f"by {_many(x['people'], 'person', 'people')}" for x in m["groups"]) or "none") + ".",
        "  Runs that called a model: " + ("; ".join(
            f"{x['instance']}, {x['runs']} on {x['model']}, {x['tokens_per_run']:,} tokens each"
            + (f", {_percent(x['cached_share'])} of what they took in from the cache"
               if x["cached_share"] else "")
            + (f", costing {x['cost_per_run']:.3f} each at its prices"
               if x["cost_per_run"] is not None else ", its model's prices unknown")
            for x in m["runs"]) or "none") + ".",
        "  Changes held for a decision: " + (
            f"{h['held']}, {h['approved']} approved, {h['rejected']} rejected, "
            f"{h['lapsed']} lapsed undecided and {h['waiting']} waiting"
            + (f"; half decided within {h['decided_hours_p50']:.1f} hours, nine in ten within "
               f"{h['decided_hours_p90']:.1f}" if h["decided_hours_p50"] is not None else "")
            if h["held"] else "none") + ".",
        "  Samples graded: " + (
            f"{s['graded']}, {_percent(s['right_share'])} right, {s['wrong']} wrong and "
            f"{s['critical']} critical" if s["graded"] else "none")
        + (f"; {s['lapsed']} lapsed ungraded" if s["lapsed"] else "") + ".",
        "  Questions agents asked each other: " + ("; ".join(
            f"{x['instance']} was asked {x['asked']} and answered {x['answered']}"
            + (f", nine in ten within {x['answered_seconds_p90']:.0f}s"
               if x["answered_seconds_p90"] is not None else "")
            for x in m["questions"]) or "none") + ".",
        "  Notebooks: " + ("; ".join(
            f"{x['instance']}, {x['notes']} notes now, {x['kept']} kept and {x['refused']} "
            f"refused, {x['let_go']} let go, given {_many(x['given'], 'time')} in "
            f"{_many(x['runs_given'], 'run')}"
            for x in m["notebook"]) or "none") + ".",
    ]
    return "\n".join(lines)


def _cost(model: ModelConfig | None, r: dict[str, Any]) -> float | None:
    """What a run costs on average, at its model's prices, with what it read from the cache, or
    wrote to it, at the prices the provider charges for those."""
    if model is None or model.prices is None or not r["runs"]:
        return None
    p = model.prices
    fresh = r["tokens_in"] - r["cached"] - r["cache_written"]
    return (fresh * p.input + r["cached"] * (p.cached_input if p.cached_input is not None
                                             else p.input)
            + r["cache_written"] * (p.cache_write if p.cache_write is not None else p.input)
            + r["tokens_out"] * p.output) / 1_000_000 / r["runs"]


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _hours(seconds: Any) -> float | None:
    return None if seconds is None else float(seconds) / 3600


def _many(n: int, one: str, more: str | None = None) -> str:
    return f"{n} {one if n == 1 else more or one + 's'}"


def _percent(share: float | None) -> str:
    return "none" if share is None else f"{share:.0%}"
