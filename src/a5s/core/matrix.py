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
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from a5s.contract import Person, Scenario
from a5s.core import groups

MEMBERS_KEPT = 60.0  # seconds a room's members, as last read, stand for who's in it [TBC]
UNKNOWN = "a5s doesn't know who you are. Ask an instance approver to add your Matrix id to the directory."
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
    members: tuple[str, ...] = ()  # in a group's room, everyone in it, by their ids
    place: str | None = None  # in a group's room, the room


class Matrix:
    def __init__(self, cfg: MatrixConfig, http: httpx.Client | None = None):
        self.cfg = cfg
        self.http = http or httpx.Client(timeout=15)
        self._registered: set[str] = set()
        self._rooms: dict[str, set[str]] = {}  # each room a5s's bots have joined, and those bots
        self._told_encrypted: set[str] = set()  # group rooms told why a5s can't read them
        # Who's in each room, and whether it's private, as last read, until its state changes,
        # for the events the homeserver sends: never for what a5s checks before it writes
        self._joined: dict[str, tuple[float, list[str]]] = {}
        self._private: dict[str, tuple[float, bool]] = {}

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

    def _call(self, method: str, path: str, bot: str, json: dict | None = None,
              params: dict[str, str] | None = None) -> httpx.Response:
        return self.http.request(method, f"{self.cfg.homeserver}/_matrix/client/v3{path}",
                                 params={"user_id": bot, **(params or {})}, json=json,
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
        self._rooms.setdefault(room, set()).add(bot)

    def members(self, room: str, bot: str, cached: bool = False) -> list[str] | None:
        """Who's in a room, as the bot sees it, or None if the bot isn't in it: with `cached`,
        as last read, if nobody has joined or left it since, within a minute."""
        if cached and (seen := self._joined.get(room)) and time.monotonic() - seen[0] < MEMBERS_KEPT:
            return seen[1]
        found = self._call("GET", f"/rooms/{quote(room, safe='')}/joined_members", bot)
        if found.status_code in (403, 404):
            return None
        found.raise_for_status()
        joined = sorted(found.json().get("joined", {}))
        self._joined[room] = (time.monotonic(), joined)
        return joined

    def private(self, room: str, bot: str) -> bool:
        """Whether a room with nobody but one person and a5s's bots in it is theirs alone: only
        those invited may join it, nobody else is invited, and nobody may read it unjoined. A
        room that isn't is a group's room, however few are in it now."""
        if (seen := self._private.get(room)) and time.monotonic() - seen[0] < MEMBERS_KEPT:
            return seen[1]
        rules = self._call("GET", f"/rooms/{quote(room, safe='')}/state/m.room.join_rules", bot)
        rule = "invite" if rules.status_code == 404 else (
            rules.raise_for_status() and "" or str(rules.json().get("join_rule") or "invite"))
        invited = self._call("GET", f"/rooms/{quote(room, safe='')}/members", bot,
                             params={"membership": "invite"})
        invited.raise_for_status()
        others = [e.get("state_key") for e in invited.json().get("chunk") or []
                  if not self.agent_of(str(e.get("state_key") or ""))]
        found = (rule in ("invite", "knock") and not others
                 and self.history(room, bot) != "world_readable")
        self._private[room] = (time.monotonic(), found)
        return found

    def leave(self, room: str, bot: str) -> None:
        """Leave a room a5s won't work in, such as one with too many people."""
        self._call("POST", f"/rooms/{quote(room, safe='')}/leave", bot).raise_for_status()
        self._rooms.pop(room, None)
        self._joined.pop(room, None)

    def history(self, room: str, bot: str) -> str:
        """Who may read what was said in a room before they joined it: "shared" unless the
        room says otherwise, as the spec has it."""
        found = self._call("GET", f"/rooms/{quote(room, safe='')}/state/m.room.history_visibility",
                           bot)
        if found.status_code == 404:
            return "shared"
        found.raise_for_status()
        return str(found.json().get("history_visibility") or "shared")

    @staticmethod
    def mentioned(content: dict[str, Any], bot: str) -> bool:
        """Whether a message mentions the bot: as the spec has apps say so now, or by its id
        or its name in the text, as older apps do."""
        if bot in ((content.get("m.mentions") or {}).get("user_ids") or []):
            return True
        local = bot.removeprefix("@").partition(":")[0]
        said = f"{content.get('body', '')} {content.get('formatted_body', '')}"
        return bot in said or local in said

    @staticmethod
    def unmentioned(text: str, bot: str) -> str:
        """A message's text without the mention of the bot it opens with."""
        local = bot.removeprefix("@").partition(":")[0]
        for name in (bot, local):
            if text.startswith(name):
                return text[len(name):].lstrip(" :,").strip()
        return text.strip()

    def bots_in(self, room: str, agents: list[str]) -> list[str]:
        """Which of a5s's bots are in a room, such as the assistant and the watcher both."""
        if not self._rooms.get(room):
            found = {self.bot(a) for a in agents if self.members(room, self.bot(a)) is not None}
            if not found:
                return []
            self._rooms[room] = found
        return sorted(self._rooms[room])

    def bot_in(self, room: str, agents: list[str]) -> str | None:
        """One of a5s's bots in a room, if any is."""
        return next(iter(self.bots_in(room, agents)), None)

    def start(self, user: str, agent: str) -> dict[str, str]:
        """A direct chat an agent's bot starts with someone, inviting them to it. Where to
        send to it."""
        if not self.local(user):
            raise ValueError("a5s starts chats only with people on the organisation's own server")
        bot = self.bot(agent)
        self.register(bot)
        made = self._call("POST", "/createRoom", bot, json={  # anyone they add later reads
            "is_direct": True, "invite": [user], "preset": "trusted_private_chat",  # only what's
            "initial_state": [{"type": "m.room.history_visibility", "state_key": "",  # said
                               "content": {"history_visibility": "joined"}}]})  # once they're in
        made.raise_for_status()
        self._rooms.setdefault(made.json()["room_id"], set()).add(bot)
        return {"room": made.json()["room_id"], "bot": bot}

    def send(self, reply_to: dict[str, str], text: str, card: dict | None = None) -> None:
        """Send text into a room, as the bot that's in it. A card is Teams's alone: Matrix
        sends the text, which says what the card would."""
        if self.agent_of(reply_to.get("bot", "")) is None:
            raise ValueError("a5s speaks only as its own bots")
        self._call("PUT", f"/rooms/{quote(reply_to['room'], safe='')}/send/m.room.message/"
                          f"{uuid.uuid4().hex}", reply_to["bot"],
                   json={"msgtype": "m.text", "body": text}).raise_for_status()

    # What the homeserver sends

    def event(self, event: dict[str, Any], scenario: Scenario, agents: list[str]) -> tuple[str, Any]:
        """What to do about one event: ("join", (room, bot)), ("message", Message),
        ("turn away", (reason, people, reply, reply_to)), ("left", (person, agent, reply_to)),
        ("shared", (person, agent, reply_to)), or ("ignore", None)."""
        sender, room, kind = event.get("sender", ""), event.get("room_id", ""), event.get("type")
        content = event.get("content") or {}
        if event.get("state_key") is not None:  # who's in it, or its rules, changed: read
            self._joined.pop(room, None)  # them afresh next time
            self._private.pop(room, None)
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
            bot = self.bot_in(room, agents) if not self.agent_of(target) else None
            people = [u for u in self.members(room, bot) or [] if not self.agent_of(u)] \
                if bot else []
            if (membership in ("leave", "ban") and bot is not None  # their own chat, not a
                    and (person := self.person_of(target, scenario))  # group's room
                    and not [u for u in people if u != target]):
                return "left", (person.id, self.agent_of(bot), {"room": room, "bot": bot})
            if membership == "join" and len(people) > 1:  # someone joined a person's own chat:
                owner = next((p for u in people if u != target  # it's theirs alone no more, so
                              and (p := self.person_of(u, scenario))), None)  # a5s writes to
                if owner is not None:  # them first in a new one
                    return "shared", (owner.id, self.agent_of(bot), {"room": room, "bot": bot})
            return "ignore", None
        if kind not in ("m.room.message", "m.room.encrypted"):
            return "ignore", None
        if kind == "m.room.message" and (content.get("msgtype") != "m.text"
                                          or (content.get("m.relates_to") or {}).get("rel_type") == "m.replace"):
            return "ignore", None  # notices, files and edits
        bots = self.bots_in(room, agents)
        if not bots:
            return "ignore", None
        joined = self.members(room, bots[0], cached=True)
        if joined is None:  # it can't tell who's there, so it can't tell whose this is
            self._rooms.pop(room, None)
            return "ignore", None
        people = [u for u in joined if u != sender and not self.agent_of(u)]  # a5s's bots
        group = bool(people) or not self.private(room, bots[0])  # aren't people
        if group and kind == "m.room.encrypted":  # nobody can tell whom it mentions: say why,
            if room in self._told_encrypted:  # once
                return "ignore", None
            self._told_encrypted.add(room)
            return "turn away", ("the room is encrypted, which a5s can't read yet", [],
                                 groups.ENCRYPTED, {"room": room, "bot": bots[0]})
        # A group's room: it answers only when someone mentions one of its bots, as that bot
        bot = next((b for b in bots if self.mentioned(content, b)), None) if group else bots[0]
        if bot is None:
            return "ignore", None
        reply_to = {"room": room, "bot": bot}
        person = self.person_of(sender, scenario)
        if person is None:
            return "turn away", (f"the directory doesn't know matrix:{sender}", [], UNKNOWN, reply_to)
        if kind == "m.room.encrypted":
            return "turn away", ("a5s can't read encrypted messages yet", [person.id], ENCRYPTED,
                                 reply_to)
        if not group:
            return "message", Message(person.id, self.agent_of(bot), content.get("body", ""),
                                      reply_to)
        joined = self.members(room, bot)  # a mention in a group's room: who's in it now,
        if joined is None:  # afresh, since a run there acts for them all
            return "ignore", None
        people = [u for u in joined if u != sender and not self.agent_of(u)]
        if len(people) + 1 > groups.LIMIT:  # and it leaves, so each message there costs nothing
            return "turn away", (f"the group has more than {groups.LIMIT} people", [person.id],
                                 groups.TOO_MANY, {**reply_to, "leave": "yes"})
        known = [self.person_of(u, scenario) for u in people]
        if None in known:
            strangers = [u for u, p in zip(people, known, strict=True) if p is None]
            return "turn away", ("someone in the group isn't in the directory", [person.id],
                                 groups.STRANGERS.format(who=groups.listed(strangers)), reply_to)
        members = tuple(sorted({person.id, *(p.id for p in known if p)}))
        if self.history(room, bot) != "joined":  # "invited" shows people, once they've joined,
            # what was said while they were only invited, which the run wasn't for
            return "turn away", ("the room shows people what was said before they joined",
                                 [person.id], groups.HISTORY, reply_to)
        return "message", Message(person.id, self.agent_of(bot),
                                  self.unmentioned(content.get("body", ""), bot), reply_to,
                                  members=members, place=room)
