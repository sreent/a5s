"""Where people's messages arrive, in the core.

Every channel's messages come here first. The core checks who sent each one,
through the identity provider or the channel's own signed token, and records it.
Only then does the scheduler take it, and a run that answers it acts for the
sender the core recorded. So no service can say a message came from someone
else, and a person's token goes no further than this.

The web chat is served from here too: a page where people sign in with their
organisation's identity provider and talk to the agents through the local
channel, as the command line does. So is the page where instance approvers
approve a version of the settings, which the card in their chat opens
(core/approvals.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.contract import parse_settings
from a5s.core import approvals, chats, ledger, matrix, topics
from a5s.core.identity import IdentityError, UnknownPerson, signed_in
from a5s.core.teams import ONE_TO_ONE, UNKNOWN, Refused

log = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024  # far more than one message needs
WEBCHAT = Path(__file__).parent / "webchat"
_PAGE_HEADERS = {  # the page runs only its own script, shows only text, and goes in no frame
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                               "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                               "form-action 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-cache",
}
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8"}


class LocalMessage(BaseModel):
    agent: str
    text: str
    person: str | None = None  # in development, without an identity provider, who it's from


class Approval(BaseModel):
    """What the approval page sends with its sign-in: the salt its nonce was made with."""

    salt: str


class TokenRequest(BaseModel):
    """The web chat's sign-in, passed on to the identity provider."""

    grant_type: str
    code: str | None = None
    code_verifier: str | None = None
    redirect_uri: str | None = None
    refresh_token: str | None = None


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


class Small:
    """Refuses a body bigger than one message needs, before reading any of it. It's plain
    ASGI, so the endpoints still hear when someone has gone."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["method"] in ("POST", "PUT"):
            size = dict(scope["headers"]).get(b"content-length", b"")
            if not size.isdigit() or int(size) > MAX_BYTES:
                refused = JSONResponse(status_code=413, content={"detail": "send one message at a time"})
                await refused(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def waiting(request: Request, wait: float, take: Callable[[], list]) -> list:
    """What `take` finds, waiting up to `wait` seconds for something. Once the person has
    gone, such as by closing the page, it stops, and takes nothing they won't see."""
    deadline = time.monotonic() + min(max(wait, 0), 600)
    while not await request.is_disconnected():
        found = await run_in_threadpool(take)
        if found or time.monotonic() >= deadline:
            return found
        await asyncio.sleep(0.25)
    return []


def turned_away(conn: Any, channel: str, reason: str, people: list[str], text: str) -> None:
    ledger.append(conn, {"kind": "inbound", "action": channel, "run": None, "instance": None,
                         "acts_for": people, "decision": "deny", "reasons": [reason],
                         "args": {"chars": len(text)}})


def webchat(gw: Any) -> bool:
    """The web chat is on where people can sign in to it, or in development."""
    if gw.identity is None:
        return gw.cfg.development
    return bool(gw.cfg.webchat_client_id)


def chats_on(gw: Any) -> list[str]:
    """The chats a deployment has turned on, each by setting its own settings."""
    on = {"the command line": True, "the web chat": webchat(gw), "Teams": gw.teams is not None,
          "Matrix": gw.matrix is not None}
    return [chat for chat, is_on in on.items() if is_on]


def create_app(gw: Any) -> FastAPI:
    """The core's endpoints for channels: the only part of the core people reach."""
    app = FastAPI(title="a5s channels")

    app.add_middleware(Small)
    log.info("people reach a5s through %s", ", ".join(chats_on(gw)))

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
        if (installed := gw.teams.installed(activity, gw.scenario, bot)) is not None:
            person, reply_to, added = installed  # its bot may write to them first, or no more
            with db.transaction(gw.url) as conn:
                (chats.started if added else chats.left)(conn, "teams", person, bot.agent, reply_to)
            return Response(status_code=200)
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

    # Matrix: the homeserver sends what happens in the rooms the agents' bots are in

    def matrix_check(authorization: str | None, access_token: str | None) -> None:
        if gw.matrix is None:
            raise HTTPException(404, "Matrix isn't set up")
        try:
            gw.matrix.check(authorization, access_token)
        except matrix.Refused as exc:  # not recorded: anyone could send these
            log.warning("refused a delivery from Matrix: %s", exc.reason)
            raise HTTPException(exc.status, {"errcode": "M_FORBIDDEN", "error": exc.reason}) from None

    def tell_in_matrix(reply_to: dict[str, str], text: str) -> None:
        try:
            gw.matrix.send(reply_to, text)
        except Exception:
            log.exception("couldn't answer in Matrix")

    @app.put("/channels/matrix/_matrix/app/v1/transactions/{txn}")
    def matrix_transaction(txn: str, body: dict[str, Any], background: BackgroundTasks,
                           authorization: str | None = Header(default=None),
                           access_token: str | None = None) -> dict:
        matrix_check(authorization, access_token)
        agents = sorted(gw.definitions)
        for event in body.get("events") or []:
            try:
                what, detail = gw.matrix.event(event, gw.scenario, agents)
                if what == "join":
                    gw.matrix.join(*detail)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:  # the homeserver sends it all again later
                    raise
                # It sends nothing more until this delivery is taken, so one event it won't
                # let a5s act on, such as an invitation withdrawn before a5s joined, is skipped
                log.warning("skipped a Matrix event the homeserver refused: %s", exc)
                continue
            if what == "turn away":
                reason, people, reply, reply_to = detail
                with db.transaction(gw.url) as conn:
                    turned_away(conn, "matrix", reason, people, "")
                background.add_task(tell_in_matrix, reply_to, reply)
            elif what == "message":
                with db.transaction(gw.url) as conn:  # a resent delivery counts once
                    record(conn, channel="matrix", source_id=event["event_id"], person=detail.person,
                           agent=detail.agent, text=detail.text, reply_to=detail.reply_to,
                           identity="verified by matrix")
            elif what == "left":  # so a5s writes to them elsewhere, and doesn't ask them back
                with db.transaction(gw.url) as conn:
                    chats.left(conn, "matrix", *detail)
        return {}

    @app.get("/channels/matrix/_matrix/app/v1/users/{user}")
    def matrix_user(user: str, authorization: str | None = Header(default=None),
                    access_token: str | None = None) -> JSONResponse:
        """Whether a bot exists, made on demand, such as when someone first invites it."""
        matrix_check(authorization, access_token)
        if gw.matrix.agent_of(user) not in gw.definitions:
            return JSONResponse(status_code=404, content={"errcode": "M_NOT_FOUND"})
        gw.matrix.register(user)
        return JSONResponse({})

    @app.get("/channels/matrix/_matrix/app/v1/rooms/{alias}")
    def matrix_room(alias: str, authorization: str | None = Header(default=None),
                    access_token: str | None = None) -> JSONResponse:
        matrix_check(authorization, access_token)
        return JSONResponse(status_code=404, content={"errcode": "M_NOT_FOUND"})

    @app.post("/channels/matrix/_matrix/app/v1/ping")
    def matrix_ping(authorization: str | None = Header(default=None),
                    access_token: str | None = None) -> dict:
        matrix_check(authorization, access_token)
        return {}

    # The local channel, for the command line and the web chat

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
    async def answers(request: Request, message: str, wait: float = 0, person: str | None = None,
                      authorization: str | None = Header(default=None)) -> dict:
        """What a5s has said in answer to a message, waiting up to `wait` seconds for it."""
        who, _ = await run_in_threadpool(sender, authorization, person)
        try:
            message = str(uuid.UUID(message))
        except ValueError:
            raise HTTPException(404, "no such message") from None

        def take() -> list:
            with db.transaction(gw.url) as conn:
                row = conn.execute("select person from inbound where id = %s and channel = 'local'",
                                   (message,)).fetchone()
                if row is None or row["person"] != who:
                    raise HTTPException(404, "no such message")
                return conn.execute(
                    "update outbox set delivered_at = coalesce(delivered_at, now()) "
                    "where inbound_id = %s returning id, run_id, agent, text, at", (message,)).fetchall()

        said = sorted(await waiting(request, wait, take), key=lambda r: r["id"])
        return {"replies": [r["text"] for r in said],
                "messages": [{"from": r["agent"] if r["run_id"] else "a5s", "text": r["text"],
                              "at": r["at"].isoformat()} for r in said]}

    @app.get("/channels/local/conversation")
    def conversation(agent: str, limit: int = 50, person: str | None = None,
                     authorization: str | None = Header(default=None)) -> dict:
        """A person's latest messages with an agent through this channel, and what came back."""
        who, _ = sender(authorization, person)
        with db.transaction(gw.url) as conn:
            rows = conn.execute(
                """
                select * from (
                  select 'person' as kind, text, received_at as at, null::uuid as run_id, 0 as n
                  from inbound where person = %(who)s and agent = %(agent)s and channel = 'local'
                  union all
                  select 'agent', o.text, o.at, o.run_id, o.id
                  from outbox o where o.person = %(who)s and o.channel = 'local' and o.agent = %(agent)s
                ) said order by at desc, n desc limit %(limit)s
                """, {"who": who, "agent": agent, "limit": min(max(limit, 1), 200)}).fetchall()
        return {"messages": [{"from": "you" if r["kind"] == "person" else agent if r["run_id"] else "a5s",
                              "text": r["text"], "at": r["at"].isoformat()} for r in reversed(rows)]}

    @app.get("/channels/local/summaries")
    def summaries_kept(agent: str, person: str | None = None,
                       authorization: str | None = Header(default=None)) -> dict:
        """What a5s keeps of someone's conversation with an agent beyond what each run is given:
        a summary of each topic, for them to see, and to have an agent correct."""
        who, _ = sender(authorization, person)
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select topic, body, updated_at from summaries where person = %s "
                                "and agent = %s order by updated_at desc", (who, agent)).fetchall()
        return {"summaries": [{"topic": r["topic"], "text": topics.render(r["body"]),
                               "at": r["updated_at"].isoformat()} for r in rows]}

    @app.get("/channels/local/inbox")
    async def inbox(request: Request, wait: float = 0, person: str | None = None,
                    authorization: str | None = Header(default=None)) -> dict:
        """What's been written to someone without answering a message of theirs, such as an
        agent's reminder or a5s's escalation, waiting up to `wait` seconds for something."""
        who, _ = await run_in_threadpool(sender, authorization, person)

        def take() -> list:
            with db.transaction(gw.url) as conn:
                return conn.execute(
                    "update outbox set delivered_at = now() where id in ("
                    "  select id from outbox where person = %s and channel = 'local' "
                    "  and inbound_id is null and delivered_at is null for update skip locked) "
                    "returning id, run_id, instance_id, agent, text, at", (who,)).fetchall()

        return {"messages": [  # a run's message is its agent's; any other is a5s's own
            {"from": r["agent"] if r["run_id"] else "a5s", "about": r["agent"],
             "instance": r["instance_id"], "text": r["text"], "at": r["at"].isoformat()}
            for r in sorted(await waiting(request, wait, take), key=lambda r: r["id"])]}

    # The web chat

    def page(name: str) -> Response:
        if not webchat(gw):
            raise HTTPException(404, "the web chat isn't set up here")
        path = WEBCHAT / name
        return Response(path.read_bytes(), media_type=_TYPES[path.suffix], headers=_PAGE_HEADERS)

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        if not webchat(gw):
            raise HTTPException(404, "the web chat isn't set up here")
        return RedirectResponse("/chat/")

    @app.get("/chat/", include_in_schema=False)
    def chat() -> Response:
        return page("index.html")

    @app.get("/chat/config")
    def chat_config() -> dict:
        """How the page signs people in, and which agents they can talk to."""
        if not webchat(gw):
            raise HTTPException(404, "the web chat isn't set up here")
        signin = None
        if gw.identity is not None and gw.cfg.webchat_client_id:
            try:
                where = gw.identity.endpoints()
            except Exception as exc:  # the provider's down: the page says so, and nothing else
                raise HTTPException(503, "the identity provider can't be reached") from exc
            signin = {"authorization_endpoint": where["authorization_endpoint"],
                      "end_session_endpoint": where.get("end_session_endpoint"),
                      "client_id": gw.cfg.webchat_client_id, "scope": "openid profile"}
        return {"signin": signin, "development": gw.identity is None and gw.cfg.development,
                "agents": sorted(gw.definitions)}

    @app.post("/chat/token")
    def chat_token(body: TokenRequest) -> JSONResponse:
        """The web chat's sign-in, passed on to the identity provider, which checks the code
        and its PKCE verifier. It needs no secret, and the page never calls the provider
        itself, so the provider needn't allow it to."""
        if gw.identity is None or not gw.cfg.webchat_client_id:
            raise HTTPException(404, "the web chat's sign-in isn't set up")
        form = {"grant_type": body.grant_type, "client_id": gw.cfg.webchat_client_id}
        if body.grant_type == "authorization_code" and body.code and body.code_verifier and body.redirect_uri:
            form |= {"code": body.code, "code_verifier": body.code_verifier,
                     "redirect_uri": body.redirect_uri}
        elif body.grant_type == "refresh_token" and body.refresh_token:
            form |= {"refresh_token": body.refresh_token, "scope": "openid profile"}
        else:
            raise HTTPException(400, "send a code and its verifier, or a refresh token")
        return exchange(form, ("id_token", "refresh_token", "expires_in"))

    def exchange(form: dict, kept: tuple[str, ...]) -> JSONResponse:
        """A code or refresh token, passed on to the identity provider, and what it gives back
        that the page may keep: never the provider's access token."""
        try:
            answer = gw.identity.http.post(gw.identity.endpoints()["token_endpoint"], data=form,
                                           timeout=15)
            tokens = answer.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(502, "the identity provider didn't answer") from exc
        return JSONResponse(status_code=answer.status_code if answer.status_code < 500 else 502,
                            content={k: tokens[k] for k in (*kept, "error", "error_description")
                                     if k in tokens})

    @app.get("/chat/{name}", include_in_schema=False)
    def chat_file(name: str) -> Response:
        if name not in ("app.js", "app.css"):
            raise HTTPException(404, "no such file")
        return page(name)

    # Approving settings: the page an approver's card opens, where they decide

    def approving() -> None:
        if problem := gw.approving():
            raise HTTPException(404, problem)

    @app.get("/approve/", include_in_schema=False)
    def approve_page() -> Response:
        approving()
        return page("approve.html")

    @app.get("/approve/approve.js", include_in_schema=False)
    def approve_script() -> Response:
        approving()
        return page("approve.js")

    @app.post("/approve/token")
    def approve_token(body: TokenRequest) -> JSONResponse:
        """The approval page's sign-in, passed on to the identity provider. The page gets the
        signed sign-in alone, with no refresh token to make more like it."""
        approving()
        if body.grant_type != "authorization_code" or not (body.code and body.code_verifier
                                                            and body.redirect_uri):
            raise HTTPException(400, "send a code and its verifier")
        return exchange({"grant_type": "authorization_code", "client_id": gw.cfg.webchat_client_id,
                         "code": body.code, "code_verifier": body.code_verifier,
                         "redirect_uri": body.redirect_uri}, ("id_token",))

    @app.get("/approve/config")
    def approve_config() -> dict:
        """Where the page signs the approver in."""
        approving()
        try:
            where = gw.identity.endpoints()
        except Exception as exc:  # the provider's down: the page says so, and nothing else
            raise HTTPException(503, "the identity provider can't be reached") from exc
        return {"signin": {"authorization_endpoint": where["authorization_endpoint"],
                           "client_id": gw.cfg.webchat_client_id, "scope": "openid profile"}}

    def approver(version: str, body: Approval, authorization: str | None) -> tuple:
        """Who signed in to approve this version, what the provider signed, and the token."""
        approving()
        if not re.fullmatch(r"[0-9a-f]{64}", version):
            raise HTTPException(404, "a5s has no such version of the settings")
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to approve: send your sign-in as a bearer token")
        try:
            person, claims = approvals.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, version, body.salt, time.time())
        except approvals.Refused as exc:
            raise HTTPException(exc.status, exc.reason) from None
        return person, claims, token

    def proposal(conn: Any, version: str) -> tuple[dict, dict | None, str]:
        """A version proposed for approval, the version in force, and where it stands."""
        row = conn.execute("select * from settings_proposals where scenario = %s and digest = %s",
                           (gw.scenario.name, version)).fetchone()
        if row is None:
            raise HTTPException(404, "a5s has no such version of the settings to approve")
        last = approvals.latest(conn, gw.scenario.name)
        if row["outcome"]:
            status = row["outcome"]
        elif last and row["serial"] <= last["serial"]:
            status = "superseded"
        else:
            status = "waiting"
        return row, last, status

    @app.post("/approve/settings/{version}/review")
    def review(version: str, body: Approval, authorization: str | None = Header(default=None)) -> dict:
        """What a version changes from the one in force, as code works it out, for an instance
        approver who signed in to approve it."""
        person, _, _ = approver(version, body, authorization)
        with db.transaction(gw.url) as conn:
            row, last, status = proposal(conn, version)
            approved, _ = approvals.approvers(conn, gw.cfg.seal_keys, gw.scenario.name, version)
        before = parse_settings(bytes(last["raw"])) if last else None
        found = approvals.changes(before, parse_settings(bytes(row["raw"])), gw.definitions,
                                  gw.scenario.person)
        return {"serial": row["serial"], "proposed_at": row["proposed_at"].isoformat(),
                "in_force": last["serial"] if last else None, "changes": found,
                "approved_by": [p.name if (p := gw.scenario.person(a)) else a for a in approved],
                "you": person.name, "you_approved": person.id in approved, "status": status}

    @app.post("/approve/settings/{version}")
    def approve(version: str, body: Approval, authorization: str | None = Header(default=None)) -> dict:
        """An instance approver's approval of a version, signed through the identity provider
        for this version alone. It's recorded once, and sealed. The gateway applies the version."""
        person, claims, token = approver(version, body, authorization)
        with db.transaction(gw.url) as conn:
            row, _, status = proposal(conn, version)
            if status != "waiting":
                raise HTTPException(409, f"this version isn't waiting for approval: it's {status}")
            try:
                approvals.record(conn, gw.cfg.seal_keys, gw.scenario.name, version, person.id, token,
                                 body.salt, claims)
            except approvals.Refused as exc:
                raise HTTPException(exc.status, exc.reason) from None
            ledger.append(conn, {
                "kind": "admin", "action": "approve", "run": None, "instance": None, "acts_for": [],
                "decision": "record",
                "args": {"settings": row["version"], "serial": row["serial"], "digest": version,
                         "by": person.id, "identity": "verified: a sign-in to approve this version alone",
                         "issuer": claims["iss"],
                         "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
        return {"approved": True, "serial": row["serial"], "by": person.name}

    return app
