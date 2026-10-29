"""Obligations: what people owe, worked out by code from the scenario's records.

There's one for each record and person, naming the instance that acts on it:
one whose release chases that kind of obligation and that serves the person.
Once half the time allowed has passed, that instance reminds the person, in a
run that acts for them. If it's still open when due, the core escalates it
itself, along the person's reporting line, in each recipient's working hours,
and no sooner than a working day after the reminder or the last escalation. It
escalates whether or not an agent can act, so suspending or withdrawing an
agent never silences what's owed. A person who says they're waiting on something
until a date hears no reminder about it until then, and an escalation says why.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from a5s.contract import Obligation, Person, Scenario
from a5s.definitions import Definition

LOCK = 0x0A5_0B16  # one sweep at a time


def local(person: Person, at: datetime) -> datetime:
    return at.astimezone(ZoneInfo(person.timezone))


def _minutes(hhmm: str) -> int:
    hours, _, minutes = hhmm.partition(":")
    return int(hours) * 60 + int(minutes or 0)


def working(person: Person, at: datetime) -> bool:
    """Whether it's within the person's working hours."""
    here = local(person, at)
    start, end = (_minutes(t) for t in person.hours)
    return here.isoweekday() in person.workdays and start <= here.hour * 60 + here.minute < end


def a_working_day_after(person: Person, at: datetime) -> datetime:
    """The same time on the person's next working day."""
    here = local(person, at) + timedelta(days=1)
    for _ in range(6):
        if here.isoweekday() in person.workdays:
            break
        here += timedelta(days=1)
    return here


def day(person: Person, at: datetime) -> str:
    """Such as Mon 2 Nov, in the person's time zone."""
    here = local(person, at)
    return f"{here:%a} {here.day} {here:%b}"


def halfway(row: dict) -> datetime:
    return row["opened_at"] + (row["due_at"] - row["opened_at"]) / 2


def chain(scenario: Scenario, person: str) -> list[Person]:
    """The person's reporting line, nearest first, leaving out anyone a5s may not write to."""
    line: list[Person] = []
    seen = {person}
    current = scenario.person(person)
    while current and current.manager and current.manager not in seen:
        seen.add(current.manager)
        current = scenario.person(current.manager)
        if current and current.in_audience:
            line.append(current)
    return line


def sync(conn: psycopg.Connection, scenario: str, owed: list[Obligation],
         definitions: dict[str, Definition], now: datetime) -> None:
    """Bring the obligations in line with what the records owe now, each naming the
    instance that acts on it.

    A new due date, or a record that's open again, is owed afresh. One the
    records no longer give is done.
    """
    instances = conn.execute("select id, definition, serves from instances "
                             "where status <> 'retired' order by (status = 'active') desc, id").fetchall()

    def acting(source: str, person: str) -> str | None:
        for inst in instances:
            definition = definitions.get(inst["definition"])
            if definition and source in definition.obligations and person in inst["serves"]:
                return inst["id"]
        return None

    afresh = "(obligations.due_at <> excluded.due_at or obligations.done_at is not null)"
    for o in owed:
        conn.execute(
            f"""
            insert into obligations (scenario, source, record, person, title, link, opened_at,
                                     due_at, instance_id, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (scenario, source, record, person) do update set
              title = excluded.title, link = excluded.link, opened_at = excluded.opened_at,
              instance_id = excluded.instance_id, updated_at = excluded.updated_at,
              chased_at = case when {afresh} then null else obligations.chased_at end,
              escalations = case when {afresh} then 0 else obligations.escalations end,
              escalated_at = case when {afresh} then null else obligations.escalated_at end,
              escalated_to = case when {afresh} then null else obligations.escalated_to end,
              due_at = excluded.due_at, done_at = null
            """,
            (scenario, o.source, o.record, o.person, o.title, o.link, o.opened, o.due,
             acting(o.source, o.person), now),
        )
    conn.execute(
        "update obligations set done_at = %s, updated_at = %s "
        "where scenario = %s and done_at is null and not (source || '/' || record || '/' || person = any(%s))",
        (now, now, scenario, [f"{o.source}/{o.record}/{o.person}" for o in owed]),
    )


def to_escalate(row: dict, scenario: Scenario, now: datetime, can_act: bool) -> Person | None:
    """Whom to escalate an obligation to now, if anyone.

    Once due, it goes one step up the person's reporting line at a time, each
    in that person's working hours, and no sooner than a working day after the
    reminder or the step before. If its agent can still remind the person first,
    it waits for that, but no longer than a working day after the due time.
    """
    person = scenario.person(row["person"])
    if row["done_at"] or now < row["due_at"] or person is None:
        return None
    line = chain(scenario, row["person"])
    if row["escalations"] >= len(line):
        return None  # the top of the line has heard
    if row["escalations"]:
        last = scenario.person(row["escalated_to"]) or person
        if now < a_working_day_after(last, row["escalated_at"]):
            return None
    elif row["chased_at"]:
        if now < a_working_day_after(person, row["chased_at"]):
            return None
    elif can_act and now < a_working_day_after(person, row["due_at"]):
        return None
    recipient = line[row["escalations"]]
    return recipient if working(recipient, now) else None


def escalation(row: dict, scenario: Scenario, recipient: Person, inst: dict | None) -> str:
    """a5s's own words to the next person up the line, from the records."""
    person = scenario.person(row["person"])
    said = [(f"{row['record']}, {row['title']}, was due on {day(recipient, row['due_at'])} "
             "and is still open."), f"It's {person.name if person else row['person']}'s."]
    if row.get("waiting_on") and row.get("waiting_noted_at"):
        said.append(f"On {day(recipient, row['waiting_noted_at'])}, they said they were waiting on "
                    f"{row['waiting_on']} until {day(recipient, row['waiting_until'])}.")
    if row["chased_at"]:
        said.append(f"The {inst['definition'] if inst else 'agent'} reminded them on "
                    f"{day(recipient, row['chased_at'])}.")
    elif inst is None:
        said.append("No agent works on it for them, so nobody reminded them first.")
    else:
        why = f", because it's {inst['status']}" if inst["status"] != "active" else ""
        said.append(f"The {inst['definition']} couldn't remind them first{why}.")
    if row["escalations"] and (previous := scenario.person(row["escalated_to"])):
        said.append(f"{previous.name} heard on {day(recipient, row['escalated_at'])}.")
    said.append("You're next in their reporting line, so a5s is letting you know.")
    if row["link"]:
        said.append(row["link"])
    return " ".join(said)


def chase(row: dict, person: Person) -> str:
    """The task a5s gives the agent that reminds someone: worked out from the records."""
    due = local(person, row["due_at"])
    link = f" The record is at {row['link']}." if row["link"] else ""
    return (f"Remind {person.name} that {row['record']}, {row['title']}, is due by "
            f"{due:%H:%M} on {day(person, row['due_at'])} and is still open. Check the record "
            f"first, and offer to help with it. Write to them briefly, in one message.{link}")


def to_chase(rows: list[dict[str, Any]], scenario: Scenario, now: datetime,
             able: dict[str, bool], digest_open: Callable[[Person], bool]) -> list[dict]:
    """The obligations whose agents should remind their people now: half their time has
    passed, nobody has reminded them or escalated them yet, they aren't waiting on something
    until later, and their digest's time has come today, so the reminder goes in it fresh."""
    due = []
    for row in rows:
        person = scenario.person(row["person"])
        waiting = row.get("waiting_until") is not None and now < row["waiting_until"]
        if (person and able.get(row["instance_id"]) and row["chased_at"] is None and not waiting
                and not row["escalations"] and now >= halfway(row) and digest_open(person)):
            due.append({"kind": "obligation", "obligation": row["id"], "instance": row["instance_id"],
                        "agent": row["agent"], "person": row["person"]})
    return due
