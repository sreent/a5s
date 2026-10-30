"""The gateway: every tool call, model call and outgoing message passes through here.

For each call, in one Postgres transaction, it reads the run's envelope, asks
policy, and writes the ledger. Only then does it make the call. Workers hold
only a run token. Provider keys and tool implementations stay on this side.

It also opens and closes runs, for the scheduler: to answer a message, to
remind someone of an obligation, or to work on a schedule. And it works out
what falls due, escalating overdue obligations itself.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.config import Config, ModelConfig
from a5s.contract import (
    INSTANCE_APPROVER,
    Person,
    Scenario,
    Settings,
    Signature,
    Tool,
    ToolCall,
    parse_settings,
)
from a5s.core import (
    approvals,
    chats,
    coretools,
    digests,
    ledger,
    models,
    obligations,
    profiles,
    recall,
    registry,
    releases,
    reminders,
    reports,
    schedules,
)
from a5s.core.identity import IdentityError, UnknownPerson, Verifier, signed_in
from a5s.core.matrix import Matrix
from a5s.core.policy import Decision, PolicyEngine
from a5s.core.teams import Teams
from a5s.definitions import Definition

log = logging.getLogger(__name__)
CORE_TOOLS = {**reminders.TOOLS, **digests.TOOLS, **profiles.TOOLS,  # a5s's own, on its
              **recall.TOOLS}  # own records
RUN_MINUTES = 60  # the longest a run may last [TBC]; its token dies with it
# The chats a5s writes to itself, as each agent's bot. People collect from the local
# channel, the command line's and the web chat's, instead.
PUSHED = ("teams", "matrix")
_STATUS_AFTER = {"suspend": "suspended", "retire": "retired"}  # resume and restore: active
# Outgoing text keeps only words and the scenario's own record links. Anything that
# could fetch or point somewhere else goes: images, HTML, and links in any form,
# whatever their case, slashes or scheme.
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_TAG = re.compile(r"</?[A-Za-z][^>]*>")  # HTML, and autolinks such as <https://...>
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(\s*([^)\s]*)[^)]*\)")
_URL = re.compile(r"(?i)(?:\b[a-z][a-z0-9+.-]*:[/\\]+|(?<![\w:/\\])//|\bwww\.)[^\s)>\]]*")


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def sanitize(text: str, allowed: tuple[str, ...]) -> tuple[str, int]:
    """Keep text and the scenario's own record links. Drop images, HTML and other links."""
    removed = 0

    def kept(url: str) -> bool:
        return any(url.startswith(prefix) for prefix in allowed)

    def link(match: re.Match) -> str:
        nonlocal removed
        if kept(match.group(2)):
            return match.group(0)
        removed += 1
        return f"{match.group(1)} [link removed]"

    def url(match: re.Match) -> str:
        nonlocal removed
        if kept(match.group(0)):
            return match.group(0)
        removed += 1
        return "[link removed]"

    text, images = _IMAGE.subn("[image removed]", text)
    text, tags = _TAG.subn("[removed]", text)
    text = _MARKDOWN_LINK.sub(link, text)
    parts = re.split(r"(\[[^\]]*\]\([^)]*\))", text)  # record links already kept stay whole
    text = "".join(p if _MARKDOWN_LINK.fullmatch(p) else _URL.sub(url, p) for p in parts)
    return text, removed + images + tags


@dataclass
class Gateway:
    cfg: Config
    scenario: Scenario
    policy: PolicyEngine
    models: dict[str, ModelConfig]
    definitions: dict[str, Definition]
    http: httpx.Client
    identity: Verifier | None = None  # for the local channel's sign-in; else development only
    teams: Teams | None = None
    matrix: Matrix | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # when obligations and schedules are due
    releases: releases.Releases | None = None  # the release a5s is, which must be approved here
    _checked: dict = field(default_factory=dict)  # settings versions whose signatures checked out

    @property
    def url(self) -> str:
        return self.cfg.database_url

    def settings_in_force(self, conn: psycopg.Connection) -> tuple[Any, str | None]:
        """The latest signed version of the settings, checked again from the bytes that were signed."""
        row = conn.execute("select serial, version, raw, signatures from settings_versions "
                           "where scenario = %s order by serial desc limit 1",
                           (self.scenario.name,)).fetchone()
        if row is None:
            return None, "no settings have been applied"
        if row["version"] in self._checked:
            return self._checked[row["version"]], None
        signatures = tuple(Signature(s["signer"], s["value"]) for s in row["signatures"] or [])
        settings = parse_settings(bytes(row["raw"] or b""), signatures)
        if (settings.version, settings.serial) != (row["version"], row["serial"]):
            return None, "the settings in force aren't what was signed"
        approved, _ = approvals.approvers(conn, self.cfg.seal_keys, self.scenario.name,
                                          approvals.digest(settings.raw))
        if not registry.signers(settings, self.scenario.person, approved)[0]:
            return None, "no instance approver signed the settings in force"
        self._checked[row["version"]] = settings
        return settings, None

    def check_instance(self, conn: psycopg.Connection, inst: dict) -> list[str]:
        """Whether an instance's record is exactly what its signed settings, its release and
        the ledger say, so that nobody can widen it by editing the database."""
        settings, problem = self.settings_in_force(conn)
        if problem:
            return [problem]
        signed = next((s for s in settings.instances if s.id == inst["id"]), None)
        if signed is None or inst["settings_version"] != settings.version:
            return [f"{inst['id']} isn't in the settings in force"]
        release = self.definitions.get(signed.definition)
        if release is None or release.release_id != inst["release"]:
            return [f"{inst['id']}'s release isn't in this gateway"]
        level = min(release.autonomy.start if signed.level is None else signed.level,
                    release.autonomy.max)
        expected = (signed.definition, sorted(signed.serves), level, sorted(release.grants),
                    release.model, release.pins, signed.owner or release.owner,
                    signed.deputy or release.deputy)
        actual = (inst["definition"], sorted(inst["serves"]), inst["level"], sorted(inst["grants"]),
                  inst["model"], inst["pins"], inst["owner"], inst["deputy"])
        if expected != actual:
            log.error("instance %s doesn't match its signed settings and release", inst["id"])
            return [f"{inst['id']}'s record doesn't match its signed settings and release"]
        last = conn.execute(
            "select action from ledger where instance_id = %s and kind = 'admin' "
            "and action in ('suspend', 'resume', 'retire', 'restore') order by seq desc limit 1",
            (inst["id"],)).fetchone()
        if inst["status"] != _STATUS_AFTER.get(last["action"] if last else "", "active"):
            log.error("instance %s's status doesn't match the ledger", inst["id"])
            return [f"{inst['id']}'s status doesn't match the ledger"]
        return []

    def release_problems(self, conn: psycopg.Connection) -> list[str]:
        """Why the release a5s is can't run here, if it can't: in development, it always can."""
        if self.releases is None or self.cfg.development:
            return []
        return self.releases.problems(conn, self.scenario, self.cfg.team)

    @staticmethod
    def take_message(conn: psycopg.Connection, inbound: str) -> tuple[dict | None, str | None]:
        """The message a run will answer, which the core received and checked, used once.

        It names the sender, so no service can. The problem, if it can't be used.
        """
        taken = conn.execute(
            "update inbound set answered_at = now() where id = %s and answered_at is null "
            "returning id::text, person, channel, agent", (inbound,)).fetchone()
        if taken:
            return taken, None
        if conn.execute("select 1 from inbound where id = %s", (inbound,)).fetchone():
            return None, "the message it answers has been answered already"
        return None, "the message it answers isn't one the core received"

    @staticmethod
    def message_of(conn: psycopg.Connection, inbound: str | None) -> dict | None:
        """Who wrote the message a run answers, on which channel, and where answers go."""
        if inbound is None:
            return None
        return conn.execute("select id::text, person, channel, reply_to from inbound where id = %s",
                            (inbound,)).fetchone()

    def reach(self, conn: psycopg.Connection, person: str, agent: str | None) -> dict:
        """How to write to someone who isn't waiting for an answer, as the agent's own bot and
        never another's: in the conversation they last had with this agent, whoever started
        it, or else in the chat they last wrote in, where the agent's bot starts one if the
        chat lets it. a5s's own notices, about no agent, go in the conversation they last had.
        Otherwise, and where they've left the conversation, they collect it from the local
        channel's inbox."""
        local = {"channel": "local", "reply_to": {}}
        if agent is not None:
            had = conn.execute(
                """
                select channel, reply_to, at from (
                  select channel, reply_to, received_at as at from inbound
                  where person = %(person)s and agent = %(agent)s
                  union all
                  select channel, reply_to, started_at from chats
                  where person = %(person)s and agent = %(agent)s and started_at is not null
                ) had order by at desc limit 1
                """, {"person": person, "agent": agent}).fetchone()
            if had is not None:
                return self._in(conn, had) or local
        last = conn.execute("select channel, reply_to, received_at as at from inbound "
                            "where person = %s order by received_at desc limit 1",
                            (person,)).fetchone()
        if last is None or agent is None:
            return (last and self._in(conn, last)) or local
        who = self.scenario.person(person)
        if (last["channel"] == "matrix" and self.matrix is not None and who is not None
                and (user := self.matrix.user_of(who))):
            return {"channel": "matrix", "reply_to": {},
                    "start": {"person": person, "agent": agent, "user": user}}
        return local  # such as in Teams, where only people who added the agent's app can hear it

    def _in(self, conn: psycopg.Connection, conversation: dict) -> dict | None:
        """A new message in a conversation, not a reply, unless it's local, its chat is off
        here now, or the person left it."""
        channel = conversation["channel"]
        if (channel not in PUSHED or self.chat(channel) is None
                or chats.gone(conn, channel, conversation["reply_to"], conversation["at"])):
            return None
        return {"channel": channel,
                "reply_to": {k: v for k, v in conversation["reply_to"].items() if k != "activity"}}

    def able(self, conn: psycopg.Connection) -> dict[str, bool]:
        """Which instances can act now: active, as signed and released, in a release this
        deployment approved."""
        runs = not self.release_problems(conn)
        return {i["id"]: runs and i["status"] == "active" and not self.check_instance(conn, i)
                for i in conn.execute("select * from instances").fetchall()}

    def busy(self, conn: psycopg.Connection, person: Person, due: datetime, now: datetime,
             able: dict[str, bool]) -> bool:
        """Whether the agents' work for someone's digest is still due, or still running: a
        chase, a report, or a reminder for the day."""
        if conn.execute("select 1 from runs where closed_at is null and expires_at > now() "
                        "and %s = any(acts_for) and trigger->>'kind' = any(%s)",
                        (person.id, list(digests.KINDS))).fetchone():
            return True
        rows = conn.execute("select o.*, i.definition as agent from obligations o "
                            "left join instances i on i.id = o.instance_id "
                            "where o.scenario = %s and o.person = %s and o.done_at is null",
                            (self.scenario.name, person.id)).fetchall()
        if obligations.to_chase(rows, self.scenario, now, able, lambda _: True):
            return True
        if conn.execute("select 1 from reminders where person = %s and confirmed_at is not null "
                        "and reminded_at is null and cancelled_at is null and in_digest "
                        "and due_at <= %s and instance_id = any(%s)",
                        (person.id, now, [i for i, ok in able.items() if ok])).fetchone():
            return True
        for inst in conn.execute("select * from instances where %s = any(serves)",
                                 (person.id,)).fetchall():
            definition = self.definitions.get(inst["definition"])
            if (able.get(inst["id"]) and definition and definition.release_id == inst["release"]
                    and any(not reports.fired(conn, inst["id"], person.id, r.source, due)
                            for r in definition.reports)):
                return True
        return False

    @staticmethod
    def for_digest(conn: psycopg.Connection, run: dict) -> bool:
        """Whether what a run writes waits for its person's digest: a chase, a report, or a
        reminder for a day, but not a reminder for a particular time, which goes at once."""
        kind = run["trigger"].get("kind")
        if kind == "reminder":
            row = conn.execute("select in_digest from reminders where id = %s",
                               (run["trigger"].get("reminder"),)).fetchone()
            return bool(row and row["in_digest"])
        return kind in digests.KINDS

    def digest_open(self, conn: psycopg.Connection, now: datetime) -> Callable[[Person], bool]:
        """Whether someone's digest time has come today, and its digest hasn't gone, so their
        agents' work for it falls due: asked once a sweep for each person."""
        found: dict[str, bool] = {}

        def is_open(person: Person) -> bool:
            if person.id not in found:
                found[person.id] = digests.window(conn, person, now) is not None
            return found[person.id]

        return is_open

    def chat(self, channel: str) -> Teams | Matrix | None:
        """A chat a5s writes to itself, if it's on here."""
        return {"teams": self.teams, "matrix": self.matrix}.get(channel)

    @property
    def public_url(self) -> str:
        """Where people reach the core's channels, for links."""
        return (self.cfg.public_url or self.cfg.channels_url).rstrip("/")

    def approving(self) -> str | None:
        """Why approvers can't approve settings where they work here, if they can't: it takes
        sign-in through the organisation's identity provider, and the core's seal."""
        if self.identity is None or not self.cfg.webchat_client_id:
            return ("approving settings where people work needs the organisation's identity "
                    "provider and the web chat's client: see A5S_OIDC_ISSUER and "
                    "A5S_WEBCHAT_CLIENT_ID")
        if not self.cfg.seal_keys:
            return "approving settings where people work needs the core's seal key: see A5S_SEAL_KEYS"
        return None

    def unusable(self, settings: Settings, last: dict | None) -> list[str]:
        """Why a version of the settings couldn't be applied, before anyone's asked to approve it."""
        problems = []
        if last and settings.serial <= last["serial"]:
            problems.append(f"serial {settings.serial} isn't above {last['serial']}, the version "
                            "in force's: raise it")
        tools = self.scenario.tools()
        for instance in settings.instances:
            release = self.definitions.get(instance.definition)
            if release is None:
                problems.append(f"{instance.id} names {instance.definition}, which no release here has")
            elif missing := [t for t in release.tool_names if t not in tools]:
                problems.append(f"{instance.definition} names tools the scenario doesn't have: "
                                f"{', '.join(missing)}")
        return problems

    # What each kind of run brings when it opens.

    def answering(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                  _now: datetime) -> Opening:
        """A run that answers a message the core received, acting for its sender."""
        try:
            inbound = str(uuid.UUID(str(trigger.get("inbound"))))
        except ValueError:
            raise HTTPException(400, "name the message the run answers") from None
        message, problem = self.take_message(conn, inbound)
        sender = message["person"] if message else None
        opening = Opening(
            trigger={"kind": "message", "inbound": inbound,
                     "channel": message["channel"] if message else None, "sender": sender},
            acts_for=[sender] if sender else [], reasons=[problem] if problem else [],
            args={"channel": message["channel"] if message else None, "inbound": inbound},
            used=problem is not None and "already" in problem)
        if message and message["agent"] != inst["definition"]:
            opening.reasons.append(f"the message is for the {message['agent']}, "
                                   f"not the {inst['definition']}")
        return opening

    def reminding(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                  now: datetime) -> Opening:
        """A run that reminds someone of what they owe, acting for them."""
        try:
            number = int(trigger.get("obligation"))
        except (TypeError, ValueError):
            raise HTTPException(400, "name the obligation the run is for") from None
        row = conn.execute("select * from obligations where id = %s and scenario = %s for update",
                           (number, self.scenario.name)).fetchone()
        if row is None:
            return Opening({"kind": "obligation", "obligation": number}, [], {"obligation": number},
                           ["there's no such obligation"])
        person = self.scenario.person(row["person"])
        opening = Opening(
            trigger={"kind": "obligation", "obligation": number, "record": row["record"],
                     "person": row["person"]},
            acts_for=[row["person"]], args={"obligation": number, "record": row["record"]},
            reasons=[], task=obligations.chase(row, person) if person else None,
            used=row["chased_at"] is not None or row["escalations"] > 0)
        if row["done_at"]:
            opening.reasons.append("the records no longer owe it")
        if opening.used:
            opening.reasons.append("its person has been reminded, or it has been escalated")
        if row["instance_id"] != inst["id"]:
            opening.reasons.append(f"{inst['id']} doesn't act on it")
        if now < obligations.halfway(row):
            opening.reasons.append("half its time hasn't passed yet")
        if person is None or digests.window(conn, person, now) is None:
            opening.reasons.append(f"it waits for {row['person']}'s digest")
        return opening

    def scheduled(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                  now: datetime) -> Opening:
        """A run on one of the release's schedules, acting for nobody."""
        name = str(trigger.get("schedule"))
        definition = self.definitions.get(inst["definition"])
        found = [s for s in definition.schedules if s.name == name] if (
            definition and definition.release_id == inst["release"]) else []
        due = schedules.due_now(found[0], schedules.zone(self.scenario, inst["owner"]),
                                now) if found else None
        opening = Opening(trigger={"kind": "schedule", "schedule": name,
                                   "due": due.isoformat() if due else None},
                          acts_for=[], args={"schedule": name, "due": due.isoformat() if due else None},
                          reasons=[], task=found[0].task if found else None, due=due)
        if not found:
            opening.reasons.append(f"{inst['id']}'s release has no schedule {name}")
        elif due is None:
            opening.reasons.append(f"{name} isn't due")
        elif conn.execute("select 1 from schedule_fires where instance_id = %s and schedule = %s "
                          "and due_at = %s", (inst["id"], name, due)).fetchone():
            opening.reasons.append(f"{name} has fired already")
            opening.used = True
        return opening

    def reporting(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                  now: datetime) -> Opening:
        """A run that tells someone what changed in their records, and what fell due, acting
        for them. The facts come from the records, worked out by code."""
        asked = trigger.get("report") if isinstance(trigger.get("report"), dict) else {}
        who, source = str(asked.get("person")), str(asked.get("source"))
        person = self.scenario.person(who)
        definition = self.definitions.get(inst["definition"])
        found = [r for r in definition.reports if r.source == source] if (
            definition and definition.release_id == inst["release"]) else []
        reachable = person is not None and person.in_audience and who in inst["serves"]
        due = digests.window(conn, person, now) if found and reachable else None
        args = {"person": who, "source": source, "due": due.isoformat() if due else None}
        opening = Opening(trigger={"kind": "report", "report": {"person": who, "source": source},
                                   "due": args["due"]},
                          acts_for=[who] if reachable else [], args=args, reasons=[])
        if not found:
            opening.reasons.append(f"{inst['id']}'s release doesn't report on {source}")
        elif person is None:
            opening.reasons.append(f"the directory doesn't know {who}")
        elif who not in inst["serves"]:
            opening.reasons.append(f"{inst['id']} doesn't serve {who}")
        elif not person.in_audience:
            opening.reasons.append(f"a5s may not write to {who}")
        elif due is None:
            opening.reasons.append(f"{who}'s report isn't due")
        elif reports.fired(conn, inst["id"], who, source, due):
            opening.reasons.append(f"{who}'s report has gone already today")
            opening.used = True
        else:
            try:
                news = reports.news(conn, self.scenario.name, inst["id"], person, source,
                                    self.scenario.watched(), now)
            except Exception:  # the day's report waits until they can be read
                log.exception("couldn't read the records for %s's report", who)
                opening.reasons.append("the records can't be read")
                return opening
            if not news.facts:
                opening.reasons.append("nothing is new")
            opening.task, opening.due, opening.seen = reports.task(person, news), due, news.records
        return opening

    def following_up(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                     now: datetime) -> Opening:
        """A run that reminds someone of what they agreed to be reminded of, acting for them."""
        try:
            number = int(trigger.get("reminder"))
        except (TypeError, ValueError):
            raise HTTPException(400, "name the reminder the run is for") from None
        row = conn.execute("select * from reminders where id = %s for update", (number,)).fetchone()
        if row is None:
            return Opening({"kind": "reminder", "reminder": number}, [], {"reminder": number},
                           ["there's no such reminder"])
        person = self.scenario.person(row["person"])
        opening = Opening(
            trigger={"kind": "reminder", "reminder": number, "person": row["person"]},
            acts_for=[row["person"]], args={"reminder": number}, reasons=[],
            task=reminders.task(row, person) if person and row["confirmed_at"] else None,
            used=row["reminded_at"] is not None)
        if person is None:
            opening.reasons.append("the directory doesn't know them")
        if row["confirmed_at"] is None:
            opening.reasons.append("they never confirmed it")
        if row["cancelled_at"]:
            opening.reasons.append("it was cancelled")
        if opening.used:
            opening.reasons.append("they've been reminded already")
        if row["instance_id"] != inst["id"]:
            opening.reasons.append(f"{inst['id']} didn't take it")
        if now < row["due_at"]:
            opening.reasons.append("it isn't due yet")
        elif row["in_digest"] and person and digests.window(conn, person, now) is None:
            opening.reasons.append(f"it waits for {row['person']}'s digest")
        return opening

    # Cedar entities, built from the core's own records for every call.

    @staticmethod
    def instance_entity(row: dict) -> dict:
        return {
            "uid": {"type": "Instance", "id": row["id"]},
            "attrs": {
                "status": row["status"],
                "level": row["level"],
                "grants": list(row["grants"]),
                "model": row["model"],
                "serves": list(row["serves"]),
            },
            "parents": [],
        }

    @staticmethod
    def core_tool_entity(name: str) -> dict:
        """One of a5s's own tools: part of the trusted core's release, and changing no part's data."""
        return {"uid": {"type": "Tool", "id": name},
                "attrs": {"name": name, "known": True, "pinned": True, "reads": False,
                          "writes": False, "destructive": False, "sends_outside": False},
                "parents": []}

    @staticmethod
    def tool_entity(name: str, tool: Tool | None, pins: dict) -> dict:
        risk = tool.risk if tool else dict.fromkeys(("reads", "writes", "destructive", "sends_outside"), False)
        pinned = tool is not None and pins.get(name) == tool.schema_hash
        return {
            "uid": {"type": "Tool", "id": name},
            "attrs": {"name": name, "known": tool is not None, "pinned": pinned, **risk},
            "parents": [],
        }

    def decide(self, row: dict, action: str, resource: dict, extra: list[dict]) -> Decision:
        return self.policy.decide(
            principal={"type": "Instance", "id": row["id"]},
            action=action,
            resource=resource["uid"],
            context={
                "level": row["level"],
                "read_outside": row["read_outside"],
                "acts_for": list(row["acts_for"]),
            },
            entities=[self.instance_entity(row), resource, *extra],
        )

    def entry(self, row: dict, kind: str, action: str, decision: Decision, **fields: Any) -> dict:
        return {
            "kind": kind,
            "action": action,
            "run": row["run"],
            "instance": row["id"],
            "acts_for": list(row["acts_for"]),
            "level": row["level"],
            "policy": self.policy.version,
            "settings": row["settings_version"],
            **decision.as_dict(),
            **fields,
        }


@dataclass
class Opening:
    """What a trigger brings to a run: whom it acts for, and why it can't open, if it can't."""

    trigger: dict  # kept with the run
    acts_for: list[str]
    args: dict  # for the ledger
    reasons: list[str]
    task: str | None = None  # what a5s asks the agent to do, if it isn't answering a message
    used: bool = False  # the trigger has been used already, such as a message answered before
    due: datetime | None = None  # the time a schedule or a report fires for
    seen: dict | None = None  # a report's records as it tells them, kept once they have it


def load_run(conn: psycopg.Connection, token: str) -> dict:
    row = conn.execute(
        """
        select r.id::text as run, r.acts_for, r.read_outside, r.trigger, i.*
        from runs r join instances i on i.id = r.instance_id
        where r.token_hash = %s and r.closed_at is null and r.expires_at > now()
        """,
        (token_hash(token),),
    ).fetchone()
    if row is None:
        raise HTTPException(401, "unknown or closed run")
    return row


class OpenRun(BaseModel):
    instance: str
    # {"kind": "message", "inbound": <id>}, {"kind": "obligation", "obligation": <id>},
    # {"kind": "schedule", "schedule": <name>}, or
    # {"kind": "report", "report": {"person": <id>, "source": <kind of record>}}
    trigger: dict[str, Any]


class CloseRun(BaseModel):
    outcome: str


class StatusChange(BaseModel):
    by: str | None = None  # in development, without an identity provider, who's asking
    identity: str | None = None  # their sign-in token: who's asking, everywhere else


class ToolArgs(BaseModel):
    args: dict[str, Any] = {}


class Message(BaseModel):
    to: str
    text: str


class Notice(BaseModel):
    inbound: str  # the message it answers
    text: str
    instance: str | None = None


class Proposal(BaseModel):
    raw: str  # exactly the bytes of a version of the settings, in base64


def create_app(gw: Gateway) -> FastAPI:
    app = FastAPI(title="a5s gateway")

    @app.exception_handler(psycopg.OperationalError)
    def database_down(_request, exc: psycopg.OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "a5s can't check this call right now, so it's denied",
                     "detail": str(exc)[:200]},
        )

    def service(authorization: str = Header(default="")) -> None:
        if not secrets.compare_digest(authorization, f"Bearer {gw.cfg.service_token}"):
            raise HTTPException(401, "service token required")

    def run_token(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> str:
        token = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "run token required")
        return token

    # Runs, opened and closed by the scheduler.

    @app.post("/runs", dependencies=[Depends(service)])
    def open_run(body: OpenRun) -> dict:
        kind = body.trigger.get("kind")
        opens = {"message": gw.answering, "obligation": gw.reminding, "schedule": gw.scheduled,
                 "report": gw.reporting, "reminder": gw.following_up}
        if kind not in opens:
            raise HTTPException(400, "a run answers a message, reminds someone of an obligation "
                                     "or of what they asked, works on a schedule, or tells "
                                     "someone about their records")
        token = secrets.token_urlsafe(32)
        run_id = str(uuid.uuid4())
        now = gw.clock()
        with db.transaction(gw.url) as conn:
            inst = conn.execute("select * from instances where id = %s", (body.instance,)).fetchone()
            if inst is None:
                raise HTTPException(404, f"no instance {body.instance}")
            opening = opens[kind](conn, inst, body.trigger, now)
            reasons = opening.reasons
            if inst["status"] != "active":
                reasons.append(f"{body.instance} is {inst['status']}")
            if any(p not in inst["serves"] for p in opening.acts_for):
                reasons.append(f"{body.instance} doesn't serve {', '.join(opening.acts_for)}")
            reasons += gw.check_instance(conn, inst) + gw.release_problems(conn)
            if kind == "report" and opening.due and not opening.used:  # once a day, run or not
                report = opening.trigger["report"]
                if not reports.fire(conn, body.instance, report["person"], report["source"],
                                    opening.due, now, "; ".join(reasons) or "run",
                                    *((None, None) if reasons else (run_id, opening.seen))):
                    reasons.append(f"{report['person']}'s report has gone already today")
                    opening.used = True
            if kind == "schedule" and opening.due and not opening.used:  # once for each time
                fired = conn.execute(
                    "insert into schedule_fires (instance_id, schedule, due_at, fired_at, run_id, "
                    "outcome) values (%s, %s, %s, %s, %s, %s) on conflict do nothing returning 1",
                    (body.instance, opening.trigger["schedule"], opening.due, now,
                     None if reasons else run_id, "; ".join(reasons) or "run")).fetchone()
                if fired is None:
                    reasons.append(f"{opening.trigger['schedule']} has fired already")
                    opening.used = True
            if kind == "reminder" and not reasons:
                conn.execute("update reminders set reminded_at = %s where id = %s",
                             (now, opening.trigger["reminder"]))
            if kind == "obligation" and not reasons:
                conn.execute("update obligations set chased_at = %s, updated_at = %s where id = %s",
                             (now, now, opening.trigger["obligation"]))
            if not reasons:
                conn.execute(
                    "insert into runs (id, instance_id, token_hash, trigger, acts_for, expires_at) "
                    "values (%s, %s, %s, %s, %s, now() + make_interval(mins => %s))",
                    (run_id, body.instance, token_hash(token), Jsonb(opening.trigger),
                     opening.acts_for, RUN_MINUTES),
                )
            ledger.append(conn, {
                "kind": "run", "action": "open", "run": None if reasons else run_id,
                "instance": body.instance, "acts_for": opening.acts_for,
                "decision": "deny" if reasons else "allow", "reasons": reasons,
                "args": {"trigger": kind, **opening.args},
            })
        if reasons:
            raise HTTPException(409, {"reasons": reasons, "status": inst["status"],
                                      "owner": inst["owner"], "suspended_by": inst["suspended_by"],
                                      "answered": opening.used})
        return {"run": run_id, "token": token, "task": opening.task}

    @app.post("/runs/sweep", dependencies=[Depends(service)])
    def sweep() -> list[dict]:
        """Close runs that outlived their time, such as ones whose scheduler stopped."""
        with db.transaction(gw.url) as conn:
            stale = conn.execute(
                "update runs set closed_at = now(), outcome = 'abandoned' "
                "where closed_at is null and expires_at < now() "
                "returning id::text as run, instance_id, trigger").fetchall()
            for row in stale:
                ledger.append(conn, {"kind": "run", "action": "close", "run": row["run"],
                                     "instance": row["instance_id"], "decision": "record",
                                     "outcome": "abandoned"})
        return [{"run": r["run"], "inbound": r["trigger"].get("inbound"),
                 "instance": r["instance_id"]} for r in stale]

    @app.post("/runs/{run_id}/close", dependencies=[Depends(service)])
    def close_run(run_id: str, body: CloseRun) -> dict:
        with db.transaction(gw.url) as conn:
            row = conn.execute(
                "update runs set closed_at = now(), outcome = %s where id = %s and closed_at is null "
                "returning instance_id",
                (body.outcome, run_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "no open run")
            ledger.append(conn, {"kind": "run", "action": "close", "run": run_id,
                                 "instance": row["instance_id"], "decision": "record",
                                 "outcome": body.outcome})
        return {"closed": run_id}

    # What falls due: obligations to remind people of or escalate, and schedules to fire.

    @app.post("/obligations/sweep", dependencies=[Depends(service)])
    def sweep_obligations() -> list[dict]:
        """Bring the obligations in line with the records, and escalate those due, in code.

        Returns the ones whose agents should remind their people now, for the
        scheduler to run.
        """
        now, sends, escalated = gw.clock(), [], set()
        try:
            owed = gw.scenario.obligations()
        except Exception as exc:  # the scenario's own systems: nothing changes until they answer
            log.exception("couldn't read what the records owe")
            raise HTTPException(503, f"the records can't be read: {type(exc).__name__}") from None
        with db.transaction(gw.url) as conn:
            if not conn.execute("select pg_try_advisory_xact_lock(%s) as got",
                                (obligations.LOCK,)).fetchone()["got"]:
                return []  # another sweep is at work
            obligations.sync(conn, gw.scenario.name, owed, gw.definitions, now)
            instances = {i["id"]: i for i in conn.execute("select * from instances")}
            able = gw.able(conn)  # else code escalates
            rows = conn.execute(
                "select o.*, i.definition as agent from obligations o "
                "left join instances i on i.id = o.instance_id "
                "where o.scenario = %s and o.done_at is null order by o.due_at, o.id",
                (gw.scenario.name,)).fetchall()
            for row in rows:
                to = obligations.to_escalate(row, gw.scenario, now, able.get(row["instance_id"], False))
                if to is None:
                    continue
                text = obligations.escalation(row, gw.scenario, to, instances.get(row["instance_id"]))
                conn.execute("update obligations set escalations = escalations + 1, "
                             "escalated_at = %s, escalated_to = %s, updated_at = %s where id = %s",
                             (now, to.id, now, row["id"]))
                route = gw.reach(conn, to.id, row["agent"])
                ledger.append(conn, {
                    "kind": "notice", "action": "escalate", "run": None,
                    "instance": row["instance_id"], "acts_for": [], "decision": "record",
                    "args": {"obligation": row["id"], "record": row["record"],
                             "person": row["person"], "to": to.id, "step": row["escalations"] + 1,
                             "channel": route["channel"], "chars": len(text),
                             "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                if route["channel"] in PUSHED:
                    sends.append((route, text, row["instance_id"]))
                else:  # people collect it from the local channel's inbox
                    conn.execute("insert into outbox (instance_id, agent, person, channel, text) "
                                 "values (%s, %s, %s, 'local', %s)",
                                 (row["instance_id"], row["agent"], to.id, text))
                escalated.add(row["id"])
            due = [d for d in obligations.to_chase(rows, gw.scenario, now, able,
                                                   gw.digest_open(conn, now))
                   if d["obligation"] not in escalated]
        for route, text, instance in sends:
            deliver(route, text, None, instance)
        return due

    @app.post("/schedules/sweep", dependencies=[Depends(service)])
    def sweep_schedules() -> list[dict]:
        """The schedules due to fire now, for the scheduler to run. A time that falls while
        an instance is suspended is recorded as skipped, so it isn't made up later."""
        now, due = gw.clock(), []
        with db.transaction(gw.url) as conn:
            for inst in conn.execute("select * from instances where status in ('active', 'suspended') "
                                     "order by id").fetchall():
                definition = gw.definitions.get(inst["definition"])
                if definition is None or definition.release_id != inst["release"]:
                    continue
                where = schedules.zone(gw.scenario, inst["owner"])
                for schedule in definition.schedules:
                    at = schedules.due_now(schedule, where, now)
                    if at is None or conn.execute(
                            "select 1 from schedule_fires where instance_id = %s and schedule = %s "
                            "and due_at = %s", (inst["id"], schedule.name, at)).fetchone():
                        continue
                    if inst["status"] == "active":
                        due.append({"kind": "schedule", "schedule": schedule.name,
                                    "instance": inst["id"], "agent": inst["definition"]})
                    elif conn.execute(
                            "insert into schedule_fires (instance_id, schedule, due_at, fired_at, "
                            "outcome) values (%s, %s, %s, %s, 'suspended') on conflict do nothing "
                            "returning 1", (inst["id"], schedule.name, at, now)).fetchone():
                        ledger.append(conn, {
                            "kind": "run", "action": "open", "run": None, "instance": inst["id"],
                            "acts_for": [], "decision": "deny",
                            "reasons": [f"{inst['id']} is suspended"],
                            "args": {"trigger": "schedule", "schedule": schedule.name,
                                     "due": at.isoformat()}})
        return due

    @app.post("/reports/sweep", dependencies=[Depends(service)])
    def sweep_reports() -> list[dict]:
        """The reports due now that have something to tell, for the scheduler to run. A day
        with nothing new is recorded here, so no model starts, and so is one that falls while
        the instance is suspended, which isn't made up: what changed waits for the next one."""
        now, due, records = gw.clock(), [], None
        with db.transaction(gw.url) as conn:
            for inst in conn.execute("select * from instances where status in ('active', 'suspended') "
                                     "order by id").fetchall():
                definition = gw.definitions.get(inst["definition"])
                if definition is None or definition.release_id != inst["release"]:
                    continue
                for report, who in ((r, p) for r in definition.reports for p in inst["serves"]):
                    person = gw.scenario.person(who)  # and only people a5s may write to
                    at = digests.window(conn, person, now) if person and person.in_audience else None
                    if at is None or reports.fired(conn, inst["id"], who, report.source, at):
                        continue
                    if inst["status"] != "active":
                        reports.fire(conn, inst["id"], who, report.source, at, now, "suspended")
                        ledger.append(conn, {
                            "kind": "run", "action": "open", "run": None, "instance": inst["id"],
                            "acts_for": [who], "decision": "deny",
                            "reasons": [f"{inst['id']} is suspended"],
                            "args": {"trigger": "report", "person": who, "source": report.source,
                                     "due": at.isoformat()}})
                        continue
                    if records is None:
                        try:
                            records = gw.scenario.watched()
                        except Exception:  # each report waits for a sweep that can read them
                            log.exception("couldn't read the records for reports")
                            return due
                    news = reports.news(conn, gw.scenario.name, inst["id"], person, report.source,
                                        records, now)
                    if news.facts:
                        due.append({"kind": "report", "report": {"person": who, "source": report.source},
                                    "instance": inst["id"], "agent": inst["definition"], "person": who})
                    else:  # nothing new, so no model starts
                        reports.fire(conn, inst["id"], who, report.source, at, now, "nothing new")
        return due

    @app.post("/reminders/sweep", dependencies=[Depends(service)])
    def sweep_reminders() -> list[dict]:
        """The reminders people agreed to that are due now, for their agents to give. If an
        agent can't act, the core reminds them itself, in code, so nothing they asked for is
        lost to a suspension or a withdrawn release."""
        now, due, sends = gw.clock(), [], []
        with db.transaction(gw.url) as conn:
            runs, digest_open = not gw.release_problems(conn), gw.digest_open(conn, now)
            for row in conn.execute(
                    "select * from reminders where confirmed_at is not null and reminded_at is null "
                    "and cancelled_at is null and due_at <= %s order by due_at, id for update",
                    (now,)).fetchall():
                person = gw.scenario.person(row["person"])
                if row["in_digest"] and person and not digest_open(person):
                    continue  # it waits for their digest's time
                inst = conn.execute("select * from instances where id = %s",
                                    (row["instance_id"],)).fetchone()
                if runs and inst["status"] == "active" and not gw.check_instance(conn, inst):
                    due.append({"kind": "reminder", "reminder": row["id"], "instance": inst["id"],
                                "agent": row["agent"], "person": row["person"]})
                    continue
                conn.execute("update reminders set reminded_at = %s where id = %s", (now, row["id"]))
                if person is None or not person.in_audience:
                    continue  # a5s may not write to them now
                status = inst["status"] if inst["status"] != "active" else "unable to act"
                text = reminders.notice(row, person, status)
                if row["in_digest"]:  # a5s's own item in their digest
                    digests.keep(conn, person.id, None, inst["id"], None, text, now)
                    ledger.append(conn, {
                        "kind": "notice", "action": "remind", "run": None, "instance": inst["id"],
                        "acts_for": [person.id], "decision": "record",
                        "args": {"reminder": row["id"], "channel": "digest", "chars": len(text),
                                 "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                    continue
                route = gw.reach(conn, person.id, row["agent"])
                ledger.append(conn, {
                    "kind": "notice", "action": "remind", "run": None, "instance": inst["id"],
                    "acts_for": [person.id], "decision": "record",
                    "args": {"reminder": row["id"], "channel": route["channel"], "chars": len(text),
                             "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                if route["channel"] in PUSHED:
                    sends.append((route, text, inst["id"]))
                else:  # they collect it from the local channel's inbox
                    conn.execute("insert into outbox (instance_id, agent, person, channel, text) "
                                 "values (%s, %s, %s, 'local', %s)",
                                 (inst["id"], row["agent"], person.id, text))
        for route, text, instance in sends:
            deliver(route, text, None, instance)
        return due

    @app.post("/digests/sweep", dependencies=[Depends(service)])
    def sweep_digests() -> list[dict]:
        """Send each person's digest, once its time has come today and their agents' work for
        it is done. One item goes as itself, from its agent; more go as one message from a5s.
        A day with nothing to tell sends nothing, but closes the day all the same."""
        now, sent, sends = gw.clock(), [], []
        with db.transaction(gw.url) as conn:
            able = gw.able(conn)
            people = {p for row in conn.execute("select serves from instances "
                                                "where status <> 'retired'") for p in row["serves"]}
            people |= {r["person"] for r in conn.execute(
                "select distinct person from digest_items where digest_due is null")}
            for who in sorted(people):
                person = gw.scenario.person(who)
                due = digests.window(conn, person, now) if person and person.in_audience else None
                if due is None or gw.busy(conn, person, due, now, able):
                    continue
                items = digests.waiting(conn, who)
                if not items:
                    digests.close(conn, who, due, now, [], None)
                    continue
                one = items[0] if len(items) == 1 else None
                text = one["text"] if one else digests.compose(person, items, due)
                route = gw.reach(conn, who, one["agent"] if one else None)
                ledger.append(conn, {
                    "kind": "notice", "action": "digest", "run": None,
                    "instance": one["instance_id"] if one else None, "acts_for": [who],
                    "decision": "record", "args": {"items": len(items), "channel": route["channel"],
                                                   "chars": len(text),
                                                   "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                digests.close(conn, who, due, now, items, route["channel"])
                if route["channel"] in PUSHED:
                    sends.append((route, text, items))
                else:  # they collect it from the local channel's inbox
                    conn.execute(
                        "insert into outbox (run_id, instance_id, agent, person, channel, text) "
                        "values (%s, %s, %s, %s, 'local', %s)",
                        (one["run_id"] if one else None, one["instance_id"] if one else None,
                         one["agent"] if one else None, who, text))
                    for item in items:  # a report counts as told once it's theirs to read
                        if item["run_id"]:
                            reports.told(conn, str(item["run_id"]))
                sent.append({"person": who, "items": len(items), "channel": route["channel"]})
        for route, text, items in sends:
            if not deliver(route, text, None, items[0]["instance_id"] if len(items) == 1 else None):
                with db.transaction(gw.url) as conn:
                    for item in items:
                        if item["run_id"]:
                            reports.told(conn, str(item["run_id"]))
        return sent

    # Settings the instance approvers approve where they work (core/approvals.py)

    @app.post("/settings/proposals", dependencies=[Depends(service)])
    def propose(body: Proposal) -> dict:
        """Ask the instance approvers to approve a version of the settings: each gets a card in
        the chat they last had with a5s, or a link where there are no cards. A version asked
        about before is asked about once."""
        if problem := gw.approving():
            raise HTTPException(503, problem)
        try:
            settings = parse_settings(base64.b64decode(body.raw, validate=True))
        except (binascii.Error, ValueError, yaml.YAMLError, KeyError, TypeError,
                AttributeError) as exc:
            raise HTTPException(400, f"that isn't a version of the settings: {exc}") from None
        sends, asked = [], []
        with db.transaction(gw.url) as conn:
            last = approvals.latest(conn, gw.scenario.name)
            refused = gw.unusable(settings, last)
            if refused:
                ledger.append(conn, {"kind": "admin", "action": "propose", "decision": "deny",
                                     "reasons": refused, "args": {"settings": settings.version,
                                                                  "serial": settings.serial}})
            else:
                row, new = approvals.propose(conn, gw.scenario.name, settings)
                before = parse_settings(bytes(last["raw"])) if last else None
                found = approvals.changes(before, settings, gw.definitions, gw.scenario.person)
                link = f"{gw.public_url}/approve/?settings={row['digest']}"
            if not refused and new:
                ledger.append(conn, {"kind": "admin", "action": "propose", "decision": "record",
                                     "args": {"settings": settings.version, "serial": settings.serial,
                                              "digest": row["digest"],
                                              "widens": any(c["widens"] for c in found)}})
                text = approvals.text(settings.serial, found, link)
                for approver in gw.scenario.holders(INSTANCE_APPROVER):
                    route = gw.reach(conn, approver.id, None)
                    ledger.append(conn, {
                        "kind": "notice", "action": "ask-approval", "run": None, "instance": None,
                        "acts_for": [], "decision": "record",
                        "args": {"settings": settings.version, "to": approver.id,
                                 "channel": route["channel"], "chars": len(text),
                                 "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                    if route["channel"] in PUSHED:
                        sends.append((route, text))
                    else:  # they collect it from the local channel's inbox
                        conn.execute("insert into outbox (person, channel, text) "
                                     "values (%s, 'local', %s)", (approver.id, text))
                    asked.append(approver.id)
        if refused:
            raise HTTPException(409, {"reasons": refused})
        for route, text in sends:
            deliver(route, text, None, None, card=approvals.card(settings.serial, found, link))
        return {"settings": settings.version, "serial": settings.serial, "digest": row["digest"],
                "link": link, "changes": found, "asked": asked, "new": new}

    @app.post("/settings/sweep", dependencies=[Depends(service)])
    def sweep_settings() -> dict:
        """Apply the newest version of the settings an instance approver has approved where
        they work, and let go of the versions it leaves behind."""
        applied = []
        with db.transaction(gw.url) as conn:
            if not conn.execute("select pg_try_advisory_xact_lock(hashtext('a5s settings')) as got"
                                ).fetchone()["got"]:
                return {"applied": []}  # another sweep is at work
            last = approvals.latest(conn, gw.scenario.name)
            for row in conn.execute("select * from settings_proposals where scenario = %s "
                                    "and outcome is null order by serial desc",
                                    (gw.scenario.name,)).fetchall():
                if last and row["serial"] <= last["serial"]:
                    outcome = "superseded"
                else:
                    approved, _ = approvals.approvers(conn, gw.cfg.seal_keys, gw.scenario.name,
                                                      row["digest"])
                    settings = parse_settings(bytes(row["raw"]))
                    if not registry.signers(settings, gw.scenario.person, approved)[0]:
                        continue  # no instance approver has approved it yet
                    if refused := gw.unusable(settings, last):  # such as a release gone since
                        ledger.append(conn, {"kind": "admin", "action": "apply", "decision": "deny",
                                             "reasons": refused, "args": {
                                                 "settings": settings.version,
                                                 "serial": settings.serial}})
                    else:
                        result = registry.apply(conn, gw.definitions, settings, gw.scenario.tools(),
                                                gw.scenario.person, gw.scenario.name, approved)
                        refused = result.refused
                    outcome = ("refused: " + "; ".join(refused)) if refused else "applied"
                    if not refused:
                        last = {"serial": row["serial"]}
                        applied.append({"serial": row["serial"], "approved_by": approved})
                conn.execute("update settings_proposals set outcome = %s, decided_at = now() "
                             "where scenario = %s and digest = %s",
                             (outcome, gw.scenario.name, row["digest"]))
        return {"applied": applied}

    # Instances: anyone with the role can make a5s safer alone.

    def who_asks(body: StatusChange) -> tuple[str, str]:
        """Who's suspending or resuming, from their sign-in, and how a5s knows."""
        if gw.identity is not None:
            if not body.identity:
                raise HTTPException(401, "sign in: send your token as identity")
            try:
                person = signed_in(gw.identity, gw.scenario, body.identity)
            except UnknownPerson as exc:
                raise HTTPException(403, str(exc)) from None
            except IdentityError as exc:
                raise HTTPException(401, f"your token doesn't check out: {exc}") from None
            if body.by and body.by != person:
                raise HTTPException(403, f"you're signed in as {person}, not {body.by}")
            return person, "verified"
        if not gw.cfg.development:
            raise HTTPException(503, "suspending and resuming need sign-in: set A5S_OIDC_ISSUER")
        if not body.by or gw.scenario.person(body.by) is None:
            raise HTTPException(400, "say who you are, as someone in the directory")
        return body.by, "unverified (development)"

    @app.post("/instances/{instance}/suspend", dependencies=[Depends(service)])
    def suspend(instance: str, body: StatusChange) -> dict:
        by, identity = who_asks(body)
        with db.transaction(gw.url) as conn:
            problem = registry.set_status(conn, instance, by=by, suspend=True, identity=identity)
        if problem:
            raise HTTPException(404, problem)
        return {"suspended": instance, "by": by}

    @app.post("/instances/{instance}/resume", dependencies=[Depends(service)])
    def resume(instance: str, body: StatusChange) -> dict:
        by, identity = who_asks(body)
        with db.transaction(gw.url) as conn:
            problem = registry.set_status(conn, instance, by=by, suspend=False, identity=identity)
        if problem:
            raise HTTPException(403, problem)
        return {"resumed": instance, "by": by}

    # What a worker may ask, with its run token.

    @app.get("/run")
    def run_info(token: str = Depends(run_token)) -> dict:
        """What a worker needs for its run: the release's instructions, the model, the tools,
        and what a5s knows from its own records for the run, built by code, such as the
        profile of the one person it acts for."""
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            person = gw.scenario.person(row["acts_for"][0]) if len(row["acts_for"]) == 1 else None
            context = [profiles.section(conn, person)] if person else []
        definition = gw.definitions.get(row["definition"])
        if definition is None or definition.release_id != row["release"]:
            raise HTTPException(409, f"release {row['release']} isn't loaded in this gateway")
        model = gw.models.get(row["model"])
        tools = {**gw.scenario.tools(), **CORE_TOOLS}  # a5s's own first
        return {
            "run": row["run"],
            "instance": row["id"],
            "acts_for": list(row["acts_for"]),
            "instructions": definition.instructions,
            "context": context,
            "model": {"alias": model.alias, "api": model.api} if model else None,
            "tools": [tools[n].definition() for n in row["grants"] if n in tools],
        }

    def record(entry: dict) -> bool:
        """Record what happened after a call was made. If that fails, the call still happened."""
        try:
            with db.transaction(gw.url) as conn:
                ledger.append(conn, entry)
            return True
        except psycopg.Error:
            log.exception("couldn't record the outcome of %s %s", entry["kind"], entry["action"])
            return False

    @app.post("/run/tools/{name}")
    def call_tool(name: str, body: ToolArgs, token: str = Depends(run_token)) -> Any:
        core = CORE_TOOLS.get(name)
        tool = None if core else gw.scenario.tools().get(name)
        args, removed = dict(body.args), 0
        for field_name in (core or tool).text_fields if (core or tool) else ():
            if isinstance(args.get(field_name), str):
                args[field_name], dropped = sanitize(args[field_name], gw.scenario.record_links)
                removed += dropped
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            entity = gw.core_tool_entity(name) if core else gw.tool_entity(name, tool, row["pins"])
            decision = gw.decide(row, "call_tool", entity, [])
            seq = ledger.append(conn, gw.entry(row, "tool", name, decision, args=ledger.mask(args),
                                               links_removed=removed))
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if core is not None:
            return call_core_tool(core, args, row, seq)
        try:
            result = tool.run(ToolCall(args=args, instance=row["id"], run=row["run"],
                                       acts_for=tuple(row["acts_for"])))
            outcome = {"status": "ok", "result_sha256": ledger.digest(result)}
        except Exception as exc:  # noqa: BLE001 - the tool's own failure, recorded and reported
            result, outcome = None, {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:200]}
        recorded = record({"kind": "tool", "action": name, "run": row["run"], "instance": row["id"],
                           "decision": "record", "of": seq, "outcome": outcome})
        if outcome["status"] != "ok":
            return JSONResponse(status_code=502, content={"error": outcome["error"]})
        return {"result": result, "recorded": recorded}

    def call_core_tool(core: coretools.CoreTool, args: dict, row: dict, seq: int) -> Any:
        """One of a5s's own tools, in one transaction with what it changes. A rule of a5s's
        it would break is a denial, in words the agent passes on."""
        try:
            with db.transaction(gw.url) as conn:
                result = core.run(coretools.Call(conn, row, args, gw.clock(), gw.scenario))
        except coretools.Refused as exc:
            record({"kind": "tool", "action": core.name, "run": row["run"], "instance": row["id"],
                    "decision": "record", "of": seq,
                    "outcome": {"status": "refused", "reason": str(exc)}})
            return JSONResponse(status_code=403, content={"denied": True, "reasons": [str(exc)],
                                                          "explanations": [str(exc)]})
        except Exception as exc:  # noqa: BLE001 - recorded and reported, as for any tool
            outcome = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:200]}
            record({"kind": "tool", "action": core.name, "run": row["run"], "instance": row["id"],
                    "decision": "record", "of": seq, "outcome": outcome})
            return JSONResponse(status_code=502, content={"error": outcome["error"]})
        recorded = record({"kind": "tool", "action": core.name, "run": row["run"],
                           "instance": row["id"], "decision": "record", "of": seq,
                           "outcome": {"status": "ok", "result_sha256": ledger.digest(result)}})
        return {"result": result, "recorded": recorded}

    @app.post("/run/messages")
    def send_message(body: Message, token: str = Depends(run_token)) -> Any:
        person = gw.scenario.person(body.to)
        text, removed = sanitize(body.text, gw.scenario.record_links)
        recipient = {
            "uid": {"type": "Person", "id": body.to},
            "attrs": {"in_audience": bool(person and person.in_audience)},
            "parents": [],
        }
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            inbound = row["trigger"].get("inbound")
            route = None
            if body.to not in row["acts_for"]:
                why = ("a run writes only to the people it acts for, such as whoever sent the "
                       "message it answers")
                decision = Decision(False, ("writes-to-whom-it-acts-for",), explanations=(why,))
            else:
                decision = gw.decide(row, "send_message", recipient, [])
                route = (gw.message_of(conn, inbound) if inbound  # an answer, where it was asked
                         else {"channel": "digest", "reply_to": {}} if gw.for_digest(conn, row)
                         else gw.reach(conn, body.to, row["definition"]))
            ledger.append(conn, gw.entry(row, "message", "send", decision, args={
                "to": body.to, "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "links_removed": removed, **({"channel": route["channel"]} if route else {}),
            }))
            if decision.allowed and route["channel"] == "digest":  # it goes in their next digest
                digests.keep(conn, body.to, row["definition"], row["id"], row["run"], text, gw.clock())
            elif decision.allowed and route["channel"] not in PUSHED:  # people collect it from here
                conn.execute(
                    "insert into outbox (run_id, instance_id, agent, inbound_id, person, channel, "
                    "text) values (%s, %s, %s, %s, %s, %s, %s)",
                    (row["run"], row["id"], row["definition"], inbound, body.to, route["channel"],
                     text))
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if route["channel"] in PUSHED:
            problem = deliver(route, text, row["run"], row["id"])
            if problem:
                return JSONResponse(status_code=502, content={"error": problem})
        return {"sent": True, "text": text, "links_removed": removed}

    def deliver(route: dict, text: str, run: str | None, instance: str | None,
                card: dict | None = None) -> str | None:
        """Send text through a chat a5s writes to itself, such as Teams or Matrix, starting the
        conversation first if the route says to, and record whether it got there. The problem,
        if not. In Teams, a card goes instead of the text, if there is one."""
        channel, problem, started = route["channel"], None, False
        chat = gw.chat(channel)
        if chat is None:
            problem = f"{channel} isn't set up in this gateway"
        else:
            try:
                reply_to = route["reply_to"]
                if "start" in route:
                    reply_to, started = start(channel, chat, **route["start"])
                if card is not None and channel == "teams":
                    chat.send(reply_to, text, card=card)
                else:
                    chat.send(reply_to, text)
            except (httpx.HTTPError, ValueError) as exc:
                problem = f"{channel} didn't take it: {type(exc).__name__}: {exc}"[:200]
        record({"kind": "message", "action": "deliver", "run": run, "instance": instance,
                "decision": "record", "outcome": {"status": "error", "error": problem} if problem
                else {"status": "ok", "channel": channel, **({"started": True} if started else {})}})
        return problem

    def start(channel: str, chat: Any, person: str, agent: str, user: str) -> tuple[dict, bool]:
        """The conversation an agent's bot starts with someone, unless another delivery started
        it first. Where to send to it, and whether this started it."""
        with db.transaction(gw.url) as conn:
            conn.execute("select pg_advisory_xact_lock(hashtext(%s))",
                         (f"start {channel} {person} {agent}",))
            row = conn.execute(
                "select reply_to from chats where channel = %s and person = %s and agent = %s "
                "and started_at is not null and left_at is null order by started_at desc limit 1",
                (channel, person, agent)).fetchone()
            if row is not None:
                return row["reply_to"], False
            reply_to = chat.start(user, agent)
            chats.started(conn, channel, person, agent, reply_to)
            return reply_to, True

    @app.post("/notices", dependencies=[Depends(service)])
    def notice(body: Notice) -> dict:
        """a5s's own words, such as "the assistant is suspended", only ever in answer to someone."""
        text, _ = sanitize(body.text, ())
        try:
            inbound = str(uuid.UUID(body.inbound))
        except ValueError:
            raise HTTPException(404, "no such message") from None
        with db.transaction(gw.url) as conn:
            row = conn.execute(
                "update inbound set notices = notices + 1 where id = %s and notices < 3 "
                "returning person, agent, channel, reply_to", (inbound,)).fetchone()
            if row is not None:
                ledger.append(conn, {"kind": "notice", "action": "send", "run": None,
                                     "instance": body.instance, "acts_for": [row["person"]],
                                     "decision": "allow", "args": {
                                         "inbound": inbound, "chars": len(text),
                                         "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                if row["channel"] not in PUSHED:
                    conn.execute(
                        "insert into outbox (instance_id, agent, inbound_id, person, channel, text) "
                        "values (%s, %s, %s, %s, %s, %s)",
                        (body.instance, row["agent"], inbound, row["person"], row["channel"], text))
        if row is None:
            raise HTTPException(403, "a5s only answers a message someone sent, and briefly")
        if row["channel"] in PUSHED:
            problem = deliver(row, text, None, body.instance)
            if problem:
                raise HTTPException(502, problem)
        return {"sent": True, "text": text}

    # The model gateway, in both API styles.

    def model_call(api: str, body: dict[str, Any], token: str) -> JSONResponse:
        alias = body.get("model", "")
        model = gw.models.get(alias)
        if body.get("stream"):
            return JSONResponse(status_code=400, content=models.error_body(
                api, "streaming isn't supported yet", "invalid_request_error"))
        approved = {
            "uid": {"type": "Model", "id": alias},
            "attrs": {"name": alias, "approved": bool(model and model.api == api)},
            "parents": [],
        }
        prompt = {"system": body.get("system"), "messages": body.get("messages")}
        forwarded, dropped, refusal = models.screen(api, body)
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            if refusal:
                decision = Decision(False, ("agents-use-their-own-tools",), explanations=(refusal,))
            else:
                decision = gw.decide(row, "call_model", approved, [])
            seq = ledger.append(conn, gw.entry(row, "model", alias, decision, args={
                "prompt_sha256": ledger.digest(prompt),
                "messages": len(body.get("messages") or []),
                "tools": len(body.get("tools") or []),
                "tools_sha256": ledger.digest(forwarded.get("tools")),
                "params": {k: v for k, v in forwarded.items()
                           if k not in ("model", "messages", "system", "tools")},
                "left_out": dropped,
            }, provider=model.provider if model else None))
        if not decision.allowed:
            return JSONResponse(status_code=403, content=models.error_body(
                api, "denied by policy: " + "; ".join(decision.explanations)))
        try:
            status, data = models.forward(model, forwarded, gw.http)
        except models.ModelUnavailable as exc:
            status, data = 503, models.error_body(api, str(exc), "model_unavailable")
        reported = data.get("model") if isinstance(data, dict) else None
        expected = model.reported_model or model.model
        if status < 400 and reported != expected:
            status, data = 502, models.error_body(
                api, f"the provider reported {reported}, not the approved {expected}",
                "model_mismatch")
        recorded = record({"kind": "model", "action": alias, "run": row["run"], "instance": row["id"],
                           "decision": "record", "of": seq,
                           "outcome": {"status": status, "reported_model": reported,
                                       "usage": data.get("usage") if isinstance(data, dict) else None}})
        return JSONResponse(status_code=status, content=data,
                            headers=None if recorded else {"x-a5s-recorded": "false"})

    @app.post("/v1/chat/completions")
    def openai_style(body: dict[str, Any], token: str = Depends(run_token)) -> JSONResponse:
        return model_call("openai", body, token)

    @app.post("/v1/messages")
    def anthropic_style(body: dict[str, Any], token: str = Depends(run_token)) -> JSONResponse:
        return model_call("anthropic", body, token)

    return app
