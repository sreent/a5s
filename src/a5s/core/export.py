"""Exports: what a5s keeps about someone, for their request to see it (docs/data-protection.md).

The data protection officer, signed in with the role, names someone by their id, and gets all
a5s keeps that names them: their conversations with each agent, with what a5s and the agents
said to them, and the summaries of those; their notes, preferences and reminders; what they
owed; the changes asked for them, and those they decided; samples of those, and the grades
they gave; the questions agents asked each other for them; the chats a5s writes to them in;
their use of each day's budget, and their digests. If they've left, it gathers their archive
too, by the record of whose archive is which (core/departures.py).

It gives nobody else's words: in a group chat, what they said, and only how much they heard
others say. It names records by key and title, never what they hold, which is the records
system's to answer for. Runs and the ledger keep what was said only by hash, so it counts
them. The ledger records each export, by whom and for whom, in counts.
"""

from __future__ import annotations

from typing import Any

import psycopg

from a5s.core import proposals, topics


def gather(conn: psycopg.Connection, person: str) -> dict[str, Any]:
    """All a5s keeps about someone, under their id and any archive of theirs."""
    archives = conn.execute(
        "select archived_as, missing_since, archived_at from departures where person = %s "
        "and archived_as is not null order by archived_at", (person,)).fetchall()
    names = [person, *(a["archived_as"] for a in archives)]

    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in conn.execute(sql, {"names": names})]

    def count(sql: str) -> int:
        return conn.execute(sql, {"names": names}).fetchone()["n"]

    samples = rows(
        "select id, action, said, decided, grade, drawn_at, graded_at, "
        "acts_for && %(names)s as for_them, decided_by = any(%(names)s) as decided_it, "
        "graded_by = any(%(names)s) as graded_it from samples where acts_for && %(names)s "
        "or decided_by = any(%(names)s) or graded_by = any(%(names)s) order by id")
    return {
        "person": person,
        "archives": [{"name": a["archived_as"], "missing_since": a["missing_since"],
                      "archived_at": a["archived_at"]} for a in archives],
        "conversations": rows(
            "select agent, topic, role, content, at from turns where person = any(%(names)s) "
            "order by at, id"),
        "summaries": [{**r, "body": topics.render(r["body"])} for r in rows(
            "select agent, topic, body, updated_at from summaries "
            "where person = any(%(names)s) order by agent, topic")],
        "said_in_group_chats": rows(
            "select person as chat, agent, content, at from turns where speaker = any(%(names)s) "
            "and person like 'group:%%' order by at, id"),
        "heard_in_group_chats": {  # others' words, which aren't theirs to have, counted
            "turns": count("select count(*) as n from turns where heard_by && %(names)s "
                           "and not coalesce(speaker = any(%(names)s), false)"),
            "summaries": count("select count(*) as n from summaries "
                               "where heard_by && %(names)s")},
        "messages_received": rows(
            "select channel, agent, text, received_at, conversation is not null as in_group "
            "from inbound where person = any(%(names)s) order by received_at"),
        "messages_sent": rows(
            "select channel, agent, text, at, delivered_at from outbox "
            "where person = any(%(names)s) order by at, id"),
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
        "reminders": rows(
            "select agent, about, record, due_at, offered_at, confirmed_at, reminded_at, "
            "cancelled_at from reminders where person = any(%(names)s) order by due_at, id"),
        "owed": rows(
            "select record, title, opened_at, due_at, done_at, chased_at, escalations, "
            "waiting_on, waiting_until from obligations where person = any(%(names)s) "
            "order by due_at, id"),
        "changes_for_them": [{"change": proposals.key(r), **{k: v for k, v in r.items()
                                                             if k != "id"}} for r in rows(
            "select id, action, said, status, proposed_at, decided_at, ended_at, outcome "
            "from proposals where acts_for && %(names)s order by id")],
        "decisions": [{"change": proposals.key(r), **{k: v for k, v in r.items() if k != "id"}}
                      for r in rows(
            "select p.id, d.decision, d.reason, d.decided_at from proposal_decisions d "
            "join proposals p on p.digest = d.digest where d.person = any(%(names)s) "
            "order by d.id")],
        "samples": [{"sample": r["id"], "as": [role for role, held in (
            ("for", r["for_them"]), ("decider", r["decided_it"]), ("grader", r["graded_it"]))
            if held], **{k: r[k] for k in ("action", "said", "decided", "grade", "drawn_at",
                                           "graded_at")}} for r in samples],
        "questions": rows(
            "select asker, asked, text, answer, asked_at, answered_at, problem from questions "
            "where acts_for && %(names)s order by asked_at"),
        "chats": rows(
            "select channel, place, agent, started_at, left_at, shared_at from chats "
            "where person = any(%(names)s) order by channel, place"),
        "reports": rows(  # which of their records each told them of, by key
            "select instance_id, source, looked_at, "
            "array(select jsonb_object_keys(records) order by 1) as records "
            "from report_seen where person = any(%(names)s) order by instance_id, source"),
        "days": {
            "budget": rows("select instance_id, day, tokens from spend "
                           "where person = any(%(names)s) order by day, instance_id"),
            "digests": rows("select due_at, sent_at, items, channel from digests "
                            "where person = any(%(names)s) order by due_at")},
        "settings": {
            "asked_for": rows("select asked_at, outcome, decided_at from settings_requests "
                              "where person = any(%(names)s) order by asked_at"),
            "approved": rows("select digest, approved_at from settings_approvals "
                             "where person = any(%(names)s) and refused is null "
                             "order by approved_at")},
        "instances_they_run": [r["id"] for r in rows(
            "select id from instances where owner = any(%(names)s) or deputy = any(%(names)s) "
            "order by id")],
        "evidence": {  # what the ledger and runs hold for them: what was said only by hash
            "runs": count("select count(*) as n from runs where acts_for && %(names)s"),
            "ledger": {r["kind"]: r["n"] for r in rows(
                "select kind, count(*) as n from ledger "
                "where (entry::jsonb -> 'acts_for') ?| %(names)s group by kind order by kind")}},
    }


def counts(found: dict[str, Any]) -> dict[str, Any]:
    """How much an export held, for the ledger, which keeps none of it."""
    out: dict[str, Any] = {}
    for section, held in found.items():
        if isinstance(held, list):
            out[section] = len(held)
        elif isinstance(held, dict):
            out[section] = {k: len(v) if isinstance(v, list) else v for k, v in held.items()
                            if not isinstance(v, dict)}
    return out
