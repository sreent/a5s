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
(core/approvals.py), and the pages people sign in to for one thing, each a router
of its own whose API checks who's signed in (core/web.py): the studio's, the
settings app's, the notebook's, people's own tasks', the auditors' and the
administrators'.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import psycopg
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.contract import (
    DATA_PROTECTION,
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
)
from a5s.core import (
    admin_api,
    administration,
    approve_api,
    audit,
    audit_api,
    chats,
    decide_api,
    grade_api,
    groups,
    ledger,
    matrix,
    notebook_api,
    officer_api,
    registry,
    samples,
    settings_api,
    studio_api,
    tasks_api,
    topics,
    web,
)
from a5s.core.teams import UNKNOWN, Refused

AWAY = "a5s can't reach its records just now, so it couldn't take that. Try again in a moment."
AWAY_RETRY = 5  # seconds a chat or a person is asked to wait before trying again

log = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024  # far more than one message needs
TRIES = 3  # deliveries of a Matrix event a5s can't act on before it's skipped, and recorded


class LocalMessage(BaseModel):
    agent: str
    text: str
    person: str | None = None  # in development, without an identity provider, who it's from


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


def chats_on(gw: Any) -> list[str]:
    """The chats a deployment has turned on, each by setting its own settings."""
    on = {"the command line": True, "the web chat": web.webchat(gw), "Teams": gw.teams is not None,
          "Matrix": gw.matrix is not None}
    return [chat for chat, is_on in on.items() if is_on]


def create_app(gw: Any) -> FastAPI:
    """The core's endpoints for channels: the only part of the core people reach."""
    app = FastAPI(title="a5s channels")

    app.add_middleware(Small)
    log.info("people reach a5s through %s", ", ".join(chats_on(gw)))

    @app.exception_handler(psycopg.OperationalError)
    def database_away(_request: Request, exc: psycopg.OperationalError) -> JSONResponse:
        """While a5s's database is away, as in a managed database's failover: a refusal for a
        moment, which says so and when to try again, so a person sends their message again and
        a chat delivers it again, rather than an error of a5s's own. One line in the log, not a
        trace for each request."""
        log.warning("the database can't be reached, so a request was refused for now: %s",
                    str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__)
        return JSONResponse(status_code=503, headers={"Retry-After": str(AWAY_RETRY)},
                            content={"detail": AWAY})

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
        """Who's writing, and how a5s knows (core/web.py)."""
        return web.sender(gw, authorization, claimed)

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
        return web.page(gw, name)

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        if not web.webchat(gw):
            raise HTTPException(404, "the web chat isn't set up here")
        return RedirectResponse("/chat/")

    @app.get("/chat/", include_in_schema=False)
    def chat() -> Response:
        return page("index.html")

    @app.get("/chat/config")
    def chat_config() -> dict:
        """How the page signs people in, and which agents they can talk to."""
        if not web.webchat(gw):
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
    def chat_token(body: web.TokenRequest) -> JSONResponse:
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
        return web.exchange(gw, form, ("id_token", "refresh_token", "expires_in"))

    @app.get("/chat/{name}", include_in_schema=False)
    def chat_file(name: str) -> Response:
        if name not in ("app.js", "app.css", "shell.js"):
            raise HTTPException(404, "no such file")
        return page(name)

    # The pages where people sign in afresh for one act, each a router of its own whose act's
    # route checks its sign-in: approving a version of the settings (core/approve_api.py), the
    # officer's requests, deciding held changes, and grading samples
    for acts in (approve_api, officer_api, decide_api, grade_api):
        app.include_router(acts.router(gw))

    # The pages people sign in to for one thing, each a router whose API checks who's signed in:
    # the studio's (core/studio_api.py), the settings app's, the notebook's, people's own tasks',
    # the auditors' and the administrators'
    for pages in (studio_api, settings_api, notebook_api, tasks_api, audit_api, admin_api):
        app.include_router(pages.router(gw))

    # Every page's sidebar: who signed in, and the pages they may use (webchat/shell.js)

    @app.get("/shell/api")
    def shell(authorization: str | None = Header(default=None)) -> dict:
        """Who signed in, and the pages they may use, for the sidebar every page shows: each
        by the check its own page makes, as its router makes it. Every page still checks for
        itself, so this only leaves out the pages that would refuse them."""
        person = web.known(gw, authorization)
        roles = set(person.roles)
        decides = INSTANCE_APPROVER in roles or any(
            r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:")) for r in roles)
        found = {"chat": True, "tasks": True, "notebook": bool(notebook_api.kept(gw, person)),
                 "studio": True, "decide": decides, "grade": samples.GRADER in roles,
                 "settings": registry.approves(person), "audit": audit.reads(person),
                 "admin": administration.administers(person, gw.cfg.team),
                 "officer": DATA_PROTECTION in roles}
        return {"you": person.name, "pages": [name for name, may in found.items() if may]}

    return app
