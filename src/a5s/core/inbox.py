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
(core/approvals.py), and the settings app, where they review the whole version in
force and ask for a new one, which the gateway then proposes to everyone it needs.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.contract import (
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    Person,
    Settings,
    parse_settings,
)
from a5s.core import (
    approvals,
    chats,
    groups,
    ledger,
    matrix,
    notebook,
    officer,
    proposals,
    registry,
    samples,
    studio,
    tasking,
    topics,
)
from a5s.core.gateway import sanitize
from a5s.core.identity import IdentityError, UnknownPerson, signed_in
from a5s.core.releases import agent_owner
from a5s.core.tasks import TaskError
from a5s.core.teams import UNKNOWN, Refused

log = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024  # far more than one message needs
TRIES = 3  # deliveries of a Matrix event a5s can't act on before it's skipped, and recorded
REQUESTS_A_DAY = 5  # versions one person may ask for in the settings app [TBC]
MAX_SETTINGS = 64 * 1024  # characters of settings, as written
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


class Asking(BaseModel):
    """What the officer's page sends with its sign-in: what it's to do, for whom, and the salt
    its nonce was made with."""

    action: str
    person: str
    salt: str


class Deciding(BaseModel):
    """What the decision page sends with a sign-in made to decide: the changes it decides, by
    their digests, the decision, the salt its nonce was made with, and, for a rejection, why,
    if the decider says."""

    proposals: list[str]
    decision: str
    salt: str
    reason: str | None = None


class Grade(BaseModel):
    """A grader's grade of one sample of an agent's work, with the salt of the sign-in made
    to give it."""

    grade: str
    salt: str = ""


class Grading(BaseModel):
    """What the grading page sends with a sign-in made to grade: the grades, by sample, and the
    salt its nonce was made with."""

    grades: dict[int, str]
    salt: str


class Draft(BaseModel):
    """A version of the settings as someone wrote it in the settings app."""

    text: str


class TokenRequest(BaseModel):
    """The web chat's sign-in, passed on to the identity provider."""

    grant_type: str
    code: str | None = None
    code_verifier: str | None = None
    redirect_uri: str | None = None
    refresh_token: str | None = None


def record(conn: Any, *, channel: str, source_id: str, person: str, agent: str, text: str,
           reply_to: dict, identity: str, place: str | None = None,
           members: list[str] | None = None) -> str | None:
    """Record a message whose sender the core checked, and wake the scheduler: in a group chat,
    the chat it was said in, `place`, and everyone in it then, `members` (core/groups.py).

    None if the channel sent it before, so it's answered once.
    """
    inbound = str(uuid.uuid4())
    conversation = groups.record(conn, channel, place) if place else None
    fresh = conn.execute(
        "insert into inbound (id, channel, source_id, person, agent, text, reply_to, "
        "conversation, members) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "on conflict do nothing returning id",
        (inbound, channel, source_id, person, agent, text, Jsonb(reply_to), conversation,
         sorted(members) if place and members else None),
    ).fetchone()
    if fresh is None:
        return None
    ledger.append(conn, {
        "kind": "inbound", "action": channel, "run": None, "instance": None,
        "acts_for": sorted(members) if place and members else [person],
        "decision": "allow", "reasons": [],
        "args": {"inbound": inbound, "agent": agent, "identity": identity, "chars": len(text),
                 "sha256": hashlib.sha256(text.encode()).hexdigest(),
                 **({"sender": person, "group": conversation} if conversation else {})},
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
        if message is None or not message.mentioned:  # in a group chat, only what mentions it
            return Response(status_code=200)
        people = [message.person] if message.person else []
        group = message.kind == "groupChat"
        members: list[str | None] = []
        strangers: list[str] = []
        if group and message.person:  # who's in it, from Teams itself, at each message
            try:
                members = gw.teams.members(message.reply_to, gw.scenario, strangers)
            except (httpx.HTTPError, ValueError) as exc:  # recorded, and said, not dropped
                log.warning("couldn't read who's in a Teams group chat: %s", exc)
                with db.transaction(gw.url) as conn:
                    turned_away(conn, "teams", "a5s couldn't read who's in the chat",
                                people, message.text)
                background.add_task(tell_in_teams, message.reply_to, groups.UNREAD)
                return Response(status_code=200)
        everyone = sorted({message.person, *members}) if group and None not in members else []
        with db.transaction(gw.url) as conn:
            if message.person is None:
                turned_away(conn, "teams", f"the directory doesn't know entra:{message.entra_id}",
                            people, message.text)
                background.add_task(tell_in_teams, message.reply_to, UNKNOWN)
            elif not message.personal and not group:  # such as a team's channel
                turned_away(conn, "teams", "a5s works in group chats, not a team's channels",
                            people, message.text)
                background.add_task(tell_in_teams, message.reply_to, groups.CHANNELS)
            elif group and len({message.person, *members}) > groups.LIMIT:  # before naming
                turned_away(conn, "teams", f"the group has more than {groups.LIMIT} people", people,
                            message.text)
                background.add_task(tell_in_teams, message.reply_to, groups.TOO_MANY)
            elif group and not everyone:
                turned_away(conn, "teams", "someone in the group isn't in the directory", people,
                            message.text)
                background.add_task(tell_in_teams, message.reply_to, groups.STRANGERS.format(
                    who=groups.listed(strangers) if strangers else "someone here"))
            else:  # Teams' message ids are unique only within a conversation
                source = f"{message.reply_to['conversation']}/{message.reply_to['activity']}"
                record(conn, channel="teams", source_id=source, person=message.person,
                       agent=message.agent, text=message.text, reply_to=message.reply_to,
                       identity="verified by teams",
                       place=message.reply_to["conversation"] if group else None,
                       members=everyone or None)
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

    def leave_in_matrix(reply_to: dict[str, str]) -> None:
        try:
            gw.matrix.leave(reply_to["room"], reply_to["bot"])
        except Exception:
            log.exception("couldn't leave a Matrix room")

    failures: dict[str, int] = {}  # Matrix events a5s couldn't act on, by id, and how often

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
            except httpx.HTTPError as exc:
                failed = failures[event.get("event_id", "")] = failures.get(
                    event.get("event_id", ""), 0) + 1
                server = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500
                if not server and failed < TRIES:  # the homeserver sends it all again later
                    raise
                # It sends nothing more until this delivery is taken, so one event it won't let
                # a5s act on, such as an invitation withdrawn before a5s joined, or one room it
                # can't read three times running, is skipped, and recorded
                log.warning("skipped a Matrix event: %s", exc)
                failures.pop(event.get("event_id", ""), None)
                with db.transaction(gw.url) as conn:
                    turned_away(conn, "matrix", f"a5s couldn't act on it: {type(exc).__name__}",
                                [], "")
                continue
            if what == "turn away":
                reason, people, reply, reply_to = detail
                with db.transaction(gw.url) as conn:
                    turned_away(conn, "matrix", reason, people, "")
                background.add_task(tell_in_matrix, {k: v for k, v in reply_to.items()
                                                     if k != "leave"}, reply)
                if reply_to.get("leave"):  # a room it won't ever work in: it goes
                    background.add_task(leave_in_matrix, reply_to)
            elif what == "message":
                with db.transaction(gw.url) as conn:  # a resent delivery counts once
                    record(conn, channel="matrix", source_id=event["event_id"], person=detail.person,
                           agent=detail.agent, text=detail.text, reply_to=detail.reply_to,
                           identity="verified by matrix", place=detail.place,
                           members=list(detail.members))
            elif what == "left":  # so a5s writes to them elsewhere, and doesn't ask them back
                with db.transaction(gw.url) as conn:
                    chats.left(conn, "matrix", *detail)
            elif what == "shared":  # someone joined their own chat: a5s writes first elsewhere
                with db.transaction(gw.url) as conn:
                    chats.shared(conn, "matrix", *detail)
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
        if problem := gw.approving(sealing=False):  # the gateway seals, never the channels app
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
            approved = approvals.recorded(conn, gw.scenario.name, version)
        before = parse_settings(bytes(last["raw"])) if last else None
        settings = parse_settings(bytes(row["raw"]))
        found = approvals.changes(before, settings, gw.definitions, gw.scenario.person)
        valid, _ = registry.signers(settings, gw.scenario.person, approved)
        return {"serial": row["serial"], "proposed_at": row["proposed_at"].isoformat(),
                "in_force": last["serial"] if last else None, "changes": found,
                "whole": approvals.described(settings, gw.definitions, gw.scenario.person),
                "needs": registry.missing(settings, gw.scenario.person, valid, before)
                if status == "waiting" else [],
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
                approvals.record(conn, gw.scenario.name, version, person.id, token, body.salt,
                                 claims)
            except approvals.Refused as exc:
                raise HTTPException(exc.status, exc.reason) from None
            ledger.append(conn, {
                "kind": "admin", "action": "approve", "run": None, "instance": None, "acts_for": [],
                "decision": "record",
                "args": {"settings": row["version"], "serial": row["serial"], "digest": version,
                         "by": person.id, "identity": "verified: a sign-in to approve this version alone",
                         "issuer": claims["iss"],
                         "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
            approved = approvals.recorded(conn, gw.scenario.name, version)
            last = approvals.latest(conn, gw.scenario.name)
        settings = parse_settings(bytes(row["raw"]))
        valid, _ = registry.signers(settings, gw.scenario.person, approved)
        before = parse_settings(bytes(last["raw"])) if last else None
        return {"approved": True, "serial": row["serial"], "by": person.name,
                "needs": registry.missing(settings, gw.scenario.person, valid, before)}

    # The data protection officer's requests: the page where they ask to export, or erase,
    # what a5s keeps about someone, signed in afresh for that request alone, which someone from
    # the team that runs a5s then carries out, once, within ten minutes (core/officer.py).

    @app.get("/officer/", include_in_schema=False)
    def officer_page() -> Response:
        approving()
        return page("officer.html")

    @app.get("/officer/officer.js", include_in_schema=False)
    def officer_script() -> Response:
        approving()
        return page("officer.js")

    @app.get("/officer/config")
    def officer_config() -> dict:
        """Where the page signs the officer in."""
        return approve_config()

    @app.post("/officer/token")
    def officer_token(body: TokenRequest) -> JSONResponse:
        """The officer's sign-in, passed on to the identity provider: the signed sign-in alone."""
        return approve_token(body)

    @app.post("/officer/requests")
    def officer_request(body: Asking, authorization: str | None = Header(default=None)) -> dict:
        """The officer's request, signed through the identity provider for it alone, and
        recorded for the gateway to check again and carry out, once."""
        approving()
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to ask: send your sign-in as a bearer token")
        person = body.person.strip()
        try:
            who, claims = officer.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                        token, body.action, person, body.salt, time.time())
            with db.transaction(gw.url) as conn:
                officer.record(conn, body.action, person, who.id, token, body.salt, claims)
                ledger.append(conn, {
                    "kind": "admin", "action": "ask", "run": None, "instance": None,
                    "acts_for": [person], "decision": "record",
                    "args": {"to": body.action, "person": person, "by": who.id,
                             "identity": "verified: a sign-in to ask for this alone",
                             "issuer": claims["iss"],
                             "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
        except approvals.Refused as exc:
            raise HTTPException(exc.status, exc.reason) from None
        named = gw.scenario.person(person)
        return {"asked": body.action, "person": person, "name": named.name if named else None,
                "by": who.name, "lasts": "ten minutes",
                "command": f"a5s export --person {person} --out <file>" if body.action == "export"
                else f"a5s erase --person {person} --confirm {person}"}

    # Deciding held changes: the page a decider's card opens. They sign in to see what waits
    # for them, and again, afresh, to decide: that sign-in's nonce commits to their decision on
    # exactly the changes they chose, so the provider signs the decision. The gateway makes
    # what's approved.

    @app.get("/decide/", include_in_schema=False)
    def decide_page() -> Response:
        approving()
        return page("decide.html")

    @app.get("/decide/decide.js", include_in_schema=False)
    def decide_script() -> Response:
        approving()
        return page("decide.js")

    @app.post("/decide/token")
    def decide_token(body: TokenRequest) -> JSONResponse:
        """The decision page's sign-ins, passed on to the identity provider, as for approving."""
        return approve_token(body)

    @app.get("/decide/config")
    def decide_config() -> dict:
        return approve_config()

    @app.post("/decide/review")
    def review_proposals(authorization: str | None = Header(default=None)) -> dict:
        """The held changes whoever signed in may decide now, oldest first, since those lapse
        first, as the directory stands now; those they were told of as a decider's manager,
        which they may see but not decide; and those they decided lately. Each in the words
        code worked out when it was asked for, with a link to each record, and whether it has
        changed since."""
        approving()
        who, _ = sender(authorization, None)
        person = gw.scenario.person(who)
        roles = person.roles if person else ()
        mine = sorted({r.split(":", 1)[1] for r in roles
                       if r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:"))})
        with db.transaction(gw.url) as conn:
            rows = conn.execute(
                "select p.*, d.decision as yours from proposals p left join proposal_decisions d "
                "on d.digest = p.digest and d.person = %(who)s where p.scenario = %(scenario)s "
                "and ((p.status = 'waiting' and (p.parts && %(parts)s or %(who)s = any(p.escalated) "
                "or (%(approver)s and cardinality(p.parts) = 0))) or (d.id is not null and "
                "(p.ended_at is null or p.ended_at > %(week)s))) "
                "order by (p.status = 'waiting') desc, p.id limit 500",
                {"who": who, "scenario": gw.scenario.name, "parts": mine,
                 "approver": INSTANCE_APPROVER in roles,
                 "week": gw.clock() - timedelta(days=7)}).fetchall()
        shown = []
        for row in rows:
            waits = row["status"] == "waiting"
            decides = waits and proposals.may_decide(gw.scenario, row, who)
            if waits and not decides and who not in (row["escalated"] or []):
                continue  # they no longer own what it touches, or may no longer see it
            if len(shown) >= 50:
                break
            try:
                changed = proposals.changed(gw.scenario, row) if waits else []
            except Exception:  # the records system didn't answer: say so, rather than nothing
                log.exception("couldn't read the records of %s", proposals.key(row))
                changed = list(row["records"])
            standing = row["standing"] or {}
            shown.append({"key": proposals.key(row), "digest": row["digest"], "said": row["said"],
                          "flags": row["flags"], "sensitive": row["sensitive"],
                          "status": row["status"], "yours": row["yours"], "may_decide": decides,
                          "outcome": row["outcome"], "proposed_at": row["proposed_at"].isoformat(),
                          "lapses_at": row["lapses_at"].isoformat(),
                          "links": [r["link"] for r in standing.values() if r and r.get("link")],
                          "changed": [f"{k} has changed since it was asked for" for k in changed]})
        return {"you": person.name if person else who, "proposals": shown}

    @app.post("/decide/proposals")
    def decide_proposals(body: Deciding, authorization: str | None = Header(default=None)) -> dict:
        """A decision on held changes, signed through the identity provider for that decision on
        exactly those changes. It's recorded once, and sealed. The gateway makes what's approved."""
        approving()
        digests = sorted(set(body.proposals))
        if not 1 <= len(digests) <= 20 or not all(re.fullmatch(r"[0-9a-f]{64}", d) for d in digests):
            raise HTTPException(400, "name from one to 20 changes to decide, by their digests")
        reason = None
        if body.reason and body.reason.strip() and body.decision == "reject":
            if len(body.reason) > proposals.REASON:
                raise HTTPException(400, f"say why in at most {proposals.REASON} characters")
            reason, _ = sanitize(" ".join(body.reason.split()), gw.scenario.record_links)
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to decide: send your sign-in as a bearer token")
        try:
            person, claims = proposals.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, digests, body.decision, body.salt, time.time())
        except proposals.Refused as exc:
            raise HTTPException(exc.status, exc.reason) from None
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select * from proposals where scenario = %s and digest = any(%s) "
                                "order by id", (gw.scenario.name, digests)).fetchall()
            if len(rows) != len(digests):
                raise HTTPException(404, "a5s has no such change to decide")
            for row in rows:
                if row["status"] != "waiting":
                    raise HTTPException(409, f"{proposals.key(row)} isn't waiting for a decision: "
                                             f"it's {row['status']}")
                if not proposals.may_decide(gw.scenario, row, person.id):
                    raise HTTPException(403, f"{person.name} may not decide {proposals.key(row)}")
            if len(rows) > 1 and any(r["sensitive"] for r in rows):
                raise HTTPException(409, "a sensitive change is decided on its own, with a sign-in "
                                         "of its own")
            try:
                proposals.record(conn, gw.scenario.name, rows, body.decision, person.id, token,
                                 body.salt, claims, gw.clock(), reason)
            except proposals.Refused as exc:
                raise HTTPException(exc.status, exc.reason) from None
            ledger.append(conn, {
                "kind": "admin", "action": "decide", "run": None, "instance": None, "acts_for": [],
                "decision": "record",
                "args": {"proposals": [proposals.key(r) for r in rows], "decided": body.decision,
                         "by": person.id,
                         "identity": "verified: a sign-in to make this decision on these alone",
                         "issuer": claims["iss"],
                         "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
        return {"decided": [proposals.key(r) for r in rows], "decision": body.decision,
                "by": person.name}

    # Grading: where people outside the team that built an agent grade samples of its changes,
    # whose grades raise or lower a5s's cap on its level (core/samples.py).

    @app.get("/grade/", include_in_schema=False)
    def grade_page() -> Response:
        approving()
        return page("grade.html")

    @app.get("/grade/grade.js", include_in_schema=False)
    def grade_script() -> Response:
        approving()
        return page("grade.js")

    @app.post("/grade/token")
    def grade_token(body: TokenRequest) -> JSONResponse:
        return approve_token(body)

    @app.get("/grade/config")
    def grade_config() -> dict:
        return approve_config()

    def grader(authorization: str | None) -> Person:
        approving()
        who, _ = sender(authorization, None)
        person = gw.scenario.person(who)
        if person is None or samples.GRADER not in person.roles:
            raise HTTPException(403, "grading is for the people who grade agents' work")
        return person

    @app.post("/grade/review")
    def review_samples(authorization: str | None = Header(default=None)) -> dict:
        """The samples waiting for a grade that whoever signed in may grade, oldest first: read
        in pages, leaving out in the query what it can, until 20 are found."""
        person = grader(authorization)
        shown: list[dict] = []
        after = 0
        with db.transaction(gw.url) as conn:
            minders = {r["id"]: (r["owner"], r["deputy"]) for r in conn.execute(
                "select id, owner, deputy from instances")}
            while len(shown) < 20:
                rows = conn.execute(
                    "select * from samples where scenario = %s and grade is null and lapsed_at "
                    "is null and id > %s and not (%s = any(acts_for)) and decided_by is distinct "
                    "from %s order by id limit 200",
                    (gw.scenario.name, after, person.id, person.id)).fetchall()
                if not rows:
                    break
                after = rows[-1]["id"]
                shown += [{"id": r["id"], "kind": r["kind"], "agent": r["definition"],
                           "part": r["part"], "action": r["action"], "said": r["said"],
                           "records": r["records"], "flags": r["flags"],
                           "decided": r["decided"], "drawn_at": r["drawn_at"].isoformat()}
                          for r in rows if samples.may_grade(
                              gw.scenario, r, person, minders.get(r["instance_id"], ())) is None]
        return {"you": person.name, "samples": shown[:20]}

    @app.post("/grade/samples")
    def grade_samples(body: Grading, authorization: str | None = Header(default=None)) -> dict:
        """Grades of samples, signed through the identity provider for exactly those grades of
        exactly those samples, by someone who may grade each, once. The core seals each."""
        return grading(body.grades, body.salt, authorization)

    @app.post("/grade/samples/{sample}")
    def grade_sample(sample: int, body: Grade, authorization: str | None = Header(default=None)
                     ) -> dict:
        """One sample's grade, as above."""
        return grading({sample: body.grade}, body.salt, authorization)

    def grading(grades: dict[int, str], salt: str, authorization: str | None) -> dict:
        approving()
        if not 1 <= len(grades) <= 20 or any(g not in samples.GRADES for g in grades.values()):
            raise HTTPException(400, "grade from one to 20 samples, each right, wrong or critical")
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to grade: send your sign-in as a bearer token")
        try:
            person, claims = proposals.fresh(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, samples.nonce(grades, salt), salt, time.time(),
                                             "grade these samples")
        except proposals.Refused as exc:
            raise HTTPException(exc.status, exc.reason) from None
        if samples.GRADER not in person.roles:
            raise HTTPException(403, "grading is for the people who grade agents' work")
        hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
        with db.transaction(gw.url) as conn:
            if conn.execute("select 1 from samples where grade_token = %s limit 1",
                            (hashed,)).fetchone():
                raise HTTPException(409, "that sign-in has graded already: sign in again")
            rows = {r["id"]: r for r in conn.execute(
                "select * from samples where scenario = %s and id = any(%s) order by id for update",
                (gw.scenario.name, sorted(grades)))}
            minders = {r["id"]: (r["owner"], r["deputy"]) for r in conn.execute(
                "select id, owner, deputy from instances")}
            for sample in sorted(grades):
                row = rows.get(sample)
                if row is None:
                    raise HTTPException(404, f"a5s has no sample {sample}")
                if (why := samples.may_grade(gw.scenario, row, person,
                                             minders.get(row["instance_id"], ()))) is not None:
                    raise HTTPException(403, why)
                if row["grade"] is not None or row["lapsed_at"] is not None:
                    raise HTTPException(409, f"sample {sample} has been graded already, or lapsed")
            now = gw.clock()
            for sample, grade in sorted(grades.items()):
                entry = {**rows[sample], "grade": grade, "graded_by": person.id, "graded_at": now,
                         "grade_token": hashed, "grade_nonce": claims["nonce"], "grade_salt": salt,
                         "grade_issuer": claims["iss"],
                         "grade_subject": str(claims.get("sub") or ""), "grade_proof": token}
                conn.execute(  # with the sign-in, which the gateway checks again and seals
                    "update samples set grade = %(grade)s, graded_by = %(graded_by)s, "
                    "graded_at = %(graded_at)s, grade_token = %(grade_token)s, grade_nonce = "
                    "%(grade_nonce)s, grade_salt = %(grade_salt)s, grade_issuer = %(grade_issuer)s, "
                    "grade_subject = %(grade_subject)s, grade_proof = %(grade_proof)s "
                    "where id = %(id)s", entry)
                ledger.append(conn, {
                    "kind": "admin", "action": "grade", "run": str(rows[sample]["run_id"]),
                    "instance": rows[sample]["instance_id"], "acts_for": [], "decision": "record",
                    "args": {"sample": sample, "grade": grade, "by": person.id,
                             "release": rows[sample]["release"], "part": rows[sample]["part"],
                             "action": rows[sample]["action"],
                             "identity": "verified: a sign-in to give these grades alone",
                             "token_sha256": hashed.removeprefix(approvals.HASHED)}})
        return {"graded": sorted(grades), "grades": {str(k): v for k, v in grades.items()},
                "by": person.name}

    # The settings app: where the people who approve instances review the whole version in
    # force, and ask for a new one. The gateway proposes it to everyone it needs, who approve
    # it on the page above, so asking for a version changes nothing by itself.

    def settling(authorization: str | None) -> Person:
        """Who signed in to the settings app: someone who approves instances."""
        approving()
        who, _ = sender(authorization, None)
        person = gw.scenario.person(who)
        if person is None or not registry.approves(person):
            raise HTTPException(403, "the settings app is for the people who approve instances: "
                                     "each part's owner, and the instance approvers")
        return person

    def drafted(text: str, last: dict | None) -> tuple[Settings | None, bytes, list[str]]:
        """The version someone wrote, with the next serial, and why it can't be proposed. It's
        checked strictly before a5s works with it: no YAML anchors or aliases, which can make a
        few bytes into gigabytes, and only what a5s's format allows."""
        if len(text) > MAX_SETTINGS:
            return None, b"", [f"settings are at most {MAX_SETTINGS // 1024} KB"]
        try:
            parse_settings(text.encode())
            data = yaml.safe_load(text)
            data["serial"] = (last["serial"] if last else 0) + 1
            raw = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode()
            settings = parse_settings(raw)
        except (yaml.YAMLError, ValueError, KeyError, TypeError, AttributeError) as exc:
            return None, b"", [f"a5s can't read it as settings: {exc}"]
        return settings, raw, gw.unusable(settings, last)

    # The notebook: what agents learned from records, for their owners to read and remove

    def keeping(authorization: str | None) -> tuple[Person, list[dict]]:
        """Who signed in to the notebook, and the instances whose entries they keep: those of an
        agent they own, or that they run, as its owner or deputy."""
        approving()
        who, _ = sender(authorization, None)
        person = gw.scenario.person(who)
        if person is None:
            raise HTTPException(403, "a5s doesn't know who you are")
        owns = {r.removeprefix("agent-owner:") for r in person.roles if r.startswith("agent-owner:")}
        with db.transaction(gw.url) as conn:
            kept = [i for i in conn.execute("select id, definition, owner, deputy from instances "
                                            "where status <> 'retired' order by id")
                    if i["definition"] in owns or person.id in (i["owner"], i["deputy"])]
        if not kept:
            raise HTTPException(403, "the notebook is for the people who own an agent, or run one "
                                     "of its instances")
        return person, kept

    @app.get("/notebook/", include_in_schema=False)
    def notebook_page() -> Response:
        approving()
        return page("notebook.html")

    @app.get("/notebook/notebook.js", include_in_schema=False)
    def notebook_script() -> Response:
        approving()
        return page("notebook.js")

    def may_see(person: Person, row: dict) -> bool:
        """Whether someone may see a note: every record its run read, as it reached runs."""
        return all(gw.scenario.sees(person.id, k) for k in row["read_records"] or row["sources"])

    @app.get("/notebook/api")
    def notebook_now(authorization: str | None = Header(default=None)) -> dict:
        """The entries of the instances someone keeps, those whose every record they may see,
        each with links to its records, and who else keeps the ones they may not see."""
        person, kept = keeping(authorization)
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select * from notebook where instance_id = any(%s) "
                                "order by instance_id, written_at desc, id desc",
                                ([i["id"] for i in kept],)).fetchall()
        shown = [r for r in rows if may_see(person, r)]
        hidden = {r["instance_id"] for r in rows if not may_see(person, r)}
        others = sorted({p.name for i in kept if i["id"] in hidden
                         for k in (i["owner"], i["deputy"])
                         if k and k != person.id and (p := gw.scenario.person(k))})
        return {"you": person.name, "instances": [i["id"] for i in kept],
                "entries": [{"entry": f"N-{r['id']}", "instance": r["instance_id"],
                             "text": r["text"],
                             "sources": [{"key": k, "link": (r["links"] or {}).get(k)}
                                         for k in r["sources"]],
                             "noted": r["written_at"].date().isoformat(),
                             "checked": r["checked_at"].date().isoformat()} for r in shown],
                "hidden": len(rows) - len(shown), "others": others}

    @app.post("/notebook/api/{entry}/remove")
    def notebook_remove(entry: str, authorization: str | None = Header(default=None)) -> dict:
        """Remove an entry, as someone who keeps its instance's notebook and may see its records."""
        person, kept = keeping(authorization)
        number = entry.removeprefix("N-")
        if not number.isdigit():
            raise HTTPException(404, "no such entry")
        with db.transaction(gw.url) as conn:
            row = conn.execute("delete from notebook where id = %s and instance_id = any(%s) "
                               "returning *", (int(number), [i["id"] for i in kept])).fetchone()
            if row is None or not may_see(person, row):
                raise HTTPException(404, "no such entry in a notebook you keep")
            ledger.append(conn, notebook.entry(row, "remove", "its keeper removed it", person.id))
        return {"removed": f"N-{row['id']}"}

    # People's own tasks: what they asked agents to do over more than one run (core/tasking.py)

    def tasked(authorization: str | None) -> Person:
        """Who signed in to their tasks' page: anyone the directory knows."""
        approving()
        who, _ = sender(authorization, None)
        person = gw.scenario.person(who)
        if person is None:
            raise HTTPException(403, "a5s doesn't know who you are")
        return person

    @app.get("/tasks/", include_in_schema=False)
    def tasks_page() -> Response:
        approving()
        return page("tasks.html")

    @app.get("/tasks/tasks.js", include_in_schema=False)
    def tasks_script() -> Response:
        approving()
        return page("tasks.js")

    @app.get("/tasks/api")
    def tasks_now(authorization: str | None = Header(default=None)) -> dict:
        """Someone's own tasks, with every agent: how each stands, what it waits on, and
        what it has spent. One whose words name a record they may no longer see shows how it
        stands alone."""
        person = tasked(authorization)
        with db.transaction(gw.url) as conn:
            return {"you": person.name,
                    "tasks": tasking.theirs(conn, gw.scenario, person, gw.clock())}

    @app.post("/tasks/api/{task}/cancel")
    def tasks_cancel(task: str, authorization: str | None = Header(default=None)) -> dict:
        """Cancel one of someone's own tasks, at their word, and the parts of it still open."""
        person = tasked(authorization)
        try:
            with db.transaction(gw.url) as conn:
                return tasking.cancel_theirs(conn, person, task, gw.clock())
        except TaskError as exc:
            raise HTTPException(404 if "isn't one of" in str(exc) else 409, str(exc)) from None

    # The studio's pages: what someone may watch, read only, worked out as the core's API works
    # it out for the team that runs a5s (core/studio.py)

    def studying(authorization: str | None) -> Person:
        """Who signed in to the studio: someone who may watch an instance, or owns an agent."""
        approving()
        who, _ = sender(authorization, None)
        person = gw.scenario.person(who)
        if person is None:
            raise HTTPException(403, "a5s doesn't know who you are")
        with db.transaction(gw.url) as conn:
            theirs = studio.instances(conn, person)
        if not theirs and not any(r.startswith("agent-owner:") for r in person.roles):
            raise HTTPException(403, "the studio is for the people who run an instance, own an "
                                     "agent, own or decide for one of its parts, or approve "
                                     "instances")
        return person

    def watched(conn: Any, person: Person, instance: str) -> dict:
        found = next((i for i in studio.instances(conn, person) if i["id"] == instance), None)
        if found is None:
            raise HTTPException(404, "there's no such instance that you may watch")
        return found

    @app.get("/studio/", include_in_schema=False)
    def studio_page() -> Response:
        approving()
        return page("studio.html")

    @app.get("/studio/studio.js", include_in_schema=False)
    def studio_script() -> Response:
        approving()
        return page("studio.js")

    @app.get("/studio/api")
    def studio_now(authorization: str | None = Header(default=None)) -> dict:
        """The agents someone may watch, and where each runs: the instances they may watch."""
        person = studying(authorization)
        with db.transaction(gw.url) as conn:
            return {"you": person.name, "agents": studio.catalogue(
                conn, gw.scenario, gw.definitions, gw.scenario.tools(), person)}

    @app.get("/studio/api/agents/{agent}")
    def studio_agent(agent: str, authorization: str | None = Header(default=None)) -> dict:
        """One agent someone owns, or watches an instance of, with its instructions."""
        person = studying(authorization)
        definition = gw.definitions.get(agent)
        with db.transaction(gw.url) as conn:
            insts = studio.instances(conn, person)
        if definition is None or (agent_owner(agent) not in person.roles
                                  and not any(i["definition"] == agent for i in insts)):
            raise HTTPException(404, "there's no such agent that you may watch")
        return studio.agent(gw.scenario, definition, gw.scenario.tools(), insts, whole=True)

    @app.get("/studio/api/agents/{agent}/measures")
    def studio_agent_measures(agent: str, days: int = 30,
                              authorization: str | None = Header(default=None)) -> dict:
        """How the instances of an agent that someone may watch are doing."""
        person = studying(authorization)
        with db.transaction(gw.url) as conn:
            insts = [i for i in studio.instances(conn, person) if i["definition"] == agent]
            if not insts:
                raise HTTPException(404, "there's no instance of that agent that you may watch")
            return studio.figures(conn, gw.scenario, gw.models, insts, days, gw.clock())

    @app.get("/studio/api/instances/{instance}")
    def studio_instance(instance: str, days: int = 30,
                        authorization: str | None = Header(default=None)) -> dict:
        """How an instance someone may watch is doing, over the last `days` days."""
        person = studying(authorization)
        with db.transaction(gw.url) as conn:
            return studio.figures(conn, gw.scenario, gw.models,
                                  [watched(conn, person, instance)], days, gw.clock())

    @app.get("/studio/api/instances/{instance}/runs")
    def studio_runs(instance: str, before: str | None = None, limit: int = studio.RUNS,
                    authorization: str | None = Header(default=None)) -> dict:
        """An instance's runs that someone may see, newest first, and how many others: whom
        each acted for named only once the officer agrees."""
        person = studying(authorization)
        with db.transaction(gw.url) as conn:
            try:
                return studio.runs(conn, gw.scenario, watched(conn, person, instance), person,
                                   before, limit, names=gw.cfg.studio_names)
            except ValueError:
                raise HTTPException(400, "before is where the page before ended, as it said")

    @app.get("/studio/api/runs/{run_id}")
    def studio_run(run_id: str, authorization: str | None = Header(default=None)) -> dict:
        """What a run did, if someone may watch its instance and see every record it named."""
        person = studying(authorization)
        with db.transaction(gw.url) as conn:
            found = studio.run(conn, gw.scenario, run_id, person, names=gw.cfg.studio_names)
        if found is None:
            raise HTTPException(404, "there's no such run that you may see")
        return found

    @app.get("/settings/", include_in_schema=False)
    def settings_page() -> Response:
        approving()
        return page("settings.html")

    @app.get("/settings/settings.js", include_in_schema=False)
    def settings_script() -> Response:
        approving()
        return page("settings.js")

    @app.get("/settings/api")
    def settings_now(authorization: str | None = Header(default=None)) -> dict:
        """The whole version in force, in words and as written, the versions waiting for
        approval, and what the person asked for lately."""
        person = settling(authorization)
        words = (gw.definitions, gw.scenario.person)
        with db.transaction(gw.url) as conn:
            last = approvals.latest(conn, gw.scenario.name)
            in_force = parse_settings(bytes(last["raw"])) if last else None
            waiting = []
            for row in conn.execute("select * from settings_proposals where scenario = %s and "
                                    "outcome is null and serial > %s order by serial desc",
                                    (gw.scenario.name, last["serial"] if last else -1)):
                settings = parse_settings(bytes(row["raw"]))
                approved = approvals.recorded(conn, gw.scenario.name, row["digest"])
                valid, _ = registry.signers(settings, gw.scenario.person, approved)
                waiting.append({
                    "serial": row["serial"], "link": f"/approve/?settings={row['digest']}",
                    "changes": approvals.changes(in_force, settings, *words),
                    "approved_by": [p.name if (p := gw.scenario.person(a)) else a for a in valid],
                    "needs": registry.missing(settings, gw.scenario.person, valid, in_force)})
            asked = conn.execute("select * from settings_requests where scenario = %s and "
                                 "person = %s order by id desc limit 5",
                                 (gw.scenario.name, person.id)).fetchall()
        return {
            "you": person.name,
            "in_force": {"serial": last["serial"], "text": bytes(last["raw"]).decode(),
                         "whole": approvals.described(in_force, *words)} if last else None,
            "waiting": waiting,
            "requests": [{"asked_at": r["asked_at"].isoformat(),
                          "serial": parse_settings(bytes(r["raw"])).serial,
                          "outcome": r["outcome"] or "waiting for a5s to ask its approvers",
                          "link": f"/approve/?settings={r['digest']}" if r["digest"] else None}
                         for r in asked],
        }

    @app.post("/settings/api/review")
    def settings_review(body: Draft, authorization: str | None = Header(default=None)) -> dict:
        """What a version someone wrote would change, the whole of it in words, and who'd
        have to approve it, before they ask for it."""
        settling(authorization)
        with db.transaction(gw.url) as conn:
            last = approvals.latest(conn, gw.scenario.name)
        settings, _, problems = drafted(body.text, last)
        if settings is None:
            return {"problems": problems}
        before = parse_settings(bytes(last["raw"])) if last else None
        words = (gw.definitions, gw.scenario.person)
        return {"serial": settings.serial, "problems": problems,
                "changes": approvals.changes(before, settings, *words),
                "whole": approvals.described(settings, *words),
                "approvers": [p.name for p in registry.approvers(settings, gw.scenario.holders,
                                                                 before)]}

    @app.post("/settings/api/requests", status_code=202)
    def settings_request(body: Draft, authorization: str | None = Header(default=None)) -> dict:
        """Ask for a version: the gateway proposes it to everyone it needs within a minute."""
        person = settling(authorization)
        with db.transaction(gw.url) as conn:
            conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"settings {person.id}",))
            asked = conn.execute(
                "select count(*) filter (where outcome is null) as waiting, count(*) filter "
                "(where asked_at > now() - interval '1 day') as today from settings_requests "
                "where scenario = %s and person = %s", (gw.scenario.name, person.id)).fetchone()
            if asked["waiting"]:
                raise HTTPException(409, {"problems": [
                    "a5s is still proposing what you asked for last: try again in a minute"]})
            if asked["today"] >= REQUESTS_A_DAY:
                raise HTTPException(429, {"problems": [(
                    f"you've asked for {REQUESTS_A_DAY} versions today, which is as many as a "
                    "day allows: try again tomorrow")]})
            last = approvals.latest(conn, gw.scenario.name)
            settings, raw, problems = drafted(body.text, last)
            if settings is None or problems:
                raise HTTPException(409, {"problems": problems})
            row = conn.execute("insert into settings_requests (scenario, person, raw) "
                               "values (%s, %s, %s) returning id",
                               (gw.scenario.name, person.id, raw)).fetchone()
            ledger.append(conn, {"kind": "admin", "action": "request", "run": None,
                                 "instance": None, "acts_for": [], "decision": "record",
                                 "args": {"settings": settings.version, "serial": settings.serial,
                                          "by": person.id, "identity": "verified"}})
        return {"request": row["id"], "serial": settings.serial}

    return app
