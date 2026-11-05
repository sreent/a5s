"""Profiles: what a run knows of the person it acts for, from a5s's own records.

Each run that acts for one person is given their profile, built by code: their name,
working hours, working days and time zone from the directory, their typed preferences,
such as their digest's time, and a short note, in their own words, on how they like to
work.

An agent whose release lets people set the note offers one with a typed tool, showing it to
them as it will be kept, and a5s keeps it only once they say yes in a later message of their
own, as with a reminder (core/reminders.py). It's theirs alone: only a run answering their
own message can offer, confirm or forget one, and never a run that has read content from
outside. A note they confirm replaces the one before, and every agent that acts for them
sees it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import psycopg

from a5s.contract import Person
from a5s.core import digests
from a5s.core.coretools import Call, CoreTool, Refused, one_to_one

CONFIRM_WITHIN = timedelta(days=1)  # an offer they don't confirm by then lapses [TBC]
LONGEST = 600  # characters: it's a short note
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def note(conn: psycopg.Connection, person: str) -> str | None:
    """How someone likes to work, in their own words, as they last confirmed it."""
    row = conn.execute("select text from profile_notes where person = %s and confirmed_at is not null "
                       "and ended_at is null order by confirmed_at desc limit 1", (person,)).fetchone()
    return row["text"] if row else None


def workdays(person: Person) -> str:
    """Such as Monday to Friday."""
    days = sorted(person.workdays)
    if len(days) > 2 and days == list(range(days[0], days[-1] + 1)):
        return f"{_DAYS[days[0] - 1]} to {_DAYS[days[-1] - 1]}"
    names = [_DAYS[d - 1] for d in days]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def section(conn: psycopg.Connection, person: Person) -> dict:
    """The person's profile, as a run that acts for them is given it."""
    told = [(f"{person.name} works {person.hours[0]} to {person.hours[1]}, {workdays(person)}, "
             f"in {person.timezone} time. Their digest comes at {digests.chosen(conn, person)}.")]
    if kept := note(conn, person.id):
        told.append(f"How they like to work, in their own words: {kept}")
    return {"title": f"Who you're working for: {person.name}", "text": "\n".join(told)}


def waiting(conn: psycopg.Connection, person: Person, agent: str) -> list[str]:
    """The note this agent offered the person, if it waits for their yes, for its context.
    Offers count from when the core received the message, by the database's clock."""
    row = conn.execute("select text from profile_notes where person = %s and agent = %s "
                       "and confirmed_at is null and ended_at is null and asked_at > now() - %s "
                       "order by asked_at desc, id desc limit 1",
                       (person.id, agent, CONFIRM_WITHIN)).fetchone()
    return [(f"A note on how they like to work: \"{row['text']}\". If they say yes to it, "
             "keep it with confirm_note, and don't offer it again.")] if row else []


def _offered_before(call: Call, lock: bool = False) -> dict | None:
    """The note this agent last offered the person in answer to an earlier message of theirs,
    not this one, if it waits for their yes: the one a yes in this message keeps."""
    return call.conn.execute(
        "select * from profile_notes where person = %s and agent = %s and confirmed_at is null "
        "and ended_at is null and offered_run <> %s and asked_at < %s and asked_at > %s "
        f"order by asked_at desc, id desc limit 1{' for update' if lock else ''}",
        (call.person.id, call.run["definition"], call.run["run"], call.asked_at,
         call.asked_at - CONFIRM_WITHIN)).fetchone()


def offer(call: Call) -> dict:
    """Offer a note, to keep once they say yes. Offered again in answer to their yes, as a
    model may do, it points to confirm_note, which keeps what they said yes to."""
    person, text = call.person, " ".join(str(call.args["note"]).split())
    if not text:
        raise Refused("say how they like to work, in a sentence or two")
    if len(text) > LONGEST:
        raise Refused(f"keep it to {LONGEST} characters: it's a short note")
    if note(call.conn, person.id) == text:  # such as when a model keeps it in the same breath
        return {"note": text, "status": "it's their note already"}
    before = _offered_before(call)
    if before is not None and before["text"] == text:
        return {"note": text, "status": "you offered this in answer to their last message, and "
                                        "it waits for their yes: if this message says yes to it, "
                                        "keep it now with confirm_note, and don't offer it again"}
    if call.conn.execute(  # the same offer, made in this answer already
            "select 1 from profile_notes where person = %s and agent = %s and text = %s "
            "and confirmed_at is null and ended_at is null and offered_run = %s",
            (person.id, call.run["definition"], text, call.run["run"])).fetchone():
        return {"note": text, "status": "you've offered this already: it's kept only once they "
                                        "say yes, in their next message"}
    call.conn.execute(
        "insert into profile_notes (person, agent, text, offered_at, offered_run, asked_at) "
        "values (%s, %s, %s, %s, %s, %s)",
        (person.id, call.run["definition"], text, call.now, call.run["run"], call.asked_at))
    if before is not None:
        return {"note": text, "status": (
            f"offered. But you offered \"{before['text']}\" in answer to their last message, and "
            "it waits for their yes. If this message says yes to it, keep it now with "
            "confirm_note, which keeps the one they said yes to, and this offer lapses. If they "
            "asked for a different note, this one is kept only once they say yes to it, in their "
            "next message")}
    return {"note": text, "status": "offered: it's kept only once they say yes, in their next "
                                    "message"}


def confirm(call: Call) -> dict:
    """Keep the note they said yes to, in place of any they had. Any other offer this agent
    made them lapses."""
    person = call.person
    row = _offered_before(call, lock=True)  # offered in answer to an earlier message of theirs
    if row is None:
        raise Refused("no note is waiting for them to confirm. Offer it first, and keep it once "
                      "they say yes in a later message")
    call.conn.execute("update profile_notes set ended_at = %s where person = %s "
                      "and confirmed_at is not null and ended_at is null", (call.now, person.id))
    call.conn.execute("update profile_notes set ended_at = %s where person = %s and agent = %s "
                      "and confirmed_at is null and ended_at is null and id <> %s",
                      (call.now, person.id, call.run["definition"], row["id"]))
    call.conn.execute("update profile_notes set confirmed_at = %s, confirmed_run = %s where id = %s",
                      (call.now, call.run["run"], row["id"]))
    return {"note": row["text"], "status": "kept: every agent that works for them sees it"}


def forget(call: Call) -> dict:
    person = call.person
    if not call.conn.execute("update profile_notes set ended_at = %s, text = '' where person = %s "
                             "and ended_at is null returning id", (call.now, person.id)).fetchall():
        raise Refused("they have no note to forget")
    return {"forgotten": True}


TOOLS = {t.name: t for t in (
    CoreTool("offer_note",
             "Offer to note how the person you're answering likes to work, such as how long or "
             "how formal your answers should be, in a sentence or two. Every agent that works "
             "for them will see it. It's kept only once they say yes in their next message: tell "
             "them what you'll note, and ask them. When they say yes to a note you offered, keep "
             "it with confirm_note instead.",
             {"type": "object", "required": ["note"], "properties": {
                 "note": {"type": "string", "description": "The note, as it will be kept"}}},
             offer, text_fields=("note",)),
    CoreTool("confirm_note",
             "Keep the note you offered the person in an earlier message, once they've said yes "
             "to it: at once, without offering it again. It replaces any note they had.",
             {"type": "object", "properties": {}}, confirm),
    CoreTool("forget_note", "Forget the person's note on how they like to work, when they ask "
                            "you to.", {"type": "object", "properties": {}}, forget),
)}
# One person's own: offered only in their own chat, never a group chat
TOOLS = {n: replace(t, offered=one_to_one) for n, t in TOOLS.items()}
