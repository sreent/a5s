"""Conversations with an agent's bot that a person didn't start by writing to it.

Each agent writes to people only as its own bot. When it writes first, such as
with a reminder, the core sends it in the conversation the person last had with
that agent, whoever started it. In Matrix, an agent's bot can start one itself;
in Teams, a person lets an agent's bot write to them by adding its app. Once a
person leaves a conversation, a5s stops writing there until they write again.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb


def place(reply_to: dict[str, Any]) -> str:
    """The chat's own id for a conversation: a Matrix room, or a Teams conversation."""
    return reply_to.get("room") or reply_to.get("conversation") or ""


def started(conn: Any, channel: str, person: str, agent: str, reply_to: dict[str, Any]) -> None:
    """An agent's bot started a conversation with someone, or they let it in."""
    conn.execute(
        "insert into chats (channel, place, person, agent, reply_to, started_at) "
        "values (%s, %s, %s, %s, %s, now()) on conflict (channel, place) do update set "
        "reply_to = excluded.reply_to, started_at = excluded.started_at, left_at = null",
        (channel, place(reply_to), person, agent, Jsonb(reply_to)))


def left(conn: Any, channel: str, person: str, agent: str, reply_to: dict[str, Any]) -> None:
    """Someone left a conversation with an agent's bot, or took its app away."""
    conn.execute(
        "insert into chats (channel, place, person, agent, reply_to, left_at) "
        "values (%s, %s, %s, %s, %s, now()) on conflict (channel, place) do update set "
        "left_at = excluded.left_at",
        (channel, place(reply_to), person, agent, Jsonb(reply_to)))


def gone(conn: Any, channel: str, reply_to: dict[str, Any], since: datetime) -> bool:
    """Whether the person has left a conversation since they last wrote in it, or it started."""
    return conn.execute("select 1 from chats where channel = %s and place = %s and left_at >= %s",
                        (channel, place(reply_to), since)).fetchone() is not None
