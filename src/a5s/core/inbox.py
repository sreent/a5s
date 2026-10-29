"""Where people's messages arrive, in the core.

Every channel's messages come here first. The core checks who sent each one,
through the identity provider or the channel's own signed token, and records it.
Only then does the scheduler take it, and a run that answers it acts for the
sender the core recorded. So no service can say a message came from someone
else, and a person's token goes no further than this.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.core import ledger
from a5s.core.identity import IdentityError, UnknownPerson, signed_in
from a5s.core.teams import ONE_TO_ONE, UNKNOWN, Refused

log = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024  # far more than one message needs


class LocalMessage(BaseModel):
    agent: str
    text: str
    person: str | None = None  # in development, without an identity provider, who it's from


def record(conn: Any, *, channel: str, source_id: str, person: str, agent: str, text: str,
           reply_to: dict, identity: str) -> str | None:
    """Record a message whose sender the core checked, and wake the scheduler.

    None if the channel sent it before, so it's answered once.
    """
    inbound = str(uuid.uuid4())
    fresh = conn.execute(
        "insert into inbound (id, channel, source_id, person, agent, text, reply_to) "
        "values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing returning id",
        (inbound, channel, source_id, person, agent, text, Jsonb(reply_to)),
    ).fetchone()
    if fresh is None:
        return None
    ledger.append(conn, {
        "kind": "inbound", "action": channel, "run": None, "instance": None, "acts_for": [person],
        "decision": "allow", "reasons": [],
        "args": {"inbound": inbound, "agent": agent, "identity": identity, "chars": len(text),
                 "sha256": hashlib.sha256(text.encode()).hexdigest()},
    })
    conn.execute("notify a5s_inbound")
    return inbound


def turned_away(conn: Any, channel: str, reason: str, people: list[str], text: str) -> None:
    ledger.append(conn, {"kind": "inbound", "action": channel, "run": None, "instance": None,
                         "acts_for": people, "decision": "deny", "reasons": [reason],
                         "args": {"chars": len(text)}})


def create_app(gw: Any) -> FastAPI:
    """The core's endpoints for channels: the only part of the core people reach."""
    app = FastAPI(title="a5s channels")

    @app.middleware("http")
    async def small(request: Request, call_next: Any) -> Any:
        if request.method == "POST":
            size = request.headers.get("content-length")
            if size is None or not size.isdigit() or int(size) > MAX_BYTES:
                return JSONResponse(status_code=413, content={"detail": "send one message at a time"})
        return await call_next(request)

    # Teams

    def tell_in_teams(reply_to: dict[str, str], text: str) -> None:
        try:
            gw.teams.send(reply_to, text)
        except Exception:
            log.exception("couldn't answer in Teams")

    @app.post("/channels/teams/messages")
    def teams_message(activity: dict[str, Any], background: BackgroundTasks,
                      authorization: str | None = Header(default=None)) -> Response:
        if gw.teams is None:
            raise HTTPException(404, "Teams isn't set up")
        try:
            bot = gw.teams.check(activity, authorization)
        except Refused as exc:  # not recorded: anyone on the internet can send these
            log.warning("refused a message for Teams: %s", exc.reason)
            raise HTTPException(exc.status, exc.reason) from None
        message = gw.teams.message(activity, gw.scenario, bot)
        if message is None:
            return Response(status_code=200)
        people = [message.person] if message.person else []
        with db.transaction(gw.url) as conn:
            if message.person is None:
                turned_away(conn, "teams", f"the directory doesn't know entra:{message.entra_id}",
                            people, message.text)
                background.add_task(tell_in_teams, message.reply_to, UNKNOWN)
            elif not message.personal:
                turned_away(conn, "teams", "a5s talks one to one for now", people, message.text)
                background.add_task(tell_in_teams, message.reply_to, ONE_TO_ONE)
            else:  # Teams' message ids are unique only within a conversation
                source = f"{message.reply_to['conversation']}/{message.reply_to['activity']}"
                record(conn, channel="teams", source_id=source, person=message.person,
                       agent=message.agent, text=message.text, reply_to=message.reply_to,
                       identity="verified by teams")
        return Response(status_code=200)

    # The local channel, for the command line and, later, a web app

    def sender(authorization: str | None, claimed: str | None) -> tuple[str, str]:
        """Who's writing, and how a5s knows."""
        if gw.identity is not None:
            token = (authorization or "").removeprefix("Bearer ").strip()
            if not token:
                raise HTTPException(401, "sign in first: send your token as a bearer token")
            try:
                person = signed_in(gw.identity, gw.scenario, token)
            except UnknownPerson as exc:
                raise HTTPException(403, str(exc)) from None
            except IdentityError as exc:
                raise HTTPException(401, f"your token doesn't check out: {exc}") from None
            if claimed and claimed != person:
                raise HTTPException(403, f"you're signed in as {person}, not {claimed}")
            return person, "verified"
        if not gw.cfg.development:
            raise HTTPException(503, "the local channel needs sign-in: set A5S_OIDC_ISSUER, "
                                     "or A5S_DEVELOPMENT=1 to develop without it")
        if not claimed:
            raise HTTPException(400, "say who the message is from")
        if gw.scenario.person(claimed) is None:
            raise HTTPException(403, "a5s doesn't know who you are")
        return claimed, "unverified (development)"

    @app.post("/channels/local/messages", status_code=202)
    def local_message(body: LocalMessage, authorization: str | None = Header(default=None)) -> dict:
        person, identity = sender(authorization, body.person)
        with db.transaction(gw.url) as conn:
            inbound = record(conn, channel="local", source_id=str(uuid.uuid4()), person=person,
                             agent=body.agent, text=body.text, reply_to={}, identity=identity)
        return {"message": inbound}

    @app.get("/channels/local/messages/{message}")
    def answers(message: str, wait: float = 0, person: str | None = None,
                authorization: str | None = Header(default=None)) -> dict:
        """What a5s has said in answer to a message, waiting up to `wait` seconds for it."""
        who, _ = sender(authorization, person)
        try:
            message = str(uuid.UUID(message))
        except ValueError:
            raise HTTPException(404, "no such message") from None
        deadline = time.monotonic() + min(max(wait, 0), 600)
        while True:
            with db.transaction(gw.url) as conn:
                row = conn.execute("select person from inbound where id = %s and channel = 'local'",
                                   (message,)).fetchone()
                if row is None or row["person"] != who:
                    raise HTTPException(404, "no such message")
                said = conn.execute(
                    "update outbox set delivered_at = coalesce(delivered_at, now()) "
                    "where inbound_id = %s returning id, text", (message,)).fetchall()
            if said or time.monotonic() >= deadline:
                return {"replies": [r["text"] for r in sorted(said, key=lambda r: r["id"])]}
            time.sleep(0.25)

    return app
