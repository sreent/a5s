"""Context: each person's conversation with each agent, kept as a5s's own records.

Every run starts fresh and reads the conversation from here, so a conversation
never runs out of room and an upgrade never strands it.
"""

from __future__ import annotations

import psycopg

GENERAL = "general"
HISTORY_CHARS = 120_000  # the conversation's share of a run's context: about 30,000 tokens [TBC]


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
    conn: psycopg.Connection, *, person: str, agent: str, topic: str = GENERAL,
    max_chars: int = HISTORY_CHARS,
) -> list[dict]:
    """The latest turns of a topic that fit the budget, oldest first, with when each was."""
    kept, used = [], 0
    for row in conn.execute(
        "select role, content, at from turns where person = %s and agent = %s and topic = %s "
        "order by id desc limit 500",
        (person, agent, topic),
    ):
        used += len(row["content"])
        if kept and used > max_chars:
            break
        kept.append({"role": row["role"], "content": row["content"], "at": row["at"].isoformat()})
    return kept[::-1]
