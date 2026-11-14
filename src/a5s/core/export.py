"""Exports: what a5s keeps about someone, for their request to see it (docs/data-protection.md).

The data protection officer, signed in with the role, names someone, and gets all a5s keeps
that names them: their conversations with each agent, with what a5s and the agents said to
them there, and the summaries of those; their notes, preferences and reminders; what they
owed; the changes asked for them, and those they could decide or did; samples of those, and
the grades they gave; the questions agents asked each other for them alone; the chats a5s writes to them
in; what reports told them; their use of each day's budget, and their digests.

One holder at a time. When someone leaves, a5s archives what it kept for them under a name of
its own (core/departures.py), and the directory may later give their id to someone else. So
an export by id gives what's its holder's since its last archive, and lists its archives. The
officer exports each archive by its own name, which gives what's under that name, and what a5s
keeps by the id itself, such as the changes asked for them, from before it was archived.

It gives nobody else's words: in a group chat, what they said, and only how much they heard
others say, or were answered there, and of a question asked for others too, only that it was.
It names records by key and title, and changes by what they do, never what records held,
which is the records system's to answer for, nor whom else they were for. Runs and the ledger
keep what was said only by hash, so it counts them. The ledger records each export, by whom
and for whom, in counts.
"""

from __future__ import annotations

from typing import Any

import psycopg

from a5s.core import departures, proposals, topics

FIRST_LINE = "split_part(said, E'\\n', 1)"  # what a change does: the rest is records and people
# What each kind of the ledger's entries is, in words the officer can pass on
LEDGER = {"admin": "what the team that runs a5s and the officer did",
          "inbound": "messages a5s received", "message": "messages agents sent",
          "notice": "notices a5s sent", "run": "runs opened and closed",
          "model": "calls to a model", "tool": "tools agents called",
          "summary": "summaries kept", "proposal": "changes asked for and decided",
          "obligation": "chases and escalations", "reminder": "reminders",
          "schedule": "schedules", "report": "reports", "notebook": "notes kept",
          "budget": "budget warnings", "cap": "caps", "breaker": "models turned off and on",
          "retention": "deletions"}
LEDGER_AT = "(entry::jsonb ->> 'at')::timestamptz"  # when an entry was written


def holder(conn: psycopg.Connection, person: str) -> dict[str, Any]:
    """Whose time an id, or an archive's name, covers: the id, and from when to when it was
    theirs (core/export.py). An archive's runs from the id's archive before it, if any."""
    if person.startswith(departures.FORMER):
        left = conn.execute("select person, archived_at from departures where archived_as = %s",
                            (person,)).fetchone()
        if left is None:
            return {"id": None, "since": None, "until": None, "archives": []}
        before = conn.execute("select max(archived_at) as at from departures where person = %s "
                              "and archived_at < %s", (left["person"], left["archived_at"])
                              ).fetchone()["at"]
        return {"id": left["person"], "since": before, "until": left["archived_at"],
                "archives": []}
    archives = [dict(r) for r in conn.execute(
        "select archived_as as name, missing_since, archived_at from departures "
        "where person = %s and archived_as is not null order by archived_at", (person,))]
    return {"id": person, "since": archives[-1]["archived_at"] if archives else None,
            "until": None, "archives": archives}


def gather(conn: psycopg.Connection, person: str) -> dict[str, Any]:
    """All a5s keeps about one holder of an id, or of an archive's name."""
    whose = holder(conn, person)
    archives, since, until = whose["archives"], whose["since"], whose["until"]
    ids = [whose["id"]] if whose["id"] else []
    params = {"names": [person], "ids": ids, "since": since, "until": until}

    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in conn.execute(sql, params)]

    def count(sql: str) -> int:
        return conn.execute(sql, params).fetchone()["n"]

    def within(column: str) -> str:  # what a5s keeps by the id itself: this holder's time
        return (f"(%(since)s::timestamptz is null or {column} >= %(since)s) "
                f"and (%(until)s::timestamptz is null or {column} < %(until)s)")

    samples = rows(
        f"select id, action, case when acts_for && %(ids)s then {FIRST_LINE} end as said, "
        "decided, grade, drawn_at, graded_at, acts_for && %(ids)s as for_them, "
        "coalesce(decided_by = any(%(ids)s), false) as decided_it, "
        "coalesce(graded_by = any(%(ids)s), false) as graded_it from samples "
        "where (acts_for && %(ids)s or decided_by = any(%(ids)s) or graded_by = any(%(ids)s)) "
        f"and {within('drawn_at')} order by id")
    alone = "acts_for && %(names)s and acts_for <@ %(names)s"  # for them, and nobody else
    return {
        "person": person,
        "archives": archives,
        "conversations": rows(
            "select agent, topic, role, content, at from turns where person = any(%(names)s) "
            "order by at, id"),
        "summaries": [{**r, "body": topics.render(r["body"])} for r in rows(
            "select agent, topic, body, updated_at from summaries "
            "where person = any(%(names)s) order by agent, topic")],
        "said_in_group_chats": rows(
            "select person as chat, agent, content, at from turns where speaker = any(%(names)s) "
            "and person like 'group:%%' order by at, id"),
        "facts_in_group_summaries": rows(  # the keys, amounts and dates they said there,
            "select s.person as chat, s.agent, s.topic, f ->> 'value' as value, "  # as a
            "f ->> 'when' as said_at from summaries s cross join lateral "  # summary keeps them
            "jsonb_array_elements(coalesce(s.body -> 'facts', '[]'::jsonb)) f "
            "where s.person like 'group:%%' and f ->> 'speaker' = any(%(names)s) "
            "order by s.person, s.topic"),
        "corrections_in_group_summaries": rows(  # in their words, as they said them there
            "select s.person as chat, s.agent, s.topic, c ->> 'said' as said, "
            "c ->> 'when' as said_at from summaries s cross join lateral "
            "jsonb_array_elements(coalesce(s.body -> 'corrections', '[]'::jsonb)) c "
            "where s.person like 'group:%%' and c ->> 'speaker' = any(%(names)s) "
            "order by s.person, s.topic"),
        "heard_in_group_chats": {  # others' words, which aren't theirs to have, counted
            "turns": count("select count(*) as n from turns where heard_by && %(names)s "
                           "and not coalesce(speaker = any(%(names)s), false)"),
            "summaries": count("select count(*) as n from summaries "
                               "where heard_by && %(names)s"),
            "answers": count("select count(*) as n from outbox o join inbound i "  # to the group
                             "on i.id = o.inbound_id where o.person = any(%(names)s) "
                             "and i.conversation is not null")},
        "messages_received": rows(
            "select channel, agent, text, received_at, conversation is not null as in_group "
            "from inbound where person = any(%(names)s) order by received_at"),
        "messages_sent": rows(  # in their own conversations: what a group was told is counted
            "select o.channel, o.agent, o.text, o.at, o.delivered_at from outbox o "
            "left join inbound i on i.id = o.inbound_id where o.person = any(%(names)s) "
            "and i.conversation is null order by o.at, o.id"),
        "digest_items": rows(
            "select agent, text, at, digest_due from digest_items where person = any(%(names)s) "
            "order by at, id"),
        "held_urgent": rows(
            "select agent, text, at, sent_at from urgent_held where person = any(%(names)s) "
            "order by at, id"),
        "notes": rows(
            "select agent, text, offered_at, confirmed_at, ended_at from profile_notes "
            "where person = any(%(names)s) order by offered_at, id"),
        "preferences": rows(
            "select name, value, set_at from preferences where person = any(%(names)s) "
            "order by name"),
        "groups": rows(  # those their latest sign-in showed, of the ones the settings name
            "select groups, seen_at from sign_in_groups where person = any(%(names)s)"),
        "drafts": rows(  # the agents they're making in the studio, file by file
            "select agent, based_on, files, published, created_at, updated_at from agent_drafts "
            "where person = any(%(names)s) order by created_at, agent"),
        "reminders": rows(
            "select agent, about, record, due_at, offered_at, confirmed_at, reminded_at, "
            "cancelled_at from reminders where person = any(%(names)s) order by due_at, id"),
        "owed": rows(  # what the id owed in their time, and what they said of it then
            "select record, title, opened_at, due_at, done_at, handed_on, chased_at, "
            f"escalations, case when {within('waiting_noted_at')} then waiting_on end "
            f"as waiting_on, case when {within('waiting_noted_at')} then waiting_until end "
            "as waiting_until from obligations where person = any(%(ids)s) "
            "and (%(until)s::timestamptz is null or owed_since < %(until)s) "
            "and (%(since)s::timestamptz is null or done_at is null or done_at > %(since)s) "
            "order by due_at, id"),
        "changes_for_them": [{"change": proposals.key(r), **{k: v for k, v in r.items()
                                                             if k != "id"}} for r in rows(
            f"select id, action, {FIRST_LINE} as said, status, proposed_at, decided_at, "
            "ended_at from proposals where acts_for && %(ids)s "
            f"and {within('proposed_at')} order by id")],
        "changes_they_could_decide": count(
            "select count(*) as n from proposals where deciders && %(ids)s "
            f"and {within('proposed_at')}"),
        "decisions": [{"change": proposals.key(r), **{k: v for k, v in r.items() if k != "id"}}
                      for r in rows(
            "select p.id, d.decision, d.reason, d.decided_at from proposal_decisions d "
            "join proposals p on p.digest = d.digest where d.person = any(%(ids)s) "
            f"and {within('d.decided_at')} order by d.id")],
        "samples": [{"sample": r["id"], "as": [role for role, held in (
            ("for", r["for_them"]), ("decider", r["decided_it"]), ("grader", r["graded_it"]))
            if held], **{k: r[k] for k in ("action", "said", "decided", "grade", "drawn_at",
                                           "graded_at")}} for r in samples],
        "questions": rows(  # which an archive takes, as it does their conversations
            "select asker, asked, text, answer, asked_at, answered_at, problem from questions "
            f"where {alone} order by asked_at"),
        "questions_with_others": count(
            "select count(*) as n from questions where acts_for && %(names)s "
            "and not (acts_for <@ %(names)s)"),
        "tasks": rows(  # what they asked agents to do over more than one run, in their words,
            "select id::text as id, number, parent::text as parent, instance_id, task, "
            "status, plan, partial, result, answered, last_error, tokens, token_budget, "
            "deadline, created_at, updated_at "
            "from tasks where owner = any(%(names)s) order by created_at, id"),  # as an archive
        "repeats": rows(  # and what they asked to be done again and again, in their words
            "select number, instance_id, task, days, at, status, created_at, updated_at "
            "from task_repeats where owner = any(%(names)s) order by created_at, number"),
        "tasks_for_them_by_others": count(  # takes them; someone else's words are counted
            "select count(*) as n from tasks where audience && %(names)s "
            "and not owner = any(%(names)s)"),
        "chats": rows(
            "select channel, place, agent, started_at, left_at, shared_at from chats "
            "where person = any(%(names)s) order by channel, place"),
        "reports": {  # which of their records each told them of, by key
            "last_told": rows(
                "select instance_id, source, looked_at, "
                "array(select jsonb_object_keys(records) order by 1) as records "
                "from report_seen where person = any(%(names)s) order by instance_id, source"),
            "sent": rows("select instance_id, source, due_at, fired_at, outcome from report_fires "
                         "where person = any(%(names)s) order by due_at")},
        "days": {
            "budget": rows("select instance_id, day, tokens from spend "
                           "where person = any(%(names)s) order by day, instance_id"),
            "digests": rows("select due_at, sent_at, items, channel from digests "
                            "where person = any(%(names)s) order by due_at")},
        "settings": {
            "asked_for": rows("select asked_at, outcome, decided_at from settings_requests "
                              f"where person = any(%(ids)s) and {within('asked_at')} "
                              "order by asked_at"),
            "approved": rows("select digest, approved_at, refused is not null as refused "
                             "from settings_approvals where person = any(%(ids)s) "
                             f"and {within('approved_at')} order by approved_at")},
        "instances_they_run": [r["id"] for r in rows(
            "select id from instances where owner = any(%(names)s) or deputy = any(%(names)s) "
            "order by id")],
        "evidence": {  # what the ledger and runs hold for them: what was said only by hash
            "runs": count("select count(*) as n from runs where acts_for && %(ids)s "
                          f"and {within('opened_at')}"),
            "ledger": {LEDGER.get(r["kind"], r["kind"]): r["n"] for r in rows(
                "select kind, count(*) as n from ledger where (entry::jsonb -> 'acts_for') "
                f"?| %(ids)s and {within(LEDGER_AT)} "
                "group by kind order by kind")}},
    }


def counts(found: dict[str, Any]) -> dict[str, Any]:
    """How much an export held, for the ledger, which keeps none of it."""
    out: dict[str, Any] = {}
    for section, held in found.items():
        if isinstance(held, list):
            out[section] = len(held)
        elif isinstance(held, int) and not isinstance(held, bool):
            out[section] = held
        elif isinstance(held, dict):
            out[section] = {k: len(v) if isinstance(v, list) else v for k, v in held.items()
                            if not isinstance(v, dict)}
    return out


def holds(found: dict[str, Any]) -> bool:
    """Whether an export holds anything at all, or lists an archive that might."""
    def anything(value: Any) -> bool:
        if isinstance(value, list):
            return bool(value)
        if isinstance(value, dict):
            return any(anything(v) for v in value.values())
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    return any(anything(v) for k, v in found.items() if k != "person")
