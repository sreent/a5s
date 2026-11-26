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

import json
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from a5s import db
from a5s.core import anchor, rotation, samples, sealing

# a5s's starting objectives [starting value]: set from the first users' baseline
OBJECTIVES = {"reply_seconds_p90": 120, "chased_on_time": 0.95}
# How a run ends: a fixed set, so no figure, the status or the studio carries anyone's words
OUTCOMES = ("done", "done, leaving some out", "failed", "reply denied", "model unavailable",
            "budget spent", "abandoned")


def outcome(found: str | None) -> str:
    """A run's outcome as the figures say it: open, one of OUTCOMES, or other."""
    if found is None:
        return "open"
    return found if found in OUTCOMES else "other"



# How long the core's record of the status may age, at a minute between records, before the
# Status page says the scheduler, which asks for it, or the core may be away
SEEN_LATE = 3 * 60


def seen(conn: db.Connection, status: dict[str, Any]) -> None:
    """Record the status as the core found it, for the studio's Status page."""
    conn.execute("insert into status_seen (only_one, at, status) values (true, now(), %s) "
                 "on conflict (only_one) do update set at = excluded.at, "
                 "status = excluded.status", (json.dumps(status, default=str),))


def last_seen(conn: db.Connection) -> tuple[dict[str, Any], float] | None:
    """The status as the core last recorded it, and how many seconds ago: None if never."""
    found = conn.execute("select status, extract(epoch from now() - at) as age "
                         "from status_seen").fetchone()
    return (found["status"], float(found["age"])) if found else None


def second_factor_refused(conn: db.Connection, doing: str) -> None:
    """Count a refusal of what counts for want of a second factor, by what it was."""
    conn.execute("insert into second_factor_refusals (day, doing, n) values (current_date, %s, 1) "
                 "on conflict (day, doing) do update set n = second_factor_refusals.n + 1",
                 (doing[:40],))

def report(conn: db.Connection, breakers: list[str], keys: tuple[str, ...] = (),
           rubber_stamps: bool = False,
           sign_ins: tuple[str, tuple[str, ...]] | Literal[False] | None = False,
           scenario: str | None = None) -> dict[str, Any]:
    """The last day's status, by the database's clock. `keys` are the core's seal keys, for
    the caps that count; deciders are named for rubber stamps only if `rubber_stamps`.
    `sign_ins` is the second factor the identity provider's sign-ins must show for what
    counts: None for none, and False with no identity provider. With the `scenario` a5s
    serves, the models the health gate stopped for it, which nobody has put back."""
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
    moving = rotation.waiting(conn, keys)  # seals under a key it moves away from (round 15, D2)
    leaked_held = rotation.leaked_held(conn, keys)  # one never to seal again with (round 16)
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
    copies = anchor.state(conn)  # as the copier records it (round 15, D8)
    heard = conn.execute(  # the scheduler's heartbeat: it asks the core to record this each minute
        "select extract(epoch from now() - at) as age from status_seen").fetchone()
    gated = [r["model"] for r in conn.execute(  # stopped by the health gate (core/health.py)
        "select distinct model from model_health where scenario = %s and gated_at is not null "
        "order by model", (scenario,))] if scenario else []
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
                    "on_its_own": [{"part": r["part"], "action": r["action"],
                                 "since": r["since"].isoformat()} for r in raised],
                    "caps_lowered": lowered["n"],
                    "rubber_stamps": samples.rubber_stamps(conn) if rubber_stamps else None},
        "unsealed": unsealed,
        "seals_waiting": moving,
        "seal_keys_leaked": leaked_held,
        "sign_ins": None if sign_ins is False else {  # what counts, with a second factor
            "second_factor": (f"{sign_ins[0]}:{','.join(sign_ins[1])}" if sign_ins[1]
                              else sign_ins[0]) if sign_ins else None,  # none, said so (A10)
            "refused": {r["doing"]: int(r["n"]) for r in refused}},
        "tasks": {"at_work": tasked["at_work"], "lapsed": tasked["lapsed"], "due": tasked["due"],
                  "oldest_due_seconds": _number(tasked["oldest_due"]),
                  "blocked": tasked["blocked"], "done": tasked["done"],
                  "failed": tasked["failed"]},
        "missing": missing["n"],
        "copies": copies,
        "scheduler_seen_seconds": _number(heard["age"]) if heard else None,
        "not_active": [dict(r) for r in stopped],
        "breakers_open": breakers,
        "models_stopped": gated,
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


# What needs someone now, out of hours too, as docs/runbooks.md#on-call says what pages, and what
# can wait for working hours: each with the runbook section that says what to do
NOW, LATER = "now", "working hours"
QUEUE_LATE = 5 * 60  # seconds the oldest message may wait before it's worth a look
COPIES_LATE = 30 * 60  # seconds the ledger's newest copy may age, entries waiting, before a page
CHECK_LATE = 2 * 86400  # seconds since the copier last checked the whole ledger, before a look


EXPIRY_SOON = 30  # days before a credential expires that the status says so


def expiring(expires: Mapping[str, date] | None, today: date) -> list[dict[str, Any]]:
    """The credentials A5S_EXPIRES notes as expiring within EXPIRY_SOON days, or expired,
    soonest first: each with the day, and the days left, below 0 once it's past."""
    return [{"credential": name, "on": on.isoformat(), "days": (on - today).days}
            for name, on in sorted((expires or {}).items(), key=lambda item: item[1])
            if (on - today).days <= EXPIRY_SOON]


def expiry(credential: dict[str, Any]) -> str:
    """When a credential expires, in words, and what to do: as the status and the doctor say."""
    name, on, days = credential["credential"], credential["on"], credential["days"]
    if days < 0:
        return (f"{name} expired on {on}, as A5S_EXPIRES notes, so whatever a5s reaches with it "
                "refuses it: make a new one, set it where a5s takes it, and note when it expires")
    when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
    return (f"{name} expires on {on}, {when}, as A5S_EXPIRES notes: make a new one and set it "
            "where a5s takes it before then, and note when that one expires")


COPYING = "the-ledgers-copies-stop"  # the runbook's section on the ledger's copies


def copies_needs(copies: dict[str, Any] | None, development: bool) -> list[tuple[str, str]]:
    """What the ledger's copies need of someone, and when, as the copier records them: the one
    rule the status and `a5s doctor` each judge them by, so neither passes what the other
    pages (round 17, A2)."""
    found: list[tuple[str, str]] = []
    if copies is None:
        if not development:  # which copies nothing to locked storage
            found.append((LATER, ("No copier has run here, so the ledger has no locked copies: "
                                  "run `a5s anchor --every`, as the chart's anchor part does")))
        return found
    if copies["stopped"]:
        return [(NOW, f"The ledger's copies have stopped until someone acts: {copies['problem']}")]
    if copies["problem"]:
        found.append((NOW, f"The copier's last try failed: {copies['problem']}"))
    age = copies.get("copied_seconds_ago")
    if age is not None and age > COPIES_LATE and copies.get("behind"):
        found.append((NOW, (f"The ledger's newest copy is {age / 60:.0f} minutes old, with "
                            f"{copies['behind']} entries waiting to be copied")))
    full = copies.get("checked")
    if full and full["problems"]:
        found.append((NOW, "The copier's check of the whole ledger found: "
                      + "; ".join(full["problems"])))
    elif full and full["seconds_ago"] > CHECK_LATE:
        found.append((LATER, (f"The copier last checked the whole ledger "
                              f"{full['seconds_ago'] / 86400:.0f} days ago")))
    return found


def needs(status: dict[str, Any]) -> list[dict[str, str]]:
    """What in the status needs someone, what pages out of hours first: each `when`, now or
    in working hours, what it is, in a sentence, and the runbook section on what to do."""
    found: list[dict[str, str]] = []

    def need(when: str, said: str, section: str) -> None:
        found.append({"when": when, "said": said, "runbook": f"docs/runbooks.md#{section}"})

    development = bool((status.get("configuration") or {}).get("development"))
    for when, said in copies_needs(status.get("copies"), development):
        need(when, said, COPYING)
    if stuck := status["changes"]["stuck"]:
        need(NOW, f"{stuck} {'change' if stuck == 1 else 'changes'} stopped part way through "
                  "being made: `a5s proposals` lists them", "changes-wait-or-stop-part-way")
    for credential in status.get("expiring") or []:  # expired first, as the soonest
        need(LATER, expiry(credential), "credentials-that-expire")
    if unread := status.get("expires_unread"):  # a note mistyped stops nothing (round 17, A12)
        need(LATER, unread, "credentials-that-expire")
    release = status.get("release") or {}
    if release.get("problems"):
        need(LATER, _sentence("; ".join(release["problems"])) + " So the core opens no run.",
             "settings-or-the-release-dont-check-out")
    if problem := (status.get("settings") or {}).get("problem"):  # as each run finds them (A1)
        need(LATER, _sentence(problem) + " So the core opens no run.",
             "settings-or-the-release-dont-check-out")
    for model in status.get("breakers_open") or []:
        need(LATER, f"{model}'s breaker is open after three failures in a row: a5s tries it "
                    "again every five minutes", "runs-fail-or-a-model-isnt-answering")
    for model in status.get("models_stopped") or []:
        need(LATER, f"{model} is stopped, as it stalled on more than half its calls in a day: "
                    "once its provider answers again, the release approver puts it back with "
                    f"`a5s health --restore {model}`", "runs-fail-or-a-model-isnt-answering")
    heard = status.get("scheduler_seen_seconds")
    if heard is not None and heard > SEEN_LATE:  # it asked once, and has stopped asking
        need(LATER, f"The scheduler last asked the core to record how a5s is doing "
                    f"{heard / 60:.0f} minutes ago, as it does each minute, so it may be away: "
                    "nothing is answered or swept while it is", "messages-are-waiting")
    elif heard is None and not development:  # it never has: its token, or its way here (D5)
        need(LATER, "The scheduler has never asked the core to record how a5s is doing, as it "
                    "does each minute once it runs, so it may not be running, or not reach the "
                    "core with its token: nothing is answered or swept until it does",
             "messages-are-waiting")
    queue = status["queue"]
    if queue["waiting"] and (queue["oldest_seconds"] or 0) > QUEUE_LATE:
        need(LATER, f"{queue['waiting']} messages are waiting, the oldest for "
                    f"{queue['oldest_seconds'] / 60:.0f} minutes", "messages-are-waiting")
    if status.get("seal_keys_leaked"):
        need(LATER, "A5S_SEAL_KEYS holds a key retired as leaked: take it out and restart the "
                    "core, as what it sealed counts until you do", "rotating-the-seal-key")
    if status.get("seals_waiting"):
        need(LATER, "Seals wait under a key A5S_SEAL_KEYS is moving away from: run `a5s "
                    "seal-again` as the core, then drop the old key", "rotating-the-seal-key")
    if unsealed := status.get("unsealed"):
        need(LATER, f"{unsealed} approvals, decisions and grades the gateway hasn't sealed in "
                    "5 minutes, which don't count until it does: see A5S_SEAL_KEYS",
             "changes-wait-or-stop-part-way")
    for inst in status.get("not_active") or []:
        if inst["status"] == "suspended":  # retired, a version of the settings meant
            by = f" by {inst['suspended_by']}" if inst.get("suspended_by") else ""
            need(LATER, f"{inst['id']} is suspended{by}: they resume it on its page, or the "
                        "release approver does", "an-instance-isnt-active")
    if left := status["deliveries"]["left_in_inbox"]:
        need(LATER, f"{left} deliveries a chat didn't take were left in people's local inbox",
             "deliveries-a-chat-didnt-take")
    for spent in status.get("tokens") or []:
        if spent["budget_warnings"]:
            need(LATER, f"{spent['instance']} went past four fifths of its budget",
                 "budgets-run-out")
    if lapsed := status["samples"]["lapsed"]:
        need(LATER, f"{lapsed} samples lapsed ungraded this quarter",
             "samples-wait-to-be-graded-or-a-cap-falls")
    objectives = status["objectives"]
    if objectives["replies"]["met"] is False:
        need(LATER, "Replies are slower than the objective, nine in ten within "
                    f"{objectives['replies']['objective_seconds']}s", "an-objective-is-missed")
    if objectives["chases"]["met"] is False:
        need(LATER, "Fewer chases went out before what's owed fell due than the objective, "
                    f"{objectives['chases']['objective']:.0%}", "an-objective-is-missed")
    if missing := status.get("missing"):
        need(LATER, f"{missing} people the directory no longer names wait to be archived",
             "people-the-directory-no-longer-names")
    sign_ins = status.get("sign_ins")
    if sign_ins and not sign_ins["second_factor"]:
        need(LATER, "Approvals, decisions, grades and the officer's requests aren't checked "
                    "for a second factor: set A5S_OIDC_MFA, such as amr:mfa",
             "sign-ins-refused-for-want-of-a-second-factor")
    return sorted(found, key=lambda n: n["when"] != NOW)  # what pages first, else as listed


def verdict(status: dict[str, Any]) -> str:
    """The status's first line: what needs someone now, and what in working hours."""
    found = status.get("needs")
    if found is None:
        found = needs(status)
    now = sum(n["when"] == NOW for n in found)
    later = len(found) - now
    if not found:
        return "Nothing needs anyone."
    parts = ([f"{now} {'needs' if now == 1 else 'need'} someone now, out of hours too"]
             if now else []) + ([f"{later} can wait for working hours"] if later else [])
    return " and ".join(parts) + "."


def released(release: dict[str, Any] | None) -> str | None:
    """The release a5s is, and whether this deployment approved it, in a line."""
    if not release:
        return None
    named = f"Release {release['version']} of a5s ({release['digest'][:12]})"
    if release.get("approved") is None:
        return f"{named}, run for development, which runs any release."
    return f"{named}, {'approved here' if release['approved'] else 'not approved here'}."


def _sentence(text: str) -> str:
    text = text.strip()
    return (text[:1].upper() + text[1:]).rstrip(".") + "."


def told(status: dict[str, Any]) -> str:
    """The status in words, for the command line: first what needs someone and the release,
    then the last day."""
    found = status.get("needs")
    if found is None:
        found = needs(status)
    head = [f"a5s: {verdict({'needs': found})}"]
    head += [f"  {'Now' if n['when'] == NOW else 'In working hours'}: "  # ids keep their case
             f"{n['said'].rstrip('.')}. ({n['runbook']})" for n in found]
    if line := released(status.get("release")):
        head.append(f"  {line}")
    return "\n".join([*head, "", _day(status)])


def _day(status: dict[str, Any]) -> str:
    """The last day, line by line."""
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
        "  Acting on its own: " + ("; ".join(f"{r['action']} in {r['part']}"
                                          for r in status["samples"]["on_its_own"]) or "nothing")
        + (f"; {status['samples']['caps_lowered']} caps lowered in the last day"
           if status["samples"]["caps_lowered"] else "") + ".",
        *(["  Approvals graded wrong far more than others': " + (
            ", ".join(f"{r['person']}, {r['graded_wrong']} of {r['approved']}"
                      for r in status["samples"]["rubber_stamps"]) or "nobody") + "."]
          if status["samples"]["rubber_stamps"] is not None else []),
        *([(f"  Approvals, decisions and grades the gateway hasn't sealed in 5 minutes: "
            f"{status['unsealed']}, which don't count until it does (see A5S_SEAL_KEYS).")]
          if status.get("unsealed") else []),
        *([("  Sealed with a key A5S_SEAL_KEYS is moving away from: " + "; ".join(
            f"{kind}, {n}" for kind, n in status["seals_waiting"].items()) + ". Run `a5s "
            "seal-again` as the core, then drop the old key (docs/runbooks.md#rotating-the-seal"
            "-key).")] if status.get("seals_waiting") else []),
        *([("  A5S_SEAL_KEYS holds a key retired as leaked: "
            + ", ".join(status["seal_keys_leaked"]) + ". Take it out and restart the core: "
            "what it sealed counts until you do, and `a5s seal-again` won't seal it again "
            "(docs/runbooks.md#rotating-the-seal-key).")]
          if status.get("seal_keys_leaked") else []),
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
        _copies_told(status.get("copies")),
        "  Not active: " + (", ".join(f"{i['id']}, {i['status']}"
                                      + (f" by {i['suspended_by']}" if i["suspended_by"] else "")
                                      for i in status["not_active"]) or "none") + ".",
        "  Breakers open: " + (", ".join(status["breakers_open"]) or "none") + ".",
        *([f"  Models the health gate stopped: {', '.join(status['models_stopped'])}."]
          if status.get("models_stopped") else []),
        *([_configuration_told(status["configuration"])] if status.get("configuration") else []),
    ]
    return "\n".join(lines)


def _copies_told(found: dict[str, Any] | None) -> str:
    """How the ledger's copies stand, as the copier last recorded it (round 15, D8)."""
    if found is None:
        return ("  The ledger's copies: none recorded, as no copier has run here "
                "(A5S_ANCHOR_STORE).")
    if found["stopped"]:
        return (f"  The ledger's copies: stopped, until someone acts: {found['problem']} "
                "(docs/runbooks.md#the-ledgers-copies-stop).")
    age = found["copied_seconds_ago"]
    held = (f"through entry {found['through']}, {found['behind']} entries behind, copied "
            f"{age / 60:.0f} minutes ago" if found["through"] is not None and age is not None
            else "nothing copied yet")
    full = found.get("checked")  # the copier's check of the whole ledger (round 15, E8)
    checked = ("; the whole ledger not checked yet" if not full else
               f"; the whole ledger checked {full['seconds_ago'] / 3600:.0f} hours ago: "
               + ("; ".join(full["problems"]) if full["problems"] else "it checks out"))
    return (f"  The ledger's copies: {held}"
            + (f"; the last try failed: {found['problem']}" if found["problem"] else "")
            + checked + ".")


def _configuration_told(found: dict[str, Any]) -> str:
    """What the core runs with, as its environment sets it: the rest are a5s's defaults."""
    here = ", ".join(f"{k}={v}" for k, v in found["set"].items()) or "nothing"
    return (f"  The core's configuration: {here} set here, and {found['defaults']} settings at "
            "a5s's defaults (`a5s config` in its container lists every one).")


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
