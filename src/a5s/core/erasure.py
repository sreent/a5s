"""Erasure: what a5s keeps about someone, erased at their request (docs/data-protection.md).

The data protection officer asks for it on the core's page (core/officer.py), naming someone,
and a5s erases what it keeps that names them, one holder of an id at a time, as an export gives
it (core/export.py). By an id, it erases what's its holder's since the id's last archive: their
conversations with each agent, and what a5s and the agents said to them there, with the
summaries of those; their notes, preferences and reminders; the chats a5s writes to them in, and
what reports told them; their use of each day's budget, and their digests; what they said in
group chats, with the summaries of the group's that hold any of it, which the group's next run
makes again from what's left; the questions agents asked each other for them alone; what they
said they were waiting on; the tasks they asked for; and what they owed that the records no
longer owe. An archive of the id may be someone else's, who held it before, so it stays, and the
officer erases each of theirs by its name, which erases that archive alone, with what its holder
said they were waiting on and what they owed that's done, and the record of whose archive it
was.

It keeps what's evidence of what agents did, for as long as retention keeps it
(core/retention.py): the ledger, which keeps what was said only by hash, and runs, which name
whom they acted for; the changes agents asked for, their decisions and the samples of them; and
what they owe while the records owe it, which the records system answers for. Where they were
in a group chat, a name no person has stands in their place, so runs there still know who heard
what: only the runs kept as evidence link it back to them. The agents' answers in a group chat
are the group's, and stay. And while someone is still here, the chats a5s writes to them in
stay, so what's for them, such as a card to decide a change, still reaches them.

It waits for nothing: while a run, or a task's slice, is at work for them, which might write
what it read of them after it's gone, it refuses, to be asked again in a minute or two. It holds
them still while it works, as archiving does, and runs about to open for them wait for it
(core/departures.py).

The ledger records each erasure, by whom and for whom, in counts, and nothing it erased.
"""

from __future__ import annotations

from datetime import datetime
from typing import LiteralString

from psycopg.abc import Params
from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import chats, departures, export

# What each kind an erasure counts is, in the words of what a5s keeps (docs/data-protection.md)
WORDS = {
    "turns": "what they and the agents said in their conversations",
    "summaries": "summaries of their conversations",
    "inbound": "messages they sent",
    "outbox": "messages a5s sent them",
    "digest_items": "items waiting for their digest",
    "urgent_held": "urgent messages held for them",
    "profile_notes": "notes on how they work",
    "reminders": "reminders",
    "chats": "chats a5s wrote to them in",
    "report_fires": "reports sent them",
    "preferences": "preferences",
    "report_seen": "what reports told them",
    "digest_waits": "digests that wait for them",
    "urgent_sent": "counts of urgent messages sent them",
    "digests": "their digests",
    "spend": "days of the budget they used",
    "archives": "archives, with the record of whose each was",
    "waiting": "what they said they were waiting on",
    "owed": "what they owed that's done",
    "said_in_groups": "what they said in group chats",
    "group_summaries": "group chats' summaries that held what they said",
    "questions": "questions agents asked each other for them alone",
    "tasks": "tasks they asked for, with what each did",
    "repeats": "tasks they asked to be done again and again",
}


class Busy(Exception):
    """A run is at work for them: it might write what it read of them once they're erased."""


def busy(conn: db.Connection, person: str) -> bool:
    """Whether a run, or a task's slice, is at work for someone now: open, and alive."""
    return conn.execute(
        "select 1 from runs where %(p)s = any(acts_for) and closed_at is null "
        "and expires_at > now() union all select 1 from tasks where (owner = %(p)s or "
        "%(p)s = any(audience)) and status = 'running' and lease_expires_at > now() limit 1",
        {"p": person}).fetchone() is not None


def erase(conn: db.Connection, person: str, now: datetime,
          here: bool = False) -> tuple[dict[str, int], list[str]]:
    """Erase what a5s keeps about one holder of an id, or one archive, in the caller's
    transaction, holding them still: `here` if the directory names them now. How much of each
    kind went, leaving out the kinds where none did, and the archives of the id it left, for
    the officer to erase each by its name if it's theirs. Busy, while a run is at work for them."""
    departures.hold(conn, person)  # first, so it sees an archive made as it waited
    whose = export.holder(conn, person)
    if busy(conn, person):
        raise Busy(person)
    gone: dict[str, int] = {}

    def delete(kind: str, sql: LiteralString, params: Params) -> None:
        if count := conn.execute(sql, params).rowcount:
            gone[kind] = gone.get(kind, 0) + count

    window = ("(%(since)s::timestamptz is null or {at} >= %(since)s) "
              "and (%(until)s::timestamptz is null or {at} < %(until)s)")
    span = {"id": whose["id"], "since": whose["since"], "until": whose["until"]}
    if person.startswith(departures.FORMER):  # one archive, and the record of whose it was
        names = [person]
        delete("archives", "delete from departures where archived_as = %s", (person,))
    else:  # their holder's, since the id's last archive: a name only this links to them
        for table in departures.LET_GO:
            delete(table, f"delete from {table} where person = %s", (person,))
        last = conn.execute(  # where each agent last heard from them, in their own chat
            "select distinct on (agent) agent, channel, reply_to, received_at from inbound "
            "where person = %s and conversation is null and agent is not null "
            "order by agent, received_at desc", (person,)).fetchall()
        if count := departures.unsummarise(conn, [person]):  # what a group's summary held
            gone["group_summaries"] = count  # of theirs, made again from what's left
        names = [departures.rename(conn, person, now)]
        if here:  # where a5s writes to them stays theirs, without a word they said
            conn.execute("update chats set person = %s where person = %s", (person, names[0]))
            for chat in last:
                if where := chats.place(chat["reply_to"] or {}):
                    conn.execute(
                        "insert into chats (channel, place, person, agent, reply_to, started_at) "
                        "values (%s, %s, %s, %s, %s, %s) on conflict (channel, place) do update "
                        "set person = excluded.person, started_at = coalesce(chats.started_at, "
                        "excluded.started_at)", (chat["channel"], where, person, chat["agent"],
                                                 Jsonb(chat["reply_to"]), chat["received_at"]))
    if whose["id"]:
        delete("waiting", "update obligations set waiting_on = null where person = %(id)s and "
               "waiting_on is not null and " + window.format(at="waiting_noted_at"),
               span)  # in their words: what the id owes stays, while the records owe it
        delete("owed", "delete from obligations where person = %(id)s and done_at is not null "
               "and " + window.format(at="owed_since"), span)  # owed only in their time
    for table in departures.KEPT:  # what a5s keeps for someone, as archiving finds it
        delete(table, f"delete from {table} where person = any(%s)", (names,))
    delete("said_in_groups", "delete from turns where speaker = any(%s)", (names,))
    delete("questions", "delete from questions where acts_for && %s and acts_for <@ %s",
           (names, names))  # for them alone: one for others too is theirs as well
    delete("repeats", "delete from task_repeats where owner = any(%s)", (names,))
    delete("tasks", "delete from tasks where owner = any(%s)", (names,))  # and each one's
    # children, which are theirs too
    if count := departures.unsummarise(conn, names):  # what a group's summary held of theirs,
        gone["group_summaries"] = count  # made again from what's left
    return gone, [a["name"] for a in whose["archives"]]
