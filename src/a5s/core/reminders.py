"""Reminders: what people ask an agent to remind them of, and what agents promise to follow
up, kept in a5s's own records.

An agent whose release records reminders offers one with a typed tool, and the reminder
counts only once the person confirms it, in a later message of their own. It's theirs
alone: only a run answering their own message can offer or confirm one, and never a run
that has read content from outside. When it falls due, the agent reminds them, in a run
that acts for them: in their digest that day, for a day, or at once, for a particular
time. If the agent can't act, the core reminds them itself, so suspending an agent never
silences what someone asked for.

A person can also say what they're waiting on for one of their records, and until when,
which pauses chases to them about it until then.

These are among a5s's own tools (core/coretools.py).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg

from a5s.contract import Person, record_of
from a5s.core import parts
from a5s.core.coretools import Call, CoreTool, Refused, one_to_one
from a5s.core.obligations import day, local

CONFIRM_WITHIN = timedelta(days=1)  # an offer they don't confirm by then lapses [TBC]
FURTHEST = timedelta(days=366)


def when(given: str, person: Person) -> datetime:
    """A time someone gave, in their own time zone. A date alone means the start of their
    working day."""
    zone = ZoneInfo(person.timezone)
    try:
        if "T" in given:
            at = datetime.fromisoformat(given)
            return at.astimezone(zone) if at.tzinfo else at.replace(tzinfo=zone)
        return datetime.combine(date.fromisoformat(given), time.fromisoformat(person.hours[0]),
                                tzinfo=zone)
    except ValueError:
        raise Refused(f"{given} isn't a date such as 2026-11-06, or a time such as "
                      "2026-11-06T09:00") from None


def say(person: Person, at: datetime) -> str:
    """Such as Fri 6 Nov at 09:00, in the person's time zone."""
    return f"{day(person, at)} at {local(person, at):%H:%M}"


def _number(reminder: str) -> int:
    try:
        return int(str(reminder).removeprefix("R-"))
    except ValueError:
        raise Refused(f"{reminder} isn't a reminder, such as R-12") from None


def offer(call: Call) -> dict:
    person, about, record = call.asker, call.args["about"].strip(), call.args.get("record")
    at = when(str(call.args["on"]), person)
    if not about:
        raise Refused("say what to remind them of")
    if at <= call.now:
        raise Refused(f"{say(person, at)} has passed")
    if at > call.now + FURTHEST:
        raise Refused("a reminder can be a year ahead at most")
    if record and (record_of(call.scenario, record) is None
                   or not parts.workable(call.scenario, call.run, record)):
        raise Refused(f"there's no record {record} that they may see")
    again = call.conn.execute(  # the same reminder, offered before: it waits for their yes,
        # or has it, such as when a model confirms it in the same breath, in parallel
        "select id, confirmed_at from reminders where person = %s and agent = %s and due_at = %s "
        "and record is not distinct from %s and about = %s and cancelled_at is null "
        "and reminded_at is null and (confirmed_at is not null or asked_at > %s) "
        "and conversation is not distinct from %s",
        (person.id, call.run["definition"], at, record, about,
         call.asked_at - CONFIRM_WITHIN, call.conversation)).fetchone()
    if again is not None:
        return {"reminder": f"R-{again['id']}", "when": say(person, at), "about": about,
                "record": record,
                "status": "they've said yes to this already: it's set" if again["confirmed_at"]
                else "you offered this already: if they've said yes, confirm it with confirm_reminder"}
    in_digest = "T" not in str(call.args["on"])  # a day, not a particular time
    number = call.conn.execute(
        "insert into reminders (person, agent, instance_id, about, record, due_at, offered_at, "
        "offered_run, asked_at, in_digest, conversation, heard_by) values (%s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s, %s, %s) returning id",
        (person.id, call.run["definition"], call.run["id"], about, record, at, call.now,
         call.run["run"], call.asked_at, in_digest, call.conversation,
         list(call.run["acts_for"]) if call.conversation else None),
    ).fetchone()["id"]
    return {"reminder": f"R-{number}", "when": say(person, at), "about": about, "record": record,
            "status": (f"offered: it's set only once {person.name} says yes, in a later message "
                       "that mentions you, as you hear only those here: ask them to answer so")
            if call.conversation else
            "offered: it's set only once they say yes, in their next message"}


def waiting_for_yes(conn: psycopg.Connection, person: Person, agent: str,
                    conversation: str | None = None,
                    members: list[str] | None = None) -> list[str]:
    """The reminders this agent offered the person that wait for their yes, for its context:
    in their own chat with it, or those offered in the group chat named, while everyone now in
    it, `members`, heard the offer. Offers count from when the core received the message, by
    the database's clock."""
    rows = conn.execute("select * from reminders where person = %s and agent = %s "
                        "and confirmed_at is null and cancelled_at is null "
                        "and asked_at > now() - %s and conversation is not distinct from %s "
                        "and (%s::text[] is null or heard_by @> %s::text[]) "
                        "order by asked_at, id",
                        (person.id, agent, CONFIRM_WITHIN, conversation, members,
                         members)).fetchall()
    return [f"R-{r['id']}, a reminder on {say(person, r['due_at'])}: {r['about']}. If they say "
            f"yes to it, set it with confirm_reminder, naming R-{r['id']}." for r in rows]


def confirm(call: Call) -> dict:
    """Keep a reminder the person said yes to: the one named, or the one offered last, in
    the chat it was offered in: their own, or the group chat where they asked for it."""
    person, asked = call.asker, call.asked_at
    named = _number(call.args["reminder"]) if call.args.get("reminder") else None
    members = list(call.run["acts_for"]) if call.conversation else None  # in a group, one
    row = call.conn.execute(  # everyone now in it heard offered, in answer to an earlier
        "select * from reminders where person = %s and agent = %s and confirmed_at is null "
        "and cancelled_at is null and offered_run <> %s and asked_at < %s and asked_at > %s "
        "and (%s::bigint is null or id = %s) and conversation is not distinct from %s "
        "and (%s::text[] is null or heard_by @> %s::text[]) "
        "order by asked_at desc, id desc limit 1 for update",  # message of theirs, not this one
        (person.id, call.run["definition"], call.run["run"], asked, asked - CONFIRM_WITHIN,
         named, named, call.conversation, members, members),
    ).fetchone()
    if row is None:
        raise Refused("no reminder is waiting for them to confirm here. Offer it first, and "
                      "confirm it once they say yes in a later message")
    if row["record"] and not parts.workable(call.scenario, call.run, row["record"]):
        raise Refused(f"{row['record']} isn't a record everyone here may see now: confirm it one "
                      "to one")
    call.conn.execute("update reminders set confirmed_at = %s, confirmed_run = %s where id = %s",
                      (call.now, call.run["run"], row["id"]))
    return {"reminder": f"R-{row['id']}", "set for": say(person, row["due_at"]),
            "about": row["about"]}


def upcoming(call: Call) -> dict:
    person = call.person
    rows = call.conn.execute(
        "select * from reminders where person = %s and agent = %s and reminded_at is null "
        "and cancelled_at is null and (confirmed_at is not null or offered_at > %s) "
        "order by due_at", (person.id, call.run["definition"], call.now - CONFIRM_WITHIN)).fetchall()
    return {"reminders": [{"reminder": f"R-{r['id']}", "when": say(person, r["due_at"]),
                           "about": r["about"], "record": r["record"],
                           "confirmed": r["confirmed_at"] is not None} for r in rows]}


def cancel(call: Call) -> dict:
    person = call.person
    row = call.conn.execute(
        "update reminders set cancelled_at = %s where id = %s and person = %s and agent = %s "
        "and reminded_at is null and cancelled_at is null returning id, about",
        (call.now, _number(call.args["reminder"]), person.id, call.run["definition"])).fetchone()
    if row is None:
        raise Refused(f"{call.args['reminder']} isn't one of their upcoming reminders")
    return {"reminder": f"R-{row['id']}", "cancelled": True, "about": row["about"]}


def waiting(call: Call) -> dict:
    person, record, what = call.person, call.args["record"], call.args["waiting_on"].strip()
    until = when(str(call.args["until"]), person)
    if until <= call.now:
        raise Refused(f"{say(person, until)} has passed")
    row = call.conn.execute(
        "update obligations set waiting_on = %s, waiting_until = %s, waiting_noted_at = %s, "
        "updated_at = %s where scenario = %s and person = %s and record = %s and done_at is null "
        "returning record, title",
        (what, until, call.now, call.now, call.scenario.name, person.id, record)).fetchone()
    if row is None:
        raise Refused(f"{record} isn't one of their open records")
    theirs = call.conn.execute(  # their own reminders about it still come, unless they cancel
        "select id, due_at from reminders where person = %s and record = %s and due_at < %s "
        "and reminded_at is null and cancelled_at is null and confirmed_at is not null "
        "order by due_at", (person.id, record, until)).fetchall()
    return {"record": record, "waiting on": what,
            "a5s won't chase them about it until": say(person, until),
            **({"their own reminders about it before then, which still come unless they ask you "
                "to cancel them": [f"R-{r['id']} on {say(person, r['due_at'])}" for r in theirs]}
               if theirs else {})}


_WHEN = {"type": "string", "description": "A date, such as 2026-11-06, for the start of their "
                                          "working day, or a time, such as 2026-11-06T14:00, in "
                                          "their time zone"}

TOOLS = {t.name: t for t in (
    CoreTool("offer_reminder",
             "Offer to remind the person you're answering of something on a day, or to follow it "
             "up then. It's set only once they say yes in their next message: ask them.",
             {"type": "object", "required": ["about", "on"], "properties": {
                 "about": {"type": "string", "description": "What to remind them of, in a sentence"},
                 "on": _WHEN,
                 "record": {"type": "string", "description": "The record it's about, if any"}}},
             offer, text_fields=("about",), sourced=lambda result: result),
    CoreTool("confirm_reminder",
             "Set a reminder you offered the person, once they've said yes to it: the one they "
             "said yes to, or, if you offered only one, that one.",
             {"type": "object", "properties": {
                 "reminder": {"type": "string",
                              "description": "Such as R-12, if you offered more than one"}}},
             confirm, sourced=lambda result: result),
    CoreTool("list_reminders", "The reminders the person has with you that haven't come yet.",
             {"type": "object", "properties": {}}, upcoming, sourced=lambda result: result),
    CoreTool("cancel_reminder", "Cancel one of the person's reminders, when they ask you to.",
             {"type": "object", "required": ["reminder"], "properties": {
                 "reminder": {"type": "string", "description": "Such as R-12"}}}, cancel,
             sourced=lambda result: result),
    CoreTool("note_waiting",
             "Note that the person is waiting on something for one of their records, until a "
             "date. a5s won't chase them about it until then. Reminders they asked for still "
             "come, unless they ask you to cancel them.",
             {"type": "object", "required": ["record", "waiting_on", "until"], "properties": {
                 "record": {"type": "string", "description": "The record's key"},
                 "waiting_on": {"type": "string", "description": "What they're waiting on"},
                 "until": _WHEN}},
             waiting, text_fields=("waiting_on",), sourced=lambda result: result),
)}
# One person's own, offered only in their own chat: a reminder offered in a group
# chat is the asker's alone, there
TOOLS = {n: replace(t, offered=one_to_one) if n in ("list_reminders", "cancel_reminder",
                                                    "note_waiting") else t
         for n, t in TOOLS.items()}


def task(row: dict, person: Person) -> str:
    """The task a5s gives the agent when a reminder falls due."""
    record = (f" It's about {row['record']}: check the record first, and if there's no need any "
              "more, say so in a sentence.") if row["record"] else ""
    return (f"On {day(person, row['confirmed_at'])}, {person.name} agreed you'd remind them now: "
            f"{row['about']}.{record} Write to them briefly, in one message.")


def notice(row: dict, person: Person, status: str) -> str:
    """a5s's own words, when the agent can't remind them itself."""
    return (f"On {day(person, row['confirmed_at'])}, you asked the {row['agent']} to remind you "
            f"now: {row['about']}. The {row['agent']} is {status}, so a5s is reminding you itself.")
