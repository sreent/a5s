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

from datetime import timedelta

import psycopg

from a5s.contract import Person
from a5s.core import digests
from a5s.core.coretools import Call, CoreTool, Refused

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
             "keep it with confirm_note.")] if row else []


def offer(call: Call) -> dict:
    person, text = call.person, " ".join(str(call.args["note"]).split())
    if not text:
        raise Refused("say how they like to work, in a sentence or two")
    if len(text) > LONGEST:
        raise Refused(f"keep it to {LONGEST} characters: it's a short note")
    if note(call.conn, person.id) == text:  # such as when a model keeps it in the same breath
        return {"note": text, "status": "it's their note already"}
    if call.conn.execute(  # the same offer, made before: it waits for their yes
            "select 1 from profile_notes where person = %s and agent = %s and text = %s "
            "and confirmed_at is null and ended_at is null and asked_at > %s",
            (person.id, call.run["definition"], text, call.asked_at - CONFIRM_WITHIN)).fetchone():
        return {"note": text, "status": "you offered this already: if they've said yes, keep it "
                                        "with confirm_note"}
    call.conn.execute(
        "insert into profile_notes (person, agent, text, offered_at, offered_run, asked_at) "
        "values (%s, %s, %s, %s, %s, %s)",
        (person.id, call.run["definition"], text, call.now, call.run["run"], call.asked_at))
    return {"note": text, "status": "offered: it's kept only once they say yes, in their next "
                                    "message"}


def confirm(call: Call) -> dict:
    person, asked = call.person, call.asked_at
    row = call.conn.execute(  # offered in answer to an earlier message of theirs, not this one
        "select * from profile_notes where person = %s and agent = %s and confirmed_at is null "
        "and ended_at is null and offered_run <> %s and asked_at < %s and asked_at > %s "
        "order by asked_at desc, id desc limit 1 for update",
        (person.id, call.run["definition"], call.run["run"], asked, asked - CONFIRM_WITHIN),
    ).fetchone()
    if row is None:
        raise Refused("no note is waiting for them to confirm. Offer it first, and keep it once "
                      "they say yes in a later message")
    call.conn.execute("update profile_notes set ended_at = %s where person = %s "
                      "and confirmed_at is not null and ended_at is null", (call.now, person.id))
    call.conn.execute("update profile_notes set confirmed_at = %s, confirmed_run = %s where id = %s",
                      (call.now, call.run["run"], row["id"]))
    return {"note": row["text"], "status": "kept: every agent that works for them sees it"}


def forget(call: Call) -> dict:
    person = call.person
    if not call.conn.execute("update profile_notes set ended_at = %s where person = %s "
                             "and ended_at is null returning id", (call.now, person.id)).fetchall():
        raise Refused("they have no note to forget")
    return {"forgotten": True}


TOOLS = {t.name: t for t in (
    CoreTool("offer_note",
             "Offer to note how the person you're answering likes to work, such as how long or "
             "how formal your answers should be, in a sentence or two. Every agent that works "
             "for them will see it. It's kept only once they say yes in their next message: tell "
             "them what you'll note, and ask them.",
             {"type": "object", "required": ["note"], "properties": {
                 "note": {"type": "string", "description": "The note, as it will be kept"}}},
             offer, text_fields=("note",)),
    CoreTool("confirm_note",
             "Keep the note you last offered the person, once they've said yes to it. It "
             "replaces any note they had.",
             {"type": "object", "properties": {}}, confirm),
    CoreTool("forget_note", "Forget the person's note on how they like to work, when they ask "
                            "you to.", {"type": "object", "properties": {}}, forget),
)}
