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
import json
import logging
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
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
    budgets,
    chats,
    coretools,
    digests,
    handles,
    ledger,
    models,
    obligations,
    parts,
    profiles,
    proposals,
    provenance,
    recall,
    registry,
    releases,
    reminders,
    reports,
    retention,
    schedules,
    status,
    topics,
    traces,
    urgent,
)
from a5s.core.breakers import FAILURES, Breakers
from a5s.core.identity import IdentityError, UnknownPerson, Verifier, signed_in
from a5s.core.matrix import Matrix
from a5s.core.policy import Decision, PolicyEngine
from a5s.core.teams import Teams
from a5s.definitions import Context, Definition

log = logging.getLogger(__name__)
CORE_TOOLS = {**reminders.TOOLS, **digests.TOOLS, **profiles.TOOLS,  # a5s's own, on its
              **recall.TOOLS}  # own records
RUN_MINUTES = 60  # the longest a run may last [TBC]; its token dies with it
CHARS_PER_TOKEN = 4  # roughly, for a run's budget for its conversation
OWN_RUNS = ("summary",)  # a5s's own work on a conversation: no tools, and it writes to nobody
TRIES = 5  # deliveries to a chat before what it didn't take is left in the person's inbox
WHY = {  # why an agent's run didn't get its message through, in words people read
    "model unavailable": "its model isn't answering", "budget spent": "it has used its budget "
    "for today", "reply denied": "a5s didn't let its message through", "abandoned": "it stopped "
    "before it finished"}
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
# a5s's own note on values, which only a5s writes: an agent's copy of one is dropped
_FORGED_NOTE = re.compile(r"(?is)\(\s*a5s\s*:.*?\)")


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

    text, forged = _FORGED_NOTE.subn("", text)
    text, images = _IMAGE.subn("[image removed]", text)
    text, tags = _TAG.subn("[removed]", text)
    text = _MARKDOWN_LINK.sub(link, text)
    parts = re.split(r"(\[[^\]]*\]\([^)]*\))", text)  # record links already kept stay whole
    text = "".join(p if _MARKDOWN_LINK.fullmatch(p) else _URL.sub(url, p) for p in parts)
    return text.strip() if forged else text, removed + images + tags + forged


def cleaned(value: Any, allowed: tuple[str, ...]) -> tuple[Any, int]:
    """Text at any depth of a value, sanitized, and how many things were removed."""
    if isinstance(value, str):
        return sanitize(value, allowed)
    if isinstance(value, list):
        found = [cleaned(item, allowed) for item in value]
        return [v for v, _ in found], sum(n for _, n in found)
    if isinstance(value, dict):
        found = {k: cleaned(v, allowed) for k, v in value.items()}
        return {k: v for k, (v, _) in found.items()}, sum(n for _, n in found.values())
    return value, 0


def strings(value: Any) -> list[str]:
    """Every string at any depth of a value, in order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    return []


_TYPES = {"string": str, "integer": int, "number": int | float, "boolean": bool, "object": dict,
          "array": list, "null": type(None)}


def misfit(schema: dict[str, Any], value: Any, where: str = "") -> str | None:
    """Why a tool's arguments don't fit its pinned schema, if they don't: the types, required
    properties and items it names. A model can send anything, so a call must fit its schema
    before policy looks at it."""
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind] if kind else []
    if kinds and not any(isinstance(value, _TYPES.get(k, object)) and not (
            k in ("integer", "number") and isinstance(value, bool)) for k in kinds):
        return f"{where or 'the arguments'} should be {' or '.join(kinds)}"
    if isinstance(value, dict):
        for name in schema.get("required") or []:
            if name not in value:
                return f"{where}{'.' if where else ''}{name} is missing"
        for name, found in value.items():
            sub = (schema.get("properties") or {}).get(name)
            if sub is None and schema.get("additionalProperties") is False:
                return f"{where}{'.' if where else ''}{name} isn't one of its arguments"
            if sub and (problem := misfit(sub, found, f"{where}{'.' if where else ''}{name}")):
                return problem
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for n, item in enumerate(value):
            if problem := misfit(schema["items"], item, f"{where}[{n}]"):
                return problem
    return None


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
    breakers: Breakers = field(default_factory=Breakers)  # models not called for now (core/breakers.py)

    @property
    def url(self) -> str:
        return self.cfg.database_url

    def settings_in_force(self, conn: psycopg.Connection) -> tuple[Any, str | None]:
        """The latest signed version of the settings, checked again from the bytes that were
        signed, against the directory as it is now: every time, with nothing cached, so an
        approver who loses their role, or a seal key withdrawn, counts at once."""
        rows = conn.execute("select serial, version, raw, signatures from settings_versions "
                            "where scenario = %s order by serial desc limit 2",
                            (self.scenario.name,)).fetchall()
        if not rows:
            return None, "no settings have been applied"
        try:
            found = [(row, parse_settings(bytes(row["raw"] or b""), tuple(
                Signature(s["signer"], s["value"]) for s in row["signatures"] or [])))
                for row in rows]
        except ValueError as exc:
            return None, f"the settings in force can't be read: {exc}"
        if any((s.version, s.serial) != (row["version"], row["serial"]) for row, s in found):
            return None, "the settings in force aren't what was signed"
        settings, before = found[0][1], found[1][1] if len(found) > 1 else None
        approved, _ = approvals.approvers(conn, self.cfg.seal_keys, self.scenario.name,
                                          approvals.digest(settings.raw))
        valid, _ = registry.signers(settings, self.scenario.person, approved)
        if needs := registry.missing(settings, self.scenario.person, valid, before):
            return None, f"the settings in force aren't approved: {needs[0]}"
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
        level, scope = registry.levels(signed, release)
        expected = (signed.definition, sorted(signed.serves), level, scope, sorted(release.grants),
                    release.model, release.pins, signed.owner or release.owner,
                    signed.deputy or release.deputy)
        actual = (inst["definition"], sorted(inst["serves"]), inst["level"], inst["parts"] or {},
                  sorted(inst["grants"]), inst["model"], inst["pins"], inst["owner"],
                  inst["deputy"])
        if expected != actual:
            log.error("instance %s doesn't match its signed settings and release", inst["id"])
            return [f"{inst['id']}'s record doesn't match its signed settings and release"]
        last = conn.execute(
            "select action, entry from ledger where instance_id = %s and kind = 'admin' "
            "and action in ('suspend', 'resume', 'retire', 'restore') order by seq desc limit 1",
            (inst["id"],)).fetchone()
        expected = _STATUS_AFTER.get(last["action"] if last else "", "active")
        if last and last["action"] == "restore":  # as it was before it was retired
            expected = (json.loads(last["entry"]).get("args") or {}).get("status", "active")
        if inst["status"] != expected:
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
            "returning id::text, person, channel, agent, text", (inbound,)).fetchone()
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

    def at_once(self, conn: psycopg.Connection, person: str, agent: str | None, *,
                count: bool = True) -> dict:
        """How to write at once to someone who isn't waiting for it, as reach says, unless
        they've had today's urgent messages, when it waits for their next batch. Only a
        message that will go is counted."""
        if count and not urgent.counted(conn, self.scenario, person, self.clock()):
            return {"channel": "batch", "reply_to": {}}
        return self.reach(conn, person, agent)

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
        chase, a report, or a reminder for the day. What's due is checked before what's
        running: a run that opens between the two checks has marked its work as begun before
        the second, so it's seen running, never missed; and one that ends has left its item."""
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
        for inst in conn.execute("select * from instances where status <> 'retired'").fetchall():
            if not registry.serving(self.scenario, inst["serves"], person.id):
                continue
            definition = self.definitions.get(inst["definition"])
            if (able.get(inst["id"]) and definition and definition.release_id == inst["release"]
                    and any(not reports.fired(conn, inst["id"], person.id, r.source, due)
                            for r in definition.reports)):
                return True
        return bool(conn.execute("select 1 from runs where closed_at is null and expires_at > now() "
                                 "and %s = any(acts_for) and trigger->>'kind' = any(%s)",
                                 (person.id, list(digests.KINDS))).fetchone())

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
        """Why a version of the settings couldn't be applied, before anyone's asked to approve
        it: an old serial, a release or tools this deployment doesn't have, or people the
        directory doesn't know."""
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
            groups = [p for p in instance.serves if p.startswith(("team:", "role:"))]
            people = [p for p in instance.serves if p not in groups]
            people += [p for p in (instance.owner, instance.deputy) if p]
            if unknown := sorted({p for p in people if self.scenario.person(p) is None}):
                problems.append(f"{instance.id} names people the directory doesn't know: "
                                f"{', '.join(unknown)}")
            if empty := sorted(g for g in groups if not registry.served(self.scenario, [g])):
                problems.append(f"{instance.id} serves groups nobody in the directory is in: "
                                f"{', '.join(empty)}")
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
        topic = topics.of_message(conn, self.scenario, sender, inst["definition"],
                                  message["text"]) if message else topics.GENERAL
        opening = Opening(
            trigger={"kind": "message", "inbound": inbound,
                     "channel": message["channel"] if message else None, "sender": sender,
                     "topic": topic},
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
                     "person": row["person"], "topic": row["record"]},
            acts_for=[row["person"]], args={"obligation": number, "record": row["record"]},
            reasons=[], task=obligations.chase(row, person, withheld=self.title_hidden(
                conn, inst["model"])) if person else None,
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
        reachable = (person is not None and person.in_audience
                     and registry.serving(self.scenario, inst["serves"], who))
        due = digests.window(conn, person, now) if found and reachable else None
        args = {"person": who, "source": source, "due": due.isoformat() if due else None}
        opening = Opening(trigger={"kind": "report", "report": {"person": who, "source": source},
                                   "due": args["due"], "topic": topics.GENERAL},
                          acts_for=[who] if reachable else [], args=args, reasons=[])
        if not found:
            opening.reasons.append(f"{inst['id']}'s release doesn't report on {source}")
        elif person is None:
            opening.reasons.append(f"the directory doesn't know {who}")
        elif not registry.serving(self.scenario, inst["serves"], who):
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
                unseen = self.unseen(conn, inst["model"])  # what its model never sees
                watched = self.scenario.watched()
                reach = parts.within(self.scenario, inst, [who], watched)
                news = reports.news(conn, self.scenario.name, inst["id"], person, source, [
                    replace(r, fields={k: v for k, v in r.fields.items() if k not in unseen})
                    for r in reach], now, withheld="title" in unseen,
                    beyond=reports.beyond(watched, reach, who))
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
            trigger={"kind": "reminder", "reminder": number, "person": row["person"],
                     "topic": row["record"] or topics.GENERAL},
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

    def summarising(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                    now: datetime) -> Opening:
        """A run of a5s's own that folds the turns of a topic that no longer fit in its runs
        into the topic's summary, acting for the person whose conversation it is. It has no
        tools, and writes to nobody."""
        who, topic = str(trigger.get("person")), str(trigger.get("topic") or topics.GENERAL)
        opening = Opening(trigger={"kind": "summary", "person": who, "topic": topic},
                          acts_for=[who], args={"person": who, "topic": topic}, reasons=[])
        if self.scenario.person(who) is None:
            opening.reasons.append(f"the directory doesn't know {who}")
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
                          "writes": False, "destructive": False, "sends_outside": False,
                          "action": ""},
                "parents": []}

    @staticmethod
    def tool_entity(name: str, tool: Tool | None, pins: dict) -> dict:
        risk = tool.risk if tool else dict.fromkeys(("reads", "writes", "destructive", "sends_outside"), False)
        pinned = tool is not None and pins.get(name) == tool.schema_hash
        return {
            "uid": {"type": "Tool", "id": name},
            "attrs": {"name": name, "known": tool is not None, "pinned": pinned, **risk,
                      "action": (tool.action or "") if tool else ""},
            "parents": [],
        }

    def decide(self, row: dict, action: str, resource: dict, extra: list[dict],
               **context: Any) -> Decision:
        given = {"level": row["level"], "read_outside": row["read_outside"],
                 "acts_for": list(row["acts_for"])}
        if action != "call_model":  # about no record, unless the call says otherwise
            given |= {"in_scope": True, "visible": True}
        return self.policy.decide(
            principal={"type": "Instance", "id": row["id"]},
            action=action,
            resource=resource["uid"],
            context={**given, **context},
            entities=[self.instance_entity(row), resource, *extra],
        )

    def unseen(self, conn: psycopg.Connection, alias: str) -> set[str]:
        """The fields of a class the instance's model isn't approved for, which it never sees.
        If the settings in force don't check out, nothing a5s could hand over is safe: it
        raises, and the call fails closed."""
        settings, problem = self.settings_in_force(conn)
        if settings is None:
            raise RuntimeError(f"the settings in force don't check out: {problem}")
        model = self.models.get(alias)
        classes = model.data_classes if model else ()
        return {f for f, cls in settings.classified.items() if cls not in classes}

    def title_hidden(self, conn: psycopg.Connection, alias: str) -> bool:
        """Whether records' titles are of a class the model isn't approved for, or the settings
        in force can't say, so a5s writes no title into what it tells the model."""
        try:
            return "title" in self.unseen(conn, alias)
        except RuntimeError:
            return True

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


def values_of(traced: list[dict]) -> dict:
    """For the ledger: how many of the values an agent wrote came from what it read, and
    which it wrote itself."""
    return {"sourced": sum(1 for t in traced if t["from"]),
            "own": [t["value"] for t in traced if not t["from"]]}


def load_run(conn: psycopg.Connection, token: str) -> dict:
    row = conn.execute(
        """
        select r.id::text as run, r.acts_for, r.read_outside, r.trigger, r.tokens, i.*
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
        with traces.span("open_run", **{"a5s.instance": body.instance,
                                        "a5s.trigger": str(body.trigger.get("kind"))}) as current:
            return opening_run(body, current)

    def opening_run(body: OpenRun, current: Any) -> dict:
        kind = body.trigger.get("kind")
        opens = {"message": gw.answering, "obligation": gw.reminding, "schedule": gw.scheduled,
                 "report": gw.reporting, "reminder": gw.following_up, "summary": gw.summarising}
        if kind not in opens:
            raise HTTPException(400, "a run answers a message, reminds someone of an obligation "
                                     "or of what they asked, works on a schedule, tells someone "
                                     "about their records, or keeps a topic's summary")
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
            if any(not registry.serving(gw.scenario, inst["serves"], p) for p in opening.acts_for):
                reasons.append(f"{body.instance} doesn't serve {', '.join(opening.acts_for)}")
            reasons += gw.check_instance(conn, inst) + gw.release_problems(conn)
            release = gw.definitions.get(inst["definition"])
            spent = None if reasons or release is None else budgets.refused(
                conn, gw.scenario, release.budget, body.instance, opening.acts_for, kind, 0, now)
            pushing = []
            if spent:  # the work waits, a report for the next day; a5s gives what's owed itself
                reasons.append(spent)
                if kind in ("reminder", "obligation") and not opening.used:
                    pushing = give_instead(conn, opening.trigger, WHY["budget spent"])
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
                if opening.task:  # what a5s asks it, from the records: something it has read
                    provenance.read(conn, run_id, provenance.A5S, opening.task,
                                    gw.scenario.record_pattern)
            ledger.append(conn, {
                "kind": "run", "action": "open", "run": None if reasons else run_id,
                "instance": body.instance, "acts_for": opening.acts_for,
                "decision": "deny" if reasons else "allow", "reasons": reasons,
                "args": {"trigger": kind, **opening.args},
            })
        traces.note(current, **{"a5s.run.id": None if reasons else run_id,
                                "a5s.decision": "deny" if reasons else "allow"})
        push(pushing)
        if reasons:
            raise HTTPException(409, {"reasons": reasons, "status": inst["status"],
                                      "owner": inst["owner"], "suspended_by": inst["suspended_by"],
                                      "answered": opening.used, "out_of_budget": bool(spent)})
        return {"run": run_id, "token": token, "task": opening.task,
                "topic": opening.trigger.get("topic", topics.GENERAL),
                "history_chars": CHARS_PER_TOKEN * (release.context.budget_tokens if release
                                                    else Context().budget_tokens)}

    @app.post("/runs/sweep", dependencies=[Depends(service)])
    def sweep() -> list[dict]:
        """Close runs that outlived their time, such as ones whose scheduler stopped."""
        with db.transaction(gw.url) as conn:
            stale = conn.execute(
                "update runs set closed_at = now(), outcome = 'abandoned' "
                "where closed_at is null and expires_at < now() "
                "returning id::text as run, instance_id, trigger").fetchall()
            sends = []
            for row in stale:
                ledger.append(conn, {"kind": "run", "action": "close", "run": row["run"],
                                     "instance": row["instance_id"], "decision": "record",
                                     "outcome": "abandoned"})
                sends += give_instead(conn, row["trigger"], WHY["abandoned"])
        push(sends)
        return [{"run": r["run"], "inbound": r["trigger"].get("inbound"),
                 "instance": r["instance_id"]} for r in stale]

    @app.post("/runs/{run_id}/close", dependencies=[Depends(service)])
    def close_run(run_id: str, body: CloseRun) -> dict:
        """Close a run, with how it ended. A reminder or chase whose run didn't get its message
        through, a5s gives itself, in its own words."""
        with db.transaction(gw.url) as conn:
            row = conn.execute(
                "update runs set closed_at = now(), outcome = %s where id = %s and closed_at is null "
                "returning instance_id, trigger",
                (body.outcome, run_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "no open run")
            ledger.append(conn, {"kind": "run", "action": "close", "run": run_id,
                                 "instance": row["instance_id"], "decision": "record",
                                 "outcome": body.outcome})
            sends = [] if body.outcome == "done" else give_instead(conn, row["trigger"],
                                                                     WHY.get(body.outcome))
        push(sends)
        return {"closed": run_id}

    def give_instead(conn: psycopg.Connection, trigger: dict, why: str | None) -> list[int | None]:
        """Give a reminder or a chase that its agent's run couldn't, in a5s's own words, so
        nothing someone agreed to or owes lapses because a model, a budget or a run failed.
        What to push once the transaction is done."""
        why, now = why or "it couldn't finish", gw.clock()
        if trigger.get("kind") == "reminder":
            row = conn.execute("select * from reminders where id = %s for update",
                               (trigger.get("reminder"),)).fetchone()
            person = gw.scenario.person(row["person"]) if row else None
            if row is None or row["cancelled_at"] or person is None or not person.in_audience:
                return []
            conn.execute("update reminders set reminded_at = %s where id = %s", (now, row["id"]))
            text = reminders.notice(row, person, f"unable to write to you just now, as {why}")
            ledger.append(conn, {"kind": "notice", "action": "remind", "run": None,
                                 "instance": row["instance_id"], "acts_for": [person.id],
                                 "decision": "record", "args": {
                                     "reminder": row["id"], "instead": why, "chars": len(text),
                                     "sha256": hashlib.sha256(text.encode()).hexdigest()}})
            noted(conn, person.id, row["agent"], text, row["record"])
            if row["in_digest"]:  # a reminder for a day goes in their digest
                digests.keep(conn, person.id, None, row["instance_id"], None, text, now)
                return []
            return [outbound(conn, gw.reach(conn, person.id, row["agent"]), person.id, text,
                             instance=row["instance_id"], agent=row["agent"])]
        if trigger.get("kind") == "obligation":
            row = conn.execute("select o.*, i.definition as agent from obligations o left join "
                               "instances i on i.id = o.instance_id where o.id = %s for update of o",
                               (trigger.get("obligation"),)).fetchone()
            person = gw.scenario.person(row["person"]) if row else None
            if row is None or row["done_at"] or person is None or not person.in_audience:
                return []
            conn.execute("update obligations set chased_at = %s, updated_at = %s where id = %s",
                         (now, now, row["id"]))
            text = obligations.instead(row, person, why)
            ledger.append(conn, {"kind": "notice", "action": "chase", "run": None,
                                 "instance": row["instance_id"], "acts_for": [person.id],
                                 "decision": "record", "args": {
                                     "obligation": row["id"], "record": row["record"],
                                     "instead": why, "chars": len(text),
                                     "sha256": hashlib.sha256(text.encode()).hexdigest()}})
            noted(conn, person.id, row["agent"], text, row["record"])
            digests.keep(conn, person.id, None, row["instance_id"], None, text, now)  # as chases go
        return []

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
            obligations.sync(conn, gw.scenario.name, owed, gw.definitions, now,
                             gw.scenario.part_of,
                             lambda serves, who: registry.serving(gw.scenario, serves, who))
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
                route = gw.at_once(conn, to.id, row["agent"])
                ledger.append(conn, {
                    "kind": "notice", "action": "escalate", "run": None,
                    "instance": row["instance_id"], "acts_for": [], "decision": "record",
                    "args": {"obligation": row["id"], "record": row["record"],
                             "person": row["person"], "to": to.id, "step": row["escalations"] + 1,
                             "channel": route["channel"], "chars": len(text),
                             "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                if route["channel"] == "batch":  # they've had today's urgent messages
                    urgent.hold(conn, to.id, None, row["instance_id"], None, text, now)  # a5s's
                else:  # in the chat, after this transaction, or in the local channel's inbox
                    sends.append(outbound(conn, route, to.id, text, instance=row["instance_id"],
                                          agent=row["agent"]))
                noted(conn, to.id, row["agent"], text, row["record"])
                escalated.add(row["id"])
            due = [d for d in obligations.to_chase(rows, gw.scenario, now, able,
                                                   gw.digest_open(conn, now))
                   if d["obligation"] not in escalated]
        push(sends)
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
                for report, who in ((r, p) for r in definition.reports
                                    for p in registry.served(gw.scenario, inst["serves"])):
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
                    reach = parts.within(gw.scenario, inst, [who], records)
                    news = reports.news(conn, gw.scenario.name, inst["id"], person, report.source,
                                        reach, now, beyond=reports.beyond(records, reach, who))
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
                if person is None or not person.in_audience:  # they've left, or a5s may not
                    conn.execute("update reminders set cancelled_at = %s where id = %s",  # write
                                 (now, row["id"]))  # to them: it ends, once, not every minute
                    ledger.append(conn, {"kind": "notice", "action": "remind", "run": None,
                                         "instance": row["instance_id"], "acts_for": [],
                                         "decision": "record", "args": {"reminder": row["id"]},
                                         "outcome": {"status": "ended", "why": "a5s may not "
                                                     "write to them now"}})
                    continue
                if row["in_digest"] and not digest_open(person):
                    continue  # it waits for their digest's time
                inst = conn.execute("select * from instances where id = %s",
                                    (row["instance_id"],)).fetchone()
                if runs and inst["status"] == "active" and not gw.check_instance(conn, inst):
                    due.append({"kind": "reminder", "reminder": row["id"], "instance": inst["id"],
                                "agent": row["agent"], "person": row["person"]})
                    continue
                conn.execute("update reminders set reminded_at = %s where id = %s", (now, row["id"]))
                status = inst["status"] if inst["status"] != "active" else "unable to act"
                text = reminders.notice(row, person, status)
                if row["in_digest"]:  # a5s's own item in their digest
                    digests.keep(conn, person.id, None, inst["id"], None, text, now)
                    noted(conn, person.id, row["agent"], text, row["record"])
                    ledger.append(conn, {
                        "kind": "notice", "action": "remind", "run": None, "instance": inst["id"],
                        "acts_for": [person.id], "decision": "record",
                        "args": {"reminder": row["id"], "channel": "digest", "chars": len(text),
                                 "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                    continue
                route = gw.reach(conn, person.id, row["agent"])  # they asked for it then
                ledger.append(conn, {
                    "kind": "notice", "action": "remind", "run": None, "instance": inst["id"],
                    "acts_for": [person.id], "decision": "record",
                    "args": {"reminder": row["id"], "channel": route["channel"], "chars": len(text),
                             "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                if route["channel"] == "batch":  # they've had today's urgent messages
                    urgent.hold(conn, person.id, None, inst["id"], None, text, now)  # a5s's
                else:  # in the chat, after this transaction, or in the local channel's inbox
                    sends.append(outbound(conn, route, person.id, text, instance=inst["id"],
                                          agent=row["agent"]))
                noted(conn, person.id, row["agent"], text, row["record"])
        push(sends)
        return due

    @app.post("/digests/sweep", dependencies=[Depends(service)])
    def sweep_digests() -> list[dict]:
        """Send each person's digest, once its time has come today and their agents' work for
        it is done, or has had half an hour: what's ready goes then, and the rest waits for the
        next. In a chat, where each agent writes as its own bot, each agent's items go as its
        own message, in its own chat, so an answer to one reaches the agent that wrote it. In
        the local inbox, one item goes as itself, from its agent, and more go as one message
        from a5s, each under its agent. A day with nothing to tell sends nothing, but closes
        the day all the same. And send the urgent messages held for someone, together, once
        the oldest has waited an hour, in their working hours."""
        now, sent, sends = gw.clock(), [], []
        with db.transaction(gw.url) as conn:
            able = gw.able(conn)
            agents = {i["id"]: i["definition"]
                      for i in conn.execute("select id, definition from instances")}
            people = {p for row in conn.execute("select serves from instances "
                                                "where status <> 'retired'")
                      for p in registry.served(gw.scenario, row["serves"])}
            people |= {r["person"] for r in conn.execute(
                "select distinct person from digest_items where digest_due is null")}
            for who in sorted(people):
                person = gw.scenario.person(who)
                due = digests.window(conn, person, now) if person and person.in_audience else None
                if due is None or (gw.busy(conn, person, due, now, able)
                                   and digests.waiting_since(conn, who, due, now) + digests.WAIT
                                   > now):
                    continue  # its work isn't done, and hasn't had half an hour since a5s looked
                items = digests.waiting(conn, who)
                if not items:
                    digests.close(conn, who, due, now, [], None)
                    continue
                for item in items:  # a report counts as told once a5s has it to deliver
                    if item["run_id"]:
                        reports.told(conn, str(item["run_id"]))
                groups: dict[str | None, list[dict]] = {}
                if gw.reach(conn, who, None)["channel"] in PUSHED:  # each agent in its own chat
                    for item in items:
                        groups.setdefault(item["agent"] or agents.get(item["instance_id"]),
                                          []).append(item)
                else:
                    groups[None] = items
                channels = []
                for agent, group in groups.items():
                    one = group[0] if len(group) == 1 else None
                    writer = agent or (one["agent"] if one else None)
                    text = one["text"] if one else digests.compose(person, group, due, agent)
                    route = gw.reach(conn, who, writer)
                    ledger.append(conn, {
                        "kind": "notice", "action": "digest", "run": None,
                        "instance": one["instance_id"] if one else None, "acts_for": [who],
                        "decision": "record", "args": {
                            "items": len(group), "channel": route["channel"], "chars": len(text),
                            "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                    sends.append(outbound(conn, route, who, text,
                                          run=one["run_id"] if one else None,
                                          instance=one["instance_id"] if one else None,
                                          agent=writer))
                    channels.append(route["channel"])
                digests.close(conn, who, due, now, items, channels[0])
                sent.append({"person": who, "items": len(items), "channel": channels[0]})
            for who, items in urgent.due(conn, now).items():
                person = gw.scenario.person(who)
                if person is None or not person.in_audience or not obligations.working(person, now):
                    continue  # a5s may not write to them now, or it's outside their hours
                one = items[0] if len(items) == 1 else None
                text = one["text"] if one else urgent.compose(items)
                route = gw.reach(conn, who, one["agent"] if one else None)
                ledger.append(conn, {
                    "kind": "notice", "action": "batch", "run": None,
                    "instance": one["instance_id"] if one else None, "acts_for": [who],
                    "decision": "record", "args": {"items": len(items), "channel": route["channel"],
                                                   "chars": len(text),
                                                   "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                urgent.sent(conn, items, now)
                sends.append(outbound(conn, route, who, text, run=one["run_id"] if one else None,
                                      instance=one["instance_id"] if one else None,
                                      agent=one["agent"] if one else None))
                sent.append({"person": who, "items": len(items), "channel": route["channel"],
                             "batch": True})
        push(sends)
        return sent

    # Settings the instance approvers approve where they work (core/approvals.py)

    def proposing(conn: psycopg.Connection, settings: Settings, by: str | None = None) -> dict:
        """Record a version for its approvers, and ask each of them where they work, once. What
        to send them once the transaction is done, and what the version changes; or why it
        can't be proposed. `by` is who asked for it in the settings app, if anyone did."""
        last = approvals.latest(conn, gw.scenario.name)
        asker = {"by": by} if by else {}
        if refused := gw.unusable(settings, last):
            ledger.append(conn, {"kind": "admin", "action": "propose", "decision": "deny",
                                 "reasons": refused, "args": {"settings": settings.version,
                                                              "serial": settings.serial, **asker}})
            return {"refused": refused}
        row, new = approvals.propose(conn, gw.scenario.name, settings)
        before = parse_settings(bytes(last["raw"])) if last else None
        found = approvals.changes(before, settings, gw.definitions, gw.scenario.person)
        link = f"{gw.public_url}/approve/?settings={row['digest']}"
        sends, asked = [], []
        if new:
            ledger.append(conn, {"kind": "admin", "action": "propose", "decision": "record",
                                 "args": {"settings": settings.version, "serial": settings.serial,
                                          "digest": row["digest"], **asker,
                                          "widens": any(c["widens"] for c in found)}})
            text = approvals.text(settings.serial, found, link)
            for approver in registry.approvers(settings, gw.scenario.holders, before):
                route = gw.reach(conn, approver.id, None)
                ledger.append(conn, {
                    "kind": "notice", "action": "ask-approval", "run": None, "instance": None,
                    "acts_for": [], "decision": "record",
                    "args": {"settings": settings.version, "to": approver.id,
                             "channel": route["channel"], "chars": len(text),
                             "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                sends.append(outbound(conn, route, approver.id, text,
                                      card=approvals.card(settings.serial, found, link)))
                asked.append(approver.id)
        return {"refused": [], "row": row, "new": new, "changes": found, "link": link,
                "asked": asked, "sends": sends}

    @app.post("/settings/proposals", dependencies=[Depends(service)])
    def propose(body: Proposal) -> dict:
        """Ask a version's approvers to approve it: each gets a card in the chat they last had
        with a5s, or a link where there are no cards. A version asked about before is asked
        about once."""
        if problem := gw.approving():
            raise HTTPException(503, problem)
        try:
            settings = parse_settings(base64.b64decode(body.raw, validate=True))
        except (binascii.Error, ValueError, yaml.YAMLError, KeyError, TypeError,
                AttributeError) as exc:
            raise HTTPException(400, f"that isn't a version of the settings: {exc}") from None
        with db.transaction(gw.url) as conn:
            done = proposing(conn, settings)
        if done["refused"]:
            raise HTTPException(409, {"reasons": done["refused"]})
        push(done["sends"])
        return {"settings": settings.version, "serial": settings.serial,
                "digest": done["row"]["digest"], "link": done["link"], "changes": done["changes"],
                "asked": done["asked"], "new": done["new"]}

    def requested(conn: psycopg.Connection) -> list[int | None]:
        """Propose the versions people asked for in the settings app, once each, if they still
        approve instances. What to send their approvers once the transaction is done. Each
        request is worked on alone, so one a5s can't use is refused, and holds up nothing."""
        sends, problem = [], gw.approving()
        for req in conn.execute("select * from settings_requests where scenario = %s "
                                "and outcome is null order by id for update",
                                (gw.scenario.name,)).fetchall():
            digest = None
            try:
                with conn.transaction():  # a savepoint
                    person = gw.scenario.person(req["person"])
                    if problem:  # such as no seal key here, though the channels have one
                        outcome = f"refused: {problem}"
                    elif person is None or not registry.approves(person):
                        outcome = "refused: they don't approve instances"
                    else:
                        done = proposing(conn, parse_settings(bytes(req["raw"])), by=person.id)
                        outcome = ("refused: " + "; ".join(done["refused"])) if done["refused"] \
                            else "proposed"
                        if not done["refused"]:
                            digest = done["row"]["digest"]
                            sends += done["sends"]
            except ValueError as exc:
                outcome = f"refused: {exc}"[:500]
            except Exception as exc:  # recorded on the request, and logged
                log.exception("couldn't work on settings request %s", req["id"])
                outcome = f"refused: a5s couldn't work on it ({type(exc).__name__})"
            conn.execute("update settings_requests set outcome = %s, digest = %s, decided_at = now() "
                         "where id = %s", (outcome, digest, req["id"]))
        return sends

    def applying(conn: psycopg.Connection, row: dict, last: dict | None) -> tuple[str | None, list]:
        """Apply a proposed version once everyone it needs has approved it: what became of it,
        or None while it waits, and who approved it."""
        approved, _ = approvals.approvers(conn, gw.cfg.seal_keys, gw.scenario.name, row["digest"])
        settings = parse_settings(bytes(row["raw"]))
        valid, _ = registry.signers(settings, gw.scenario.person, approved)
        before = parse_settings(bytes(last["raw"])) if last and last.get("raw") else None
        if registry.missing(settings, gw.scenario.person, valid, before):
            return None, approved  # it waits for the rest of the approvers it needs
        if refused := gw.unusable(settings, last):  # such as a release gone since
            ledger.append(conn, {"kind": "admin", "action": "apply", "decision": "deny",
                                 "reasons": refused, "args": {"settings": settings.version,
                                                              "serial": settings.serial}})
        else:
            refused = registry.apply(conn, gw.definitions, settings, gw.scenario.tools(),
                                     gw.scenario.person, gw.scenario.name, approved).refused
        return ("refused: " + "; ".join(refused)) if refused else "applied", approved

    @app.post("/settings/sweep", dependencies=[Depends(service)])
    def sweep_settings() -> dict:
        """Propose the versions people asked for in the settings app. Apply the newest version
        that everyone it needs has approved where they work, and let go of the versions it
        leaves behind. Each version is worked on alone: one a5s can't use holds up no other."""
        applied = []
        with db.transaction(gw.url) as conn:
            if not conn.execute("select pg_try_advisory_xact_lock(hashtext('a5s settings')) as got"
                                ).fetchone()["got"]:
                return {"applied": []}  # another sweep is at work
            sends = requested(conn)
            last = approvals.latest(conn, gw.scenario.name)
            for row in conn.execute("select * from settings_proposals where scenario = %s "
                                    "and outcome is null order by serial desc",
                                    (gw.scenario.name,)).fetchall():
                if last and row["serial"] <= last["serial"]:
                    outcome = "superseded"
                else:
                    try:
                        with conn.transaction():  # a savepoint
                            outcome, approved = applying(conn, row, last)
                    except ValueError as exc:
                        outcome = f"refused: {exc}"[:500]
                    except Exception as exc:  # recorded on the proposal, and logged
                        log.exception("couldn't apply settings %s", row["digest"])
                        outcome = f"refused: a5s couldn't apply it ({type(exc).__name__})"
                    if outcome is None:
                        continue
                    if outcome == "applied":
                        last = approvals.latest(conn, gw.scenario.name)
                        applied.append({"serial": row["serial"], "approved_by": approved})
                conn.execute("update settings_proposals set outcome = %s, decided_at = now() "
                             "where scenario = %s and digest = %s",
                             (outcome, gw.scenario.name, row["digest"]))
        push(sends)  # what the settings app's requests ask their approvers
        return {"applied": applied}

    @app.get("/status", dependencies=[Depends(service)])
    def status_now() -> dict:
        """How a5s is doing, for the team that runs it and its dashboards (core/status.py)."""
        with db.transaction(gw.url) as conn:
            return status.report(conn, gw.breakers.open())

    @app.post("/retention/sweep", dependencies=[Depends(service)])
    def sweep_retention() -> dict:
        """Delete what's past its time to keep (core/retention.py), and record how much went."""
        with db.transaction(gw.url) as conn:
            gone = retention.sweep(conn)
            if gone:
                ledger.append(conn, {"kind": "retention", "action": "delete", "run": None,
                                     "instance": None, "acts_for": [], "decision": "record",
                                     "args": gone})
        return {"deleted": gone}

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
            topic = row["trigger"].get("topic", topics.GENERAL)
            if topic != topics.GENERAL and not parts.workable(gw.scenario, row, topic):
                context.append({"title": f"The case: {topic}, from the records",
                                "text": f"a5s has nothing on {topic} for this run: {parts.UNSEEN}."})
            elif topic != topics.GENERAL:
                context.append(topics.brief(conn, gw.scenario, topic, person, gw.clock(),
                                            gw.unseen(conn, row["model"])))
                provenance.read(conn, row["run"], f"the records, on {topic}", context[-1]["text"],
                                gw.scenario.record_pattern)
            if person and (offered := [  # so a yes in their next message finds what it's to
                    *profiles.waiting(conn, person, row["definition"]),
                    *reminders.waiting_for_yes(conn, person, row["definition"])]):
                context.append({"title": "What you offered them, waiting for their yes",
                                "text": "You offered these in an earlier message. If they say yes "
                                        "to one now, keep it with the tool named, at once, "
                                        "without asking again.\n"
                                        + "\n".join(f"- {o}" for o in offered)})
                provenance.read(conn, row["run"], provenance.A5S, context[-1]["text"],
                                gw.scenario.record_pattern)  # a5s told it these dates
            if person:  # and the day each turn of the conversation was said, which it's shown
                said = conn.execute("select distinct to_char(at at time zone 'UTC', 'YYYY-MM-DD') "
                                    "as day from turns where person = %s and agent = %s",
                                    (person.id, row["definition"])).fetchall()
                provenance.read(conn, row["run"], "when things were said",
                                " ".join(d["day"] for d in said), gw.scenario.record_pattern)
        definition = gw.definitions.get(row["definition"])
        if definition is None or definition.release_id != row["release"]:
            raise HTTPException(409, f"release {row['release']} isn't loaded in this gateway")
        model = gw.models.get(row["model"])
        tools = {**gw.scenario.tools(), **CORE_TOOLS}  # a5s's own first
        own = row["trigger"].get("kind") in OWN_RUNS  # a5s's own work, with one model call
        return {
            "run": row["run"],
            "instance": row["id"],
            "acts_for": list(row["acts_for"]),
            "instructions": topics.SUMMARY if own else definition.instructions,
            "context": [] if own else context,
            "model": {"alias": model.alias, "api": model.api} if model else None,
            "tools": [] if own else [tools[n].definition() for n in row["grants"] if n in tools],
            "plain": own,
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
        with traces.span(f"execute_tool {name}", **{
                "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name,
                "a5s.tool.own": name in CORE_TOOLS or None}) as current:
            return calling_tool(name, body, token, current)

    def calling_tool(name: str, body: ToolArgs, token: str, current: Any) -> Any:
        core = CORE_TOOLS.get(name)
        tool = None if core else gw.scenario.tools().get(name)
        args, removed = dict(body.args), 0
        for field_name in (core or tool).text_fields if (core or tool) else ():
            if field_name in args:  # outgoing text, at any depth
                args[field_name], dropped = cleaned(args[field_name], gw.scenario.record_links)
                removed += dropped
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            entity = gw.core_tool_entity(name) if core else gw.tool_entity(name, tool, row["pins"])
            arg = tool.record_arg if tool else None  # the record it's about, if it names one
            named = args.get(arg) if arg else None
            records = [] if named in (None, "") else named if isinstance(named, list) else [named]
            decision = gw.decide(row, "call_tool", entity, [],
                                 **parts.about(gw.scenario, row, [r for r in records
                                                                  if isinstance(r, str) and r]))
            if (found := gw.settings_in_force(conn))[0] is None:  # fail closed
                decision = Decision(False, ("settings-must-check-out",), explanations=(
                    f"a5s can't use the settings in force: {found[1]}",))
            elif problem := misfit((core or tool).schema if (core or tool) else {}, args):
                decision = Decision(False, ("arguments-fit-the-schema",), explanations=(
                    f"the arguments don't fit the tool: {problem}",))
            elif any(not isinstance(r, str) or not r for r in records):
                decision = Decision(False, ("records-are-named-by-key",), explanations=(
                    "a record is named by its key, in words",))
            if row["trigger"].get("kind") in OWN_RUNS:
                decision = Decision(False, ("a5s-runs-call-no-tools",), explanations=(
                    "a5s's own runs, such as keeping a summary, call no tools",))
            deciding = holding(decision, records, row)
            if deciding is None:  # nobody else may decide it, or nobody can decide it here
                decision = Decision(False, ("someone-else-decides",), explanations=(
                    unheld(records, row),))
            texts = [s for f in tool.text_fields for s in strings(args.get(f))] if tool else []
            if decision.held:  # what deciders should know: every value the agent wrote itself
                texts = strings(args)
            traced = provenance.traced(conn, gw.scenario, row, "\n".join(texts))
            last = next((f for f in reversed(tool.text_fields) if isinstance(args.get(f), str)),
                        None) if tool else None
            if (own := [t["value"] for t in traced if t["from"] is None]) and last:
                args[last] += "\n\n" + provenance.note(row["definition"], own)  # apart
            plain = (*((arg,) if arg else ()), *(core.plain if core else ()))
            seq = ledger.append(conn, gw.entry(row, "tool", name, decision,
                                               args=ledger.mask(args, plain),
                                               links_removed=removed,
                                               **({"values": values_of(traced)} if traced else {})))
            if decision.held:  # it waits for a person: the exact call, kept for its deciders
                proposal, sends = held(conn, row, tool, args, records, deciding or [], seq, traced)
        traces.note(current, **{"a5s.run.id": row["run"], "a5s.instance": row["id"],
                                "a5s.decision": decision.label})
        if decision.held:
            push(sends)
            names = approvals.names_of([p.name for p in deciding or []])
            whom = approvals.names_of([p.name if (p := gw.scenario.person(w)) else w
                                       for w in row["acts_for"]])
            return {"result": {
                "held": proposals.key(proposal), "decides": names,
                "status": f"Not made yet: it waits for {names} to decide it, on a5s's own page. "
                          f"a5s will tell {whom if row['acts_for'] else 'its owner'} what they "
                          "decide, and makes the change if they approve it."}, "recorded": True}
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if core is not None:
            return call_core_tool(core, args, row, seq)
        try:
            with db.transaction(gw.url) as conn:  # a system gets the values handles stand for
                given = handles.resolved_args(conn, row["run"], args)
            result = tool.run(ToolCall(args=given, instance=row["id"], run=row["run"],
                                       acts_for=tuple(row["acts_for"])))
            outcome = {"status": "ok", "result_sha256": ledger.digest(result)}
            result, withheld = parts.kept(gw.scenario, row, tool.record_field, result)
            if withheld:
                outcome["withheld"] = withheld
            with db.transaction(gw.url) as conn:  # the agent gets handles for sensitive values,
                hidden = (*tool.handles, *sorted(gw.unseen(conn, row["model"])))  # and classified
                result = handles.issue(conn, row["run"], name, result, hidden)  # ones it can't see
        except Exception as exc:  # noqa: BLE001 - the tool's own failure, recorded and reported
            with db.transaction(gw.url) as conn:  # it may repeat an argument: no handle's value
                said = handles.masked(conn, row["run"], f"{type(exc).__name__}: {exc}")
            result, outcome = None, {"status": "error", "error": said[:200]}
        if outcome["status"] == "ok":
            try:
                with db.transaction(gw.url) as conn:
                    provenance.read(conn, row["run"], name, result, gw.scenario.record_pattern)
            except psycopg.Error:  # the values it wrote will be flagged as its own: never worse
                log.exception("couldn't note what %s read from %s", row["run"], name)
        recorded = record({"kind": "tool", "action": name, "run": row["run"], "instance": row["id"],
                           "decision": "record", "of": seq, "outcome": outcome})
        traces.note(current, **{"error.type": "tool_error" if outcome["status"] != "ok" else None})
        if outcome["status"] != "ok":
            return JSONResponse(status_code=502, content={"error": outcome["error"]})
        return {"result": result, "recorded": recorded}

    def holding(decision: Decision, records: list[str], row: dict) -> list[Person] | None:
        """Who may decide a call policy holds, if it holds it and someone may: None if nobody
        but the people the run acts for may, or nobody can decide anything here."""
        if not decision.held:
            return []
        if gw.approving() is not None:
            return None
        return proposals.deciders(gw.scenario, records, list(row["acts_for"])) or None

    def unheld(records: list[str], row: dict) -> str:
        if (problem := gw.approving()) is not None:
            return f"a change can't wait for a decision here, since {problem}"
        return ("nobody but the people this run is for may decide this change, and nobody decides "
                "what they asked for themselves: they can make it themselves, in the records system")

    def held(conn: psycopg.Connection, row: dict, tool: Tool, args: dict, records: list[str],
             deciding: list[Person], seq: int, traced: list[dict]) -> tuple[dict, list]:
        """Keep a held call for its deciders, and ask each of them, where they work, to decide
        it on the core's page. The proposal, and what to send them once the transaction is done."""
        whom = approvals.names_of([p.name if (p := gw.scenario.person(w)) else w
                                   for w in row["acts_for"]])
        flags = [f"{t['value']} came from the {row['definition']} itself, not from the records "
                 f"or from {whom}" for t in traced if t["from"] is None]
        if row["read_outside"]:
            flags.append(f"the {row['definition']} read content from outside the organisation "
                         "before it asked for this")
        proposal = proposals.hold(conn, gw.scenario, row, tool, args, records, deciding, seq,
                                  flags, gw.clock())
        link = f"{gw.public_url}/decide/?proposal={proposal['digest']}"
        text = proposals.asking(proposal, link)
        sends = []
        for person in deciding:
            route = gw.reach(conn, person.id, None)
            ledger.append(conn, {
                "kind": "notice", "action": "ask-decision", "run": row["run"],
                "instance": row["id"], "acts_for": list(row["acts_for"]), "decision": "record",
                "args": {"proposal": proposals.key(proposal), "to": person.id,
                         "channel": route["channel"], "chars": len(text),
                         "sha256": hashlib.sha256(text.encode()).hexdigest()}})
            sends.append(outbound(conn, route, person.id, text, card=proposals.card(proposal, link)))
        return proposal, sends

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
        if core.sourced is not None:
            try:
                with db.transaction(gw.url) as conn:
                    provenance.read(conn, row["run"], core.name, core.sourced(result),
                                    gw.scenario.record_pattern)
            except psycopg.Error:  # the values it wrote will be flagged as its own: never worse
                log.exception("couldn't note what %s read from %s", row["run"], core.name)
        return {"result": result, "recorded": recorded}

    @app.post("/run/messages")
    def send_message(body: Message, token: str = Depends(run_token)) -> Any:
        with traces.span("send_message") as current:
            return sending_message(body, token, current)

    def sending_message(body: Message, token: str, current: Any) -> Any:
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
            if row["trigger"].get("kind") in OWN_RUNS:
                decision = Decision(False, ("a5s-runs-write-to-nobody",), explanations=(
                    "a5s's own runs, such as keeping a summary, write to nobody",))
            elif body.to not in row["acts_for"]:
                why = ("a run writes only to the people it acts for, such as whoever sent the "
                       "message it answers")
                decision = Decision(False, ("writes-to-whom-it-acts-for",), explanations=(why,))
            else:
                decision = gw.decide(row, "send_message", recipient, [])
                route = (gw.message_of(conn, inbound) if inbound  # an answer, where it was asked
                         else {"channel": "digest", "reply_to": {}} if gw.for_digest(conn, row)
                         else gw.at_once(conn, body.to, row["definition"],  # not what they
                                         count=decision.allowed  # asked to be reminded of then
                                         and row["trigger"].get("kind") != "reminder"))
            traced = provenance.traced(conn, gw.scenario, row, text) if decision.allowed else []
            said, note = text, None  # the agent's words, apart from a5s's own note on them
            if own := [t["value"] for t in traced if t["from"] is None]:  # people see it apart
                note = provenance.note(row["definition"], own)
                text += "\n\n" + note
            ledger.append(conn, gw.entry(row, "message", "send", decision, args={
                "to": body.to, "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "links_removed": removed, **({"channel": route["channel"]} if route else {}),
                **({"values": values_of(traced)} if traced else {}),
            }))
            shown = handles.resolved(conn, row["run"], text)  # what people read: the values
            if decision.allowed and route["channel"] == "digest":  # it goes in their next digest
                digests.keep(conn, body.to, row["definition"], row["id"], row["run"], shown, gw.clock())
            elif decision.allowed and route["channel"] == "batch":  # it waits for their next batch
                urgent.hold(conn, body.to, row["definition"], row["id"], row["run"], shown, gw.clock())
            elif decision.allowed:  # in the chat, after this transaction, or in the inbox
                sending = outbound(conn, route, body.to, shown, run=row["run"], instance=row["id"],
                                   agent=row["definition"], inbound=inbound)
        traces.note(current, **{"a5s.run.id": row["run"], "a5s.instance": row["id"],
                                "a5s.channel": route["channel"] if route else None,
                                "a5s.decision": decision.label})
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if route["channel"] not in ("digest", "batch"):
            push([sending])  # a chat that doesn't take it now gets it again, later
        # As the agent wrote it, with its handles, for the conversation a later run reads, and
        # a5s's note apart, so no run takes a5s's words for the agent's, or learns to imitate them
        return {"sent": True, "text": said, "note": note, "links_removed": removed}

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

    def outbound(conn: psycopg.Connection, route: dict, person: str, text: str, *,
                 run: str | None = None, instance: str | None = None, agent: str | None = None,
                 inbound: str | None = None, card: dict | None = None) -> int | None:
        """Keep what a5s will write to someone, in the transaction that decides it: in the
        local channel's inbox, or, for a chat a5s writes to itself, to deliver once the
        transaction is done. The row's id, to push, for a chat."""
        pushed = route["channel"] in PUSHED
        row = conn.execute(
            "insert into outbox (run_id, instance_id, agent, inbound_id, person, channel, text, "
            "route, card) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
            (run, instance, agent, inbound, person, route["channel"], text,
             Jsonb(route) if pushed else None, Jsonb(card) if card else None)).fetchone()
        return row["id"] if pushed else None

    def noted(conn: psycopg.Connection, person: str, agent: str | None, text: str,
              topic: str | None) -> None:
        """a5s's own words to someone, in their conversation with the agent whose chat they
        go in, so the agent's next run knows what the person is answering."""
        if agent:
            conn.execute("insert into turns (person, agent, topic, role, content) "
                         "values (%s, %s, %s, 'notice', %s)",
                         (person, agent, topic or topics.GENERAL, text))

    def push(ids: list[int | None] | None = None) -> None:
        """Deliver what waits for a chat a5s writes to itself: the rows given, or every one
        that's due again. Each is taken for five minutes while it's tried, so two gateways
        don't send it twice. One the chat doesn't take is tried again, after a minute, then
        two, four and eight, and after five tries it's left in the person's local inbox."""
        wanted = None if ids is None else [i for i in ids if i is not None]
        if wanted == []:
            return
        now = gw.clock()  # by the core's clock, as everything that falls due is
        with db.transaction(gw.url) as conn:
            rows = conn.execute(
                "update outbox set attempts = attempts + 1, retry_at = %s where id in ("
                "  select id from outbox where delivered_at is null and channel = any(%s) "
                "  and (retry_at is null or retry_at <= %s) "
                "  and (%s::bigint[] is null or id = any(%s)) "
                "  order by id limit 100 for update skip locked) returning *",
                (now + timedelta(minutes=5), list(PUSHED), now, wanted, wanted)).fetchall()
        for row in sorted(rows, key=lambda r: r["id"]):  # in the order a5s wrote them
            run = str(row["run_id"]) if row["run_id"] else None
            problem = deliver(row["route"], row["text"], run, row["instance_id"], card=row["card"])
            with db.transaction(gw.url) as conn:
                if problem is None:
                    conn.execute("update outbox set delivered_at = now(), retry_at = null, "
                                 "problem = null where id = %s", (row["id"],))
                elif row["attempts"] >= TRIES:  # the chat won't take it: the inbox will
                    conn.execute("update outbox set channel = 'local', inbound_id = null, "
                                 "retry_at = null, problem = %s where id = %s",
                                 (problem, row["id"]))
                    ledger.append(conn, {
                        "kind": "message", "action": "fallback", "run": run,
                        "instance": row["instance_id"], "acts_for": [row["person"]],
                        "decision": "record", "args": {"outbox": row["id"], "tries": row["attempts"],
                                                       "channel": row["route"]["channel"]},
                        "outcome": {"status": "error", "error": problem}})
                else:
                    conn.execute("update outbox set retry_at = %s, problem = %s where id = %s",
                                 (now + timedelta(minutes=2 ** (row["attempts"] - 1)), problem,
                                  row["id"]))

    @app.post("/proposals/sweep", dependencies=[Depends(service)])
    def sweep_proposals() -> dict:
        """Make the held changes their deciders approved, and tell whoever each was for what
        became of it: made, rejected, lapsed, or not made since its records changed or the
        instance may no longer act. Remind deciders once after two working days, and tell
        their managers after five."""
        now, sends, made = gw.clock(), [], []
        with db.transaction(gw.url) as conn:
            waiting = [r["id"] for r in conn.execute(
                "select id from proposals where scenario = %s and status = 'waiting' order by id",
                (gw.scenario.name,))]
        for pid in waiting:
            with db.transaction(gw.url) as conn:  # each alone, so one can't hold up another
                p = conn.execute("select * from proposals where id = %s and status = 'waiting' "
                                 "for update skip locked", (pid,)).fetchone()
                if p is None:
                    continue
                found, problems = proposals.decision(conn, gw.cfg.seal_keys, gw.scenario, p)
                for problem in problems:  # a decision that doesn't count, such as an unsealed one
                    log.warning("%s: %s", proposals.key(p), problem)
                if found is not None:
                    decider = gw.scenario.person(found["person"])
                    if now < proposals.effective(decider, found["decided_at"]):
                        continue  # their authenticator was reset lately: it waits a day
                    going = deciding(conn, p, found, decider, now)
                elif now >= p["lapses_at"]:
                    going = ended(conn, p, "lapsed", None, now)
                else:
                    going = chasing(conn, p, now)
                if going is None:
                    continue
                sends += going.get("sends", [])
                if going.get("make"):
                    made.append(going["make"])
        push(sends)
        for p, values, decider in made:  # outside any transaction, once it's marked as making
            push(making(p, values, decider))
        return {"swept": True, "made": len(made)}

    def deciding(conn: psycopg.Connection, p: dict, found: dict, decider: Person | None,
                 now: datetime) -> dict:
        """What becomes of a held change once someone who may decide it has: whether it's made."""
        if found["decision"] == "reject":
            return ended(conn, p, "rejected", found["person"], now)
        if changed := proposals.unchanged(gw.scenario, p):
            return ended(conn, p, "changed", found["person"], now, ", ".join(changed))
        if (why := allowed_now(conn, p)) is not None:
            return ended(conn, p, "refused", found["person"], now, why)
        conn.execute("update proposals set status = 'making', decided_by = %s, decided_at = %s "
                     "where id = %s", (found["person"], found["decided_at"], p["id"]))
        ledger.append(conn, {"kind": "proposal", "action": "decide", "run": str(p["run_id"]),
                             "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                             "decision": "allow", "of": p["seq"],
                             "args": {"proposal": proposals.key(p), "by": found["person"],
                                      "decided": "approve", "decision": found["id"]}})
        return {"make": (p, proposals.values(conn, p), found["person"])}

    def allowed_now(conn: psycopg.Connection, p: dict) -> str | None:
        """Why an approved change can't be made now, if it can't: the instance may no longer
        act, the tool has changed since, or policy would deny the call."""
        if (found := gw.settings_in_force(conn))[0] is None:
            return f"the settings in force don't check out: {found[1]}"
        row = conn.execute(
            "select r.id::text as run, r.acts_for, r.read_outside, r.trigger, r.tokens, i.* "
            "from runs r join instances i on i.id = r.instance_id where r.id = %s",
            (p["run_id"],)).fetchone()
        tool = gw.scenario.tools().get(p["tool"])
        if row is None or tool is None or tool.schema_hash != p["schema_hash"]:
            return "the tool has changed since it was asked for"
        if problems := gw.check_instance(conn, row) + gw.release_problems(conn):
            return "; ".join(problems)
        decision = gw.decide(row, "call_tool", gw.tool_entity(p["tool"], tool, row["pins"]), [],
                             **parts.about(gw.scenario, row, list(p["records"])))
        if not (decision.allowed or decision.held):
            return "; ".join(decision.explanations) or "policy denies it now"
        return None

    def making(p: dict, values: dict, decider: str) -> list:
        """Make an approved change, and tell whoever it was for. It's marked as making first,
        so it's never made twice: if a5s stops part way, it stays marked, for someone to see."""
        tool = gw.scenario.tools()[p["tool"]]
        try:
            result = tool.run(ToolCall(args=proposals.resolved(p["args"], values),
                                       instance=p["instance_id"], run=str(p["run_id"]),
                                       acts_for=tuple(p["acts_for"])))
            failed = result.get("error") if isinstance(result, dict) else None
            outcome = ({"status": "error", "error": str(failed)[:200]} if failed
                       else {"status": "ok", "result_sha256": ledger.digest(result)})
        except Exception as exc:  # noqa: BLE001 - the system's own failure, recorded and told
            outcome = {"status": "error", "error": f"{type(exc).__name__}"}
        with db.transaction(gw.url) as conn:
            ledger.append(conn, {"kind": "tool", "action": p["tool"], "run": str(p["run_id"]),
                                 "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                                 "decision": "record", "of": p["seq"], "outcome": outcome,
                                 "args": {"proposal": proposals.key(p)}})
            if outcome["status"] == "ok":
                going = ended(conn, p, "made", decider, gw.clock())
            else:
                going = ended(conn, p, "failed", decider, gw.clock(), outcome["error"])
        return going["sends"]

    def ended(conn: psycopg.Connection, p: dict, became: str, decider: str | None,
              now: datetime, extra: str = "") -> dict:
        """End a held change, let go of the values it kept, and tell whoever it was for, in the
        conversation with its agent, so its next run knows too."""
        name = who.name if decider and (who := gw.scenario.person(decider)) else decider
        text = proposals.told(p, became, name, extra)
        conn.execute("update proposals set status = %s, decided_by = coalesce(decided_by, %s), "
                     "ended_at = %s, outcome = %s where id = %s",
                     ("made" if became == "made" else "not made" if became in (
                         "changed", "refused", "failed") else became,
                      decider, now, text, p["id"]))
        conn.execute("delete from proposal_values where proposal_id = %s", (p["id"],))
        ledger.append(conn, {"kind": "proposal", "action": became, "run": str(p["run_id"]),
                             "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                             "decision": "record", "of": p["seq"],
                             "args": {"proposal": proposals.key(p), "by": decider}})
        told_to = list(p["acts_for"])
        if not told_to:  # a run for nobody: its instance's owner hears instead
            owner = conn.execute("select owner from instances where id = %s",
                                 (p["instance_id"],)).fetchone()
            told_to = [owner["owner"]] if owner and owner["owner"] else []
        sends = []
        for person in told_to:
            route = gw.reach(conn, person, p["definition"])  # what they're waiting for: at once
            sends.append(outbound(conn, route, person, text, instance=p["instance_id"],
                                  agent=p["definition"]))
            noted(conn, person, p["definition"], text, next(iter(p["records"]), None))
        return {"sends": sends}

    def chasing(conn: psycopg.Connection, p: dict, now: datetime) -> dict | None:
        """Remind a held change's deciders once, after two working days, and tell their
        managers once, after five, each in their working hours."""
        first = gw.scenario.person(p["deciders"][0]) if p["deciders"] else None
        if first is None:
            return None
        link = f"{gw.public_url}/decide/?proposal={p['digest']}"
        if p["escalated_at"] is None and now >= proposals.working_days_after(
                first, p["proposed_at"], proposals.ESCALATE):
            above: dict[str, Person] = {}  # each decider's manager, who may hear of the record
            for decider in p["deciders"]:
                who = gw.scenario.person(decider)
                boss = gw.scenario.person(who.manager) if who and who.manager else None
                if (boss is not None and boss.in_audience and boss.id not in p["acts_for"]
                        and all(gw.scenario.sees(boss.id, r) for r in p["records"])):
                    above.setdefault(boss.id, boss)
            if above and not any(obligations.working(b, now) for b in above.values()):
                return None  # it waits for their working hours
            sends = []
            for boss in above.values():
                names = approvals.names_of([w.name for d in p["deciders"]
                                            if (w := gw.scenario.person(d)) and w.manager == boss.id])
                text = (f"{proposals.key(p)} has waited {proposals.ESCALATE} working days for "
                        f"{names} to decide it.\n{p['said']}\nIt lapses on "
                        f"{obligations.day(boss, p['lapses_at'])} unless someone decides it: {link}")
                sends.append(outbound(conn, gw.reach(conn, boss.id, None), boss.id, text))
            conn.execute("update proposals set escalated_at = %s where id = %s", (now, p["id"]))
            ledger.append(conn, {"kind": "proposal", "action": "escalate", "run": str(p["run_id"]),
                                 "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                                 "decision": "record", "of": p["seq"],
                                 "args": {"proposal": proposals.key(p), "to": sorted(above)}})
            return {"sends": sends}
        if p["reminded_at"] is None and now >= proposals.working_days_after(
                first, p["proposed_at"], proposals.REMIND):
            due = [d for d in p["deciders"]
                   if (who := gw.scenario.person(d)) and obligations.working(who, now)]
            if not due:
                return None
            text = "Still waiting for your decision. " + proposals.asking(p, link)
            sends = [outbound(conn, gw.reach(conn, d, None), d, text,
                              card=proposals.card(p, link)) for d in due]
            conn.execute("update proposals set reminded_at = %s where id = %s", (now, p["id"]))
            ledger.append(conn, {"kind": "proposal", "action": "remind", "run": str(p["run_id"]),
                                 "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                                 "decision": "record", "of": p["seq"],
                                 "args": {"proposal": proposals.key(p), "to": due}})
            return {"sends": sends}
        return None

    @app.post("/deliveries/sweep", dependencies=[Depends(service)])
    def sweep_deliveries() -> dict:
        """Try again what a chat a5s writes to itself didn't take, once it's due."""
        push()
        return {"swept": True}

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
                sending = outbound(conn, {"channel": row["channel"], "reply_to": row["reply_to"]},
                                   row["person"], text, instance=body.instance, agent=row["agent"],
                                   inbound=inbound)
        if row is None:
            raise HTTPException(403, "a5s only answers a message someone sent, and briefly")
        push([sending])
        return {"sent": True, "text": text}

    # The model gateway, in both API styles.

    def model_call(api: str, body: dict[str, Any], token: str) -> JSONResponse:
        """A model call, one at a time for each run: the run's budget is checked before it and
        counted after it, so calls a run makes at once wait their turn rather than each pass
        the same check, across every gateway, by a lock the database holds."""
        with psycopg.connect(gw.url, autocommit=True) as held:
            held.execute("select pg_advisory_lock(hashtext(%s))", (f"model {token_hash(token)}",))
            try:
                return calling(api, body, token)
            finally:
                held.execute("select pg_advisory_unlock(hashtext(%s))",
                             (f"model {token_hash(token)}",))

    def calling(api: str, body: dict[str, Any], token: str) -> JSONResponse:
        alias = body.get("model", "")
        model = gw.models.get(alias)
        if body.get("stream"):
            return JSONResponse(status_code=400, content=models.error_body(
                api, "streaming isn't supported yet", "invalid_request_error"))
        approved = {
            "uid": {"type": "Model", "id": alias},
            "attrs": {"name": alias, "approved": bool(model and model.api == api),
                      "classes": list(model.data_classes) if model else []},
            "parents": [],
        }
        prompt = {"system": body.get("system"), "messages": body.get("messages")}
        forwarded, dropped, refusal = models.screen(api, body)
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            release = gw.definitions.get(row["definition"])
            spent = None if release is None else budgets.refused(
                conn, gw.scenario, release.budget, row["id"], list(row["acts_for"]),
                row["trigger"].get("kind"), row["tokens"], gw.clock())
            if refusal:
                decision = Decision(False, ("agents-use-their-own-tools",), explanations=(refusal,))
            elif spent:
                decision = Decision(False, ("budgets",), explanations=(spent,))
            elif (found := gw.settings_in_force(conn))[0] is None:
                decision = Decision(False, ("settings-must-check-out",), explanations=(
                    f"a5s can't use the settings in force: {found[1]}",))
            else:
                decision = gw.decide(row, "call_model", approved, [],
                                     data_class=found[0].data_class)
            seq = ledger.append(conn, gw.entry(row, "model", alias, decision, args={
                "prompt_sha256": ledger.digest(prompt),
                "messages": len(body.get("messages") or []),
                "tools": len(body.get("tools") or []),
                "tools_sha256": ledger.digest(forwarded.get("tools")),
                "params": {k: v for k, v in forwarded.items()
                           if k not in ("model", "messages", "system", "tools")},
                "left_out": dropped,
            }, provider=model.provider if model else None))
        if spent:
            return JSONResponse(status_code=429, content=models.error_body(
                api, f"out of budget: {spent}", "budget_spent"))
        if not decision.allowed:
            return JSONResponse(status_code=403, content=models.error_body(
                api, "denied by policy: " + "; ".join(decision.explanations)))
        called = gw.breakers.allow(alias)
        with traces.span(f"chat {alias}", **{
                "gen_ai.operation.name": "chat", "gen_ai.provider.name": model.provider,
                "gen_ai.request.model": alias, "a5s.run.id": row["run"],
                "a5s.instance": row["id"]}) as current:
            if not called:  # it failed in a row lately: it isn't called for a few minutes
                status, data = 503, models.error_body(
                    api, f"{alias} failed {FAILURES} times in a row, so a5s isn't calling it for "
                         "a few minutes", "model_unavailable")
            else:
                try:
                    status, data = models.forward(model, forwarded, gw.http)
                except models.ModelUnavailable as exc:
                    status, data = 503, models.error_body(api, str(exc), "model_unavailable")
            usage = data.get("usage") if isinstance(data, dict) else None
            current.set_attributes({k: v for k, v in {
                "gen_ai.response.model": data.get("model") if isinstance(data, dict) else None,
                "gen_ai.usage.input_tokens": (usage or {}).get("prompt_tokens",
                                                               (usage or {}).get("input_tokens")),
                "gen_ai.usage.output_tokens": (usage or {}).get("completion_tokens",
                                                                (usage or {}).get("output_tokens")),
                "error.type": str(status) if status >= 400 else None}.items() if v is not None})
        reported = data.get("model") if isinstance(data, dict) else None
        expected = model.reported_model or model.model
        if called and status < 400 and reported != expected:
            status, data = 502, models.error_body(
                api, f"the provider reported {reported}, not the approved {expected}",
                "model_mismatch")
        if called and (change := "open" if (status >= 500 or status == 429)
                       and gw.breakers.failed(alias) else "close" if status < 400
                       and gw.breakers.worked(alias) else None):
            log.warning("the breaker for %s is %s", alias, "open" if change == "open" else "closed again")
            record({"kind": "breaker", "action": change, "run": row["run"], "instance": row["id"],
                    "decision": "record", "args": {"model": alias, "status": status}})
        recorded = record({"kind": "model", "action": alias, "run": row["run"], "instance": row["id"],
                           "decision": "record", "of": seq,
                           "outcome": {"status": status, "reported_model": reported,
                                       "usage": data.get("usage") if isinstance(data, dict) else None}})
        tokens = budgets.tokens_of(data.get("usage")) if isinstance(data, dict) else 0
        if tokens and release is not None:
            try:
                with db.transaction(gw.url) as conn:
                    if warning := budgets.spent(conn, gw.scenario, release.budget, row, tokens,
                                                gw.clock()):
                        log.warning("%s has used %s of its %s tokens for %s today", row["id"],
                                    warning["used"], warning["budget"], warning["person"])
                        ledger.append(conn, {
                            "kind": "budget", "action": "warn", "run": row["run"],
                            "instance": row["id"], "acts_for": [warning["person"]],
                            "decision": "record", "args": {"used": warning["used"],
                                                           "budget": warning["budget"]}})
            except psycopg.Error:
                log.exception("couldn't count %s tokens for run %s", tokens, row["run"])
        return JSONResponse(status_code=status, content=data,
                            headers=None if recorded else {"x-a5s-recorded": "false"})

    @app.post("/v1/chat/completions")
    def openai_style(body: dict[str, Any], token: str = Depends(run_token)) -> JSONResponse:
        return model_call("openai", body, token)

    @app.post("/v1/messages")
    def anthropic_style(body: dict[str, Any], token: str = Depends(run_token)) -> JSONResponse:
        return model_call("anthropic", body, token)

    return app
