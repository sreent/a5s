"""Status: how a5s is doing, for the team that runs it, from the core's own records.

Over the last day: what waits in the queue, the runs and how they ended, what was denied,
the tokens each instance used and any budget warnings, the instances that aren't active,
and the models whose breakers are open. And a5s's objectives, with whether it meets them:
how quickly people get answers, and how many chases go out before what's owed falls due.
`a5s status` prints it, and the gateway's /status gives it to a dashboard. What to do about
each is in docs/runbooks.md.
"""

from __future__ import annotations

from typing import Any

import psycopg

# a5s's starting objectives [TBC]: set from the first users' baseline
OBJECTIVES = {"reply_seconds_p90": 120, "chased_on_time": 0.95}


def report(conn: psycopg.Connection, breakers: list[str]) -> dict[str, Any]:
    """The last day's status, by the database's clock."""
    queue = conn.execute(
        "select count(*) as waiting, extract(epoch from now() - min(received_at)) as oldest "
        "from inbound where answered_at is null and (retry_at is null or retry_at <= now())"
    ).fetchone()
    runs = conn.execute(
        "select trigger->>'kind' as kind, coalesce(outcome, 'open') as outcome, count(*) as n "
        "from runs where opened_at > now() - interval '1 day' group by 1, 2 order by 1, 2"
    ).fetchall()
    denied = conn.execute(
        "select kind, action, count(*) as n from ("
        "  select kind, action, entry::jsonb->>'at' as at from ledger "
        "  where decision = 'deny' order by seq desc limit 10000) recent "
        "where at::timestamptz > now() - interval '1 day' group by 1, 2 order by 3 desc, 1, 2"
    ).fetchall()
    tokens = conn.execute(
        "select r.instance_id, sum(r.tokens) as tokens, (select count(*) from ("
        "  select instance_id, entry::jsonb->>'at' as at from ledger where kind = 'budget' "
        "  order by seq desc limit 1000) w where w.instance_id = r.instance_id "
        "  and w.at::timestamptz > now() - interval '1 day') as warnings "
        "from runs r where r.opened_at > now() - interval '1 day' and r.tokens > 0 "
        "group by 1 order by 1").fetchall()
    stopped = conn.execute(
        "select id, status, suspended_by from instances where status <> 'active' order by id"
    ).fetchall()
    replies = conn.execute(
        "select percentile_cont(0.5) within group (order by seconds) as p50, "
        "       percentile_cont(0.9) within group (order by seconds) as p90, count(*) as n from ("
        "  select extract(epoch from r.closed_at - i.received_at) as seconds from runs r "
        "  join inbound i on i.id = (r.trigger->>'inbound')::uuid "
        "  where r.trigger->>'kind' = 'message' and r.outcome = 'done' "
        "  and r.closed_at > now() - interval '1 day') answered").fetchone()
    chased = conn.execute(
        "select count(*) as due, count(*) filter (where chased_at is not null "
        "and chased_at <= due_at) as on_time from obligations "
        "where due_at between now() - interval '7 days' and now()").fetchone()
    on_time = chased["on_time"] / chased["due"] if chased["due"] else None
    return {
        "queue": {"waiting": queue["waiting"], "oldest_seconds": _number(queue["oldest"])},
        "runs": [dict(r) for r in runs],
        "denied": [dict(r) for r in denied],
        "tokens": [{"instance": r["instance_id"], "tokens": int(r["tokens"]),
                    "budget_warnings": r["warnings"]} for r in tokens],
        "not_active": [dict(r) for r in stopped],
        "breakers_open": breakers,
        "objectives": {
            "replies": {"answered": replies["n"], "p50_seconds": _number(replies["p50"]),
                        "p90_seconds": _number(replies["p90"]),
                        "objective_seconds": OBJECTIVES["reply_seconds_p90"],
                        "met": replies["p90"] is None
                        or replies["p90"] <= OBJECTIVES["reply_seconds_p90"]},
            "chases": {"due": chased["due"], "on_time": on_time,
                       "objective": OBJECTIVES["chased_on_time"],
                       "met": on_time is None or on_time >= OBJECTIVES["chased_on_time"]},
        },
    }


def told(status: dict[str, Any]) -> str:
    """The status in words, for the command line."""
    q, o = status["queue"], status["objectives"]
    by_kind: dict[str, int] = {}
    for r in status["runs"]:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + r["n"]
    ended: dict[str, int] = {}
    for r in status["runs"]:
        ended[r["outcome"]] = ended.get(r["outcome"], 0) + r["n"]
    lines = [
        "a5s over the last day:",
        f"  Queue: {q['waiting']} waiting" + (f", the oldest for {q['oldest_seconds']:.0f}s"
                                             if q["oldest_seconds"] else "") + ".",
        f"  Runs: {sum(by_kind.values())} ({_listed(by_kind)}), ended {_listed(ended)}.",
        "  Replies: " + (f"half within {o['replies']['p50_seconds']:.0f}s, nine in ten within "
                         f"{o['replies']['p90_seconds']:.0f}s" if o["replies"]["answered"]
                         else "none yet")
        + f" (objective: nine in ten within {o['replies']['objective_seconds']}s"
        + ("" if o["replies"]["met"] else ", missed") + ").",
        "  Chases before they fell due, over a week: "
        + (f"{o['chases']['on_time']:.0%} of {o['chases']['due']}" if o["chases"]["due"]
           else "nothing fell due")
        + f" (objective: {o['chases']['objective']:.0%}" + ("" if o["chases"]["met"]
                                                              else ", missed") + ").",
        "  Denied: " + (_listed({f"{d['kind']} {d['action']}": d["n"] for d in status["denied"]})
                        or "nothing") + ".",
        "  Tokens: " + ("; ".join(f"{t['instance']} {t['tokens']:,}"
                                  + (f", {t['budget_warnings']} past four fifths"
                                     if t["budget_warnings"] else "")
                                  for t in status["tokens"]) or "none") + ".",
        "  Not active: " + (", ".join(f"{i['id']}, {i['status']}"
                                      + (f" by {i['suspended_by']}" if i["suspended_by"] else "")
                                      for i in status["not_active"]) or "none") + ".",
        "  Breakers open: " + (", ".join(status["breakers_open"]) or "none") + ".",
    ]
    return "\n".join(lines)


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _listed(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {n}" for name, n in counts.items())
