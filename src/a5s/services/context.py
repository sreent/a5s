"""Context: each person's conversation with each agent, kept as a5s's own records.

Every run starts fresh and reads the conversation from here, so a conversation
never runs out of room and an upgrade never strands it. The conversation is in
topics, such as one for each case, and the core decides each run's topic
(core/topics.py). A run gets the topic's summary, the conversation's latest
turns, whatever their topic, and in a case, the case's older turns too, each
within its share of the budget the agent's release gives it. Turns that no
longer fit are folded into the summary (services/summaries.py).
"""

from __future__ import annotations

import psycopg

from a5s.core.topics import render
from a5s.services import summaries

GENERAL = "general"
CHARS = 120_000  # a run's budget for its conversation, if it isn't given one: about 30,000 tokens
LATEST = 2 / 3  # in a case, the latest turns' share of the budget; the case's older turns get the rest
FOLD = 0.1  # turns that no longer fit are folded into the summary once they're this share of it


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


def history(
    conn: psycopg.Connection, *, person: str, agent: str, topic: str = GENERAL,
    chars: int = CHARS,
) -> list[dict]:
    """What a run is given of the conversation, oldest first, with when each was and its
    topic: the topic's summary, if it has one, then the conversation's latest turns that fit
    the rest of the budget, or in a case, their share of it, and the case's older turns that
    fit what's left."""
    summary = summaries.load(conn, person, agent, topic)
    told = render(summary["body"]) if summary else ""
    turns = [{"role": t["role"], "content": t["content"], "at": t["at"].isoformat(),
              "topic": t["topic"]} for _, t in sorted(_kept(conn, person, agent, topic,
                                                             chars - len(told)).items())]
    return ([{"role": "summary", "content": told, "at": summary["updated_at"].isoformat(),
              "topic": topic}] if told else []) + turns


def dropped(conn: psycopg.Connection, *, person: str, agent: str, topic: str,
            chars: int) -> tuple[dict | None, list[dict]]:
    """The topic's summary, and its turns that no run is given any more and the summary
    doesn't hold yet, oldest first: what to fold into it."""
    summary = summaries.load(conn, person, agent, topic)
    told = render(summary["body"]) if summary else ""
    shown = [i for i, t in _kept(conn, person, agent, topic, chars - len(told)).items()
             if t["topic"] == topic]
    first = min(shown) if shown else None
    return summary, conn.execute(
        "select id, role, content, at, topic from turns where person = %s and agent = %s "
        "and topic = %s and id > %s and (%s::bigint is null or id < %s) order by id",
        (person, agent, topic, summary["through"] if summary else 0, first, first)).fetchall()


def _kept(conn: psycopg.Connection, person: str, agent: str, topic: str, chars: int) -> dict:
    """The turns that fit, by id: the conversation's latest, and in a case, its older ones."""
    kept, used = _fit(conn.execute(
        "select id, role, content, at, topic from turns where person = %s and agent = %s "
        "order by id desc limit 500", (person, agent)),
        chars if topic == GENERAL else int(chars * LATEST))
    if topic != GENERAL:
        before = min(kept) if kept else None
        older, _ = _fit(conn.execute(
            "select id, role, content, at, topic from turns where person = %s and agent = %s "
            "and topic = %s and (%s::bigint is null or id < %s) order by id desc limit 500",
            (person, agent, topic, before, before)), chars - used, keep_one=False)
        kept |= older
    return kept


def _fit(rows, chars: int, *, keep_one: bool = True) -> tuple[dict, int]:
    """The newest turns that fit, by id, and the characters they take. The newest is kept
    even if it doesn't fit, unless `keep_one` is off."""
    kept, used = {}, 0
    for row in rows:
        if used + len(row["content"]) > chars and (kept or not keep_one):
            break
        used += len(row["content"])
        kept[row["id"]] = row
    return kept, used
