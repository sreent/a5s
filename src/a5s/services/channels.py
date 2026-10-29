"""Channels: how messages reach people.

Agents' messages arrive in the outbox through the gateway. When an agent can't
help, the channel service says so itself, in code, without running a model.
Phase 1 has the local channel. The Teams adapter delivers from the same outbox.
"""

from __future__ import annotations

from typing import Any

import psycopg
from pydantic import BaseModel


class Inbound(BaseModel):
    person: str
    agent: str
    text: str


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


def create_app(scheduler: Any, database_url: str) -> Any:
    """The local channel, for development. Bind it to localhost: it trusts who people say they are."""
    from fastapi import FastAPI

    from a5s import db

    app = FastAPI(title="a5s local channel")

    @app.post("/channels/local/messages")
    def receive(body: Inbound) -> dict[str, str]:
        return {"reply": scheduler.handle_message(person=body.person, agent=body.agent,
                                                  text=body.text)}

    @app.get("/channels/local/outbox/{person}")
    def outbox(person: str) -> list[dict]:
        with db.transaction(database_url) as conn:
            return [{"text": m["text"], "at": str(m["at"])} for m in undelivered(conn, person=person)]

    return app
