"""Topics: each person's conversation with an agent, in topics, such as one for each case.

A message that names one of the scenario's records goes in that record's case. One that
names none, or several, stays in the conversation's current topic: the topic of its latest
turn, if that was within the last few hours, or else its general topic. A chase or a
reminder about a record goes in the record's case, and a report in the general topic. The
core decides each run's topic as it opens it, and the context service gives the run the
conversation's latest turns and the topic's older ones (services/context.py).

A run in a case is given a brief of it, built by code from the records: the record as it
stands, and, for the person the run acts for, what a5s keeps about it for them, such as when
it's due, when they were reminded, what they're waiting on, and their reminders about it.
It never says what a5s keeps for anyone else, such as another owner's chases.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import psycopg

from a5s.contract import Person, Scenario
from a5s.core.obligations import day
from a5s.core.reminders import say

log = logging.getLogger(__name__)
GENERAL = "general"
CURRENT = timedelta(hours=4)  # how long a conversation stays on its topic without a word [TBC]
# What a summary run is told: a5s's own words, not a release's. It has no tools, writes to
# nobody, and what it says is checked by code before it's kept (services/summaries.py).
SUMMARY = (
    "You keep a short summary of one topic of a conversation between a person and an agent, "
    "for the agent to read later, when the turns themselves no longer fit. You're given the "
    "summary so far and the turns to fold into it. Reply with JSON alone, in this form: "
    '{"decisions": [...], "commitments": [...], "open_questions": [...]}. Each is a list of '
    "short sentences: what was decided, what the person or the agent promised to do, and what's "
    "still open. Fold in the summary so far, keeping what still holds. Write keys, amounts and "
    "dates exactly as they were written, and never one that wasn't. Don't guess."
)


PARTS = {"decisions": "Decided", "commitments": "Promised", "open_questions": "Still open"}


def render(body: dict) -> str:
    """A topic's summary as a run, or its person, reads it (services/summaries.py)."""
    told = [f"{label}: " + " ".join(body[part]) for part, label in PARTS.items() if body.get(part)]
    if body.get("facts"):
        told.append("Keys, amounts and dates, exactly as said: " + "; ".join(
            f"{f['value']} ({f['who']}, {f['when']})" for f in body["facts"]))
    if body.get("corrections"):
        told.append("Corrections, in their words: " + " ".join(
            f"{c['said']} ({c['when']})" for c in body["corrections"]))
    return "\n".join(told)


def named(scenario: Scenario, text: str) -> list[str]:
    """The records a message names, by their keys, in the order it names them."""
    pattern = getattr(scenario, "record_pattern", None)
    return list(dict.fromkeys(re.findall(pattern, text))) if pattern else []


def of_message(conn: psycopg.Connection, scenario: Scenario, person: str, agent: str,
               text: str) -> str:
    """The topic a message goes in: the one record it names, or else the conversation's
    current topic. Turns are timed by the database's clock."""
    keys = named(scenario, text)
    if len(keys) == 1:
        return keys[0]
    row = conn.execute("select topic from turns where person = %s and agent = %s "
                       "and at > now() - %s order by id desc limit 1",
                       (person, agent, CURRENT)).fetchone()
    return row["topic"] if row else GENERAL


def brief(conn: psycopg.Connection, scenario: Scenario, key: str, person: Person | None,
          now: datetime, unseen: set[str] = frozenset()) -> dict:
    """What the records say about a case, for a run in it, built by code, leaving out the
    fields of a class its model isn't approved for."""
    title = f"The case: {key}, from the records"
    try:
        record = next((r for r in scenario.watched() if r.key == key), None)
    except Exception:  # the scenario's own systems: the run goes on without the brief
        log.exception("couldn't read the records for %s's brief", key)
        return {"title": title, "text": f"The records can't be read right now, so a5s has "
                                        f"nothing on {key}."}
    if record is None:
        return {"title": title, "text": f"The records have no {key}."}
    owner = scenario.person(record.person)
    facts = ", ".join(f"{name} {value}" for name, value in record.fields.items()
                      if name not in unseen)
    told = [f"{key}, {record.title}: {facts}. {owner.name if owner else record.person} owns it."
            + (f" {record.link}" if record.link else "")]
    if person is not None:
        told += _theirs(conn, scenario, key, person, now)
    return {"title": title, "text": "\n".join(told)}


def _theirs(conn: psycopg.Connection, scenario: Scenario, key: str, person: Person,
            now: datetime) -> list[str]:
    """What a5s keeps about a case for one person: what they owe, and their reminders."""
    told = []
    row = conn.execute("select * from obligations where scenario = %s and record = %s "
                       "and person = %s and done_at is null", (scenario.name, key, person.id)).fetchone()
    if row is not None:
        said = [(f"{person.name} owes it, by the end of their working day on "
                 f"{day(person, row['due_at'])}.")]
        if row["chased_at"]:
            said.append(f"a5s reminded them on {day(person, row['chased_at'])}.")
        if row["escalations"]:
            to = scenario.person(row["escalated_to"]) if row["escalated_to"] else None
            said.append(f"It was escalated to {to.name if to else row['escalated_to']} on "
                        f"{day(person, row['escalated_at'])}.")
        if row["waiting_on"] and row["waiting_until"] and row["waiting_until"] > now:
            said.append(f"They're waiting on {row['waiting_on']} until "
                        f"{day(person, row['waiting_until'])}.")
        told.append(" ".join(said))
    for r in conn.execute("select * from reminders where person = %s and record = %s "
                          "and confirmed_at is not null and reminded_at is null "
                          "and cancelled_at is null order by due_at", (person.id, key)):
        told.append(f"Their reminder about it: on {say(person, r['due_at'])}, {r['about']}.")
    return told
