"""Reports: what an agent tells each person it serves about their own records, worked out by
code.

An agent whose release reports on a kind of record, such as the watcher, tells each
person it serves, once a day in their digest (core/digests.py), what changed in their
records of that kind since it last told them, and what fell due since. The first time,
it tells them what's open. Code
compares the records with what the agent last told them, so the model only puts the
facts into words, and a day with nothing new starts no model at all. What's open and
what fell due come from the obligations the core keeps, so the reports sweep follows the
obligations sweep. The run acts for the person, so it writes to them and to nobody else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import Person, Record
from a5s.core.obligations import day, local

MOST = 20  # facts in one report; the rest are counted [TBC]


def fired(conn: psycopg.Connection, instance: str, person: str, source: str,
          due: datetime) -> bool:
    return conn.execute("select 1 from report_fires where instance_id = %s and person = %s "
                        "and source = %s and due_at = %s",
                        (instance, person, source, due)).fetchone() is not None


def fire(conn: psycopg.Connection, instance: str, person: str, source: str, due: datetime,
         now: datetime, outcome: str, run: str | None = None,
         records: dict[str, Any] | None = None) -> bool:
    """Record that the day's report went, whether it ran or not, with what a run tells them
    about. False if it went already."""
    return conn.execute(
        "insert into report_fires (instance_id, person, source, due_at, fired_at, run_id, outcome, "
        "records) values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing returning 1",
        (instance, person, source, due, now, run, outcome,
         None if records is None else Jsonb(records))).fetchone() is not None


@dataclass(frozen=True)
class News:
    """What to tell someone about their records, worked out by code."""

    facts: list[str]
    first: bool  # the first time the agent tells them about these records
    since: datetime | None  # when it last looked, if it has
    records: dict[str, dict[str, Any]] = field(default_factory=dict)  # theirs now, kept once told


def news(conn: psycopg.Connection, scenario: str, instance: str, person: Person, source: str,
         records: list[Record], now: datetime) -> News:
    """What changed in someone's records of a kind since the agent last told them, and what
    fell due since it last looked: or, the first time, what's open."""
    mine = {r.key: {"title": r.title, "fields": r.fields, "link": r.link}
            for r in records if r.person == person.id and r.source == source}
    seen = conn.execute("select records, looked_at from report_seen where instance_id = %s "
                        "and person = %s and source = %s", (instance, person.id, source)).fetchone()
    owed = conn.execute("select record, title, link, due_at from obligations where scenario = %s "
                        "and person = %s and source = %s and done_at is null order by due_at, record",
                        (scenario, person.id, source)).fetchall()
    facts: list[str] = []
    if seen is None:
        facts = [_open(o, person, now) for o in owed]
    else:
        before = seen["records"]
        facts += [_new(key, mine[key]) for key in sorted(mine.keys() - before.keys())]
        for key in sorted(mine.keys() & before.keys()):
            facts += _changed(key, before[key], mine[key])
        facts += [f"{key}, {before[key]['title']}, is no longer among their records."
                  for key in sorted(before.keys() - mine.keys())]
        facts += [_open(o, person, now) for o in owed if seen["looked_at"] < o["due_at"] <= now]
    if len(facts) > MOST:
        more = len(facts) - MOST
        facts = [*facts[:MOST], f"There are {more} more, so suggest they look through their records."]
    return News(facts, first=seen is None, since=seen["looked_at"] if seen else None, records=mine)


def _link(link: str | None) -> str:
    return f" {link}" if link else ""


def _open(o: dict, person: Person, now: datetime) -> str:
    if o["due_at"] <= now:
        return (f"{o['record']}, {o['title']}, was due on {day(person, o['due_at'])} and is still "
                f"open.{_link(o['link'])}")
    return (f"{o['record']}, {o['title']}, is open, and due by {local(person, o['due_at']):%H:%M} "
            f"on {day(person, o['due_at'])}.{_link(o['link'])}")


def _new(key: str, record: dict) -> str:
    fields = ", ".join(f"{name} {value}" for name, value in record["fields"].items())
    return f"{key}, {record['title']}, is new to them: {fields}.{_link(record['link'])}"


def _changed(key: str, before: dict, now: dict) -> list[str]:
    said = []
    if before["title"] != now["title"]:
        said.append(f"{key} is now called {now['title']}, not {before['title']}.")
    for name in [*now["fields"], *(n for n in before["fields"] if n not in now["fields"])]:
        old, new = before["fields"].get(name), now["fields"].get(name)
        if old == new:
            continue
        if old is None:
            said.append(f"{key}, {now['title']}: its {name} is now {new}.")
        elif new is None:
            said.append(f"{key}, {now['title']}: it no longer has a {name}.")
        else:
            said.append(f"{key}, {now['title']}: its {name} changed from {old} to {new}.")
    return [f"{fact}{_link(now['link'])}" for fact in said]


def task(person: Person, news: News) -> str:
    """The task a5s gives the agent that reports: the facts, worked out from the records."""
    if news.first:
        head = (f"Tell {person.name} where their records stand. It's the first time you're "
                "writing to them about them, so say what you'll do: tell them each working "
                "morning what changed.")
    else:
        head = (f"Tell {person.name} what changed in their records since you last looked, on "
                f"{day(person, news.since)}, and what fell due.")
    close = ("That's everything new: don't add to it. Check a record first if you need to. "
             "Write to them briefly, in one message, and change nothing.")
    return "\n".join([head, *(f"- {fact}" for fact in news.facts), close])


def told(conn: psycopg.Connection, run: str) -> None:
    """The person has the report a run made, sent or waiting in their inbox: remember what it
    told them, as of when it looked, so the next report says only what changed since. A
    report that never reached them is told again, with whatever else changed, next time."""
    row = conn.execute("select instance_id, person, source, records, fired_at from report_fires "
                       "where run_id = %s and records is not null", (run,)).fetchone()
    if row is not None:
        conn.execute(
            "insert into report_seen (instance_id, person, source, records, looked_at) "
            "values (%s, %s, %s, %s, %s) on conflict (instance_id, person, source) do update set "
            "records = excluded.records, looked_at = excluded.looked_at",
            (row["instance_id"], row["person"], row["source"], Jsonb(row["records"]),
             row["fired_at"]))
