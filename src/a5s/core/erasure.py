"""Erasure: what a5s keeps about someone, erased at their request (docs/data-protection.md).

The data protection officer, signed in with the role, names someone and confirms the id, and
a5s erases what it keeps that names them, as an export gives it (core/export.py): their
conversations with each agent, and what a5s and the agents said to them there, with the
summaries of those; their notes, preferences and reminders; the chats a5s writes to them in,
and what reports told them; their use of each day's budget, and their digests; what they said
in group chats, with the facts a group's summary keeps of it; the questions agents asked each
other for them alone; what they said they were waiting on; and what they owed that the
records no longer owe. If they've left, it erases their archives too, and the record of whose
archive each was. An archive's own name erases that archive alone.

It keeps what's evidence of what agents did, for as long as retention keeps it
(core/retention.py): the ledger, which keeps what was said only by hash, and runs; the changes
agents asked for, their decisions and the samples of them; and what they owe while the records
owe it, which the records system answers for. Where they were in a group chat, a name no
person has, which nothing links back to them, stands in their place, so runs there still know
who heard what. The agents' answers in a group chat are the group's, and stay.

The ledger records each erasure, by whom and for whom, in counts, and nothing it erased.
"""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from a5s.core import departures

# What a5s keeps under a person's name, or their archive's, by table: each erased
UNDER = ("turns", "summaries", "inbound", "outbox", "digest_items", "urgent_held",
         "profile_notes", "reminders", "chats", "report_fires")


def erase(conn: psycopg.Connection, person: str, now: datetime) -> dict[str, int]:
    """Erase what a5s keeps about someone, and their archives, in the caller's transaction.
    How much of each kind went, leaving out the kinds where none did."""
    gone: dict[str, int] = {}

    def delete(kind: str, sql: str, params: tuple) -> None:
        if count := conn.execute(sql, params).rowcount:
            gone[kind] = gone.get(kind, 0) + count

    if person.startswith(departures.FORMER):  # one archive
        names = [person]
        delete("archives", "delete from departures where archived_as = %s", (person,))
    else:  # them, and every archive of theirs, whose record goes too
        names = [r["archived_as"] for r in conn.execute(
            "select archived_as from departures where person = %s and archived_as is not null",
            (person,))]
        delete("archives", "delete from departures where person = %s", (person,))
        for table in departures.LET_GO:  # what served them only while they were here
            delete(table, f"delete from {table} where person = %s", (person,))
        names.append(departures.rename(conn, person, now))  # a name only this links to them
        delete("waiting", "update obligations set waiting_on = null where person = %s "
                          "and waiting_on is not null", (person,))  # in their words
        delete("owed", "delete from obligations where person = %s and done_at is not null",
               (person,))  # what they owe now stays, while the records owe it
    for table in UNDER:
        delete(table, f"delete from {table} where person = any(%s)", (names,))
    delete("said_in_groups", "delete from turns where speaker = any(%s)", (names,))
    delete("questions", "delete from questions where acts_for && %s and acts_for <@ %s",
           (names, names))  # for them alone: one for others too is theirs as well
    for row in conn.execute(  # the facts a group's summary keeps of what they said there
            "select person, agent, topic, body from summaries, jsonb_array_elements("
            "coalesce(body -> 'facts', '[]'::jsonb)) f where f ->> 'speaker' = any(%s) "
            "group by person, agent, topic, body", (names,)).fetchall():
        kept = [f for f in row["body"]["facts"] if f.get("speaker") not in names]
        gone["facts_in_groups"] = gone.get("facts_in_groups", 0) + len(row["body"]["facts"]) \
            - len(kept)
        conn.execute("update summaries set body = %s where person = %s and agent = %s "
                     "and topic = %s", (Jsonb({**row["body"], "facts": kept}), row["person"],
                                        row["agent"], row["topic"]))
    return gone
