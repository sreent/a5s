"""Digests: one message a day for each person, from all the agents together.

What agents write to someone on their own, such as a chase of what falls due, a report
on their records or a reminder for a day, waits for the person's digest. It goes at a
time they choose, the start of their working day unless they say otherwise, on their
working days and in their working hours. The work for it is done just before it goes:
once a person's digest time comes, the agents' runs for them fall due, and the digest
goes once they're done, so nothing in it is stale. What comes up after that waits for
the next one. Answers to people's messages, escalations, and reminders for a particular
time go at once.

A digest with one item is that item, from its agent. One with more is a5s's own message,
with each item under the agent that wrote it. People set their digest's time by asking an
agent whose release lets them, with one of a5s's own tools (core/coretools.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, time

import psycopg

from a5s.contract import Person
from a5s.core.coretools import Call, CoreTool, Refused
from a5s.core.obligations import day, local, working

KINDS = ("obligation", "report", "reminder")  # the runs whose messages wait for a digest
TIME = "digest-time"


def chosen(conn: psycopg.Connection, person: Person) -> str:
    """The time the person's digest goes, such as 09:00, in their own time zone."""
    row = conn.execute("select value from preferences where person = %s and name = %s",
                       (person.id, TIME)).fetchone()
    return row["value"] if row else person.hours[0]


def window(conn: psycopg.Connection, person: Person, now: datetime) -> datetime | None:
    """Today's digest time for someone, once it has come, while they're at work and the
    day's digest hasn't gone. Their agents' work for it falls due then."""
    here = local(person, now)
    at = datetime.combine(here.date(), time.fromisoformat(chosen(conn, person)), tzinfo=here.tzinfo)
    if here.isoweekday() not in person.workdays or here < at or not working(person, now):
        return None
    due = at.astimezone(UTC)
    if conn.execute("select 1 from digests where person = %s and due_at = %s",
                    (person.id, due)).fetchone():
        return None
    return due


def keep(conn: psycopg.Connection, person: str, agent: str | None, instance: str | None,
         run: str | None, text: str, now: datetime) -> None:
    """An item for someone's next digest."""
    conn.execute("insert into digest_items (person, agent, instance_id, run_id, text, at) "
                 "values (%s, %s, %s, %s, %s, %s)", (person, agent, instance, run, text, now))


def waiting(conn: psycopg.Connection, person: str) -> list[dict]:
    return conn.execute("select * from digest_items where person = %s and digest_due is null "
                        "order by id for update", (person,)).fetchall()


def compose(person: Person, items: list[dict], due: datetime) -> str:
    """One message from several agents' items, each under the agent that wrote it."""
    parts = [f"Your day from a5s, {day(person, due)}."]
    for item in items:
        parts.append(f"From the {item['agent']}:\n{item['text']}" if item["agent"]
                     else f"From a5s:\n{item['text']}")
    return "\n\n".join(parts)


def close(conn: psycopg.Connection, person: str, due: datetime, now: datetime, items: list[dict],
          channel: str | None) -> None:
    """The day's digest went, with these items, or with none, which closes the day all the same."""
    conn.execute("insert into digests (person, due_at, sent_at, items, channel) "
                 "values (%s, %s, %s, %s, %s) on conflict do nothing",
                 (person, due, now, len(items), channel))
    if items:
        conn.execute("update digest_items set digest_due = %s where id = any(%s)",
                     (due, [i["id"] for i in items]))


def set_time(call: Call) -> dict:
    """Someone's digest time, as they asked, within their working hours."""
    person, value = call.person, str(call.args["time"])
    try:
        at = time.fromisoformat(value)
    except ValueError:
        raise Refused(f"{value} isn't a time such as 08:30") from None
    start, end = (time.fromisoformat(t) for t in person.hours)
    if not start <= at < end:
        raise Refused(f"{at:%H:%M} is outside their working hours, {person.hours[0]} to "
                      f"{person.hours[1]}")
    call.conn.execute(
        "insert into preferences (person, name, value, set_at, set_run) values (%s, %s, %s, %s, %s) "
        "on conflict (person, name) do update set value = excluded.value, set_at = excluded.set_at, "
        "set_run = excluded.set_run", (person.id, TIME, f"{at:%H:%M}", call.now, call.run["run"]))
    return {"digest time": f"{at:%H:%M}", "time zone": person.timezone}


TOOLS = {t.name: t for t in (
    CoreTool("set_digest_time",
             "Set the time the person's daily digest comes, in their own time zone, when they "
             "ask you to. It gathers what all their agents have for them into one message.",
             {"type": "object", "required": ["time"], "properties": {
                 "time": {"type": "string", "description": "Such as 08:30"}}}, set_time),
)}
