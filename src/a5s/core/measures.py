"""Measures: how a5s is doing for the people it serves, worked out from its own records, for
the baseline phase 1 asks of its first users (docs/phase-1.md), which the pilot plans
(docs/pilot.md).

- Nothing lapses unnoticed: of what people owed that fell due, how much was done by when it
  was due, and of the reminders they asked for that fell due, how many came on time.
- People spend less time chasing: how long after it fell due what was done late was done.
- People keep using the agents: of those who wrote to an agent in the window before this one,
  how many wrote to it again in this one.
- What it costs: tokens for each run that called a model, and for a model whose prices its
  approved list gives, what such a run costs.

Each is over the last `days` days, by the database's clock, and counts people, never names
them. What people owed is the scenario's now, so a deployment that changed scenarios counts
only the new one's. Someone who has left isn't counted as not coming back, once a5s has
archived what it kept for them (core/departures.py).
"""

from __future__ import annotations

from typing import Any

import psycopg

from a5s.config import ModelConfig

GRACE = "1 hour"  # a reminder for a particular time is on time within this of it [TBC]


def report(conn: psycopg.Connection, scenario: str, models: dict[str, ModelConfig],
           days: int = 30) -> dict[str, Any]:
    """The measures over the last `days` days, at least one, for the scenario named."""
    days = max(1, int(days))
    window = f"{days} days"
    owed = conn.execute(
        "select count(*) as due, "
        "count(*) filter (where done_at <= due_at) as on_time, "
        "count(*) filter (where done_at > due_at) as late, "
        "count(*) filter (where done_at is null) as open, "
        "percentile_cont(0.5) within group (order by extract(epoch from done_at - due_at)) "
        "  filter (where done_at > due_at) as late_p50, "
        "percentile_cont(0.9) within group (order by extract(epoch from done_at - due_at)) "
        "  filter (where done_at > due_at) as late_p90 "
        "from obligations where scenario = %(scenario)s "
        "and due_at > now() - %(window)s::interval and due_at <= now()",
        {"scenario": scenario, "window": window}).fetchone()
    by = "due_at + case when in_digest then interval '1 day' else %(grace)s::interval end"
    reminded = conn.execute(  # one for a day comes in that day's digest, at its own time, so
        "select count(*) as due, "  # it's counted once that day is over
        f"count(*) filter (where reminded_at <= {by}) as on_time, "
        "count(*) filter (where reminded_at is null) as missed "
        "from reminders where confirmed_at is not null and cancelled_at is null "
        f"and due_at > now() - %(window)s::interval and {by} <= now()",
        {"window": window, "grace": GRACE}).fetchone()
    returning = conn.execute(
        "with before as (select distinct agent, person from inbound where "
        "  received_at > now() - 2 * %(window)s::interval "
        "  and received_at <= now() - %(window)s::interval and person not like 'former:%%'), "
        "since as (select distinct agent, person from inbound "
        "  where received_at > now() - %(window)s::interval) "
        "select b.agent, count(*) as wrote_before, count(s.person) as came_back "
        "from before b left join since s on s.agent = b.agent and s.person = b.person "
        "group by b.agent order by b.agent", {"window": window}).fetchall()
    runs = conn.execute(  # by the model each called, or, before runs said, their instance's
        "select r.instance_id, coalesce(r.model, i.model) as model, count(*) as runs, "
        "sum(r.tokens)::bigint as tokens, "
        "sum(r.tokens_in)::bigint as tokens_in, sum(r.tokens_out)::bigint as tokens_out, "
        "percentile_cont(0.9) within group (order by r.tokens) as p90 "
        "from runs r join instances i on i.id = r.instance_id "
        "where r.opened_at > now() - %(window)s::interval and r.tokens > 0 "
        "group by 1, 2 order by 1", {"window": window}).fetchall()
    return {
        "days": days,
        "obligations": {"due": owed["due"], "on_time": owed["on_time"], "late": owed["late"],
                        "open": owed["open"], "on_time_share": _share(owed["on_time"], owed["due"]),
                        "late_hours_p50": _hours(owed["late_p50"]),
                        "late_hours_p90": _hours(owed["late_p90"])},
        "reminders": {"due": reminded["due"], "on_time": reminded["on_time"],
                      "missed": reminded["missed"],
                      "on_time_share": _share(reminded["on_time"], reminded["due"])},
        "returning": [{"agent": r["agent"], "wrote_before": r["wrote_before"],
                       "came_back": r["came_back"],
                       "share": _share(r["came_back"], r["wrote_before"])} for r in returning],
        "runs": [{"instance": r["instance_id"], "model": r["model"], "runs": r["runs"],
                  "tokens_per_run": round(r["tokens"] / r["runs"]),
                  "tokens_p90": round(float(r["p90"])),
                  "cost_per_run": _cost(models.get(r["model"]), r["tokens_in"], r["tokens_out"],
                                        r["runs"])} for r in runs],
    }


def told(m: dict[str, Any]) -> str:
    """The measures in words, for the command line."""
    o, r = m["obligations"], m["reminders"]
    lines = [
        f"a5s over the last {m['days']} days:",
        "  What people owed that fell due: " + (
            f"{o['due']}, {_percent(o['on_time_share'])} done by when it was due, "
            f"{o['late']} done late, {o['open']} still open"
            + (f"; done late, half within {o['late_hours_p50']:.0f} hours of falling due, "
               f"nine in ten within {o['late_hours_p90']:.0f}" if o["late"] else "")
            if o["due"] else "nothing") + ".",
        "  Reminders people asked for that fell due: " + (
            f"{r['due']}, {_percent(r['on_time_share'])} on time, {r['missed']} never sent"
            if r["due"] else "none") + ".",
        "  People who came back to an agent, of those who wrote to it the window before: " + (
            "; ".join(f"the {x['agent']}, {x['came_back']} of {x['wrote_before']}"
                      for x in m["returning"]) or "nobody wrote to one before") + ".",
        "  Runs that called a model: " + ("; ".join(
            f"{x['instance']}, {x['runs']} on {x['model']}, {x['tokens_per_run']:,} tokens each"
            + (f", costing {x['cost_per_run']:.3f} each at its prices"
               if x["cost_per_run"] is not None else ", its model's prices unknown")
            for x in m["runs"]) or "none") + ".",
    ]
    return "\n".join(lines)


def _cost(model: ModelConfig | None, tokens_in: int, tokens_out: int, runs: int) -> float | None:
    if model is None or model.prices is None or not runs:
        return None
    return (tokens_in * model.prices[0] + tokens_out * model.prices[1]) / 1_000_000 / runs


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _hours(seconds: Any) -> float | None:
    return None if seconds is None else float(seconds) / 3600


def _percent(share: float | None) -> str:
    return "none" if share is None else f"{share:.0%}"
