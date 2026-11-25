"""Where people's messages arrive, in the core.

Every channel's messages come here first. The core checks who sent each one,
through the identity provider or the channel's own signed token, and records it.
Only then does the scheduler take it, and a run that answers it acts for the
sender the core recorded. So no service can say a message came from someone
else, and a person's token goes no further than this.

The channels app is made here too: the chats' routes, Teams', Matrix's and the
local channel's, which the command line and the web chat use; and the pages
people use, each a router of its own (core/web.py). They are the web chat's
(core/chat_api.py); those where someone signs in afresh for one act, such as
approving a version of the settings from the card in their chat
(core/approve_api.py); and those people sign in to for one thing, whose API
checks who's signed in: the studio's, the settings app's, the notebook's,
people's own tasks', the auditors' and the administrators', with every page's
sidebar (core/shell_api.py).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import psycopg
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from a5s import db
from a5s.core import (
    admin_api,
    approve_api,
    audit_api,
    chat_api,
    chats,
    decide_api,
    events,
    feedback,
    files,
    grade_api,
    groups,
    health_api,
    languages,
    ledger,
    matrix,
    notebook_api,
    officer_api,
    registry,
    settings_api,
    shell_api,
    status_api,
    studio_api,
    tasks_api,
    topics,
    web,
    words,
)
from a5s.core.slack import CHANNELS as SLACK_CHANNELS
from a5s.core.slack import Refused as SlackRefused
from a5s.core.teams import UNKNOWN, Refused

AWAY = "a5s can't reach its records just now, so it couldn't take that. Try again in a moment."
AWAY_RETRY = 5  # seconds a chat or a person is asked to wait before trying again

log = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024  # far more than one message needs
MAX_UPLOAD = 6 * 1024 * 1024  # a local message's, with its files, in base64
TEXT_MOST = 40_000  # characters a local message says, as Slack allows one: its files are apart
# Each file a local message brings waits in a5s's database until a day after it's answered, so
# one person, or a script with their sign-in, can't fill it (round 14): a5s holds so many of
# their messages with files unanswered at once, and so many bytes of their files a day
WAITING_FILES = 3
FILES_A_DAY = 40 * 1024 * 1024
TRIES = 3  # deliveries of a Matrix event a5s can't act on before it's skipped, and recorded


class Sent(BaseModel):
    """A file sent with a message on the local channel, such as from the web chat: its name,
    its kind, and its bytes in base64."""

    name: str
    type: str
    data: str


class Said(BaseModel):
    """That an agent's answer in the web chat was wrong: the answer, and why, if they say."""

    message: int
    said: str | None = None
    person: str | None = None  # in development, without an identity provider, who it's from


class LocalMessage(BaseModel):
    agent: str
    text: str = Field(max_length=TEXT_MOST)  # a message's words: its files may be larger
    person: str | None = None  # in development, without an identity provider, who it's from
    files: list[Sent] = []  # what they sent with it, a few megabytes in all


def record(conn: Any, *, channel: str, source_id: str, person: str, agent: str, text: str,
           reply_to: dict, identity: str, place: str | None = None,
           members: list[str] | None = None,
           sent: tuple[files.File, ...] | list[files.File] = ()) -> str | None:
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
                 **({"sender": person, "group": conversation} if conversation else {}),
                 **({"files": len(sent)} if sent else {})},
    })
    if sent:  # what came with it, for a5s's reader, once the agent asks (core/files.py)
        files.keep(conn, inbound, list(sent))
    conn.execute("notify a5s_inbound")
    return inbound


# Why a5s won't keep another message with files, in the words someone reads (core/words.py)
HOLDS = ("a5s holds {waiting} of your messages with files that wait for an answer: send more once "
         "it has answered them")
SENT_TODAY = ("you've sent {today} MB of files here today, and a5s keeps {most} MB of them a day: "
              "send more tomorrow")


def holding(conn: Any, person: str, adding: int, language: str = languages.ENGLISH) -> str | None:
    """Why a5s won't keep another message with files someone sends through the local channel,
    such as from the web chat, if it won't, in the caller's transaction, in the language they
    read (round 15, A12): it holds WAITING_FILES of theirs unanswered, or this would take what
    they've sent today past FILES_A_DAY. Their messages are counted one at a time, so two sent
    at once count as two."""
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"a5s local files {person}",))
    held = conn.execute(
        "select count(distinct i.id) filter (where i.answered_at is null) as waiting, "
        "coalesce(sum(f.size) filter (where i.received_at > now() - interval '1 day'), 0) "
        "as today from inbound i join inbound_files f on f.inbound_id = i.id where "
        "i.person = %s and i.channel = 'local' and i.received_at > now() - interval '7 days'",
        (person,)).fetchone() or {"waiting": 0, "today": 0}
    mb = 1024 * 1024
    if held["waiting"] >= WAITING_FILES:
        return words.say(language, HOLDS, waiting=held["waiting"])
    if held["today"] + adding > FILES_A_DAY:
        return words.say(language, SENT_TODAY, today=f"{held['today'] / mb:.0f}",
                         most=FILES_A_DAY // mb)
    return None


class Small:
    """Refuses a body bigger than one message needs, before reading any of it. It's plain
    ASGI, so the endpoints still hear when someone has gone."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["method"] in ("POST", "PUT"):
            size = dict(scope["headers"]).get(b"content-length", b"")
            most = MAX_UPLOAD if scope.get("path") == "/channels/local/messages" else MAX_BYTES
            if not size.isdigit() or int(size) > most:
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
          "Slack": gw.slack is not None, "Matrix": gw.matrix is not None}
    return [chat for chat, is_on in on.items() if is_on]


def create_app(gw: Any) -> FastAPI:
    """The core's endpoints for channels: the only part of the core people reach."""
    explorer = gw.cfg.development  # FastAPI's explorer pages load scripts from a CDN
    app = FastAPI(title="a5s channels", docs_url="/docs" if explorer else None,
                  redoc_url="/redoc" if explorer else None)

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

    def wrong_in_teams(activity: dict[str, Any]) -> Response:
        """Teams' 👎 on an agent's answer, with what they wrote in its form, if anything, for
        the agent's owners (core/feedback.py). Teams asks for an answer to show them."""
        raw = activity.get("value")
        value: dict[str, Any] = raw if isinstance(raw, dict) else {}
        raw = value.get("actionValue")
        acted: dict[str, Any] = raw if isinstance(raw, dict) else {}
        said = acted.get("feedback")
        try:
            said = json.loads(said).get("feedbackText") if isinstance(said, str) else None
        except (ValueError, AttributeError):
            said = None
        entra = (activity.get("from") or {}).get("aadObjectId")
        person = gw.scenario.find(f"entra:{entra}") if entra else None
        told = "Thanks."
        conversation = (activity.get("conversation") or {}).get("id")
        if (value.get("actionName") == "feedback" and acted.get("reaction") == "dislike"
                and person is not None and activity.get("replyToId") and conversation):
            with db.transaction(gw.url) as conn:  # in this conversation: Teams' ids are its own
                found = feedback.sent(conn, "teams", f"{conversation}/{activity['replyToId']}")
                try:
                    if found is not None and feedback.record(
                            conn, found["id"], person.id, said if isinstance(said, str) else None,
                            "teams") is not None:
                        told = feedback.noted(conn, person)
                except feedback.Refused:
                    pass
        return JSONResponse({"statusCode": 200, "type": "application/vnd.microsoft.activity.message",
                             "value": told})

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
        if activity.get("type") == "invoke" and activity.get("name") == "message/submitAction":
            return wrong_in_teams(activity)  # Teams' buttons on an agent's answer
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
                       members=everyone or None, sent=message.files)
        return Response(status_code=200)

    # Slack: each agent's app sends what's said in the conversations it's in, signed

    def tell_in_slack(reply_to: dict[str, str], text: str, user: str | None = None) -> None:
        try:
            if gw.slack is not None:
                (gw.slack.whisper(reply_to, user, text) if user else gw.slack.send(reply_to, text))
        except Exception:
            log.exception("couldn't answer in Slack")

    def wrong_in_slack(payload: dict[str, Any], bot: Any, background: BackgroundTasks) -> None:
        """A 👎 on an agent's answer in Slack, from whom it answered or someone in the group DM
        it was said in (core/feedback.py): kept, and they're told privately what that means."""
        raw = payload.get("event")
        event: dict[str, Any] = raw if isinstance(raw, dict) else {}
        raw = event.get("item")
        item: dict[str, Any] = raw if isinstance(raw, dict) else {}
        if item.get("type") != "message" or not feedback.wrong("slack", str(event.get("reaction") or "")):
            return
        assert gw.slack is not None
        person = gw.scenario.find(f"slack:{gw.slack.cfg.team_id}/{event.get('user')}")
        if person is None:
            return
        with db.transaction(gw.url) as conn:
            found = feedback.sent(conn, "slack", f"{item.get('channel')}/{item.get('ts')}")
            try:
                made = found is not None and feedback.record(conn, found["id"], person.id, None,
                                                             "slack") is not None
            except feedback.Refused:
                made = False
            told = feedback.noted(conn, person)
        if made:
            background.add_task(tell_in_slack, {"channel": str(item.get("channel")),
                                                "app_id": bot.app_id},
                                told, str(event.get("user")))

    def slack_events(body: bytes, timestamp: str | None, signature: str | None,
                     background: BackgroundTasks) -> Response:
        slack = gw.slack
        assert slack is not None
        try:
            bot, payload = slack.check(body, timestamp, signature)
        except SlackRefused as exc:  # not recorded: anyone on the internet can send these
            log.warning("refused a request for Slack: %s", exc.reason)
            raise HTTPException(exc.status, exc.reason) from None
        if payload.get("type") == "url_verification":  # as an app's events are set up
            return JSONResponse({"challenge": str(payload.get("challenge") or "")})
        if payload.get("type") != "event_callback":
            return Response(status_code=200)
        if (payload.get("event") or {}).get("type") == "reaction_added":
            wrong_in_slack(payload, bot, background)  # a 👎 on an agent's answer
            return Response(status_code=200)
        message = slack.message(payload, gw.scenario, bot)
        if message is None or not message.mentioned:  # in a group DM, only what mentions it
            return Response(status_code=200)
        people = [message.person] if message.person else []
        members: list[str | None] = []
        strangers: list[str] = []
        if message.group and message.person:  # who's in it, from Slack itself, at each message
            try:
                members = slack.members(message.reply_to, gw.scenario, strangers)
            except (httpx.HTTPError, ValueError) as exc:  # recorded, and said, not dropped
                log.warning("couldn't read who's in a Slack group DM: %s", exc)
                with db.transaction(gw.url) as conn:
                    turned_away(conn, "slack", "a5s couldn't read who's in the chat",
                                people, message.text)
                background.add_task(tell_in_slack, message.reply_to, groups.UNREAD)
                return Response(status_code=200)
        everyone = (sorted({p for p in (message.person, *members) if p})
                    if message.group and message.person and None not in members else [])
        with db.transaction(gw.url) as conn:
            if message.person is None:
                turned_away(conn, "slack", f"the directory doesn't know "
                            f"slack:{slack.cfg.team_id}/{message.user}", people, message.text)
                background.add_task(tell_in_slack, message.reply_to, UNKNOWN,
                                    None if message.personal else message.user)
            elif not message.personal and not message.group:  # a channel, public or private
                turned_away(conn, "slack", "a5s works in direct messages and group DMs, not "
                            "channels", people, message.text)
                background.add_task(tell_in_slack, message.reply_to, SLACK_CHANNELS, message.user)
            elif message.group and len({message.person, *members}) > groups.LIMIT:  # before naming
                turned_away(conn, "slack", f"the group has more than {groups.LIMIT} people",
                            people, message.text)
                background.add_task(tell_in_slack, message.reply_to, groups.TOO_MANY)
            elif message.group and not everyone:
                turned_away(conn, "slack", "someone in the group isn't in the directory", people,
                            message.text)
                background.add_task(tell_in_slack, message.reply_to, groups.STRANGERS.format(
                    who=groups.listed(strangers) if strangers else "someone here"))
            else:  # Slack's message times are unique only within a conversation
                record(conn, channel="slack",
                       source_id=f"{message.reply_to['channel']}/{message.reply_to['ts']}",
                       person=message.person, agent=message.agent, text=message.text,
                       reply_to=message.reply_to, identity="verified by slack",
                       place=message.reply_to["channel"] if message.group else None,
                       members=everyone or None, sent=message.files)
        return Response(status_code=200)

    @app.post("/channels/slack/events")
    async def slack_event(request: Request, background: BackgroundTasks,
                          x_slack_request_timestamp: str | None = Header(default=None),
                          x_slack_signature: str | None = Header(default=None)) -> Response:
        """What Slack sends an agent's app, its signature checked over the body as it came."""
        if gw.slack is None:
            raise HTTPException(404, "Slack isn't set up")
        body = await request.body()
        return await run_in_threadpool(slack_events, body, x_slack_request_timestamp,
                                       x_slack_signature, background)

    @app.post("/channels/slack/actions")
    async def slack_action(request: Request,
                           x_slack_request_timestamp: str | None = Header(default=None),
                           x_slack_signature: str | None = Header(default=None)) -> Response:
        """Someone choosing a card's button, which only opens its page, where they decide:
        acknowledged once Slack's signature checks out, and nothing done."""
        if gw.slack is None:
            raise HTTPException(404, "Slack isn't set up")
        body = await request.body()
        try:
            gw.slack.check(body, x_slack_request_timestamp, x_slack_signature)
        except SlackRefused as exc:
            raise HTTPException(exc.status, exc.reason) from None
        return Response(status_code=200)

    # Events: other systems tell a5s something happened, signed with their own secret

    def receiving_event(source: str, body: bytes, timestamp: str | None,
                        signature: str | None) -> Response:
        cfg = gw.events
        assert cfg is not None
        try:
            event = events.check(cfg, source, body, timestamp, signature)
        except events.Refused as exc:  # not recorded: anyone on the internet can send these
            log.warning("refused an event from %r: %r", source[:40], exc.reason[:200])
            raise HTTPException(exc.status, exc.reason) from None
        if not events.takers(gw.definitions, source, event["type"]):
            raise HTTPException(404, f"no agent here takes {event['type']} events from {source}")
        with db.transaction(gw.url) as conn:
            if events.waiting(conn, source) >= events.MOST_WAITING:
                raise HTTPException(429, f"{events.MOST_WAITING} of {source}'s events wait "
                                         "already: send this one again later")
            kept = events.record(conn, gw.scenario, source, event)
        return JSONResponse({"event": event["id"], "kept": kept}, status_code=202 if kept else 200)

    @app.post("/channels/events/{source}")
    async def event_received(source: str, request: Request,
                             x_a5s_timestamp: str | None = Header(default=None),
                             x_a5s_signature: str | None = Header(default=None)) -> Response:
        """An event another system sent, such as a ticket opened: checked against that
        system's signing secret before a word of it is read, kept once by its own id, for the
        core to open the run of the agent whose release takes it (core/events.py). The same
        event sent again is answered as kept already."""
        if gw.events is None:
            raise HTTPException(404, "a5s takes no events here")
        body = await request.body()
        return await run_in_threadpool(receiving_event, source, body, x_a5s_timestamp,
                                       x_a5s_signature)

    # Matrix: the homeserver sends what happens in the rooms the agents' bots are in

    def homeserver(authorization: str | None = Header(default=None),
                   access_token: str | None = None) -> None:
        """The homeserver's own token, which every route of Matrix's needs."""
        if gw.matrix is None:
            raise HTTPException(404, "Matrix isn't set up")
        try:
            gw.matrix.check(authorization, access_token)
        except matrix.Refused as exc:  # not recorded: anyone could send these
            log.warning("refused a delivery from Matrix: %s", exc.reason)
            raise HTTPException(exc.status, {"errcode": "M_FORBIDDEN", "error": exc.reason}) from None

    matrix_api = APIRouter(dependencies=[Depends(homeserver)])

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

    @matrix_api.put("/channels/matrix/_matrix/app/v1/transactions/{txn}")
    def matrix_transaction(txn: str, body: dict[str, Any], background: BackgroundTasks) -> dict:
        agents = sorted(gw.definitions)

        def act(event: dict[str, Any]) -> None:
            what, detail = gw.matrix.event(event, gw.scenario, agents)
            if what == "join":
                gw.matrix.join(*detail)
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
                           members=list(detail.members), sent=detail.files)
            elif what == "left":  # so a5s writes to them elsewhere, and doesn't ask them back
                with db.transaction(gw.url) as conn:
                    chats.left(conn, "matrix", *detail)
            elif what == "shared":  # someone joined their own chat: a5s writes first elsewhere
                with db.transaction(gw.url) as conn:
                    chats.shared(conn, "matrix", *detail)
            elif what == "wrong":  # a 👎 on an agent's answer (core/feedback.py)
                person, said_to, room = detail
                with db.transaction(gw.url) as conn:
                    found = feedback.sent(conn, "matrix", said_to)
                    row = conn.execute("select o.route, i.conversation from outbox o left join "
                                       "inbound i on i.id = o.inbound_id where o.id = %s",
                                       (found["id"],)).fetchone() if found else None
                    reply_to = (row["route"] or {}).get("reply_to") or {} if row else {}
                    try:
                        made = (found is not None and reply_to.get("room") == room
                                and feedback.record(conn, found["id"], person, None,
                                                    "matrix") is not None)
                    except feedback.Refused:
                        made = False
                    told = feedback.noted(conn, gw.scenario.person(person))
                if made and reply_to.get("bot") and row and row["conversation"] is None:
                    background.add_task(tell_in_matrix, {"room": room, "bot": reply_to["bot"]},
                                        told)  # in their own chat: a group's isn't told

        for event in body.get("events") or []:
            key = str(event.get("event_id") or "") if isinstance(event, dict) else ""
            try:
                act(event)
            except Exception as exc:  # one event never holds up every later one for long
                failed = failures[key] = failures.get(key, 0) + 1
                server = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500
                if not server and failed < TRIES:  # the homeserver sends it all again later
                    raise
                # It sends nothing more until this delivery is taken, so one event a5s can't act
                # on is skipped, and recorded: an invitation withdrawn before a5s joined, one
                # room it can't read three times running, or one it can't read at all, such as a
                # file whose size isn't a number
                log.warning("skipped a Matrix event: %s", type(exc).__name__)
                failures.pop(key, None)
                with db.transaction(gw.url) as conn:
                    turned_away(conn, "matrix", f"a5s couldn't act on it: {type(exc).__name__}",
                                [], "")
        return {}

    @matrix_api.get("/channels/matrix/_matrix/app/v1/users/{user}")
    def matrix_user(user: str) -> JSONResponse:
        """Whether a bot exists, made on demand, such as when someone first invites it."""
        if gw.matrix.agent_of(user) not in gw.definitions:
            return JSONResponse(status_code=404, content={"errcode": "M_NOT_FOUND"})
        gw.matrix.register(user)
        return JSONResponse({})

    @matrix_api.get("/channels/matrix/_matrix/app/v1/rooms/{alias}")
    def matrix_room(alias: str) -> JSONResponse:
        return JSONResponse(status_code=404, content={"errcode": "M_NOT_FOUND"})

    @matrix_api.post("/channels/matrix/_matrix/app/v1/ping")
    def matrix_ping() -> dict:
        return {}

    app.include_router(matrix_api)

    # The local channel, for the command line and the web chat

    def spoke(agent: str, run: Any, written_by: str | None = None) -> dict:
        """Who a message a5s sent is by: a run's is its agent's, one someone of a team wrote
        while the conversation was handed over is theirs, and any other is a5s's own. `by`
        says which, whatever the agent or they are called, so no name passes for another's."""
        if written_by:
            who = gw.scenario.person(written_by)
            return {"from": who.name if who else written_by, "by": "team"}
        return {"from": agent, "by": "agent"} if run else {"from": "a5s", "by": "a5s"}

    def sender(authorization: str | None, claimed: str | None) -> tuple[str, str]:
        """Who's writing, and how a5s knows (core/web.py)."""
        return web.sender(gw, authorization, claimed)

    @app.post("/channels/local/messages", status_code=202)
    def local_message(body: LocalMessage, authorization: str | None = Header(default=None)) -> dict:
        person, identity = sender(authorization, body.person)
        try:  # each file's kind as the browser says it, or by its name, where it's none a5s reads
            sent = [files.File(name=f.name[:200], media_type=files.media_type(f.name, f.type),
                               data=base64.b64decode(f.data, validate=True)) for f in body.files]
        except (binascii.Error, ValueError):
            raise HTTPException(400, "a file's data is its bytes in base64") from None
        text = body.text if body.text.strip() or not sent else files.WORDS_ONLY
        with db.transaction(gw.url) as conn:
            who = gw.scenario.person(person)
            if sent and (why := holding(conn, person, sum(len(f.data or b"") for f in sent),
                                        languages.of(who) if who else languages.ENGLISH)):
                raise HTTPException(429, why)
            inbound = record(conn, channel="local", source_id=str(uuid.uuid4()), person=person,
                             agent=body.agent, text=text, reply_to={}, identity=identity,
                             sent=sent)
        return {"message": inbound}

    @app.post("/channels/local/feedback")
    def local_feedback(body: Said, authorization: str | None = Header(default=None)) -> dict:
        """That an agent's answer in the web chat was wrong, with why, in their words, for its
        owners (core/feedback.py): whether it's newly kept."""
        person, _ = sender(authorization, body.person)
        with db.transaction(gw.url) as conn:
            row = conn.execute("select channel from outbox where id = %s", (body.message,)).fetchone()
            try:
                if row is None or row["channel"] != "local":
                    raise feedback.Refused("that isn't an agent's answer")
                made = feedback.record(conn, body.message, person, body.said, "local")
            except feedback.Refused as exc:
                raise HTTPException(404, str(exc)) from None
            told = feedback.noted(conn, gw.scenario.person(person))
        return {"noted": made is not None, "said": told}

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
                "messages": [{**spoke(r["agent"], r["run_id"]), "id": r["id"], "text": r["text"],
                              "at": r["at"].isoformat()} for r in said]}

    @app.get("/channels/local/agents")
    def local_agents(person: str | None = None,
                     authorization: str | None = Header(default=None)) -> dict:
        """The agents someone may talk to here: those an instance of serves them. Any other,
        they find in the studio, as far as they may know of it, and ask for there."""
        who, _ = sender(authorization, person)
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select definition, serves from instances "
                                "where status in ('active', 'suspended')").fetchall()
        listed: dict = {"agents": sorted({r["definition"] for r in rows
                                          if r["definition"] in gw.definitions
                                          and registry.serving(gw.scenario, r["serves"], who)})}
        if gw.cfg.development and not rows:  # none at work here at all, so the chat says to
            listed["at_work"] = False  # apply the settings first
        return listed

    @app.get("/channels/local/conversation")
    def conversation(agent: str, limit: int = 50, person: str | None = None,
                     authorization: str | None = Header(default=None)) -> dict:
        """A person's latest messages with an agent through this channel, and what came back."""
        who, _ = sender(authorization, person)
        with db.transaction(gw.url) as conn:
            rows = conn.execute(
                """
                select * from (
                  select 'person' as kind, text, received_at as at, null::uuid as run_id, 0 as n,
                         null as written_by
                  from inbound where person = %(who)s and agent = %(agent)s and channel = 'local'
                  union all
                  select 'agent', o.text, o.at, o.run_id, o.id, o.written_by
                  from outbox o where o.person = %(who)s and o.channel = 'local' and o.agent = %(agent)s
                ) said order by at desc, n desc limit %(limit)s
                """, {"who": who, "agent": agent, "limit": min(max(limit, 1), 200)}).fetchall()
            # What the agent does, for the first words of a conversation with it, to someone
            # it serves alone: an agent nobody's told them of stays as unknown as before
            served = any(registry.serving(gw.scenario, i["serves"], who) for i in conn.execute(
                "select serves from instances where definition = %s and status in "
                "('active', 'suspended')", (agent,)))
        definition = gw.definitions.get(agent)
        return {"messages": [{**({"from": "you", "by": "person"} if r["kind"] == "person"
                                 else {**spoke(agent, r["run_id"], r["written_by"]),
                                       "id": r["n"]}),
                              "text": r["text"], "at": r["at"].isoformat()} for r in reversed(rows)],
                "does": definition.does if definition and served else None}

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
                    "returning id, run_id, instance_id, agent, text, at, written_by",
                    (who,)).fetchall()

        return {"messages": [  # a run's message is its agent's; any other is a5s's own
            {**spoke(r["agent"], r["run_id"], r["written_by"]), "id": r["id"], "about": r["agent"],
             "instance": r["instance_id"], "text": r["text"], "at": r["at"].isoformat()}
            for r in sorted(await waiting(request, wait, take), key=lambda r: r["id"])]}

    # The web chat (core/chat_api.py), which talks to the agents through the local channel
    app.include_router(chat_api.router(gw))

    # Where the studio signs people in, for its pages and for each act (core/web.py)
    app.include_router(web.signing(gw, "/studio/sign-in"))

    # The acts people sign in afresh for, each a router of its own whose act's route checks its
    # sign-in, and whose page is the studio's: approving a version of the settings
    # (core/approve_api.py), the officer's requests, deciding held changes, and grading samples
    for acts in (approve_api, officer_api, decide_api, grade_api):
        app.include_router(acts.router(gw))

    # The pages people sign in to for one thing, each a router whose API checks who's signed in:
    # the studio's (core/studio_api.py), the settings app's, the notebook's, people's own tasks',
    # the auditors' and the administrators'
    for pages in (studio_api, settings_api, notebook_api, tasks_api, audit_api, admin_api,
                   health_api, status_api):
        app.include_router(pages.router(gw))

    # Every page's sidebar: who signed in, and the pages they may use (core/shell_api.py)
    app.include_router(shell_api.router(gw))

    return app
