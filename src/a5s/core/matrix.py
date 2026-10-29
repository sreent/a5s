"""Matrix, as an application service on the organisation's own homeserver, such as Synapse.

The homeserver sends a5s the events in rooms its agents' bots are in, and proves
each delivery with its token, which only the core holds. Each agent is its own
bot, @a5s-<agent>:<server>. A person invites one to a direct chat, and the core
joins it if the directory knows them by their Matrix id, as matrix:@them:<server>.
An agent that writes to someone first, such as with a reminder, starts a direct
chat itself, as its own bot. People on other servers, rooms with more people, and
encrypted messages, which a5s can't read yet, are turned away. Replies, and a5s's
own notices, reach Matrix only through the core, which alone holds the token that
lets it speak as the bots.
"""

from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from a5s.contract import Person, Scenario

UNKNOWN = "a5s doesn't know who you are. Ask an instance approver to add your Matrix id to the directory."
ONE_TO_ONE = "a5s talks one to one for now. Start a direct chat with me instead."
ENCRYPTED = ("I can't read encrypted messages yet. Start a direct chat with me with encryption "
             "turned off.")


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class MatrixConfig:
    homeserver: str  # its client-server API, such as http://synapse:8008
    server_name: str  # its people's domain: @ana:<server_name>
    as_token: str  # a5s's, to speak as its bots
    hs_token: str  # the homeserver's, sent with every delivery

    @classmethod
    def from_env(cls) -> MatrixConfig | None:
        """Matrix is on where A5S_MATRIX_HOMESERVER is set, and then needs the rest."""
        if not (homeserver := os.environ.get("A5S_MATRIX_HOMESERVER")):
            return None
        rest = ("A5S_MATRIX_SERVER_NAME", "A5S_MATRIX_AS_TOKEN", "A5S_MATRIX_HS_TOKEN")
        if missing := [name for name in rest if not os.environ.get(name)]:
            raise RuntimeError(f"Matrix needs {', '.join(missing)} as well as A5S_MATRIX_HOMESERVER")
        return cls(homeserver.rstrip("/"), *(os.environ[name] for name in rest))


@dataclass(frozen=True)
class Message:
    person: str
    agent: str
    text: str
    reply_to: dict[str, str]


class Matrix:
    def __init__(self, cfg: MatrixConfig, http: httpx.Client | None = None):
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=15)
        self._registered: set[str] = set()
        self._rooms: dict[str, str] = {}  # each room a bot has joined, and that bot

    def check(self, authorization: str | None, access_token: str | None = None) -> None:
        """That the homeserver itself sent this. Refused if not."""
        token = (authorization or "").removeprefix("Bearer ").strip() or access_token or ""
        if not token:
            raise Refused(401, "the homeserver didn't send its token")
        if not secrets.compare_digest(token, self.cfg.hs_token):
            raise Refused(403, "that isn't the homeserver's token")

    def bot(self, agent: str) -> str:
        return f"@a5s-{agent}:{self.cfg.server_name}"

    def agent_of(self, user: str) -> str | None:
        local, _, server = user.removeprefix("@").partition(":")
        return local.removeprefix("a5s-") if server == self.cfg.server_name and local.startswith("a5s-") else None

    def person_of(self, user: str, scenario: Scenario) -> Person | None:
        """Who in the directory a Matrix id is: only people on the organisation's own server."""
        if not self.local(user):
            return None
        return scenario.find(f"matrix:{user}")

    def user_of(self, person: Person) -> str | None:
        """A person's Matrix id on the organisation's own server, from the directory."""
        users = (i.removeprefix("matrix:") for i in person.identities if i.startswith("matrix:"))
        return next((user for user in users if self.local(user)), None)

    def local(self, user: str) -> bool:
        """Whether a Matrix id is a person's on the organisation's own server."""
        return user.startswith("@") and user.endswith(f":{self.cfg.server_name}") \
            and not self.agent_of(user)

    # Speaking as a bot, with a5s's token

    def _call(self, method: str, path: str, bot: str, json: dict | None = None) -> httpx.Response:
        return self.http.request(method, f"{self.cfg.homeserver}/_matrix/client/v3{path}",
                                 params={"user_id": bot}, json=json,
                                 headers={"Authorization": f"Bearer {self.cfg.as_token}"})

    def register(self, bot: str) -> None:
        """Make the bot's account, if it hasn't one yet."""
        if bot in self._registered:
            return
        local = bot.removeprefix("@").partition(":")[0]
        made = self.http.post(f"{self.cfg.homeserver}/_matrix/client/v3/register",
                              json={"type": "m.login.application_service", "username": local},
                              headers={"Authorization": f"Bearer {self.cfg.as_token}"})
        if made.status_code != 200 and made.json().get("errcode") != "M_USER_IN_USE":
            made.raise_for_status()
        self._registered.add(bot)

    def join(self, room: str, bot: str) -> None:
        self.register(bot)
        self._call("POST", f"/join/{quote(room, safe='')}", bot).raise_for_status()
        self._rooms[room] = bot

    def members(self, room: str, bot: str) -> list[str] | None:
        """Who's in a room, as the bot sees it, or None if the bot isn't in it."""
        found = self._call("GET", f"/rooms/{quote(room, safe='')}/joined_members", bot)
        if found.status_code in (403, 404):
            return None
        found.raise_for_status()
        return sorted(found.json().get("joined", {}))

    def bot_in(self, room: str, agents: list[str]) -> str | None:
        """Which of a5s's bots is in a room, if one is."""
        if room in self._rooms:
            return self._rooms[room]
        for agent in agents:
            if self.members(room, self.bot(agent)) is not None:
                self._rooms[room] = self.bot(agent)
                return self._rooms[room]
        return None

    def start(self, user: str, agent: str) -> dict[str, str]:
        """A direct chat an agent's bot starts with someone, inviting them to it. Where to
        send to it."""
        if not self.local(user):
            raise ValueError("a5s starts chats only with people on the organisation's own server")
        bot = self.bot(agent)
        self.register(bot)
        made = self._call("POST", "/createRoom", bot, json={
            "is_direct": True, "invite": [user], "preset": "trusted_private_chat"})
        made.raise_for_status()
        self._rooms[made.json()["room_id"]] = bot
        return {"room": made.json()["room_id"], "bot": bot}

    def send(self, reply_to: dict[str, str], text: str) -> None:
        """Send text into a room, as the bot that's in it."""
        if self.agent_of(reply_to.get("bot", "")) is None:
            raise ValueError("a5s speaks only as its own bots")
        self._call("PUT", f"/rooms/{quote(reply_to['room'], safe='')}/send/m.room.message/"
                          f"{uuid.uuid4().hex}", reply_to["bot"],
                   json={"msgtype": "m.text", "body": text}).raise_for_status()

    # What the homeserver sends

    def event(self, event: dict[str, Any], scenario: Scenario, agents: list[str]) -> tuple[str, Any]:
        """What to do about one event: ("join", (room, bot)), ("message", Message),
        ("turn away", (reason, people, reply, reply_to)), ("left", (person, agent, reply_to)),
        or ("ignore", None)."""
        sender, room, kind = event.get("sender", ""), event.get("room_id", ""), event.get("type")
        content = event.get("content") or {}
        if (kind == "m.room.member" and self.agent_of(event.get("state_key", ""))
                and content.get("membership") in ("leave", "ban")):
            self._rooms.pop(room, None)  # a bot left, or was removed: ask again next time
        if self.agent_of(sender):  # a5s's own bots: never answer them
            return "ignore", None
        if kind == "m.room.member":
            target, membership = event.get("state_key", ""), content.get("membership")
            known = self.person_of(sender, scenario) is not None
            if membership == "invite" and self.agent_of(target) in agents and known:
                return "join", (room, target)
            if membership in ("leave", "ban") and (person := self.person_of(target, scenario)):
                bot = self.bot_in(room, agents)  # still there: they left it, or turned it down
                if bot is not None:
                    return "left", (person.id, self.agent_of(bot), {"room": room, "bot": bot})
            return "ignore", None
        if kind not in ("m.room.message", "m.room.encrypted"):
            return "ignore", None
        if kind == "m.room.message" and (content.get("msgtype") != "m.text"
                                          or (content.get("m.relates_to") or {}).get("rel_type") == "m.replace"):
            return "ignore", None  # notices, files and edits
        bot = self.bot_in(room, agents)
        if bot is None:
            return "ignore", None
        reply_to = {"room": room, "bot": bot}
        person = self.person_of(sender, scenario)
        if person is None:
            return "turn away", (f"the directory doesn't know matrix:{sender}", [], UNKNOWN, reply_to)
        if self.members(room, bot) != sorted({sender, bot}):
            return "turn away", ("a5s talks one to one for now", [person.id], ONE_TO_ONE, reply_to)
        if kind == "m.room.encrypted":
            return "turn away", ("a5s can't read encrypted messages yet", [person.id], ENCRYPTED,
                                 reply_to)
        return "message", Message(person.id, self.agent_of(bot), content.get("body", ""), reply_to)
