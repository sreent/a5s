"""Departures: what a5s does with what someone said once they leave.

Someone has left when the directory no longer names them. After a day, in case the directory
only missed them for a while, a5s archives their conversations where they are: it puts
everything it keeps for them, their conversations with each agent, their summaries, what it
sent them and what waits for their digest, the chats it wrote to them in, their notes on how
they like to work and their reminders, under a name of its own that no person has. No run
loads any of it again, and nothing more goes to them, even if the directory later gives
someone else the same id or address. Their reminders are cancelled, their notes ended, and
their preferences and what a5s had told them in their reports let go. What they owed follows
the records, to whoever the records system makes their owner.

Nothing is copied anywhere else. The archive goes on retention's usual clock, 12 months after
the last thing said (core/retention.py), and so does the record of whose archive each is, kept
for the data protection officer, such as to answer a request for someone's data. What they said
in a group chat stays in the group's conversation, under the archive's name (core/groups.py).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import psycopg

from a5s.contract import Scenario
from a5s.core import groups, ledger

GRACE = timedelta(days=1)  # how long someone is missing from the directory before a5s archives [TBC]
FORMER = "former:"  # what an archive's name starts with: never a person in the directory

# What a5s keeps for a person, which it archives under the archive's name
KEPT = ("turns", "summaries", "inbound", "outbox", "chats", "digest_items", "digests",
        "urgent_held", "profile_notes", "reminders", "report_fires")
# What only serves the person while they're here, which it lets go
LET_GO = ("preferences", "report_seen", "digest_waits", "urgent_sent")


def sweep(conn: psycopg.Connection, scenario: Scenario, now: datetime) -> list[str]:
    """Archive what a5s keeps for each person the directory has missed for a day, in the
    caller's transaction. Someone back before then is forgotten as missing. Who was archived."""
    found = {r["person"] for r in conn.execute(
        " union ".join(f"select distinct person from {table}" for table in KEPT))}
    gone = sorted(p for p in found if not p.startswith(FORMER) and not groups.of(p)
                  and scenario.person(p) is None)  # a group chat's conversation is nobody's
    conn.execute("delete from departures where archived_at is null and not (person = any(%s))",
                 (gone,))  # back again, or nothing left of them to archive
    for person in gone:
        conn.execute("insert into departures (person, missing_since) values (%s, %s) "
                     "on conflict (person) where archived_at is null do nothing", (person, now))
    due = [r["person"] for r in conn.execute(
        "select person from departures where archived_at is null and missing_since <= %s "
        "order by person", (now - GRACE,))]
    for person in due:
        archive(conn, person, now)
    return due


def archive(conn: psycopg.Connection, person: str, now: datetime) -> str:
    """Archive what a5s keeps for someone who left, under a name of its own. The name."""
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
    conn.execute("update turns set speaker = %s where speaker = %s", (name, person))
    conn.execute("update turns set heard_by = array_replace(heard_by, %s, %s) "
                 "where %s = any(heard_by)", (person, name, person))
    conn.execute("update inbound set members = array_replace(members, %s, %s) "
                 "where %s = any(members)", (person, name, person))
    conn.execute("update departures set archived_at = %s, archived_as = %s where person = %s "
                 "and archived_at is null", (now, name, person))
    ledger.append(conn, {"kind": "admin", "action": "archive", "run": None, "instance": None,
                         "acts_for": [], "decision": "record",
                         "args": {"person": person, "as": name,
                                  "why": "the directory no longer names them"}})
    return name
