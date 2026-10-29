"""Teams, through the Bot Framework: checking what Teams sends, and answering in Teams.

Teams vouches for a message with a token that doesn't cover the message's
body, so anything that held the token could change who a message says it's
from. That's why the core, not a service, receives messages from Teams
(core/inbox.py). It checks the token, the channel and the tenant, and finds the
sender in the directory by their Entra ID. Replies go back from the core too,
which alone holds the bot's credentials.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from a5s.contract import Scenario
from a5s.core.identity import IdentityConfig, IdentityError, Verifier

BOT_FRAMEWORK = "https://api.botframework.com"
METADATA = "https://login.botframework.com/v1/.well-known/openidconfiguration"
UNKNOWN = "a5s doesn't know who you are, so no agent can help. Ask whoever runs a5s to add you."
ONE_TO_ONE = "I only talk one to one for now. Message me directly, and I'll answer there."
_MENTION = re.compile(r"<at>.*?</at>", re.DOTALL)


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class Bot:
    """An agent's own identity in Teams: each agent talks to people as itself."""

    agent: str
    app_id: str  # from its Entra ID app registration
    app_secret: str = field(repr=False)


@dataclass(frozen=True)
class TeamsConfig:
    bots: tuple[Bot, ...]
    tenant_id: str  # the organisation's: messages from any other are refused
    service_hosts: tuple[str, ...] = ("smba.trafficmanager.net",)  # where Teams takes replies
    metadata_url: str = METADATA
    login_url: str = "https://login.microsoftonline.com"

    @classmethod
    def from_env(cls) -> TeamsConfig | None:
        """One bot from A5S_TEAMS_APP_ID, or several from A5S_TEAMS_BOTS, a JSON list of
        {"agent", "app_id", "secret_env"}, each secret in the variable it names."""
        if listed := os.environ.get("A5S_TEAMS_BOTS"):
            bots = tuple(Bot(b["agent"], b["app_id"], os.environ[b["secret_env"]])
                         for b in json.loads(listed))
        elif app_id := os.environ.get("A5S_TEAMS_APP_ID"):
            bots = (Bot(os.environ.get("A5S_TEAMS_AGENT", "assistant"), app_id,
                        os.environ["A5S_TEAMS_APP_SECRET"]),)
        else:
            return None
        hosts = os.environ.get("A5S_TEAMS_SERVICE_HOSTS", "smba.trafficmanager.net")
        return cls(bots=bots, tenant_id=os.environ["A5S_TEAMS_TENANT_ID"],
                   service_hosts=tuple(h.strip() for h in hosts.split(",") if h.strip()))


@dataclass(frozen=True)
class Message:
    """A message from Teams that checked out, who sent it, and to which agent."""

    person: str | None  # None when the directory doesn't know them
    agent: str
    entra_id: str
    text: str
    reply_to: dict[str, str]
    personal: bool  # a one-to-one chat with the bot


class Teams:
    def __init__(self, cfg: TeamsConfig, http: httpx.Client | None = None):
        self.cfg = cfg
        self.bots = {bot.app_id: bot for bot in cfg.bots}
        self.http = http or httpx.Client(timeout=30)
        self.verifier = Verifier(  # a token for any of a5s's bots, as the Bot Framework asks
            IdentityConfig(issuer=BOT_FRAMEWORK, audience=tuple(self.bots),
                           metadata_url=cfg.metadata_url, required=("exp", "iss", "aud"),
                           leeway=300),
            self.http)
        self._tokens: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def allowed(self, service_url: str) -> bool:
        url = urlparse(service_url)
        return url.scheme == "https" and url.hostname in self.cfg.service_hosts

    def check(self, activity: dict[str, Any], authorization: str | None) -> Bot:
        """The bot Teams sent this to, or Refused if Teams didn't send it, for this organisation."""
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
        return self.bots[claims["aud"]]

    def message(self, activity: dict[str, Any], scenario: Scenario, bot: Bot) -> Message | None:
        """The message in an activity that checked out, if it's one a person typed."""
        text = _MENTION.sub("", activity.get("text") or "").strip()
        conversation = activity.get("conversation") or {}
        if activity.get("type") != "message" or not text or not conversation.get("id"):
            return None  # such as a typing indicator, or the bot being added
        entra_id = (activity.get("from") or {}).get("aadObjectId") or ""
        person = scenario.find(f"entra:{entra_id}") if entra_id else None
        return Message(
            person=person.id if person else None, agent=bot.agent, entra_id=entra_id, text=text,
            reply_to={"service_url": activity["serviceUrl"], "conversation": conversation["id"],
                      "activity": activity.get("id") or "",
                      "bot": (activity.get("recipient") or {}).get("id") or "",
                      "app_id": bot.app_id},
            personal=conversation.get("conversationType", "personal") == "personal",
        )

    def _bot_token(self, bot: Bot) -> str:
        with self._lock:
            cached = self._tokens.get(bot.app_id)
            if cached and time.monotonic() < cached[1]:
                return cached[0]
            r = self.http.post(f"{self.cfg.login_url}/{self.cfg.tenant_id}/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": bot.app_id,
                "client_secret": bot.app_secret, "scope": f"{BOT_FRAMEWORK}/.default"})
            r.raise_for_status()
            body = r.json()
            self._tokens[bot.app_id] = (body["access_token"],
                                        time.monotonic() + int(body.get("expires_in", 3600)) - 300)
            return body["access_token"]

    def send(self, reply_to: dict[str, str], text: str) -> None:
        """Send text into the conversation a message came from, as the bot it was sent to:
        in reply to the message, if `reply_to` names one, or else as a new message."""
        if not self.allowed(reply_to["service_url"]):  # the bot's token goes nowhere else
            raise ValueError("a5s sends only to the service URLs Teams uses")
        bot = self.bots.get(reply_to.get("app_id", ""))
        if bot is None:
            raise ValueError("the message came to a bot a5s no longer has")
        conversation = quote(reply_to["conversation"], safe="")
        r = self.http.post(
            f"{reply_to['service_url'].rstrip('/')}/v3/conversations/{conversation}/activities",
            headers={"Authorization": f"Bearer {self._bot_token(bot)}"},
            json={"type": "message", "text": text, "textFormat": "markdown",
                  "from": {"id": reply_to["bot"]}, "conversation": {"id": reply_to["conversation"]},
                  **({"replyToId": reply_to["activity"]} if reply_to.get("activity") else {})},
        )
        r.raise_for_status()

