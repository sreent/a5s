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
    agent: str
    text: str
    person: str | None = None  # without an identity provider, who the message is from


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


def create_app(scheduler: Any, database_url: str, verifier: Any = None) -> Any:
    """The local channel. With an identity provider, people sign in with a token.

    Without one, it trusts who people say they are, so it's for development only.
    """
    from fastapi import FastAPI, Header, HTTPException

    from a5s import db
    from a5s.core.identity import IdentityError

    app = FastAPI(title="a5s local channel")

    def who(claimed: str | None, authorization: str | None) -> tuple[str, str | None]:
        if verifier is None:
            if not claimed:
                raise HTTPException(400, "say who the message is from")
            return claimed, None
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in first: send your token as a bearer token")
        try:
            person = verifier.person(token)
        except IdentityError as exc:
            raise HTTPException(401, f"your token doesn't check out: {exc}") from exc
        if claimed and claimed != person:
            raise HTTPException(403, f"you're signed in as {person}, not {claimed}")
        return person, token

    @app.post("/channels/local/messages")
    def receive(body: Inbound, authorization: str | None = Header(default=None)) -> dict[str, str]:
        person, token = who(body.person, authorization)
        return {"reply": scheduler.handle_message(person=person, agent=body.agent,
                                                  text=body.text, identity=token)}

    @app.get("/channels/local/outbox/{person}")
    def outbox(person: str, authorization: str | None = Header(default=None)) -> list[dict]:
        who(person, authorization)  # only they may collect their messages
        with db.transaction(database_url) as conn:
            return [{"text": m["text"], "at": str(m["at"])} for m in undelivered(conn, person=person)]

    return app
