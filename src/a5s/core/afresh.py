"""Starting a conversation afresh (round 15, A4).

Someone says "start afresh" to an agent, as a message of its own, and from then no run of the
conversation is given what came before, nor marked by what a run read from outside before
then: one file, or one look in a mailbox, need not hold every change for a person for as long
as the conversation lasts. The conversation's summaries go, as they hold what came before.
What came before stays on record, as before, for whoever may read it, for as long as retention
keeps it. In a group chat it's the group's conversation that starts afresh, for everyone in it.
"""

from __future__ import annotations

from a5s import db
from a5s.core import ledger

ASKED = ("start afresh", "/afresh", "เริ่มใหม่")  # a message of its own, and nothing else
SAID = ("Started afresh: the {agent} won't read what came before in this chat, though a5s "
        "keeps it on record as before.")


def asked(text: str) -> bool:
    """Whether a message asks to start the conversation afresh."""
    return " ".join(text.split()).strip(".!").casefold() in ASKED


def start(conn: db.Connection, conversation: str, agent: str, instance: str,
          acts_for: list[str]) -> int:
    """Start a conversation afresh, in the caller's transaction: its last turn before it."""
    found = conn.execute("select coalesce(max(id), 0) as last from turns where person = %s "
                         "and agent = %s", (conversation, agent)).fetchone()
    through = found["last"] if found else 0
    conn.execute("insert into fresh_starts (person, agent, through) values (%s, %s, %s) "
                 "on conflict (person, agent) do update set through = excluded.through, "
                 "at = now()", (conversation, agent, through))
    conn.execute("delete from summaries where person = %s and agent = %s", (conversation, agent))
    ledger.append(conn, {"kind": "conversation", "action": "afresh", "run": None,
                         "instance": instance, "acts_for": acts_for, "decision": "record",
                         "args": {"through": through}})
    return through
