"""Departures: what a5s does with what someone said once they leave.

Someone has left when the directory no longer names them. After a day, in case the directory
only missed them for a while, a5s archives their conversations where they are: it puts
everything it keeps for them, their conversations with each agent, their summaries, what it
sent them and what waits for their digest, the chats it wrote to them in, their notes on how
they like to work and their reminders, under a name of its own that no person has. No run
loads any of it again, and nothing more goes to them, even if the directory later gives
someone else the same id or address. Their reminders are cancelled, their notes ended, and
their preferences, what a5s had told them in their reports, their use of each day's budget and
the log of their digests let go. What they owed follows the records, to whoever the records
system makes their owner.

Nothing is copied anywhere else. The archive goes on retention's usual clock, 12 months after
the last thing said (core/retention.py), and the record of whose archive each is, kept for the
data protection officer, such as to answer a request for someone's data (core/export.py), goes
once nothing is left under its name. What they said
in a group chat stays in the group's conversation, under the archive's name (core/groups.py).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import psycopg

from a5s.contract import Scenario
from a5s.core import groups, ledger

GRACE = timedelta(days=1)  # how long someone is missing from the directory before a5s archives [TBC]
# Many missing at once, more than this and more than a third of everyone a5s keeps anything
# for, looks like the directory, not people leaving: they wait a week, should it be mended [TBC]
MANY, MANY_GRACE = 3, timedelta(days=7)
FORMER = "former:"  # what an archive's name starts with: never a person in the directory

# What a5s keeps for a person, which it archives under the archive's name
KEPT = ("turns", "summaries", "inbound", "outbox", "chats", "digest_items", "urgent_held",
        "profile_notes", "reminders", "report_fires")
# What only serves the person while they're here, which it lets go
LET_GO = ("preferences", "report_seen", "digest_waits", "urgent_sent", "digests", "spend")


def sweep(conn: psycopg.Connection, scenario: Scenario, now: datetime) -> list[str]:
    """Archive what a5s keeps for each person the directory has missed for a day, in the
    caller's transaction, or a week, when so many are missing at once that it looks like the
    directory. Someone back before then is forgotten as missing. Who was archived."""
    found = {r["person"] for r in conn.execute(  # what's left of them, even long after they
        " union ".join(f"select distinct person from {table}" for table in KEPT + LET_GO))}
    gone = sorted(p for p in found if p and not p.startswith(FORMER) and not groups.of(p)
                  and scenario.person(p) is None)  # a group chat's conversation is nobody's,
    # and nor is a day's use of the budget by runs that act for nobody
    conn.execute("delete from departures where archived_at is null and not (person = any(%s))",
                 (gone,))  # back again, or nothing left of them to archive
    for person in gone:
        conn.execute("insert into departures (person, missing_since) values (%s, %s) "
                     "on conflict (person) where archived_at is null do nothing", (person, now))
    known = [p for p in found if p and not p.startswith(FORMER) and not groups.of(p)]
    grace = MANY_GRACE if len(gone) > MANY and 3 * len(gone) > len(known) else GRACE
    due = [r["person"] for r in conn.execute(
        "select person from departures where archived_at is null and missing_since <= %s "
        "order by person", (now - grace,))]
    for person in due:
        archive(conn, person, now)
    return due


def hold(conn: psycopg.Connection, person: str, *, shared: bool = False) -> None:
    """Hold what a5s keeps for someone still, until the caller's transaction ends: archiving
    and erasing them each alone, and runs opening for them alongside each other, so neither
    archiving nor erasure works under a run that has just begun for them (core/erasure.py)."""
    took = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    conn.execute(f"select {took}(hashtextextended(%s, 0))", (f"a5s person {person}",))


def archive(conn: psycopg.Connection, person: str, now: datetime) -> str:
    """Archive what a5s keeps for someone who left, under a name of its own. The name, which
    the record of whose archive it is keeps, and the ledger doesn't, so that once the archive
    is erased, nothing a5s keeps of what others said links it back to them."""
    hold(conn, person)
    name = rename(conn, person, now)
    conn.execute("update obligations set waiting_on = null, waiting_until = null, "  # their
                 "waiting_noted_at = null where person = %s and (waiting_on is not null "  # words,
                 "or waiting_until is not null)", (person,))  # never the id's next holder's
    conn.execute("update departures set archived_at = %s, archived_as = %s where person = %s "
                 "and archived_at is null", (now, name, person))
    ledger.append(conn, {"kind": "admin", "action": "archive", "run": None, "instance": None,
                         "acts_for": [], "decision": "record",
                         "args": {"person": person, "why": "the directory no longer names them"}})
    return name


def unsummarise(conn: psycopg.Connection, names: list[str]) -> int:
    """Let go of each group chat's summary that holds anything these said: folded from their
    turns, or kept as their facts or corrections. The group's turns stay, and its next run
    summarises them again, without what's gone. How many went."""
    return conn.execute(
        "delete from summaries s where s.person like 'group:%%' and ("
        "exists (select 1 from turns t where t.person = s.person and t.agent = s.agent "
        "  and t.topic = s.topic and t.speaker = any(%(names)s) and t.id <= s.through) "
        "or exists (select 1 from jsonb_array_elements(coalesce(s.body -> 'facts', '[]')) f "
        "  where f ->> 'speaker' = any(%(names)s)) "
        "or exists (select 1 from jsonb_array_elements(coalesce(s.body -> 'corrections', "
        "  '[]')) c where c ->> 'speaker' = any(%(names)s)))", {"names": names}).rowcount


def rename(conn: psycopg.Connection, person: str, now: datetime) -> str:
    """Put what a5s keeps for someone under a name of its own, which no person has: ending
    what was going on for them, and letting go of what served them only while they were here.
    In group chats, the name stands where they were, so a run there still knows who heard what,
    and the summaries that hold what they said go, to be made again. The name, which only its
    caller links back to them, as the runs kept as evidence of what agents did still name whom
    they acted for (core/erasure.py)."""
    name = f"{FORMER}{secrets.token_hex(8)}"
    conn.execute("update reminders set cancelled_at = %s where person = %s "
                 "and reminded_at is null and cancelled_at is null", (now, person))
    conn.execute("update profile_notes set ended_at = %s where person = %s and ended_at is null",
                 (now, person))
    conn.execute("update inbound set answered_at = %s where person = %s and answered_at is null",
                 (now, person))  # nobody's left to answer
    conn.execute("update outbox set channel = 'local', problem = 'they left before it went' "
                 "where person = %s and delivered_at is null and channel <> 'local'", (person,))
    for table in KEPT:
        conn.execute(f"update {table} set person = %s where person = %s", (name, person))
    for table in LET_GO:
        conn.execute(f"delete from {table} where person = %s", (person,))
    # In group chats: what they said, and that they were there to hear it
    unsummarise(conn, [person])
    conn.execute("update turns set speaker = %s where speaker = %s", (name, person))
    conn.execute("update turns set heard_by = array_replace(heard_by, %s, %s) "
                 "where heard_by @> array[%s]::text[]", (person, name, person))
    conn.execute("update inbound set members = array_replace(members, %s, %s) "
                 "where members @> array[%s]::text[]", (person, name, person))
    conn.execute("update summaries set heard_by = array_replace(heard_by, %s, %s) "
                 "where %s = any(heard_by)", (person, name, person))
    conn.execute("update questions set acts_for = array_replace(acts_for, %s, %s) "  # and what
                 "where %s = any(acts_for)", (person, name, person))  # agents asked for them
    conn.execute("update reminders set heard_by = array_replace(heard_by, %s, %s) "  # and who
                 "where %s = any(heard_by)", (person, name, person))  # heard a reminder offered
    return name
