"""Teams, through the Bot Framework. The core receives each message itself.

Teams vouches for a message with a token that doesn't cover the message's
body, so anything that held the token could change who a message says it's
from. That's why the core, not a service, receives messages from Teams. It
checks the token, the channel and the tenant, finds the sender in the directory
by their Entra ID, and records the message before any service sees it. Replies
go back from the core too, which alone holds the bot's credentials.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import Scenario
from a5s.core import ledger
from a5s.core.identity import IdentityConfig, IdentityError, Verifier

log = logging.getLogger(__name__)

BOT_FRAMEWORK = "https://api.botframework.com"
METADATA = "https://login.botframework.com/v1/.well-known/openidconfiguration"
UNKNOWN = "a5s doesn't know who you are, so no agent can help. Ask whoever runs a5s to add you."
ONE_TO_ONE = "I only talk one to one for now. Message me directly, and I'll answer there."
MAX_BYTES = 256 * 1024  # far more than Teams sends in one message
_MENTION = re.compile(r"<at>.*?</at>", re.DOTALL)


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class TeamsConfig:
    app_id: str  # the bot's, from its Entra ID app registration
    app_secret: str = field(repr=False)
    tenant_id: str  # the organisation's: messages from any other are refused
    agent: str = "assistant"  # the agent people talk to through this bot
    service_hosts: tuple[str, ...] = ("smba.trafficmanager.net",)  # where Teams takes replies
    metadata_url: str = METADATA
    login_url: str = "https://login.microsoftonline.com"

    @classmethod
    def from_env(cls) -> TeamsConfig | None:
        app_id = os.environ.get("A5S_TEAMS_APP_ID")
        if not app_id:
            return None
        hosts = os.environ.get("A5S_TEAMS_SERVICE_HOSTS", "smba.trafficmanager.net")
        return cls(
            app_id=app_id,
            app_secret=os.environ["A5S_TEAMS_APP_SECRET"],
            tenant_id=os.environ["A5S_TEAMS_TENANT_ID"],
            agent=os.environ.get("A5S_TEAMS_AGENT", "assistant"),
            service_hosts=tuple(h.strip() for h in hosts.split(",") if h.strip()),
        )


@dataclass(frozen=True)
class Message:
    """A message from Teams that checked out, and who sent it."""

    person: str | None  # None when the directory doesn't know them
    entra_id: str
    text: str
    reply_to: dict[str, str]
    personal: bool  # a one-to-one chat with the bot


class Teams:
    def __init__(self, cfg: TeamsConfig, http: httpx.Client | None = None):
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=30)
        self.verifier = Verifier(
            IdentityConfig(issuer=BOT_FRAMEWORK, audience=cfg.app_id, metadata_url=cfg.metadata_url,
                           required=("exp", "iss", "aud"), leeway=300),  # as the Bot Framework asks
            self.http)
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def allowed(self, service_url: str) -> bool:
        url = urlparse(service_url)
        return url.scheme == "https" and url.hostname in self.cfg.service_hosts

    def check(self, activity: dict[str, Any], authorization: str | None) -> None:
        """Refuse anything Teams didn't send to this bot, for this organisation."""
        if not (authorization or "").startswith("Bearer "):
            raise Refused(401, "Teams sends a bearer token")
        channel = activity.get("channelId") or ""
        try:
            claims = self.verifier.claims(authorization.removeprefix("Bearer ").strip(),
                                          endorsed_for=channel)
        except IdentityError as exc:
            raise Refused(403, f"the token doesn't check out: {exc}") from exc
        service_url = activity.get("serviceUrl") or ""
        if claims.get("serviceurl", claims.get("serviceUrl")) != service_url:
            raise Refused(403, "the token is for another service URL")
        if channel != "msteams":
            raise Refused(403, f"a5s takes messages from Teams, not {channel}")
        tenants = {(activity.get("conversation") or {}).get("tenantId"),
                   ((activity.get("channelData") or {}).get("tenant") or {}).get("id")} - {None}
        if tenants != {self.cfg.tenant_id}:
            raise Refused(403, "the message is from another organisation")
        if not self.allowed(service_url):
            raise Refused(403, "the service URL isn't one Teams uses")

    def message(self, activity: dict[str, Any], scenario: Scenario) -> Message | None:
        """The message in an activity that checked out, if it's one a person typed."""
        text = _MENTION.sub("", activity.get("text") or "").strip()
        conversation = activity.get("conversation") or {}
        if activity.get("type") != "message" or not text or not conversation.get("id"):
            return None  # such as a typing indicator, or the bot being added
        entra_id = (activity.get("from") or {}).get("aadObjectId") or ""
        person = scenario.find(f"entra:{entra_id}") if entra_id else None
        return Message(
            person=person.id if person else None, entra_id=entra_id, text=text,
            reply_to={"service_url": activity["serviceUrl"], "conversation": conversation["id"],
                      "activity": activity.get("id") or "",
                      "bot": (activity.get("recipient") or {}).get("id") or ""},
            personal=conversation.get("conversationType", "personal") == "personal",
        )

    def _bot_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token[1]:
                return self._token[0]
            r = self.http.post(f"{self.cfg.login_url}/{self.cfg.tenant_id}/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": self.cfg.app_id,
                "client_secret": self.cfg.app_secret, "scope": f"{BOT_FRAMEWORK}/.default"})
            r.raise_for_status()
            body = r.json()
            self._token = (body["access_token"],
                           time.monotonic() + int(body.get("expires_in", 3600)) - 300)
            return self._token[0]

    def send(self, reply_to: dict[str, str], text: str) -> None:
        """Send text into the conversation a message came from, as the bot."""
        if not self.allowed(reply_to["service_url"]):  # the bot's token goes nowhere else
            raise ValueError("a5s sends only to the service URLs Teams uses")
        conversation = quote(reply_to["conversation"], safe="")
        r = self.http.post(
            f"{reply_to['service_url'].rstrip('/')}/v3/conversations/{conversation}/activities",
            headers={"Authorization": f"Bearer {self._bot_token()}"},
            json={"type": "message", "text": text, "textFormat": "markdown",
                  "replyToId": reply_to["activity"], "from": {"id": reply_to["bot"]},
                  "conversation": {"id": reply_to["conversation"]}},
        )
        r.raise_for_status()


def create_app(gw: Any) -> FastAPI:
    """The endpoint Teams sends messages to. It's the only part of the core on the internet."""
    teams: Teams = gw.teams
    app = FastAPI(title="a5s Teams endpoint")

    @app.middleware("http")
    async def small(request: Request, call_next: Any) -> Any:
        size = request.headers.get("content-length")
        if size is None or not size.isdigit() or int(size) > MAX_BYTES:
            return JSONResponse(status_code=413, content={"detail": "send one message, as Teams does"})
        return await call_next(request)

    def tell(reply_to: dict[str, str], text: str) -> None:
        try:
            teams.send(reply_to, text)
        except Exception:
            log.exception("couldn't answer in Teams")

    @app.post("/api/messages")
    def receive(activity: dict[str, Any], background: BackgroundTasks,
                authorization: str | None = Header(default=None)) -> Response:
        try:
            teams.check(activity, authorization)
        except Refused as exc:  # not recorded: anyone on the internet can send these
            log.warning("refused a message for Teams: %s", exc.reason)
            raise HTTPException(exc.status, exc.reason) from None
        message = teams.message(activity, gw.scenario)
        if message is None:
            return Response(status_code=200)
        if not message.personal:
            with db.transaction(gw.url) as conn:
                ledger.append(conn, {
                    "kind": "inbound", "action": "teams", "run": None, "instance": None,
                    "acts_for": [message.person] if message.person else [], "decision": "deny",
                    "reasons": ["a5s talks one to one for now"], "args": {"chars": len(message.text)}})
            background.add_task(tell, message.reply_to, ONE_TO_ONE)
            return Response(status_code=200)
        inbound = str(uuid.uuid4())
        with db.transaction(gw.url) as conn:
            fresh = message.person is not None and conn.execute(
                "insert into inbound (id, channel, source_id, person, agent, text, reply_to) "
                "values (%s, 'teams', %s, %s, %s, %s, %s) on conflict do nothing returning id",
                (inbound, message.reply_to["activity"] or inbound, message.person,
                 teams.cfg.agent, message.text, Jsonb(message.reply_to)),
            ).fetchone() is not None
            if message.person is not None and not fresh:
                return Response(status_code=200)  # Teams sent it again; it's answered once
            ledger.append(conn, {
                "kind": "inbound", "action": "teams", "run": None, "instance": None,
                "acts_for": [message.person] if message.person else [],
                "decision": "allow" if fresh else "deny",
                "reasons": [] if fresh else [f"the directory doesn't know entra:{message.entra_id}"],
                "args": {"inbound": inbound if fresh else None, "chars": len(message.text),
                         "sha256": hashlib.sha256(message.text.encode()).hexdigest()},
            })
            if fresh:
                conn.execute("notify a5s_inbound")  # the scheduler takes it from here
        if not fresh:
            background.add_task(tell, message.reply_to, UNKNOWN)
        return Response(status_code=200)

    return app
