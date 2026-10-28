"""Context: each person's conversation with each agent, kept as a5s's own records.

Every run starts fresh and reads the conversation from here, so a conversation
never runs out of room and an upgrade never strands it.
"""

from __future__ import annotations

import psycopg

GENERAL = "general"


def add_turn(
    conn: psycopg.Connection,
    *,
    person: str,
    agent: str,
    role: str,
    content: str,
    run: str | None = None,
    topic: str = GENERAL,
) -> None:
    conn.execute(
        "insert into turns (person, agent, topic, role, content, run_id) "
        "values (%s, %s, %s, %s, %s, %s)",
        (person, agent, topic, role, content, run),
    )


def recent(
    conn: psycopg.Connection, *, person: str, agent: str, topic: str = GENERAL, limit: int = 30
) -> list[dict]:
    """The last turns of a topic, oldest first."""
    rows = conn.execute(
        "select role, content from (select id, role, content from turns "
        "where person = %s and agent = %s and topic = %s order by id desc limit %s) t "
        "order by id",
        (person, agent, topic, limit),
    ).fetchall()
    return list(rows)
