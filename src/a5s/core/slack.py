"""Slack, through its Events API: checking what Slack sends, and answering in Slack.

Slack signs each request it sends with the app's signing secret, over the request's time and its
body, so the core checks the signature before it reads a word, and refuses a request more than
five minutes from now, so none can be sent again later (core/inbox.py). Each agent is a Slack app
of its own, so it talks to people as itself, and the core alone holds each app's signing secret
and bot token. People are known by their Slack user ids, which the directory lists as
slack:<workspace>/<user>, never by an email address a workspace could give someone else.

a5s works in direct messages and in group DMs, whose members are those the conversation was
made with, so nobody joins later to read what was said; never in a channel, which anyone who
joins reads back through.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from a5s import config
from a5s.contract import Person, Scenario
from a5s.core import files

API = "https://slack.com/api"
WINDOW = 300  # seconds: a request further than this from now is refused, as Slack advises
UNKNOWN = "a5s doesn't know who you are, so no agent can help. Ask whoever runs a5s to add you."
CHANNELS = ("a5s works in direct messages and group DMs, not in channels, where anyone who "
            "joins reads what was said before. Write to the agent directly, or start a group "
            "DM with the people it should help.")
_USER = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")  # a mention of someone, as Slack spells it
_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")
_CHANNEL = re.compile(r"<#[CG][A-Z0-9]+\|([^>]*)>")
_SPECIAL = re.compile(r"<!(here|channel|everyone)[^>]*>")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
TYPED = (None, "file_share", "thread_broadcast")  # what a person typed: its words, and files
FILE_HOSTS = frozenset({"files.slack.com"})  # where a5s fetches what people share, and nowhere else
BLOCK = 3000  # the most a block's text may hold, in Slack's Block Kit


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class Bot:
    """An agent's own app in Slack: each agent talks to people as itself."""

    agent: str
    app_id: str  # Slack's id for the app, as each event names it
    signing_secret: str = field(repr=False)
    token: str = field(repr=False)  # its bot's token, xoxb-...


@dataclass(frozen=True)
class SlackConfig:
    bots: tuple[Bot, ...]
    team_id: str  # the organisation's workspace: events from any other are refused
    api: str = API

    @classmethod
    def from_env(cls) -> SlackConfig | None:
        """Each agent's app from A5S_SLACK_BOTS, a JSON list of {"agent", "app_id",
        "secret_env", "token_env"}, its signing secret and bot token each in the variable it
        names; None where Slack isn't turned on."""
        listed = config.SLACK_BOTS.read()
        if not listed:
            return None
        bots = tuple(Bot(b["agent"], b["app_id"], os.environ[b["secret_env"]],
                         os.environ[b["token_env"]]) for b in listed)
        if not (team := config.SLACK_TEAM.read()):
            raise config.ConfigError(f"Slack needs {config.SLACK_TEAM.name}")
        return cls(bots=bots, team_id=team, api=config.SLACK_API.read())


@dataclass(frozen=True)
class Message:
    """A message from Slack that checked out, who sent it, and to which agent."""

    person: str | None  # None when the directory doesn't know them
    agent: str
    user: str  # their Slack user id
    text: str
    reply_to: dict[str, str]
    kind: str  # Slack's channel type: im, mpim, channel or group (a private channel)
    mentioned: bool  # whether it mentions the agent, as a message in a group DM must
    files: tuple[files.File, ...] = ()  # what they shared with it, for a5s's reader

    @property
    def personal(self) -> bool:
        return self.kind == "im"

    @property
    def group(self) -> bool:
        return self.kind == "mpim"


def mrkdwn(text: str) -> str:
    """a5s's words as Slack shows them: with &, < and > escaped, so nothing in them can mention
    everyone, or anyone, or link anywhere Slack would show; then the scenario's record links, as
    a5s's outgoing text keeps them, and bold, in Slack's own marks."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    linked = _MD_LINK.sub(lambda m: f"<{m.group(2)}|{m.group(1)}>", escaped)
    return _BOLD.sub(lambda m: f"*{m.group(1)}*", linked)


def blocks(card: dict) -> list[dict]:
    """An Adaptive Card, such as an approval's, as Slack's Block Kit draws it: its words, and each
    of its links as a button that only opens its page, where people decide, signed in afresh."""
    found: list[dict] = []
    for item in card.get("body") or []:
        if item.get("type") == "TextBlock" and str(item.get("text") or "").strip():
            said = _fit(mrkdwn(str(item["text"])), BLOCK - 2)
            if item.get("weight") == "Bolder":
                said = f"*{said}*"
            kind = "context" if item.get("isSubtle") else "section"
            found.append({"type": "context", "elements": [{"type": "mrkdwn", "text": said}]}
                         if kind == "context" else
                         {"type": "section", "text": {"type": "mrkdwn", "text": said}})
    buttons = [{"type": "button", "text": {"type": "plain_text", "text": str(a["title"])[:75]},
                "url": str(a["url"]), "action_id": f"open-{n}"}
               for n, a in enumerate(card.get("actions") or [])
               if a.get("type") == "Action.OpenUrl" and a.get("title") and a.get("url")]
    found = found[:45]  # Slack takes 50 blocks a message
    if buttons:
        found.append({"type": "actions", "elements": buttons[:25]})
    return found


def _fit(text: str, most: int) -> str:
    """Text cut to what Slack takes, saying so, rather than a message Slack refuses whole."""
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


class Slack:
    def __init__(self, cfg: SlackConfig, http: httpx.Client | None = None):
        self.cfg = cfg
        self.bots = {bot.app_id: bot for bot in cfg.bots}
        self.http = http or httpx.Client(timeout=30)
        self._users: dict[str, str] = {}  # each app's bot user, as Slack knows it
        self._lock = threading.Lock()

    # What Slack sends

    def check(self, body: bytes, timestamp: str | None, signature: str | None,
              now: float | None = None) -> tuple[Bot, dict[str, Any]]:
        """The app Slack sent this to, and what it sent, or Refused if Slack didn't send it,
        lately, for this organisation's workspace. A signature is v0, an HMAC-SHA256 of the
        request's time and body under one of the apps' signing secrets."""
        if not timestamp or not signature or not signature.startswith("v0="):
            raise Refused(401, "Slack signs what it sends")
        try:
            sent = int(timestamp)
        except ValueError:
            raise Refused(401, "the request's time isn't one") from None
        if abs((time.time() if now is None else now) - sent) > WINDOW:
            raise Refused(401, "the request was signed more than five minutes from now")
        base = b"v0:" + timestamp.encode() + b":" + body
        bot = next((b for b in self.cfg.bots if hmac.compare_digest(
            "v0=" + hmac.new(b.signing_secret.encode(), base, hashlib.sha256).hexdigest(),
            signature)), None)
        if bot is None:
            raise Refused(403, "the signature isn't any of a5s's apps'")
        payload = self._payload(body)
        if payload.get("api_app_id", bot.app_id) != bot.app_id:
            raise Refused(403, "the request names another app than the one that signed it")
        team = payload.get("team_id") or (payload.get("team") or {}).get("id")
        if payload.get("type") != "url_verification" and team != self.cfg.team_id:
            raise Refused(403, "the request is from another workspace")
        return bot, payload

    @staticmethod
    def _payload(body: bytes) -> dict[str, Any]:
        """What a request says: an event's JSON, or an interaction's, which Slack sends as a
        form with the JSON in its payload."""
        try:
            if body.startswith(b"{"):
                found = json.loads(body)
            else:
                found = json.loads(parse_qs(body.decode())["payload"][0])
        except (ValueError, KeyError, UnicodeDecodeError):
            raise Refused(400, "a5s can't read what was sent") from None
        if not isinstance(found, dict):
            raise Refused(400, "a5s can't read what was sent")
        return found

    def said(self, text: str, scenario: Scenario, bot_user: str | None) -> str:
        """What someone typed, without their mention of the agent, each other person they
        mention as the directory names them, and links and channels as words."""
        if bot_user:
            text = re.sub(rf"<@{re.escape(bot_user)}(?:\|[^>]*)?>", "", text, count=1)

        def person(found: re.Match[str]) -> str:
            who = scenario.find(f"slack:{self.cfg.team_id}/{found.group(1)}")
            return f"@{who.name}" if who else "@someone"
        text = _USER.sub(person, text)
        text = _CHANNEL.sub(lambda m: f"#{m.group(1)}", text)
        text = _SPECIAL.sub(lambda m: f"@{m.group(1)}", text)
        text = _LINK.sub(lambda m: f"{m.group(2)} ({m.group(1)})" if m.group(2) else m.group(1), text)
        return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").strip()

    def message(self, payload: dict[str, Any], scenario: Scenario, bot: Bot) -> Message | None:
        """The message in an event that checked out, if it's one a person typed, its words alone
        where they sent a file with them: never one an app sent, the agents' own among them, nor
        an edit, a deletion or someone joining."""
        event = payload.get("event") or {}
        kind = event.get("type")
        if kind not in ("message", "app_mention") or event.get("subtype") not in TYPED \
                or event.get("bot_id"):
            return None
        user, channel = str(event.get("user") or ""), str(event.get("channel") or "")
        if not user or not channel or not event.get("ts"):
            return None
        mine = self.bot_user(bot, payload)
        if user == mine:
            return None
        if kind == "app_mention":  # wherever it's mentioned: a5s answers in a channel only to
            channel_type = self.kind_of(bot, channel)  # say it isn't for channels; a DM's or a
            if channel_type in ("im", "mpim"):  # group DM's mention comes as its message too
                return None
        else:
            channel_type = str(event.get("channel_type") or "")
        raw = str(event.get("text") or "")
        shared = tuple(files.File(
            name=str(f.get("name") or "a file"), media_type=files.media_type(
                str(f.get("name") or ""), f.get("mimetype")), size=f.get("size"),
            fetch={"channel": "slack", "app_id": bot.app_id,
                   "url": str(f.get("url_private_download") or f.get("url_private") or "")})
            for f in event.get("files") or [] if isinstance(f, dict))
        text = self.said(raw, scenario, mine) or (files.WORDS_ONLY if shared else "")
        if not text:
            return None
        person = scenario.find(f"slack:{self.cfg.team_id}/{user}")
        thread = event.get("thread_ts")
        return Message(
            person=person.id if person else None, agent=bot.agent, user=user, text=text,
            reply_to={"channel": channel, "app_id": bot.app_id, "ts": str(event["ts"]),
                      **({"thread": str(thread)} if thread else {})},
            kind=channel_type,
            mentioned=channel_type == "im" or bool(mine and f"<@{mine}" in raw), files=shared)

    def kind_of(self, bot: Bot, channel: str) -> str:
        """What kind of conversation a channel id is, as Slack says: im, mpim, group (a private
        channel) or channel; a channel, if Slack can't say, so a5s says it isn't for one."""
        try:
            found = self._call(bot, "conversations.info", {"channel": channel}).get("channel") or {}
        except (httpx.HTTPError, ValueError):
            return "channel"
        return ("im" if found.get("is_im") else "mpim" if found.get("is_mpim") else
                "group" if found.get("is_private") else "channel")

    def bot_user(self, bot: Bot, payload: dict[str, Any] | None = None) -> str | None:
        """The user an app's bot is in Slack, from the event's authorizations, or else as Slack
        says when asked once (auth.test)."""
        if bot.app_id in self._users:
            return self._users[bot.app_id]
        for found in (payload or {}).get("authorizations") or []:
            if found.get("is_bot") and found.get("user_id"):
                self._users[bot.app_id] = str(found["user_id"])
                return self._users[bot.app_id]
        try:
            answer = self._call(bot, "auth.test", {})
        except (httpx.HTTPError, ValueError):
            return None
        if user := answer.get("user_id"):
            self._users[bot.app_id] = str(user)
        return self._users.get(bot.app_id)

    def members(self, reply_to: dict[str, str], scenario: Scenario,
                strangers: list[str] | None = None) -> list[str | None]:
        """Who's in a group DM, as Slack says, as the app it was sent to: each person by their
        id in the directory, or None for someone it doesn't know, whose name, as Slack shows it,
        goes in `strangers`. a5s's own bots aren't people; any other app in the conversation,
        which may read what's said there, is someone the directory doesn't know."""
        bot = self._bot(reply_to)
        ours = {u for b in self.cfg.bots if (u := self.bot_user(b))}
        found: list[str | None] = []
        cursor = ""
        while True:
            answer = self._call(bot, "conversations.members",
                                {"channel": reply_to["channel"], "limit": 200,
                                 **({"cursor": cursor} if cursor else {})})
            for user in answer.get("members") or []:
                if user in ours:
                    continue
                person = scenario.find(f"slack:{self.cfg.team_id}/{user}")
                found.append(person.id if person else None)
                if person is None and strangers is not None:
                    strangers.append(self._name(bot, str(user)))
            cursor = str((answer.get("response_metadata") or {}).get("next_cursor") or "")
            if not cursor:
                return found

    def _name(self, bot: Bot, user: str) -> str:
        try:
            profile = self._call(bot, "users.info", {"user": user}).get("user") or {}
        except (httpx.HTTPError, ValueError):
            return "someone"
        return str(profile.get("real_name") or profile.get("name") or "someone")

    # Where a5s writes

    def user_of(self, person: Person) -> str | None:
        """Someone's Slack user, in this organisation's workspace, as the directory lists it."""
        prefix = f"slack:{self.cfg.team_id}/"
        return next((i.removeprefix(prefix) for i in person.identities if i.startswith(prefix)), None)

    def person_of(self, user: str, scenario: Scenario) -> Person | None:
        return scenario.find(f"slack:{self.cfg.team_id}/{user}")

    def start(self, user: str, agent: str) -> dict[str, str]:
        """A direct message between an agent's app and someone, which its bot opens to write to
        them first: where to send to it."""
        bot = next((b for b in self.cfg.bots if b.agent == agent), None)
        if bot is None:
            raise ValueError(f"the {agent} has no app in Slack")
        answer = self._call(bot, "conversations.open", {"users": user})
        channel = (answer.get("channel") or {}).get("id")
        if not channel:
            raise ValueError("Slack opened no conversation")
        return {"channel": str(channel), "app_id": bot.app_id}

    def send(self, reply_to: dict[str, str], text: str, card: dict | None = None) -> None:
        """Send text into the conversation a message came from, as the app it was sent to, in
        its thread if it was in one; with a card, its blocks go too, and the text is what
        notifications show."""
        bot = self._bot(reply_to)
        sent: dict[str, Any] = {"channel": reply_to["channel"], "text": mrkdwn(text),
                                "unfurl_links": False, "unfurl_media": False}
        if reply_to.get("thread"):
            sent["thread_ts"] = reply_to["thread"]
        if card is not None and (drawn := blocks(card)):
            sent["text"] = mrkdwn(text.split("\n", 1)[0])
            sent["blocks"] = drawn
        self._call(bot, "chat.postMessage", sent)

    def whisper(self, reply_to: dict[str, str], user: str, text: str) -> None:
        """Say something to one person in a conversation, seen by them alone, such as that a5s
        isn't for channels, so the channel never hears it."""
        self._call(self._bot(reply_to), "chat.postEphemeral",
                   {"channel": reply_to["channel"], "user": user, "text": mrkdwn(text)})

    def download(self, where: dict[str, Any]) -> bytes:
        """A file someone shared, as the app it was sent to, from Slack's own file host alone,
        so the app's token goes nowhere else."""
        url = str(where.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in FILE_HOSTS:
            raise ValueError("a5s fetches shared files from Slack's own file host alone")
        bot = self._bot({"app_id": str(where.get("app_id") or "")})
        return files.download(self.http, url, {"Authorization": f"Bearer {bot.token}"})

    def _bot(self, reply_to: dict[str, str]) -> Bot:
        bot = self.bots.get(reply_to.get("app_id", ""))
        if bot is None:
            raise ValueError("the message came to an app a5s no longer has")
        return bot

    def _call(self, bot: Bot, method: str, args: dict[str, Any]) -> dict[str, Any]:
        """One of Slack's Web API methods, as an agent's bot, its answer checked: Slack says
        a method failed in its answer, not its status. A refusal for now, such as its rate
        limit, raises, so the outbox tries again later."""
        form = {k: json.dumps(v) if isinstance(v, list | dict) else
                str(v).lower() if isinstance(v, bool) else str(v) for k, v in args.items()}
        r = self.http.post(f"{self.cfg.api.rstrip('/')}/{method}", data=form,
                           headers={"Authorization": f"Bearer {bot.token}"})
        r.raise_for_status()
        answer = r.json()
        if not isinstance(answer, dict) or not answer.get("ok"):
            raise ValueError(f"Slack's {method} said {answer.get('error') if isinstance(answer, dict) else answer}")
        return answer
