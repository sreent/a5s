"""Channels: how messages reach people.

Agents' messages arrive in the outbox through the gateway. When an agent can't
help, the channel service says so itself, in code, without running a model.
Phase 1 has the local channel. The Teams adapter delivers from the same outbox.
"""

from __future__ import annotations

import psycopg


def say(conn: psycopg.Connection, *, person: str, text: str, channel: str = "local",
        instance: str | None = None) -> str:
    conn.execute(
        "insert into outbox (instance_id, person, channel, text) values (%s, %s, %s, %s)",
        (instance, person, channel, text),
    )
    return text


def undelivered(conn: psycopg.Connection, *, person: str, channel: str = "local") -> list[dict]:
    rows = conn.execute(
        "update outbox set delivered_at = now() where person = %s and channel = %s "
        "and delivered_at is null returning id, text, at",
        (person, channel),
    ).fetchall()
    return sorted(rows, key=lambda r: r["id"])
