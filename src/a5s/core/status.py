"""Status: how a5s is doing, for the team that runs it, from the core's own records.

Over the last day: what waits in the queue, the runs and how they ended, what was denied,
the tokens each instance used and any budget warnings, what a chat didn't take, the urgent
messages held for a batch because people had had their day's five, the instances that aren't
active, and the models whose breakers are open. And a5s's objectives, with whether it meets
them, or None while there's nothing to measure: how quickly people get answers, and how many
chases go out before what's owed falls due.
`a5s status` prints it, and the gateway's /status gives it to a dashboard. What to do about
each is in docs/runbooks.md.
"""

from __future__ import annotations

from typing import Any

import psycopg

from a5s.core import samples, sealing

# a5s's starting objectives [TBC]: set from the first users' baseline
OBJECTIVES = {"reply_seconds_p90": 120, "chased_on_time": 0.95}
# How a run ends: a fixed set, so no figure, the status or the studio carries anyone's words
OUTCOMES = ("done", "done, leaving some out", "failed", "reply denied", "model unavailable",
            "budget spent", "abandoned")


def outcome(found: str | None) -> str:
    """A run's outcome as the figures say it: open, one of OUTCOMES, or other."""
    if found is None:
        return "open"
    return found if found in OUTCOMES else "other"



def second_factor_refused(conn: psycopg.Connection, doing: str) -> None:
    """Count a refusal of what counts for want of a second factor, by what it was."""
    conn.execute("insert into second_factor_refusals (day, doing, n) values (current_date, %s, 1) "
                 "on conflict (day, doing) do update set n = second_factor_refusals.n + 1",
                 (doing[:40],))

def report(conn: psycopg.Connection, breakers: list[str], keys: tuple[str, ...] = (),
           rubber_stamps: bool = False,
           sign_ins: tuple[str, tuple[str, ...]] | None | bool = False) -> dict[str, Any]:
    """The last day's status, by the database's clock. `keys` are the core's seal keys, for
    the caps that count; deciders are named for rubber stamps only if `rubber_stamps`.
    `sign_ins` is the second factor the identity provider's sign-ins must show for what
    counts: None for none, and False with no identity provider."""
    queue = conn.execute(
        "select count(*) as waiting, extract(epoch from now() - min(received_at)) as oldest "
        "from inbound where answered_at is null and (retry_at is null or retry_at <= now())"
    ).fetchone()
    runs = conn.execute(
        "select trigger->>'kind' as kind, coalesce(outcome, 'open') as outcome, count(*) as n "
        "from runs where opened_at > now() - interval '1 day' group by 1, 2 order by 1, 2"
    ).fetchall()
    denied = conn.execute(  # the newest denials, by the ledger's index of them: a chat a5s
        "select kind, action, count(*) as n from ("  # turned away, such as a group too big,
        "  select kind, action, entry::jsonb->>'at' as at from ledger "  # counted apart
        "  where decision = 'deny' order by seq desc limit 10000) recent "
        "where at::timestamptz > now() - interval '1 day' group by 1, 2 order by 3 desc, 1, 2"
    ).fetchall()
    turned = [d for d in denied if d["kind"] == "inbound"]
    denied = [d for d in denied if d["kind"] != "inbound"]
    asked = conn.execute(  # questions agents asked each other (core/asking.py)
        "select count(*) filter (where answered_at is not null) as answered, "
        "count(*) filter (where problem is not null) as unanswered, "
        "percentile_cont(0.9) within group (order by extract(epoch from answered_at - asked_at)) "
        "filter (where answered_at is not null) as p90 "
        "from questions where asked_at > now() - interval '1 day'").fetchone()
    noted = conn.execute(  # the notebook (core/notebook.py): its notes, and those let go
        "select (select count(*) from notebook) as kept, (select count(*) from ledger "
        "where kind = 'notebook' and action = 'lapse' and (entry::jsonb ->> 'at')::timestamptz "
        "> now() - interval '1 day') as lapsed").fetchone()
    tokens = conn.execute(
        "select r.instance_id, sum(r.tokens) as tokens, (select count(*) from spend s "
        "  where s.instance_id = r.instance_id and s.warned_at > now() - interval '1 day') "
        "  as warnings "
        "from runs r where r.opened_at > now() - interval '1 day' and r.tokens > 0 "
        "group by 1 order by 1").fetchall()
    deliveries = conn.execute(  # an answer kept back from a group chat isn't a chat that's down
        "select count(*) filter (where delivered_at is null and channel <> 'local' "
        "  and attempts > 0) as retrying, "
        "count(*) filter (where channel = 'local' and problem is not null "
        "  and problem <> 'someone joined the chat while it was answering') as left_in_inbox, "
        "count(*) filter (where problem = 'someone joined the chat while it was answering') "
        "  as kept_back from outbox where at > now() - interval '1 day'").fetchone()
    held = conn.execute("select count(*) as n, count(distinct person) as people "
                        "from urgent_held where sent_at is null").fetchone()
    changes = conn.execute(
        "select count(*) filter (where status = 'waiting') as waiting, "
        "extract(epoch from now() - min(proposed_at) filter (where status = 'waiting')) as oldest, "
        "count(*) filter (where status = 'making' and decided_at < now() - interval '10 minutes') "
        "as stuck, count(*) filter (where status = 'not made' and ended_at > now() - interval "
        "'1 day') as not_made, count(*) filter (where status = 'lapsed' and ended_at > now() - "
        "interval '1 day') as lapsed from proposals").fetchone()
    graded = conn.execute(
        "select count(*) filter (where grade is null and lapsed_at is null) as waiting, "
        "count(*) filter (where lapsed_at > now() - interval '91 days') as lapsed from samples"
    ).fetchone()
    unsealed = sealing.waiting(conn, "5 minutes")  # the gateway seals each minute
    raised = sorted(samples.standing_caps(conn, keys, "cap >= 2"),
                    key=lambda r: (r["part"], r["action"]))
    lowered = conn.execute("select count(*) as n from ledger where kind = 'cap' and action = "
                           "'lower' and (entry::jsonb ->> 'at')::timestamptz > now() - "
                           "interval '1 day'").fetchone()
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
    missing = conn.execute(  # whom the directory no longer names, not yet archived
        "select count(*) as n from departures where archived_at is null").fetchone()
    tasked = conn.execute(  # people's tasks (core/tasks.py), their parts apart
        "select count(*) filter (where status = 'running' and lease_expires_at > now()) "
        "  as at_work, "
        "count(*) filter (where status = 'running' and lease_expires_at <= now()) as lapsed, "
        "count(*) filter (where status in ('queued', 'waiting') and (not_before is null "
        "  or not_before <= now())) as due, "
        "extract(epoch from now() - min(coalesce(not_before, updated_at)) filter ("
        "  where status in ('queued', 'waiting') and (not_before is null "
        "  or not_before <= now()))) as oldest_due, "
        "count(*) filter (where status = 'blocked') as blocked, "
        "count(*) filter (where status = 'done' and updated_at > now() - interval '1 day') "
        "  as done, "
        "count(*) filter (where status = 'failed' and updated_at > now() - interval '1 day') "
        "  as failed "
        "from tasks where parent is null").fetchone()
    refused = conn.execute(  # what counts, refused for want of a second factor
        "select doing, sum(n) as n from second_factor_refusals "
        "where day >= current_date - 1 group by doing order by doing").fetchall()
    return {
        "queue": {"waiting": queue["waiting"], "oldest_seconds": _number(queue["oldest"])},
        "runs": _outcomes(runs),
        "denied": [dict(r) for r in denied],
        "turned_away": sum(d["n"] for d in turned),
        "questions": {"answered": asked["answered"], "unanswered": asked["unanswered"],
                      "p90_seconds": _number(asked["p90"])},
        "notebook": {"kept": noted["kept"], "lapsed": noted["lapsed"]},
        "tokens": [{"instance": r["instance_id"], "tokens": int(r["tokens"]),
                    "budget_warnings": r["warnings"]} for r in tokens],
        "deliveries": {"retrying": deliveries["retrying"],
                       "left_in_inbox": deliveries["left_in_inbox"],
                       "kept_back": deliveries["kept_back"]},
        "urgent_held": {"messages": held["n"], "people": held["people"]},
        "changes": {"waiting": changes["waiting"], "oldest_seconds": _number(changes["oldest"]),
                    "stuck": changes["stuck"], "not_made": changes["not_made"],
                    "lapsed": changes["lapsed"]},
        "samples": {"to_grade": graded["waiting"], "lapsed": graded["lapsed"],
                    "level_2": [{"part": r["part"], "action": r["action"],
                                 "since": r["since"].isoformat()} for r in raised],
                    "caps_lowered": lowered["n"],
                    "rubber_stamps": samples.rubber_stamps(conn) if rubber_stamps else None},
        "unsealed": unsealed,
        "sign_ins": None if sign_ins is False else {  # what counts, with a second factor
            "second_factor": f"{sign_ins[0]}:{','.join(sign_ins[1])}" if sign_ins else None,
            "refused": {r["doing"]: int(r["n"]) for r in refused}},
        "tasks": {"at_work": tasked["at_work"], "lapsed": tasked["lapsed"], "due": tasked["due"],
                  "oldest_due_seconds": _number(tasked["oldest_due"]),
                  "blocked": tasked["blocked"], "done": tasked["done"],
                  "failed": tasked["failed"]},
        "missing": missing["n"],
        "not_active": [dict(r) for r in stopped],
        "breakers_open": breakers,
        "objectives": {
            "replies": {"answered": replies["n"], "p50_seconds": _number(replies["p50"]),
                        "p90_seconds": _number(replies["p90"]),
                        "objective_seconds": OBJECTIVES["reply_seconds_p90"],
                        "met": None if replies["p90"] is None
                        else replies["p90"] <= OBJECTIVES["reply_seconds_p90"]},
            "chases": {"due": chased["due"], "on_time": on_time,
                       "objective": OBJECTIVES["chased_on_time"],
                       "met": None if on_time is None else on_time >= OBJECTIVES["chased_on_time"]},
        },
    }


def _outcomes(rows: list[dict]) -> list[dict]:
    """Runs by trigger and outcome, each outcome from the fixed set."""
    found: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r["kind"], outcome(None if r["outcome"] == "open" else r["outcome"]))
        found[key] = found.get(key, 0) + r["n"]
    return [{"kind": k, "outcome": o, "n": n} for (k, o), n in sorted(found.items(),
                                                                     key=lambda i: (str(i[0][0]), i[0][1]))]


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
        + _verdict(o["replies"]["met"]) + ").",
        "  Chases before they fell due, over a week: "
        + (f"{o['chases']['on_time']:.0%} of {o['chases']['due']}" if o["chases"]["due"]
           else "nothing fell due")
        + f" (objective: {o['chases']['objective']:.0%}" + _verdict(o["chases"]["met"]) + ").",
        "  Denied: " + (_listed({f"{d['kind']} {d['action']}": d["n"] for d in status["denied"]})
                        or "nothing") + ".",
        "  Chats turned away, such as a group too big or with strangers: "
        + str(status.get("turned_away") or "none") + ".",
        "  Questions agents asked each other: " + (
            f"{status['questions']['answered']} answered"
            + (f", nine in ten within {status['questions']['p90_seconds']:.0f}s"
               if status["questions"]["p90_seconds"] is not None else "")
            + f", {status['questions']['unanswered']} not"
            if status["questions"]["answered"] or status["questions"]["unanswered"]
            else "none") + ".",
        *([_tasks_told(status["tasks"])] if status.get("tasks") else []),
        "  Notebook: " + f"{status['notebook']['kept']} notes"
        + (f", {status['notebook']['lapsed']} let go in the last day as their records changed"
           if status["notebook"]["lapsed"] else "") + ".",
        "  Tokens: " + ("; ".join(f"{t['instance']} {t['tokens']:,}"
                                  + (f", {t['budget_warnings']} past four fifths"
                                     if t["budget_warnings"] else "")
                                  for t in status["tokens"]) or "none") + ".",
        "  Deliveries a chat didn't take: " + (
            f"{status['deliveries']['retrying']} being tried again, "
            f"{status['deliveries']['left_in_inbox']} left in people's local inbox"
            if status["deliveries"]["retrying"] or status["deliveries"]["left_in_inbox"]
            else "none") + "."
        + (f" Answers kept back from a group chat someone joined: "
           f"{status['deliveries']['kept_back']}." if status["deliveries"].get("kept_back")
           else ""),
        "  Changes waiting for a decision: " + (
            f"{status['changes']['waiting']}, the oldest for "
            f"{status['changes']['oldest_seconds'] / 86400:.0f} days"
            if status["changes"]["waiting"] else "none")
        + (f"; {status['changes']['stuck']} stopped part way through being made "
           "(a5s proposals)" if status["changes"]["stuck"] else "")
        + (f"; {status['changes']['not_made']} approved but not made, and "
           f"{status['changes']['lapsed']} lapsed, in the last day"
           if status["changes"]["not_made"] or status["changes"]["lapsed"] else "") + ".",
        "  Samples waiting to be graded: " + (str(status["samples"]["to_grade"])
                                              if status["samples"]["to_grade"] else "none")
        + (f"; {status['samples']['lapsed']} lapsed ungraded this quarter"
           if status["samples"]["lapsed"] else "") + ".",
        "  Earned level 2: " + ("; ".join(f"{r['action']} in {r['part']}"
                                          for r in status["samples"]["level_2"]) or "nothing")
        + (f"; {status['samples']['caps_lowered']} caps lowered in the last day"
           if status["samples"]["caps_lowered"] else "") + ".",
        *(["  Approvals graded wrong far more than others': " + (
            ", ".join(f"{r['person']}, {r['graded_wrong']} of {r['approved']}"
                      for r in status["samples"]["rubber_stamps"]) or "nobody") + "."]
          if status["samples"]["rubber_stamps"] is not None else []),
        *([(f"  Approvals, decisions and grades the gateway hasn't sealed in 5 minutes: "
            f"{status['unsealed']}, which don't count until it does (see A5S_SEAL_KEYS).")]
          if status.get("unsealed") else []),
        *([("  Approvals, decisions, grades and the officer's requests count with a second "
            f"factor only: {status['sign_ins']['second_factor']}." if status["sign_ins"][
                "second_factor"] else
            "  Approvals, decisions, grades and the officer's requests aren't checked for a "
            "second factor: set A5S_OIDC_MFA, such as amr:mfa (docs/administration.md).")]
          if status.get("sign_ins") else []),
        *([("  Refused for want of a second factor: "
            + _listed(status["sign_ins"]["refused"]) + ". The identity provider's policy, "
            "not the people refused, decides when a sign-in asks for one (docs/runbooks.md).")]
          if (status.get("sign_ins") or {}).get("refused") else []),
        "  Urgent messages held for a batch: " + (
            f"{status['urgent_held']['messages']} for {status['urgent_held']['people']} "
            + ("person" if status["urgent_held"]["people"] == 1 else "people")
            if status["urgent_held"]["messages"] else "none") + ".",
        *([(f"  People the directory no longer names, not yet archived: {status['missing']}"
            " (many at once wait a week, in case it's the directory).")]
          if status.get("missing") else []),
        "  Not active: " + (", ".join(f"{i['id']}, {i['status']}"
                                      + (f" by {i['suspended_by']}" if i["suspended_by"] else "")
                                      for i in status["not_active"]) or "none") + ".",
        "  Breakers open: " + (", ".join(status["breakers_open"]) or "none") + ".",
    ]
    return "\n".join(lines)


def _verdict(met: bool | None) -> str:
    return "" if met else ", not known yet" if met is None else ", missed"


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _tasks_told(tasks: dict[str, Any]) -> str:
    oldest = tasks["oldest_due_seconds"]
    return ("  Tasks: " + f"{tasks['at_work']} at work, {tasks['due']} due"
            + (f", the oldest for {oldest:.0f}s" if oldest and tasks["due"] else "")
            + f", {tasks['blocked']} waiting on their owners"
            + (f", {tasks['lapsed']} whose slice's lease lapsed, for the runs' sweep"
               if tasks["lapsed"] else "")
            + f"; in the last day {tasks['done']} done and {tasks['failed']} failed.")


def _listed(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {n}" for name, n in counts.items())
