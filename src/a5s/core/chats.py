"""Conversations with an agent's bot that a person didn't start by writing to it.

Each agent writes to people only as its own bot. When it writes first, such as
with a reminder, the core sends it in the conversation the person last had with
that agent, whoever started it. In Matrix, an agent's bot can start one itself;
in Teams, a person lets an agent's bot write to them by adding its app. Once a
person leaves a conversation, a5s stops writing there until they write again. Once someone
else joins it, it's theirs alone no more, and a5s writes to them first in a new one.
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


def shared(conn: Any, channel: str, person: str, agent: str, reply_to: dict[str, Any]) -> None:
    """Someone else joined a person's own conversation with an agent's bot, so it's theirs
    alone no more: a5s writes to them first in a new one."""
    conn.execute(
        "insert into chats (channel, place, person, agent, reply_to, shared_at) "
        "values (%s, %s, %s, %s, %s, now()) on conflict (channel, place) do update set "
        "shared_at = excluded.shared_at",
        (channel, place(reply_to), person, agent, Jsonb(reply_to)))


def gone(conn: Any, channel: str, reply_to: dict[str, Any], since: datetime) -> str | None:
    """Whether a conversation is gone since the person last wrote in it, or it started: "left",
    if they left it, or "shared", if someone else joined it."""
    row = conn.execute("select left_at, shared_at from chats where channel = %s and place = %s",
                       (channel, place(reply_to))).fetchone()
    if row is None:
        return None
    if row["left_at"] is not None and row["left_at"] >= since:
        return "left"
    if row["shared_at"] is not None and row["shared_at"] >= since:
        return "shared"
    return None
