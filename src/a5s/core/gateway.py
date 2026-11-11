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
    ASSURANCE,
    DATA_PROTECTION,
    INSTANCE_APPROVER,
    PART_OWNER,
    Person,
    Scenario,
    Settings,
    Signature,
    Tool,
    ToolCall,
    parse_settings,
    record_of,
)
from a5s.core import (
    approvals,
    asking,
    budgets,
    chats,
    coretools,
    counts,
    departures,
    digests,
    erasure,
    export,
    extractor,
    groups,
    handles,
    ledger,
    measures,
    models,
    notebook,
    obligations,
    officer,
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
    samples,
    schedules,
    sealing,
    status,
    studio,
    tasking,
    topics,
    traces,
    urgent,
    values,
)
from a5s.core.breakers import FAILURES, Breakers
from a5s.core.identity import IdentityError, UnknownPerson, Verifier, signed_in
from a5s.core.matrix import Matrix
from a5s.core.policy import Decision, PolicyEngine
from a5s.core.teams import Teams
from a5s.core.values import Value
from a5s.definitions import Context, Definition

log = logging.getLogger(__name__)
CORE_TOOLS = {**reminders.TOOLS, **digests.TOOLS, **profiles.TOOLS,  # a5s's own, on its
              **recall.TOOLS, extractor.ASK: extractor.TOOL,  # own records, and asking
              asking.ASK: asking.TOOL,  # another agent (core/asking.py), and the notebook
              notebook.NOTE: notebook.TOOL,  # of what it learns from records, and long tasks
              **tasking.TOOLS}  # people ask it for (core/tasking.py)
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


def sanitize(text: str, allowed: tuple[str, ...], notes: bool = True) -> tuple[str, int]:
    """Keep text and the scenario's own record links. Drop images, HTML and other links, and,
    unless `notes` is False, copies of a5s's own notes, which only a5s writes."""
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

    text, forged = _FORGED_NOTE.subn("", text) if notes else (text, 0)
    text, images = _IMAGE.subn("[image removed]", text)
    text, tags = _TAG.subn("[removed]", text)
    text = _MARKDOWN_LINK.sub(link, text)
    parts = re.split(r"(\[[^\]]*\]\([^)]*\))", text)  # record links already kept stay whole
    text = "".join(p if _MARKDOWN_LINK.fullmatch(p) else _URL.sub(url, p) for p in parts)
    return text.strip() if forged else text, removed + images + tags + forged


def cleaned(value: Any, allowed: tuple[str, ...], notes: bool = True) -> tuple[Any, int]:
    """Text at any depth of a value, sanitized, and how many things were removed."""
    if isinstance(value, str):
        return sanitize(value, allowed, notes)
    if isinstance(value, list):
        found = [cleaned(item, allowed, notes) for item in value]
        return [v for v, _ in found], sum(n for _, n in found)
    if isinstance(value, dict):
        found = {k: cleaned(v, allowed, notes) for k, v in value.items()}
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

    @property
    def tasks(self) -> Any:
        """The task engine, as the core runs it: each slice a run (core/tasking.py)."""
        return tasking.service(self.url, self.clock, RUN_MINUTES)

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
        expected = (signed.definition, sorted(signed.serves), level, scope,
                    registry.action_levels(signed, release), sorted(release.grants),
                    release.model, release.pins, signed.owner or release.owner,
                    signed.deputy or release.deputy, sorted(signed.asks))
        actual = (inst["definition"], sorted(inst["serves"]), inst["level"], inst["parts"] or {},
                  inst["actions"] or {}, sorted(inst["grants"]), inst["model"], inst["pins"],
                  inst["owner"], inst["deputy"], sorted(inst["asks"] or []))
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
            "returning id::text, person, channel, agent, text, conversation, members",
            (inbound,)).fetchone()
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
        channel's inbox. Never in a group chat (core/groups.py): what's written to someone
        first is theirs alone."""
        local = {"channel": "local", "reply_to": {}}
        if agent is not None:
            had = conn.execute(
                """
                select channel, reply_to, at from (
                  select channel, reply_to, received_at as at from inbound
                  where person = %(person)s and agent = %(agent)s and conversation is null
                  union all
                  select channel, reply_to, started_at from chats
                  where person = %(person)s and agent = %(agent)s and started_at is not null
                ) had order by at desc limit 1
                """, {"person": person, "agent": agent}).fetchone()
            if had is not None and (found := self._in(conn, had)):
                return found
            if had is not None and chats.gone(conn, had["channel"], had["reply_to"],
                                              had["at"]) != "shared":
                return local  # they left it, or it's in the inbox: not someone else joining
        if agent is None:
            last = conn.execute("select channel, reply_to, received_at as at from inbound "
                                "where person = %s and conversation is null "
                                "order by received_at desc limit 1", (person,)).fetchone()
            return (last and self._in(conn, last)) or local
        latest = conn.execute(  # where they talk to agents, a group chat's too: only to know
            "select channel from inbound where person = %s "  # which chat, never to write
            "order by received_at desc limit 1", (person,)).fetchone()  # into a group
        who = self.scenario.person(person)
        if (latest is not None and latest["channel"] == "matrix" and self.matrix is not None
                and who is not None and (user := self.matrix.user_of(who))):
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

    @staticmethod
    def spoke(conn: psycopg.Connection, group: str, agent: str, topic: str,
              members: list[str], sender: str | None) -> list[str]:
        """Whose words a run in a group chat may be given, so whose its changes are: whoever
        asked, and whoever said anything everyone now in it heard, in its topic or among its
        latest turns, as the run's context is drawn from them (core/groups.py)."""
        said = conn.execute(
            "select distinct speaker from turns where person = %(group)s and agent = %(agent)s "
            "and role = 'person' and speaker is not null and heard_by @> %(members)s::text[] "
            "and (topic = %(topic)s or id in (select id from turns where person = %(group)s "
            "and agent = %(agent)s and heard_by @> %(members)s::text[] order by id desc "
            "limit 200))", {"group": group, "agent": agent, "topic": topic,
                            "members": members}).fetchall()
        return sorted({*(r["speaker"] for r in said), *([sender] if sender else [])})

    @staticmethod
    def reads_outside(conn: psycopg.Connection, agent: str, acts_for: list[str],
                      topic: str, conversation: str | None = None) -> bool:
        """Whether a run opens marked: whether the conversation it reads holds a turn from a
        run that read outside content, in its topic, which its summary may have folded, or
        among the conversation's latest turns. In a group chat's conversation, among the
        turns everyone it acts for heard, which are all it's given. What a marked run passed
        on stays marked."""
        group = conversation if groups.of(conversation) else None
        if group is None and len(acts_for) != 1:
            return False
        heard = " and heard_by @> %(members)s::text[]" if group else ""  # the latest turns'
        it_heard = " and t.heard_by @> %(members)s::text[]" if group else ""  # and the turn's
        return bool(conn.execute(
            "select 1 from turns t join runs r on r.id = t.run_id where r.read_outside "
            "and t.person = %(person)s and t.agent = %(agent)s and (t.topic = %(topic)s or t.id in "
            f"(select id from turns where person = %(person)s and agent = %(agent)s{heard} "
            f"order by id desc limit 200)){it_heard} limit 1",
            {"person": group or acts_for[0], "agent": agent, "topic": topic,
             "members": list(acts_for)}).fetchone())

    def approvers_in_force(self, conn: psycopg.Connection) -> list[str]:
        """Who approved the settings in force, by key or on a card the core sealed."""
        row = conn.execute("select signers from settings_versions where scenario = %s "
                           "order by serial desc limit 1", (self.scenario.name,)).fetchone()
        return list(row["signers"]) if row else []

    def caps(self, conn: psycopg.Connection, release: str) -> dict[tuple[str, str], int]:
        """a5s's caps for a release's types of action in each part, as the core sealed them
        with the ledger's last word on each: 1 where there's none."""
        return samples.caps(conn, self.cfg.seal_keys, release)

    def approving(self, sealing: bool = True) -> str | None:
        """Why approvers can't approve settings where they work here, if they can't: it takes
        sign-in through the organisation's identity provider, and, in the gateway, which seals
        what they do, the core's seal key. The channels app, which people reach, has none."""
        if self.identity is None or not self.cfg.webchat_client_id:
            return ("approving settings where people work needs the organisation's identity "
                    "provider and the web chat's client: see A5S_OIDC_ISSUER and "
                    "A5S_WEBCHAT_CLIENT_ID")
        if sealing and not self.cfg.seal_keys:
            return "approving settings where people work needs the core's seal key: see A5S_SEAL_KEYS"
        return None

    def seal_pending(self, conn: psycopg.Connection) -> None:
        """Check again, and seal, what the channels app recorded people approving, deciding and
        grading, in the gateway alone (core/sealing.py): what doesn't check out is refused.
        Without its seal key or the identity provider, it leaves them waiting, and says so."""
        if problem := self.approving():
            if waiting := sealing.waiting(conn):
                log.error("%d approvals, decisions and grades wait to be sealed, but %s",
                          waiting, problem.replace("approving settings where people work needs",
                                                   "sealing them needs"))
            return
        args = (self.cfg.seal_keys, self.identity, self.scenario, self.cfg.webchat_client_id)
        for refused in (*approvals.seal_pending(conn, *args), *proposals.seal_pending(conn, *args),
                        *samples.seal_pending(conn, *args)):
            ledger.append(conn, {"kind": "admin", "action": "refuse-sign-in", "run": None,
                                 "instance": None, "acts_for": [], "decision": "record",
                                 "args": {"what": refused}})

    def unusable(self, settings: Settings, last: dict | None) -> list[str]:
        """Why a version of the settings couldn't be applied, before anyone's asked to approve
        it: an old serial, a release or tools this deployment doesn't have, or people the
        directory doesn't know."""
        problems = []
        if last and settings.serial <= last["serial"]:
            problems.append(f"serial {settings.serial} isn't above {last['serial']}, the version "
                            "in force's: raise it")
        tools = self.scenario.tools()
        taken = sorted({t.action for t in tools.values() if t.action})  # the types of action
        if unknown := sorted(set(settings.limits) - set(taken)):
            problems.append(f"the limits name {', '.join(unknown)}, which no tool here takes: the "
                            f"types of action are {', '.join(taken) or 'none'}")
        for instance in settings.instances:
            for part, levels in sorted(instance.actions.items()):
                if unknown := sorted(set(levels) - set(taken)):
                    problems.append(f"{instance.id} sets a level in {part} for "
                                    f"{', '.join(unknown)}, which no tool here takes: the types "
                                    f"of action are {', '.join(taken) or 'none'}")
                if unlimited := sorted(a for a, lv in levels.items()
                                       if lv >= 2 and a in taken and a not in settings.limits):
                    problems.append(f"{instance.id} works at level 2 in {part} for "
                                    f"{', '.join(unlimited)}, which has no limit: give it one, "
                                    "under limits, so a run can't make any number of them")
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
        """A run that answers a message the core received, acting for its sender, or in a
        group chat, for everyone in it when it was sent (core/groups.py)."""
        try:
            inbound = str(uuid.UUID(str(trigger.get("inbound"))))
        except ValueError:
            raise HTTPException(400, "name the message the run answers") from None
        message, problem = self.take_message(conn, inbound)
        sender = message["person"] if message else None
        group = message["conversation"] if message and groups.of(message["conversation"]) else None
        topic = topics.of_message(conn, self.scenario, group or sender, inst["definition"],
                                  message["text"], sorted(message["members"]) if group else None
                                  ) if message else topics.GENERAL
        acts_for = sorted(message["members"]) if group else [sender] if sender else []
        asked_by = self.spoke(conn, group, inst["definition"], topic, acts_for, sender) \
            if group else None
        opening = Opening(
            trigger={"kind": "message", "inbound": inbound,
                     "channel": message["channel"] if message else None, "sender": sender,
                     "topic": topic, **({"conversation": group, "asked_by": asked_by}
                                        if group else {})},
            acts_for=acts_for, reasons=[problem] if problem else [],
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

    def questioned(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                   now: datetime) -> Opening:
        """A run that answers another agent's question, acting for the same people as the run
        that asked, with its day's budget and its mark, and the question as a5s's task: with
        what changed in their records, if the instance asked reports on records. It sees no
        class of data the asking run's model may not see (core/asking.py)."""
        try:
            question = str(uuid.UUID(str(trigger.get("question"))))
        except ValueError:
            raise HTTPException(400, "name the question the run answers") from None
        row = conn.execute("select * from questions where id = %s for update",
                           (question,)).fetchone()
        if row is None:
            return Opening({"kind": asking.KIND, "question": question}, [],
                           {"question": question}, ["there's no such question"])
        by = {"question": question, "asked_by": row["asker"], "by_run": str(row["asked_by_run"])}
        asker = conn.execute("select * from instances where id = %s", (row["asker"],)).fetchone()
        asking_run = conn.execute("select acts_for, trigger from runs where id = %s and "
                                  "closed_at is null and expires_at > now()",
                                  (row["asked_by_run"],)).fetchone()
        payer = budgets.payer(list(asking_run["acts_for"]), asking_run["trigger"]) \
            if asking_run else None  # whose day it is: in a group chat, whoever asked there
        opening = Opening(trigger={"kind": asking.KIND, **by, **({"payer": payer} if payer else {}),
                                   **({"asker_model": asker["model"]} if asker else {})},
                          acts_for=list(row["acts_for"]),
                          args=by, reasons=[], marked=bool(row["read_outside"]),
                          used=bool(row["run_id"] or row["answered_at"] or row["problem"]))
        if opening.used:
            opening.reasons.append("the question has been taken already")
        if row["asked"] != inst["id"]:
            opening.reasons.append(f"the question is for {row['asked']}, not {inst['id']}")
        if asker is None or inst["id"] not in (asker["asks"] or []) or self.check_instance(
                conn, asker):
            opening.reasons.append(f"{row['asker']} may not ask {inst['id']}, by the settings "
                                   "in force")
        if asking_run is None:
            opening.reasons.append("the run that asked has ended")
        changed = [] if opening.reasons else self.changed_for(
            conn, inst, list(row["acts_for"]), now, asker["model"] if asker else None)
        opening.task = asking.brief(self.scenario, row, asker["definition"] if asker else "agent",
                                    changed)
        if changed:  # from the records, by code: as it would read them in its reports
            opening.told.append(("the records, as its reports would tell them", "\n".join(changed)))
        return opening

    def changed_for(self, conn: psycopg.Connection, inst: dict, people: list[str],
                    now: datetime, other_model: str | None) -> list[str]:
        """What changed in the records of each of these people, and what's open, as the
        instance's reports would tell them, of the records all of them may see, without
        recording that it told them: for a run of an instance that reports on records, asked a
        question for them. Nothing, if its release doesn't report, or the records can't be read."""
        definition = self.definitions.get(inst["definition"])
        if definition is None or definition.release_id != inst["release"] or not definition.reports:
            return []
        try:
            unseen = self.unseen(conn, inst["model"]) | (
                self.unseen(conn, other_model) if other_model else set())
            watched = self.scenario.watched()
            reach = parts.within(self.scenario, inst, people, watched)
            facts = []
            for report in definition.reports:
                for who in people:
                    if (person := self.scenario.person(who)) is None:
                        continue
                    news = reports.news(conn, self.scenario.name, inst["id"], person, report.source, [
                        replace(r, fields={k: v for k, v in r.fields.items() if k not in unseen})
                        for r in reach], now, withheld="title" in unseen,
                        beyond=reports.beyond(watched, reach, who))
                    facts += [f"- {fact}" if len(people) == 1 else f"- For {person.name}: {fact}"
                              for fact in news.facts]
            return facts
        except Exception:  # it answers from what its tools find instead
            log.exception("couldn't work out what changed for a question to %s", inst["id"])
            return []

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

    def slicing(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                now: datetime) -> Opening:
        """A run of the next slice of someone's task, acting for its audience, on its owner's
        day: the slice itself begins as the run opens, once nothing else stops it."""
        try:
            task_id = str(uuid.UUID(str(trigger.get("task"))))
        except ValueError:
            raise HTTPException(400, "name the task the run is for") from None
        row = conn.execute("select * from tasks where id = %s", (task_id,)).fetchone()
        if row is None:
            return Opening({"kind": tasking.KIND, "task": task_id}, [], {"task": task_id},
                           ["there's no such task"])
        opening = Opening(trigger={"kind": tasking.KIND, "task": task_id, "payer": row["owner"]},
                          acts_for=list(row["audience"]), args={"task": task_id}, reasons=[])
        if row["instance_id"] != inst["id"]:
            opening.reasons.append(f"{inst['id']} didn't take it")
        if row["status"] not in ("queued", "waiting", "running"):
            opening.reasons.append(f"it's {row['status']}")
            opening.used = True
        if self.scenario.person(row["owner"]) is None:
            opening.reasons.append("the directory doesn't know whose it is")
        return opening

    def summarising(self, conn: psycopg.Connection, inst: dict, trigger: dict,
                    now: datetime) -> Opening:
        """A run of a5s's own that folds the turns of a topic that no longer fit in its runs
        into the topic's summary, acting for the person whose conversation it is: in a group
        chat's, for everyone in it when the message whose run gave way was sent, as that run
        did, with its sender's budget. It has no tools, and writes to nobody."""
        who, topic = str(trigger.get("person")), str(trigger.get("topic") or topics.GENERAL)
        if not groups.of(who):
            opening = Opening(trigger={"kind": "summary", "person": who, "topic": topic},
                              acts_for=[who], args={"person": who, "topic": topic}, reasons=[])
            if self.scenario.person(who) is None:
                opening.reasons.append(f"the directory doesn't know {who}")
            return opening
        try:
            message = conn.execute(
                "select person, conversation, members, agent from inbound where id = %s",
                (str(uuid.UUID(str(trigger.get("message")))),)).fetchone()
        except ValueError:
            message = None
        if message is None or message["conversation"] != who:
            return Opening({"kind": "summary", "person": who, "topic": topic}, [],
                           {"person": who, "topic": topic},
                           ["name the group's message whose run its turns gave way to"])
        members = sorted(message["members"])
        opening = Opening(trigger={"kind": "summary", "person": who, "topic": topic,
                                   "conversation": who, "sender": message["person"]},
                          acts_for=members, args={"person": who, "topic": topic}, reasons=[])
        if message["agent"] != inst["definition"]:
            opening.reasons.append(f"it's the {message['agent']}'s conversation, "
                                   f"not the {inst['definition']}'s")
        if unknown := [m for m in members if self.scenario.person(m) is None]:
            opening.reasons.append(f"the directory doesn't know {', '.join(unknown)}")
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
        if action != "call_model":  # about no record, and no change, unless the call says so
            given |= {"in_scope": True, "visible": True, "over_limit": False}
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

    def hidden_from(self, conn: psycopg.Connection, row: dict) -> set[str]:
        """The fields of a class a run's model isn't approved for, which it never sees: for a
        run that answers another agent's question, the asking model's too, since the answer
        goes there (core/asking.py)."""
        other = (row.get("trigger") or {}).get("asker_model")
        return self.unseen(conn, row["model"]) | (self.unseen(conn, other) if other else set())

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
    marked: bool = False  # it starts as a run that has read content from outside
    told: list = field(default_factory=list)  # (source, text): more it reads as it opens


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


class Erasure(StatusChange):
    confirm: str | None = None  # the id again, so that a mistyped one erases nobody


class CapChange(StatusChange):
    agent: str
    part: str
    action: str


class ToolArgs(BaseModel):
    args: dict[str, Any] = {}


class Message(BaseModel):
    to: str
    text: str


class Answer(BaseModel):
    text: str = ""
    problem: str | None = None  # why there's no answer, such as its model being down


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
                 "report": gw.reporting, "reminder": gw.following_up, "summary": gw.summarising,
                 asking.KIND: gw.questioned, tasking.KIND: gw.slicing}
        if kind not in opens:
            raise HTTPException(400, "a run answers a message, reminds someone of an obligation "
                                     "or of what they asked, works on a schedule, tells someone "
                                     "about their records, keeps a topic's summary, answers "
                                     "another agent's question, or works on someone's task")
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
                conn, gw.scenario, release.budget, body.instance, opening.acts_for, kind, 0, now,
                opening.trigger)
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
            if kind == tasking.KIND and not reasons:  # the slice begins: its lease the run's time
                lease, task = tasking.begin(conn, gw.tasks, opening.trigger["task"])
                if lease is None:  # it can't go on, and its owner hears so if it has ended
                    reasons.append(task.get("last_error") or "it can't go on now")
                    if task.get("status") == "failed":
                        pushing += tell_of_task(conn, task)
                else:  # its run's model calls are held to what's left of its budget
                    opening.trigger.update(lease=lease, cap=int(task["tokens_left"]))
                    opening.task = tasking.brief(task, gw.scenario.person(task["owner"]))
            if not reasons:
                for who in sorted(set(opening.acts_for)):  # not while they're erased or archived
                    departures.hold(conn, who, shared=True)
                conn.execute(
                    "insert into runs (id, instance_id, token_hash, trigger, acts_for, expires_at, "
                    "read_outside) values (%s, %s, %s, %s, %s, now() + make_interval(mins => %s), "
                    "%s)",
                    (run_id, body.instance, token_hash(token), Jsonb(opening.trigger),
                     opening.acts_for, RUN_MINUTES,
                     opening.marked or gw.reads_outside(
                         conn, inst["definition"], opening.acts_for,
                         opening.trigger.get("topic", topics.GENERAL),
                         opening.trigger.get("conversation"))),
                )
                if kind == asking.KIND:  # whose run answers it, at work on it now
                    conn.execute("update questions set run_id = %s where id = %s",
                                 (run_id, opening.trigger["question"]))
                if opening.task:  # what a5s asks it, from the records: something it has read,
                    provenance.read(conn, run_id, {  # or what a reminder's person asked for, in
                        "reminder": provenance.THEY,  # their words, or what another agent asked,
                        asking.KIND: asking.QUESTION}.get(kind, provenance.A5S),  # whose values
                        opening.task, gw.scenario.record_pattern)  # an answer can't pass off
                for source, text in opening.told:
                    provenance.read(conn, run_id, source, text, gw.scenario.record_pattern)
                studio.handled(conn, run_id, studio.given(  # the records a5s gives it, kept
                    gw.scenario, opening.trigger, opening.seen,  # as long as the run, for who
                    [opening.task or "", *(text for _, text in opening.told)]))  # may see it
            if reasons and kind == asking.KIND and not opening.used:  # so the asker hears why
                conn.execute("update questions set problem = %s where id = %s",
                             ("; ".join(reasons)[:200], opening.trigger["question"]))
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
                "returning id::text as run, instance_id, trigger, tokens, task_result").fetchall()
            sends = []
            for row in stale:
                ledger.append(conn, {"kind": "run", "action": "close", "run": row["run"],
                                     "instance": row["instance_id"], "decision": "record",
                                     "outcome": "abandoned"})
                sends += give_instead(conn, row["trigger"], WHY["abandoned"])
                if tasking.ended(task := tasking.end(conn, gw.tasks, row, "abandoned")):
                    sends += tell_of_task(conn, task)  # its slices failed once too often
        push(sends)
        return [{"run": r["run"], "inbound": r["trigger"].get("inbound"),
                 "instance": r["instance_id"]} for r in stale]

    @app.post("/tasks/sweep", dependencies=[Depends(service)])
    def tasks_sweep() -> list[dict]:
        """The tasks whose next slice is due, each for the scheduler to work on, as a run of
        its instance's (core/tasking.py)."""
        with db.transaction(gw.url) as conn:
            due = gw.tasks.due(gw.clock(), within=conn)
            rows = conn.execute(
                "select t.id::text as id, t.instance_id, t.owner, i.definition from tasks t "
                "join instances i on i.id = t.instance_id where t.id = any(%s::uuid[]) "
                "and i.status = 'active' order by t.updated_at, t.id", (due,)).fetchall()
        return [{"kind": tasking.KIND, "task": r["id"], "instance": r["instance_id"],
                 "agent": r["definition"], "owner": r["owner"]} for r in rows]

    @app.post("/runs/{run_id}/close", dependencies=[Depends(service)])
    def close_run(run_id: str, body: CloseRun) -> dict:
        """Close a run, with how it ended. A reminder or chase whose run didn't get its message
        through, a5s gives itself, in its own words."""
        ended = status.outcome(body.outcome)  # from the fixed set: never anyone's words
        if ended != body.outcome:
            log.warning("run %s ended with an outcome a5s doesn't know, kept as other", run_id)
        with db.transaction(gw.url) as conn:
            row = conn.execute(
                "update runs set closed_at = now(), outcome = %s where id = %s and closed_at is null "
                "returning instance_id, trigger, tokens, task_result",
                (ended, run_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "no open run")
            ledger.append(conn, {"kind": "run", "action": "close", "run": run_id,
                                 "instance": row["instance_id"], "decision": "record",
                                 "outcome": ended})
            sends = [] if ended.startswith("done") else give_instead(conn, row["trigger"],
                                                                      WHY.get(ended))
            task = tasking.end(conn, gw.tasks, row, ended)  # a task's slice, and what it spent
            if tasking.ended(task) and not conn.execute(  # its owner hears, if its run didn't
                    "select 1 from turns where run_id = %s and role = 'agent' limit 1",
                    (run_id,)).fetchone():
                sends += tell_of_task(conn, task)
        push(sends)
        return {"closed": run_id}

    def tell_of_task(conn: psycopg.Connection, task: dict) -> list[int | None]:
        """a5s's own word to a task's owner that it's done, needs them, or has stopped, when
        its agent's run didn't say so: never the agent's own words. What to push once the
        transaction is done."""
        row = conn.execute("select t.*, i.definition as agent from tasks t join instances i "
                           "on i.id = t.instance_id where t.id = %s", (task["id"],)).fetchone()
        person = gw.scenario.person(row["owner"]) if row else None
        if (row is None or row["status"] not in ("done", "blocked", "failed") or person is None
                or not person.in_audience):
            return []
        text = tasking.notice(dict(row), row["agent"])
        ledger.append(conn, {"kind": "notice", "action": "task", "run": None,
                             "instance": row["instance_id"], "acts_for": [person.id],
                             "decision": "record", "args": {
                                 "task": str(row["id"]), "status": row["status"],
                                 "chars": len(text),
                                 "sha256": hashlib.sha256(text.encode()).hexdigest()}})
        noted(conn, person.id, row["agent"], text, None)
        return [outbound(conn, gw.reach(conn, person.id, row["agent"]), person.id, text,
                         instance=row["instance_id"], agent=row["agent"])]

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
            last = conn.execute(  # when a5s last read them: what's done since, was done since
                "select read_at from record_reads where scenario = %s", (gw.scenario.name,)
            ).fetchone()
            conn.execute("insert into record_reads (scenario, read_at) values (%s, %s) on "
                         "conflict (scenario) do update set read_at = excluded.read_at",
                         (gw.scenario.name, now))
            obligations.sync(conn, gw.scenario.name, owed, gw.definitions, now,
                             gw.scenario.part_of,
                             lambda serves, who: registry.serving(gw.scenario, serves, who),
                             last["read_at"] if last else None)
            instances = {i["id"]: i for i in conn.execute("select * from instances")}
            able = gw.able(conn)  # else code escalates
            rows = conn.execute(
                "select o.*, i.definition as agent from obligations o "
                "left join instances i on i.id = o.instance_id "
                "where o.scenario = %s and o.done_at is null order by o.due_at, o.id",
                (gw.scenario.name,)).fetchall()
            for row in rows:
                found = obligations.to_escalate(row, gw.scenario, now,
                                                able.get(row["instance_id"], False))
                if found is None:
                    continue
                to, why = found
                text = obligations.escalation(row, gw.scenario, to,
                                              instances.get(row["instance_id"]), why)
                conn.execute("update obligations set escalations = escalations + 1, "
                             "escalated_at = %s, escalated_to = %s, updated_at = %s where id = %s",
                             (now, to.id, now, row["id"]))
                route = gw.at_once(conn, to.id, row["agent"])
                ledger.append(conn, {
                    "kind": "notice", "action": "escalate", "run": None,
                    "instance": row["instance_id"], "acts_for": [], "decision": "record",
                    "args": {"obligation": row["id"], "record": row["record"],
                             "person": row["person"], "to": to.id, "as": why,
                             "step": row["escalations"] + 1,
                             "channel": route["channel"], "chars": len(text),
                             "sha256": hashlib.sha256(text.encode()).hexdigest()}})
                if route["channel"] == "batch":  # they've had today's urgent messages
                    urgent.hold(conn, to.id, None, row["instance_id"], None, text, now)  # a5s's
                else:  # in the chat, after this transaction, or in the local channel's inbox
                    sends.append(outbound(conn, route, to.id, text, instance=row["instance_id"],
                                          agent=row["agent"]))
                noted(conn, to.id, row["agent"], text, None if why == "unseen" else row["record"])
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
            gw.seal_pending(conn)  # what the channels app recorded counts once it's sealed
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
            return status.report(conn, gw.breakers.open(), gw.cfg.seal_keys,
                                 gw.cfg.flag_rubber_stamps)

    @app.get("/measures", dependencies=[Depends(service)])
    def measures_now(days: int = 30) -> dict:
        """The measures phase 1's first users baseline, and the pilot's later stages show,
        over the last `days` days by the core's clock: what fell due and was met on time, how
        late the rest was, who came back, what runs cost, how held changes were decided and
        graded, and what agents asked each other and noted (core/measures.py)."""
        with db.transaction(gw.url) as conn:  # whom each agent serves, as the studio counts it
            return measures.report(conn, gw.scenario.name, gw.models, days, gw.clock(),
                                   studio.served(gw.scenario, studio.instances(conn)))

    # The studio's API, for code, the command line and CI: everything, for the team that runs
    # a5s. People see what they may watch through the studio's pages (core/studio.py).

    @app.get("/studio/agents", dependencies=[Depends(service)])
    def studio_agents() -> dict:
        """Each agent of the release, and where it runs."""
        with db.transaction(gw.url) as conn:
            return {"agents": studio.catalogue(conn, gw.scenario, gw.definitions,
                                               gw.scenario.tools())}

    @app.get("/studio/agents/{agent}", dependencies=[Depends(service)])
    def studio_agent(agent: str) -> dict:
        """One agent, as its release defines it, its instructions included, and where it runs."""
        definition = gw.definitions.get(agent)
        if definition is None:
            raise HTTPException(404, f"there's no agent {agent} in this release")
        with db.transaction(gw.url) as conn:
            return studio.agent(gw.scenario, definition, gw.scenario.tools(),
                                studio.instances(conn), whole=True)

    @app.get("/studio/agents/{agent}/measures", dependencies=[Depends(service)])
    def studio_agent_measures(agent: str, days: int = 30) -> dict:
        """How an agent's instances are doing over the last `days` days."""
        with db.transaction(gw.url) as conn:  # with those retired within the window
            insts = [i for i in studio.instances(conn, retired=True) if i["definition"] == agent]
            if agent not in gw.definitions and not insts:
                raise HTTPException(404, f"there's no agent {agent} here")
            return studio.figures(conn, gw.scenario, gw.models, insts, days, gw.clock())

    def studio_instance(conn: psycopg.Connection, instance: str) -> dict:
        found = next((i for i in studio.instances(conn, retired=True) if i["id"] == instance),
                     None)
        if found is None:
            raise HTTPException(404, f"there's no instance {instance}")
        return found

    @app.get("/studio/instances/{instance}/measures", dependencies=[Depends(service)])
    def studio_instance_measures(instance: str, days: int = 30) -> dict:
        """How an instance is doing over the last `days` days."""
        with db.transaction(gw.url) as conn:
            return studio.figures(conn, gw.scenario, gw.models,
                                  [studio_instance(conn, instance)], days, gw.clock())

    @app.get("/studio/instances/{instance}/runs", dependencies=[Depends(service)])
    def studio_runs(instance: str, before: str | None = None,
                    limit: int = studio.RUNS) -> dict:
        """An instance's runs, newest first, a page at a time: `before` is where the page
        before ended, as it said."""
        with db.transaction(gw.url) as conn:
            try:
                return studio.runs(conn, gw.scenario, studio_instance(conn, instance),
                                   before=before, limit=limit)
            except ValueError:
                raise HTTPException(400, "before is where the page before ended, as it said")

    @app.get("/studio/runs/{run_id}", dependencies=[Depends(service)])
    def studio_run(run_id: str) -> dict:
        """What a run did, with its entries in the ledger."""
        with db.transaction(gw.url) as conn:
            found = studio.run(conn, gw.scenario, run_id)
        if found is None:
            raise HTTPException(404, f"there's no run {run_id}")
        return found

    @app.post("/people/{person}/export", dependencies=[Depends(service)])
    def export_person(person: str, body: StatusChange) -> dict:
        """All a5s keeps about someone, for their request to see it, for the data protection
        officer alone, who asked for it on the core's page (core/officer.py). The ledger records
        it, in counts."""
        if groups.of(person):
            raise HTTPException(400, "a group chat's conversation is nobody's own: name a person")
        by, identity = officer_asked("export", person, body)
        with db.transaction(gw.url) as conn:  # as of one moment, so that a sweep that
            conn.execute("set transaction isolation level repeatable read read only")  # archives
            found = export.gather(conn, person)  # them meanwhile moves nothing it reads
        if gw.scenario.person(person) is None and not export.holds(found):
            raise HTTPException(404, f"nobody in the directory has the id {person}, and a5s "
                                     "keeps nothing under it: check the id")
        with db.transaction(gw.url) as conn:  # before anything goes out
            ledger.append(conn, {"kind": "admin", "action": "export", "run": None,
                                 "instance": None, "acts_for": [person], "decision": "record",
                                 "args": {"person": person, "by": by, "identity": identity,
                                          "counts": export.counts(found)}})
        return found

    @app.post("/people/{person}/erase", dependencies=[Depends(service)])
    def erase_person(person: str, body: Erasure) -> dict:
        """Erase all a5s keeps about someone, at their request, for the data protection officer
        alone, who asked for it on the core's page (core/officer.py), with the id sent again to
        confirm it (core/erasure.py). What's evidence of what agents did stays. The ledger
        records it, in counts."""
        if groups.of(person):
            raise HTTPException(400, "a group chat's conversation is nobody's own: name a person")
        if body.confirm != person:
            raise HTTPException(400, "send the id again as confirm, so that a mistyped id erases "
                                     "nobody")
        here = gw.scenario.person(person) is not None
        with db.transaction(gw.url) as conn:  # the request is used only if the erasure is made
            by, identity = officer_asked("erase", person, body, conn)
            try:
                gone, archives = erasure.erase(conn, person, gw.clock(), here)
            except erasure.Busy:
                raise HTTPException(409, f"a5s is at work for {person} now, and might write what "
                                         "it read of them after the erasure: try again in a "
                                         "minute or two") from None
            if not gone and not archives and not here:
                raise HTTPException(404, f"nobody in the directory has the id {person}, and a5s "
                                         "keeps nothing under it: check the id")
            ledger.append(conn, {"kind": "admin", "action": "erase", "run": None,
                                 "instance": None, "acts_for": [person], "decision": "record",
                                 "args": {"person": person, "by": by, "identity": identity,
                                          "erased": gone, "archives_left": len(archives)}})
        return {"erased": person, "by": by, "gone": gone, "archives": archives}

    @app.post("/retention/sweep", dependencies=[Depends(service)])
    def sweep_retention() -> dict:
        """Delete what's past its time to keep (core/retention.py), and record how much went.
        Archive what a5s keeps for anyone who has left (core/departures.py), apart, so neither
        holds up the other, nor the ledger's other writers."""
        with db.transaction(gw.url) as conn:
            gone = retention.sweep(conn, gw.clock(), gw.scenario.name)
            if gone:
                ledger.append(conn, {"kind": "retention", "action": "delete", "run": None,
                                     "instance": None, "acts_for": [], "decision": "record",
                                     "args": gone})
        with db.transaction(gw.url) as conn:
            archived = departures.sweep(conn, gw.scenario, gw.clock())
        return {"deleted": gone, "archived": len(archived)}

    @app.post("/notebook/sweep", dependencies=[Depends(service)])
    def sweep_notebook() -> dict:
        """Read again the records of the notes not checked for a day, outside any transaction,
        and let go of those whose records changed (core/notebook.py): asked apart from the
        other sweeps, so a records system that's slow to answer holds none of them up."""
        return notebook.check(gw.url, gw.scenario, gw.clock())

    def officer_asked(action: str, person: str, body: StatusChange,
                      conn: psycopg.Connection | None = None) -> tuple[str, dict | str]:
        """Who asked for this, and how a5s knows: where people sign in, the data protection
        officer's request on the core's page, made for this alone, which it uses up, in `conn`'s
        transaction if it's given one; in development, whoever they say, if they have the
        role."""
        if gw.identity is not None:
            try:
                if conn is not None:
                    asked = officer.take(conn, gw.identity, gw.scenario,
                                         gw.cfg.webchat_client_id, action, person)
                else:
                    with db.transaction(gw.url) as own:
                        asked = officer.take(own, gw.identity, gw.scenario,
                                             gw.cfg.webchat_client_id, action, person)
            except approvals.Refused as exc:
                raise HTTPException(exc.status, exc.reason) from None
            return asked["officer"], {"verified": "a sign-in to ask for this alone",
                                      "request": str(asked["id"]), "issuer": asked["issuer"],
                                      "token_sha256": asked["token"].removeprefix(
                                          approvals.HASHED)}
        if not gw.cfg.development:
            raise HTTPException(503, "the officer's requests need sign-in: set A5S_OIDC_ISSUER")
        who = gw.scenario.person(body.by or "")
        if who is None or DATA_PROTECTION not in who.roles:
            raise HTTPException(403, f"only the data protection officer may {action} what a5s "
                                     f"keeps about someone, and {body.by} isn't")
        return who.id, "unverified (development)"

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
            group = row["trigger"].get("conversation") if groups.of(
                row["trigger"].get("conversation")) else None
            person = gw.scenario.person(row["acts_for"][0]) if len(row["acts_for"]) == 1 \
                and not group else None
            context = [profiles.section(conn, person)] if person else []
            if group:
                context.append(groups.section(gw.scenario, list(row["acts_for"]),
                                              row["trigger"].get("sender")))
            topic = row["trigger"].get("topic", topics.GENERAL)
            if topic != topics.GENERAL and not parts.workable(gw.scenario, row, topic):
                context.append({"title": f"The case: {topic}, from the records",
                                "text": f"a5s has nothing on {topic} for this run: {parts.UNSEEN}."})
            elif topic != topics.GENERAL:
                context.append(topics.brief(conn, gw.scenario, topic, person, gw.clock(),
                                            gw.hidden_from(conn, row)))
                provenance.read(conn, row["run"], f"the records, on {topic}", context[-1]["text"],
                                gw.scenario.record_pattern)
                if waiting := proposals.brief(conn, row["id"], list(row["acts_for"]), [topic],
                                              group):
                    context.append({  # a5s's own, not the records': so it says it waits
                        "title": f"Changes to {topic} waiting for a decision",
                        "text": "a5s holds these, as they were asked for, until their deciders "
                                "decide them. Asking for one again only points at it.\n"
                                + "\n".join(waiting)})
            asker = gw.scenario.person(row["trigger"].get("sender") or "") if group else None
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
            elif asker and (offered := reminders.waiting_for_yes(conn, asker, row["definition"],
                                                                 group, list(row["acts_for"]))):
                context.append({"title": f"What you offered {asker.name} here, waiting for "
                                         "their yes",
                                "text": f"You offered these in an earlier message in this chat. "
                                        f"If {asker.name} says yes to one now, keep it with the "
                                        "tool named, at once, without asking again. Only they "
                                        "can.\n" + "\n".join(f"- {o}" for o in offered)})
                provenance.read(conn, row["run"], provenance.A5S, context[-1]["text"],
                                gw.scenario.record_pattern)
            if learned := notebook.given(conn, gw.scenario, row):  # from records alone, and
                context.append(learned)  # not counted as found: the agent checks the record
            questioned = row["trigger"].get("kind") == asking.KIND
            asked = conn.execute(  # those that work for everyone this run is for, as asked
                "select distinct definition, serves from instances where id = any(%s) and "
                "status = 'active' order by definition", (list(row["asks"] or []),)).fetchall() \
                if asking.ASK in (row["grants"] or []) and not questioned else []
            if able := sorted({a["definition"] for a in asked if all(
                    registry.serving(gw.scenario, a["serves"], p) for p in row["acts_for"])}):
                context.append({"title": "Agents you may ask",
                                "text": "With ask_agent, for the people you're working for, "
                                        "naming the agent as below. Each sees only your "
                                        "question, so name the records it's about, and answers "
                                        "within what those people may see.\n" + "\n".join(
                                            f"- {a}: " + (d.does.strip() if (
                                                d := gw.definitions.get(a)) else "")
                                            for a in able)})
            if person or group:  # and the day each turn of the conversation was said
                said = conn.execute("select distinct to_char(at at time zone 'UTC', 'YYYY-MM-DD') "
                                    "as day from turns where person = %s and agent = %s",
                                    (group or person.id, row["definition"])).fetchall()
                provenance.read(conn, row["run"], "when things were said",
                                " ".join(d["day"] for d in said), gw.scenario.record_pattern)
            released = gw.definitions.get(row["definition"])
            if released and released.skills and row["trigger"].get("kind") not in OWN_RUNS:
                provenance.read(conn, row["run"], "its release's skills",  # approved with it,
                                "\n".join(released.skills.values()),  # not the agent's own
                                gw.scenario.record_pattern)
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
            "tools": [] if own else [tools[n].definition() for n in row["grants"] if n in tools
                                     and (n not in CORE_TOOLS or not CORE_TOOLS[n].offered
                                          or CORE_TOOLS[n].offered(row))],  # only those that
            # can work for the run: nothing that could only refuse it
            "plain": own,
            "skills": {} if own else definition.skills,  # read-only, from the release
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
        arg = tool.record_arg if tool else None  # the record it's about, if it names one
        named = args.get(arg) if arg else None
        records = [] if named in (None, "") else named if isinstance(named, list) else [named]
        keys = [r for r in records if isinstance(r, str) and r]
        action = tool.action if tool else None  # a change, which levels and limits govern
        # the records as they stand, read before any lock is taken, so a slow system holds
        # up nobody else: for its deciders, the owner's report and graders
        standing = proposals.snapshot({k: record_of(gw.scenario, k) for k in keys}) if action else {}
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            # Its changes are counted and held for whoever asked, and in a group chat those who
            # spoke of them: what it sees is still only what everyone it acts for may see
            requested = {**row, "acts_for": groups.requesters(row)}
            entity = gw.core_tool_entity(name) if core else gw.tool_entity(name, tool, row["pins"])
            found = gw.settings_in_force(conn)
            change, over, again = None, None, None
            if action and found[0] is not None and all(isinstance(r, str) and r for r in records):
                change = counts.change(action, keys, args)
                again = counts.before(conn, requested, action, change)
                waits = proposals.waiting(conn, requested, change)
                if waits is not None or (again and again["state"] != "held"):
                    # asked for already: answered with what became of it, never made twice
                    ledger.append(conn, {"kind": "tool", "action": name, "run": row["run"],
                                         "instance": row["id"], "acts_for": requested["acts_for"],
                                         "decision": "record", "args": ledger.mask(args, (arg,)),
                                         "outcome": {"status": "asked already", **(
                                             {"proposal": proposals.key(waits)} if waits else
                                             {"state": again["state"]})}})
            else:
                waits = None
            if waits is None and not (again and again["state"] != "held"):
                if change:
                    over = counts.over(conn, requested, action, max(len(keys), 1), found[0].limits,
                                       gw.clock())
                about = parts.about(gw.scenario, row, keys, action, gw.approvers_in_force(conn),
                                    gw.caps(conn, row["release"])) if action else parts.about(
                    gw.scenario, row, keys)
                decision = gw.decide(row, "call_tool", entity, [], **about,
                                     over_limit=over is not None)
                if found[0] is None:  # fail closed
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
                deciding = holding(decision, records, requested)
                if isinstance(deciding, str):  # nobody may decide it, or nothing can here
                    decision = Decision(False, ("someone-else-decides",), explanations=(deciding,))
                texts = [s for f in tool.text_fields for s in strings(args.get(f))] if tool else []
                if decision.held:  # what deciders should know: every value the agent wrote itself
                    texts = strings(args)
                traced = provenance.traced(conn, gw.scenario, row, "\n".join(texts))
                last = next((f for f in reversed(tool.text_fields)
                             if isinstance(args.get(f), str)), None) if tool else None
                if (own := [t["value"] for t in traced if t["from"] is None]) and last:
                    args[last] += "\n\n" + provenance.note(row["definition"], own)  # apart
                if row["read_outside"] and last and decision.allowed:  # and what it drew on
                    args[last] += "\n\n" + extractor.DREW
                plain = (*((arg,) if arg else ()), *(core.plain if core else ()))
                seq = ledger.append(conn, gw.entry(row, "tool", name, decision,
                                                   args=ledger.mask(args, plain),
                                                   links_removed=removed,
                                                   **({"values": values_of(traced)} if traced else {})))
                studio.handled(conn, row["run"], keys)  # the records it named, whatever came of it
                if change and (decision.allowed or decision.held):  # made or held: it counts
                    counts.count(conn, requested, action, change, max(len(keys), 1),
                                 over is not None, "making" if decision.allowed else "held",
                                 gw.clock())
                if decision.held:  # it waits for a person: the exact call, kept for its deciders
                    proposal, sends = held(conn, requested, tool, args, standing, deciding or [],
                                           seq, traced, change, over, found[0])
        if waits is not None or (again and again["state"] != "held"):
            return {"result": {"held": proposals.key(waits), "status": (
                f"Asked for already, on {waits['proposed_at']:%d %b}: it still waits for a "
                "decision, on a5s's own page, and a5s makes it once it's approved.")}
                if waits is not None else {"made": (
                    "a5s made this same change already, in this run, and doesn't make it twice"
                    if again["state"] == "made" else "a5s is making this same change now, in "
                    "this run, and doesn't make it twice")}, "recorded": True}
        traces.note(current, **{"a5s.run.id": row["run"], "a5s.instance": row["id"],
                                "a5s.decision": decision.label})
        if decision.held:
            push(sends)
            names = approvals.names_of([p.name for p in deciding or []])
            whom = approvals.names_of([p.name if (p := gw.scenario.person(w)) else w
                                       for w in requested["acts_for"]])
            return {"result": {
                "held": proposals.key(proposal), "decides": names,
                "status": f"Not made yet: it waits for {names} to decide it, on a5s's own page. "
                          f"a5s will tell {whom if requested['acts_for'] else 'its owner'} what "
                          "they decide, and makes the change if they approve it."},
                "recorded": True}
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if core is not None and core.name == extractor.ASK:  # it needs the run's own model
            return asking_about(args, row, seq, token)
        if core is not None and core.name == asking.ASK:  # it waits, outside any transaction
            return asking_agent(args, row, seq)
        if core is not None:
            return call_core_tool(core, args, row, seq)
        try:
            with db.transaction(gw.url) as conn:  # a system gets the values handles stand for
                given = handles.resolved_args(conn, row["run"], args)
            for field_name in tool.text_fields:  # cleaned again: a value may hold a link,
                if field_name in given:  # though a5s's own notes stay
                    given[field_name], _ = cleaned(given[field_name], gw.scenario.record_links,
                                                   notes=False)
            result = tool.run(ToolCall(args=given, instance=row["id"], run=row["run"],
                                       acts_for=tuple(row["acts_for"]),
                                       key=counts.key(row["run"], change) if change else None))
            refused = result.get("error") if action and isinstance(result, dict) else None
            outcome = ({"status": "error", "error": str(refused)[:200], "answered": True}
                       if refused else {"status": "ok", "result_sha256": ledger.digest(result)})
            result, withheld = parts.kept(gw.scenario, row, tool.record_field, result)
            if withheld:  # first, so a5s reads nothing the run may not see
                outcome["withheld"] = withheld
            if tool.outside:  # never the content itself: the extractor's form, checked by code
                result, outcome["documents"] = read_outside(row, token, tool, result)
            with db.transaction(gw.url) as conn:  # the agent gets handles for sensitive values,
                hidden = (*tool.handles, *sorted(gw.hidden_from(conn, row)))  # and classified
                result = handles.issue(conn, row["run"], name, result, hidden)  # ones it can't see
        except Exception as exc:  # noqa: BLE001 - the tool's own failure, recorded and reported
            with db.transaction(gw.url) as conn:  # it may repeat an argument: no handle's value
                said = handles.masked(conn, row["run"], f"{type(exc).__name__}: {exc}")
            result, outcome = None, {"status": "error", "error": said[:200]}
        if outcome["status"] == "ok":
            try:
                with db.transaction(gw.url) as conn:  # the forms' values are their documents'
                    provenance.read(conn, row["run"], name, extractor.without_forms(result),
                                    gw.scenario.record_pattern)
                    provenance.read_records(conn, row["run"], name, tool.record_field,  # and
                                            extractor.without_forms(result),  # each record's
                                            gw.scenario.record_pattern)  # apart
            except psycopg.Error:  # the values it wrote will be flagged as its own: never worse
                log.exception("couldn't note what %s read from %s", row["run"], name)
            if tool is not None and tool.record_field:  # the records it gives the run, kept
                with db.transaction(gw.url) as conn:  # before the run has them, as the studio
                    studio.handled(conn, row["run"],  # shows a run only to who may see them
                                   studio.keys_in(result, tool.record_field))
        recorded = record({"kind": "tool", "action": name, "run": row["run"], "instance": row["id"],
                           "decision": "record", "of": seq, "outcome": outcome,
                           **({"level": about["level"]} if action else {})})
        if change:
            try:
                with db.transaction(gw.url) as conn:  # made, or not taken, so not counted
                    (counts.made if outcome["status"] == "ok" else counts.failed)(
                        conn, row["run"], change)
            except psycopg.Error:
                log.exception("couldn't settle the count of %s's change", row["run"])
        if action and outcome["status"] == "ok":  # a change made at level 2: someone's told
            try:
                acted(row, tool, args, keys, standing)
            except Exception:  # it's made: the agent hears so, whatever else fails
                log.exception("couldn't report the change %s made", row["run"])
        traces.note(current, **{"error.type": "tool_error" if outcome["status"] != "ok" else None})
        if outcome["status"] != "ok" and not outcome.get("answered"):
            return JSONResponse(status_code=502, content={"error": outcome["error"]})
        return {"result": result, "recorded": recorded}

    def acted(row: dict, tool: Tool, args: dict, keys: list[str], standing: dict) -> None:
        """Report a change an agent made at level 2, in words code works out, with each record
        as it stood before, and a link to it, so it can be reversed through the scenario's own
        process if it needs to be: in the digest of the instance's owner and deputy who may see
        its records, or, with neither, of the owners of its parts. Tell whoever it was for, in
        their conversation with the agent. And draw it as a sample, for grading."""
        asked = groups.requesters(row)  # whose words asked for it: in a group, not everyone
        whom = approvals.names_of([p.name if (p := gw.scenario.person(w)) else w
                                   for w in asked]) if asked else "nobody"
        with db.transaction(gw.url) as conn:
            values = {r["handle"]: r["value"] for r in conn.execute(
                "select handle, value from run_handles where run_id = %s", (row["run"],))}
            said = proposals.said(gw.scenario, tool, args, standing, asked,
                                  row["definition"], values)
            change = said.split("\n", 1)[0]
            before = " ".join(proposals.stood(standing)).replace(
                "as it stood when it was asked for", "as it stood before")
            text = (f"The {row['definition']} made a change itself, at level 2, for {whom}: "
                    f"{change}" + (f" {before}" if before else ""))
            inst = conn.execute("select owner, deputy from instances where id = %s",
                                (row["id"],)).fetchone()
            told = [p for p in (inst["owner"], inst["deputy"])
                    if p and all(gw.scenario.sees(p, k) for k in keys)]
            if not told:  # nobody runs it here: the owners of its parts hear instead
                told = [p.id for p in proposals.everyone(proposals.deciders(
                    gw.scenario, keys, []))]
            for person in dict.fromkeys(told):
                digests.keep(conn, person, row["definition"], row["id"], row["run"], text,
                             gw.clock())
            group = row["trigger"].get("conversation")  # and its next run knows a5s made it:
            for person in ([group] if groups.of(group) else row["acts_for"]):  # the group's, in one
                noted(conn, person, row["definition"],
                      f"a5s made the change the {row['definition']} asked for, at level 2: "
                      f"{change}", keys[0] if keys else None,
                      heard_by=list(row["acts_for"]) if groups.of(group) else None)
            for part in sorted({p for k in keys if (p := gw.scenario.part_of(k))}):
                samples.draw(conn, gw.cfg.seal_keys, gw.scenario.name, "action", row["release"],
                             row["definition"],
                             row["id"], row["run"], part, tool.action, said, standing,
                             asked, gw.clock())
            ledger.append(conn, {"kind": "tool", "action": "report", "run": row["run"],
                                 "instance": row["id"], "acts_for": asked,
                                 "decision": "record", "args": {"to": sorted(set(told)),
                                                                "tool": tool.name,
                                                                "records": keys}})

    def holding(decision: Decision, records: list[str], row: dict) -> list[Person] | str:
        """Who may decide a call policy holds, if it holds it: or why nobody may, in words."""
        if not decision.held:
            return []
        if (problem := gw.approving()) is not None:
            return f"a change can't wait for a decision here, since {problem}"
        asked = groups.requesters(row)  # in a group, whoever asked and whoever spoke of it
        by_part = proposals.deciders(gw.scenario, records, asked)
        if not (nobody := proposals.undecidable(by_part)):
            return proposals.everyone(by_part)
        anyone = proposals.deciders(gw.scenario, records, [])
        if all(anyone[part] for part in by_part if not by_part[part]):
            if groups.of(row["trigger"].get("conversation")):
                only = approvals.names_of([p.name for part in by_part if not by_part[part]
                                           for p in anyone[part]])
                return (f"only {only} may decide this change, and nobody decides a change their "
                        "own words in a chat asked for: ask for it one to one, where someone "
                        f"else asks, or {only} can make it in the records system")
            return ("nobody but the people this run is for may decide this change, and nobody "
                    "decides what they asked for themselves: they can make it themselves, in "
                    "the records system")
        return (f"nobody may decide this change for {approvals.names_of(nobody)}: of the people "
                "who decide changes there, none may see every record it names. Ask for a change "
                "to the records of one part at a time, or ask someone who may see them all to "
                "make it")

    def held(conn: psycopg.Connection, row: dict, tool: Tool, args: dict, standing: dict,
             deciding: list[Person], seq: int, traced: list[dict], change: str | None,
             over: str | None, settings: Settings) -> tuple[dict, list]:
        """Keep a held call for its deciders, and ask each of them, where they work with the
        agent, to decide it on the core's page, as an urgent message: past their five a day,
        it waits for their next batch. The proposal, and what to send once the transaction is
        done."""
        whom = approvals.names_of([p.name if (p := gw.scenario.person(w)) else w
                                   for w in row["acts_for"]])
        flags = []
        for t in traced:
            if t["from"] is None:
                flags.append(f"{t['value']} came from the {row['definition']} itself, not from "
                             f"the records or from {whom}")
            elif t["from"].startswith(provenance.OUTSIDE):
                flags.append(f"{t['value']} came from a document from outside the organisation "
                             f"({t['from'].removeprefix(provenance.OUTSIDE).strip()}), such as a "
                             "customer's email, not from the records")
        if row["read_outside"]:
            flags.append(f"the {row['definition']} read content from outside the organisation "
                         "before it asked for this")
        if over is not None:
            flags.append(f"it waits because {over}")
        proposal = proposals.hold(conn, gw.scenario, row, tool, args, standing, deciding, seq,
                                  flags, gw.clock(), change, proposals.sensitive(
                                      conn, row["run"], tool, args, settings.classified))
        sends = [ask(conn, proposal, person.id) for person in deciding]
        conn.execute("update proposals set asked = %s where id = %s",
                     ([p.id for p in deciding], proposal["id"]))
        return proposal, sends

    def ask(conn: psycopg.Connection, p: dict, person: str, again: bool = False) -> int | None:
        """Ask, or remind, a decider to decide a held change, where they work with its agent,
        as an urgent message. What to push once the transaction is done."""
        link = f"{gw.public_url}/decide/?proposal={p['digest']}"
        text = proposals.asking(p, link, again)
        route = gw.at_once(conn, person, p["definition"])
        ledger.append(conn, {
            "kind": "notice", "action": "remind-decision" if again else "ask-decision",
            "run": str(p["run_id"]), "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
            "decision": "record", "args": {"proposal": proposals.key(p), "to": person,
                                           "channel": route["channel"], "chars": len(text),
                                           "sha256": hashlib.sha256(text.encode()).hexdigest()}})
        if route["channel"] == "batch":  # they've had today's urgent messages
            urgent.hold(conn, person, None, p["instance_id"], None, text, gw.clock())
            return None
        return outbound(conn, route, person, text, instance=p["instance_id"],
                        agent=p["definition"], card=proposals.card(p, link, again))


    def read_outside(row: dict, token: str, tool: Tool, result: Any) -> tuple[Any, int]:
        """What a tool returned, with each item's outside content, whatever its type and at any
        depth, replaced by the extractor's form of it, which code checked, and the document's
        number. The run is marked first: once it's read outside content, it stays marked. The
        same document read again in the run keeps its number and form. The reader reads at
        most the first few thousand words of each, and a few documents a call, within what's
        left of the run's budget. How many it read."""
        with db.transaction(gw.url) as conn:
            conn.execute("update runs set read_outside = true where id = %s", (row["run"],))
            unseen = gw.hidden_from(conn, row)
            spent = conn.execute("select tokens from runs where id = %s",
                                 (row["run"],)).fetchone()["tokens"]
        model = gw.models.get(row["model"])
        release = gw.definitions.get(row["definition"])
        room = (release.budget.per_run - spent) * CHARS_PER_TOKEN if release else 0
        read = 0

        def form(item: dict) -> dict:
            nonlocal read, room
            found = [item[f] for f in tool.outside if f in item and item[f] not in (None, "")]
            whole = "\n\n".join(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                                  for v in found)
            kept = {k: walk(v) for k, v in item.items() if k not in tool.outside}
            if not whole:
                return kept
            text = whole[:extractor.MOST]  # what a5s's reader reads of it, and says so
            digest = hashlib.sha256(whole.encode()).hexdigest()
            with db.transaction(gw.url) as conn:
                again = conn.execute("select number, form from run_documents where run_id = %s "
                                     "and digest = %s", (row["run"], digest)).fetchone()
            if again is not None:  # read already in this run: no second call to the model
                return {**kept, "document": f"D-{again['number']}", extractor.OUTSIDE: again["form"]}
            filled, dropped, why = None, [], "a5s couldn't read it now"
            if any(f in unseen for f in tool.outside if f in item):
                why = "it's of a class the model here isn't approved for, so a5s didn't read it"
            elif read >= extractor.DOCUMENTS:
                why = (f"a5s reads at most {extractor.DOCUMENTS} documents a call: ask for fewer "
                       "at once")
            elif len(text) + 2_000 > room:
                why = "what's left of the run's budget hasn't room to read it"
            elif model is not None:
                room -= len(text) + 2_000
                answer = model_call(model.api, extractor.form_request(
                    model.api, row["model"], tool.extract, text), token)
                reply = extractor.reply_text(model.api, json.loads(answer.body))
                if answer.status_code < 400:
                    filled, dropped = extractor.checked(reply, text, tool.extract,
                                                        gw.scenario.record_pattern)
            shown = {**(filled if filled is not None else dict.fromkeys(tool.extract)),
                     **({"unread": why} if filled is None else {}),
                     **({"left_out": dropped} if dropped else {}),
                     **({"cut": f"a5s read the first {len(text):,} characters of {len(whole):,}"}
                        if len(whole) > len(text) else {})}
            with db.transaction(gw.url) as conn:
                number = conn.execute(
                    "insert into run_documents (run_id, number, text, digest, form) values (%s, "
                    "(select coalesce(max(number), 0) + 1 from run_documents where run_id = %s), "
                    "%s, %s, %s) returning number",
                    (row["run"], row["run"], text, digest, Jsonb(shown))).fetchone()["number"]
                if filled:  # its values are the document's, not the records'
                    provenance.read(conn, row["run"], f"{provenance.OUTSIDE} D-{number}", filled,
                                    gw.scenario.record_pattern)
            read += 1
            return {**kept, "document": f"D-{number}", extractor.OUTSIDE: shown}

        def walk(value: Any) -> Any:
            if isinstance(value, list):
                return [walk(v) for v in value]
            if isinstance(value, dict):
                if any(f in value for f in tool.outside):
                    return form(value)
                return {k: walk(v) for k, v in value.items()}
            return value

        return walk(result), read

    def asking_about(args: dict, row: dict, seq: int, token: str) -> Any:
        """a5s's reader's answer to a question about a document the run has read: in free
        text, marked as outside content, never as an instruction."""
        number = str(args.get("document", "")).removeprefix("D-")
        with db.transaction(gw.url) as conn:
            found = conn.execute("select text from run_documents where run_id = %s and number = %s",
                                 (row["run"], int(number) if number.isdigit() else -1)).fetchone()
        model = gw.models.get(row["model"])
        if found is None or model is None:
            record({"kind": "tool", "action": extractor.ASK, "run": row["run"],
                    "instance": row["id"], "decision": "record", "of": seq,
                    "outcome": {"status": "refused"}})
            return JSONResponse(status_code=403, content={
                "denied": True, "explanations": ["this run has read no such document"]})
        answer = model_call(model.api, extractor.answer_request(
            model.api, row["model"], found["text"], str(args.get("question", ""))[:500]), token)
        said = extractor.reply_text(model.api, json.loads(answer.body))
        status_now = "ok" if answer.status_code < 400 and said else "error"
        recorded = record({"kind": "tool", "action": extractor.ASK, "run": row["run"],
                           "instance": row["id"], "decision": "record", "of": seq,
                           "outcome": {"status": status_now}})
        if status_now != "ok":
            return JSONResponse(status_code=502, content={"error": "a5s's reader couldn't answer now"})
        pattern = gw.scenario.record_pattern  # its values are the outside document's own
        held = values.found(found["text"], pattern)  # only where the document holds them, as
        with db.transaction(gw.url) as conn:  # its form's are: one it made up is its own
            provenance.noted(conn, row["run"], f"{provenance.OUTSIDE} D-{number}",
                             [v for v in values.found(said, pattern)
                              if any(v.matches(h) for h in held)])
            said = handles.masked(conn, row["run"], said)
        return {"result": {extractor.OUTSIDE: True, "document": f"D-{number}", "says": said,
                           "note": extractor.NOTE}, "recorded": recorded}

    def asking_agent(args: dict, row: dict, seq: int) -> Any:
        """Ask another agent, for the people the run acts for (core/asking.py). The core opens
        the run that answers at once, and hands its token to the worker that asked, to run as
        it runs its own: so a question never waits for another worker, and no thread of the
        core's waits on it. Its answer comes back through /run/answer, with its mark."""
        agent = str(args.get("agent", "")).strip().lower().removeprefix("the ").strip()
        text = " ".join(str(args.get("question", "")).split())

        def told(status: str, **more: Any) -> bool:
            return record({"kind": "tool", "action": asking.ASK, "run": row["run"],
                           "instance": row["id"], "decision": "record", "of": seq,
                           "outcome": {"status": status, **more}})

        try:
            if not text:
                raise coretools.Refused("say what to ask, in a sentence or two")
            if len(text) > asking.LONGEST:
                raise coretools.Refused(f"keep the question to {asking.LONGEST} characters")
            with db.transaction(gw.url) as conn:
                asked = asking.whom(conn, gw.scenario, row, agent)
                question = asking.ask(conn, row, asked, text, gw.clock())
        except coretools.Refused as exc:
            told("refused", reason=str(exc))
            return JSONResponse(status_code=403, content={"denied": True, "reasons": [str(exc)],
                                                          "explanations": [str(exc)]})
        try:
            with traces.span("open_run", **{"a5s.trigger": asking.KIND}) as current:
                opened = opening_run(OpenRun(instance=asked["id"], trigger={
                    "kind": asking.KIND, "question": question}), current)
        except HTTPException as exc:  # the core says why, for the run that asked
            why = "; ".join(exc.detail.get("reasons", [])) if isinstance(exc.detail, dict) \
                else str(exc.detail)
            told("error", error=f"the {agent} can't answer: {why}"[:200], question=question)
            return JSONResponse(status_code=409, content={
                "error": f"the {agent} can't answer: {why}"[:300]})
        return {"answer_with": {"token": opened["token"], "task": opened["task"],
                                "question": question, "agent": agent}, "recorded": True}

    @app.post("/run/answer")
    def answer_question(body: Answer, token: str = Depends(run_token)) -> dict:
        """A run's answer to the question it was opened for, back to the run that asked: with
        its mark, and the values in it the run had read, from its tools and what a5s told it,
        never from the question, and without its handles. Or why there's none. Either way, the
        run that answered is over, and the run that asked gets what to tell its model."""
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            if row["trigger"].get("kind") != asking.KIND:
                raise HTTPException(403, "only a run that answers a question gives an answer")
            question = row["trigger"]["question"]
            asked = conn.execute("select * from questions where id = %s and run_id = %s "
                                 "for update", (question, row["run"])).fetchone()
            if asked is None or asked["answered_at"] or asked["problem"]:
                raise HTTPException(409, "the question has been answered, or given up on")
            agent = row["definition"]
            text, _ = sanitize(body.text, gw.scenario.record_links)
            text = asking.kept_back(text, agent)
            why = body.problem or (None if text.strip() else "its answer was empty")
            if why is not None:
                conn.execute("update questions set problem = %s where id = %s",
                             (why[:200], question))
            else:
                conn.execute("update questions set answer = %s, answered_at = %s, "
                             "answer_read_outside = (select read_outside from runs where id = %s) "
                             "where id = %s", (text, gw.clock(), row["run"], question))
            marked = bool(conn.execute("select read_outside from runs where id = %s",
                                       (row["run"],)).fetchone()["read_outside"])
            carried = [] if why else carry(conn, row, text, agent)
            to_run = str(asked["asked_by_run"])
            if why is None and marked:  # the mark follows the answer
                conn.execute("update runs set read_outside = true where id = %s", (to_run,))
            for source, said in carried:  # what it found, as found, and outside as outside
                provenance.read(conn, to_run, source, said, gw.scenario.record_pattern)
            ledger.append(conn, gw.entry(row, "message", "answer", Decision(True, ()), args={
                "question": question, "to_run": to_run, "chars": len(text),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                **({"problem": why} if why else {"carried": len(carried)})}))
            ledger.append(conn, {"kind": "tool", "action": asking.ASK, "run": to_run,
                                 "instance": asked["asker"], "decision": "record",
                                 "outcome": {"status": "error", "error": why[:200]} if why else
                                 {"status": "ok", "question": question, "marked": marked,
                                  "result_sha256": hashlib.sha256(text.encode()).hexdigest()}})
            # Its outcome is one of the figures' own (core/status.py): its words stay with
            # the question, for the run that asked.
            ended = ("done" if why is None else "model unavailable" if "model" in why
                     else "budget spent" if "budget" in why else "failed")
            conn.execute("update runs set closed_at = now(), outcome = %s where id = %s "
                         "and closed_at is null", (ended, row["run"]))
            ledger.append(conn, {"kind": "run", "action": "close", "run": row["run"],
                                 "instance": row["id"], "decision": "record", "outcome": ended})
        if why is not None:
            return {"error": f"the {agent} didn't answer: {why}"[:300]}
        result: dict[str, Any] = {"agent": agent, "answer": text}
        if marked:
            result["note"] = (f"The {agent} drew on content from outside, so this run has read "
                              "outside content now too, and works as one that has.")
        return {"result": result}

    def carry(conn: psycopg.Connection, row: dict, text: str, agent: str) -> list[tuple[str, str]]:
        """The values in an answer the run that gave it had read, from its tools and what a5s
        told it, but not from the question, which are the asker's own: each with where the
        run that asked takes it as from, outside staying outside."""
        pattern = gw.scenario.record_pattern
        reads = [(Value(r["kind"], r["text"], r["norm"]), r["source"]) for r in conn.execute(
            "select kind, text, norm, source from run_reads where run_id = %s", (row["run"],))]
        found: dict[str, list[str]] = {}
        for v in values.found(text, pattern):
            sources = {s for k, s in reads if v.matches(k) and s != asking.QUESTION}
            if sources:
                outside = all(s.startswith(provenance.OUTSIDE) for s in sources)
                found.setdefault(f"{provenance.OUTSIDE} via the {agent}" if outside
                                 else f"the {agent}'s answer", []).append(v.text)
        return [(source, " ".join(said)) for source, said in found.items()]

    def call_core_tool(core: coretools.CoreTool, args: dict, row: dict, seq: int) -> Any:
        """One of a5s's own tools, in one transaction with what it changes. A rule of a5s's
        it would break is a denial, in words the agent passes on."""
        try:
            with db.transaction(gw.url) as conn:
                result = core.run(coretools.Call(conn, row, args, gw.clock(), gw.scenario,
                                                 gw.definitions.get(row["definition"])))
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
            with db.transaction(gw.url) as conn:  # the records it names, as for the scenario's
                studio.handled(conn, row["run"], studio.named(gw.scenario, core.sourced(result)))
        return {"result": result, "recorded": recorded}

    @app.post("/run/messages")
    def send_message(body: Message, token: str = Depends(run_token)) -> Any:
        with traces.span("send_message") as current:
            return sending_message(body, token, current)

    def sending_message(body: Message, token: str, current: Any) -> Any:
        text, removed = sanitize(body.text, gw.scenario.record_links)

        def recipient(who: str) -> dict:
            person = gw.scenario.person(who)
            return {"uid": {"type": "Person", "id": who},
                    "attrs": {"in_audience": bool(person and person.in_audience)}, "parents": []}

        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            inbound = row["trigger"].get("inbound")
            # In a group chat, an answer goes to the chat, so to everyone in it, and it's kept
            # as the asker's, such as for their inbox, if the chat won't take it
            group = groups.of(body.to) and body.to == row["trigger"].get("conversation")
            owner = row["trigger"].get("sender") if group else body.to
            route = None
            if row["trigger"].get("kind") in OWN_RUNS:
                decision = Decision(False, ("a5s-runs-write-to-nobody",), explanations=(
                    "a5s's own runs, such as keeping a summary, write to nobody",))
            elif row["trigger"].get("kind") == tasking.KIND and conn.execute(
                    "select task_result ->> 'status' as said from runs where id = %s",
                    (row["run"],)).fetchone()["said"] not in ("done", "blocked"):
                decision = Decision(False, (tasking.HELD,), explanations=(
                    ("a task's run writes to its owner only once it's done or needs them, and "
                     "has said so with finish_task"),))
            elif row["trigger"].get("kind") == asking.KIND:
                decision = Decision(False, ("answers-go-to-the-asker",), explanations=(
                    ("a run that answers another agent's question writes to nobody: its answer "
                     "goes back to that agent"),))
            elif groups.of(row["trigger"].get("conversation")) and not group:
                decision = Decision(False, ("a-group-run-writes-to-the-group",), explanations=(
                    ("a run in a group chat writes only to the chat, so to everyone in it"),))
            elif not group and body.to not in row["acts_for"]:
                why = ("a run writes only to the people it acts for, such as whoever sent the "
                       "message it answers")
                decision = Decision(False, ("writes-to-whom-it-acts-for",), explanations=(why,))
            else:
                decisions = [gw.decide(row, "send_message", recipient(who), [])
                             for who in (row["acts_for"] if group else [body.to])]
                decision = next((d for d in decisions if not d.allowed), decisions[0])
                asked = gw.message_of(conn, inbound) if inbound else None
                if inbound and asked is None:  # gone meanwhile, such as erased
                    raise HTTPException(409, "the message this answers is gone: a5s answers "
                                             "nothing in its place")
                route = (dict(asked) if inbound  # an answer, where asked
                         else {"channel": "digest", "reply_to": {}} if gw.for_digest(conn, row)
                         else gw.at_once(conn, body.to, row["definition"],  # not what they
                                         count=decision.allowed  # asked to be reminded of then
                                         and row["trigger"].get("kind") != "reminder"))
            if group and route:  # so it goes only if nobody has joined since the run began
                route["members"] = list(row["acts_for"])
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
            shown, _ = sanitize(handles.resolved(conn, row["run"], said),  # what people read:
                                gw.scenario.record_links)  # the values, cleaned again, and
            shown += f"\n\n{note}" if note else ""  # a5s's own note, apart
            if decision.allowed and route["channel"] == "digest":  # it goes in their next digest
                digests.keep(conn, body.to, row["definition"], row["id"], row["run"], shown, gw.clock())
            elif decision.allowed and route["channel"] == "batch":  # it waits for their next batch
                urgent.hold(conn, body.to, row["definition"], row["id"], row["run"], shown, gw.clock())
            elif decision.allowed:  # in the chat, after this transaction, or in the inbox
                sending = outbound(conn, route, owner, shown, run=row["run"], instance=row["id"],
                                   agent=row["definition"], inbound=inbound)
        traces.note(current, **{"a5s.run.id": row["run"], "a5s.instance": row["id"],
                                "a5s.channel": route["channel"] if route else None,
                                "a5s.decision": decision.label})
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        kept = False
        if route["channel"] not in ("digest", "batch"):
            push([sending])  # a chat that doesn't take it now gets it again, later
            if group and sending is not None:  # someone joined: it went to the asker alone,
                with db.transaction(gw.url) as conn:  # no longer answering the chat's message
                    kept = bool(conn.execute("select 1 from outbox where id = %s and "
                                             "inbound_id is null", (sending,)).fetchone())
        # As the agent wrote it, with its handles, for the conversation a later run reads, and
        # a5s's note apart, so no run takes a5s's words for the agent's, or learns to imitate them
        return {"sent": True, "text": said, "note": note, "links_removed": removed,
                **({"kept_back": True} if kept else {})}

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
              topic: str | None, heard_by: list[str] | None = None) -> None:
        """a5s's own words to someone, in their conversation with the agent whose chat they
        go in, so the agent's next run knows what the person is answering: or in a group
        chat's conversation, as heard by everyone in it then, though not sent there."""
        if agent:
            conn.execute("insert into turns (person, agent, topic, role, content, heard_by) "
                         "values (%s, %s, %s, 'notice', %s, %s)",
                         (person, agent, topic or topics.GENERAL, text, heard_by))

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
        later: list[int | None] = []
        for row in sorted(rows, key=lambda r: r["id"]):  # in the order a5s wrote them
            run = str(row["run_id"]) if row["run_id"] else None
            expected = (row["route"] or {}).get("members")  # a group's answer: for whom it was
            now_in = present(row["route"]) if expected is not None else None  # worked out
            if now_in is not None and not set(now_in) <= set(expected):
                later += kept_back(row, run, now_in)
                continue
            problem = ("a5s couldn't read who's in the chat" if expected is not None
                       and now_in is None else deliver(row["route"], row["text"], run,
                                                       row["instance_id"], card=row["card"]))
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
        if [i for i in later if i is not None]:  # an answer kept back, where it goes instead,
            push(later)  # and the notice of it in the chat

    def present(route: dict) -> list[str | None] | None:
        """Who's in a group chat now, by their ids in the directory, None for anyone it doesn't
        know: or None if the chat can't say."""
        chat, reply_to = gw.chat(route["channel"]), route.get("reply_to") or {}
        try:
            if route["channel"] == "matrix" and chat is not None:
                joined = chat.members(reply_to["room"], reply_to["bot"])
                return None if joined is None else [
                    p.id if (p := chat.person_of(u, gw.scenario)) else None
                    for u in joined if not chat.agent_of(u)]
            if route["channel"] == "teams" and chat is not None:
                return chat.members(reply_to, gw.scenario)
        except (httpx.HTTPError, ValueError, KeyError):
            log.warning("couldn't read who's in a %s chat", route["channel"])
        return None

    def kept_back(row: dict, run: str | None, now_in: list[str | None]) -> list[int | None]:
        """An answer for a group chat someone joined while its run was answering: it was worked
        out for the people there then, so it goes to whoever asked alone, in a chat of their own
        where a5s can reach them, or else their inbox, and the group's conversation keeps it as
        theirs alone. The chat hears why, and where it went, as a5s's own notice, kept and tried
        again like any message. What to push."""
        route = {k: v for k, v in row["route"].items() if k != "members"}
        with db.transaction(gw.url) as conn:
            to = gw.reach(conn, row["person"], row["agent"])  # theirs alone, never the group
            pushed = to["channel"] in PUSHED
            conn.execute("update outbox set channel = %s, route = %s, inbound_id = null, "
                         "retry_at = null, attempts = 0, problem = 'someone joined the chat "
                         "while it was answering' where id = %s",
                         (to["channel"], Jsonb(to) if pushed else None, row["id"]))
            asked = conn.execute("select trigger from runs where id = %s",
                                 (run,)).fetchone() if run else None
            group = (asked["trigger"] or {}).get("conversation") if asked else None
            if groups.of(group):  # whoever asked heard it, alone
                conn.execute("update turns set heard_by = %s where person = %s and run_id = %s "
                             "and role in ('agent', 'notice')", ([row["person"]], group, run))
            told = groups.JOINED.format(
                where="it's in a chat of their own with me" if pushed
                else f"they can read it in the web chat, at {gw.public_url}/chat/")
            if groups.of(group):
                noted(conn, group, row["agent"], told, (asked["trigger"] or {}).get("topic"),
                      heard_by=sorted(p for p in now_in if p))
            notice = outbound(conn, route, row["person"], told, run=run,
                              instance=row["instance_id"], agent=row["agent"])
            ledger.append(conn, {"kind": "message", "action": "kept back", "run": run,
                                 "instance": row["instance_id"], "acts_for": [row["person"]],
                                 "decision": "record", "args": {"outbox": row["id"],
                                                                "to": to["channel"]},
                                 "outcome": {"status": "kept back",
                                             "why": "someone joined the chat while it was answering"}})
        return [row["id"] if pushed else None, notice]

    @app.post("/proposals/sweep", dependencies=[Depends(service)])
    def sweep_proposals() -> dict:
        """Make the held changes their deciders approved, and tell whoever each was for what
        became of it: made, rejected, lapsed, or not made since its records changed or the
        instance may no longer act. Remind each decider once, in their own hours, after two
        working days, and tell their managers, or the instance's owner, after five. Only the
        changes with something due are read, each on its own, so one that fails holds up
        none of the others, and each approved change is made as soon as it's marked."""
        now, made, failed = gw.clock(), 0, 0
        with db.transaction(gw.url) as conn:  # what the channels app recorded, sealed first
            gw.seal_pending(conn)
        with db.transaction(gw.url) as conn:
            due = [r["id"] for r in conn.execute(
                "select id from proposals p where scenario = %s and status = 'waiting' and ("
                "least(remind_at, escalate_at, lapses_at) <= %s or exists (select 1 from "
                "proposal_decisions d where d.digest = p.digest and d.id > p.weighed)) order by id",
                (gw.scenario.name, now))]
        for pid in due:
            try:
                going = sweeping(pid, now)
                push(going.get("sends", []))
                if going.get("make"):
                    push(making(*going["make"]))
                    made += 1
            except Exception:  # one change's failure holds up no other
                log.exception("couldn't sweep P-%s", pid)
                failed += 1
        return {"swept": True, "made": made, "failed": failed}

    def sweeping(pid: int, now: datetime) -> dict:
        """What's due for one held change, in a transaction of its own."""
        with db.transaction(gw.url) as conn:
            p = conn.execute("select * from proposals where id = %s and status = 'waiting' "
                             "for update skip locked", (pid,)).fetchone()
            if p is None:
                return {}
            found, problems = proposals.decision(conn, gw.cfg.seal_keys, gw.scenario, p)
            last = conn.execute(  # up to the first decision still to be sealed, which, once it
                # is, makes the change due again
                "select coalesce(min(id) filter (where seal is null and refused is null and proof "
                "is not null) - 1, max(id), 0) as id from proposal_decisions where digest = %s",
                (p["digest"],)).fetchone()["id"]
            if last > p["weighed"]:
                for problem in problems:  # a decision that doesn't count, such as an unsealed one
                    log.warning("%s: %s", proposals.key(p), problem)
            if found is not None and found["decision"] == "approve":
                if (settled := gw.settings_in_force(conn))[0] is None:
                    log.warning("%s waits, since the settings in force don't check out: %s",
                                proposals.key(p), settled[1])
                    return {}  # it's made once they do: nothing's weighed yet
                ready = max(proposals.effective(gw.scenario.person(r["person"]), r["decided_at"])
                            for r in found["rows"])
                if now < ready:
                    return {}  # an authenticator was reset lately: the approval waits a day
            conn.execute("update proposals set weighed = %s where id = %s", (last, p["id"]))
            if found is not None:
                return deciding(conn, p, found, now)
            if now >= p["lapses_at"]:
                return ended(conn, p, "lapsed", [], now)
            return chasing(conn, p, now)

    def deciding(conn: psycopg.Connection, p: dict, found: dict, now: datetime) -> dict:
        """What becomes of a held change once the people who may decide it have: whether it's
        made. An approved one is marked as making, so it's never made twice."""
        rows = found["rows"]
        if found["decision"] == "reject":
            return ended(conn, p, "rejected", rows, now, reason=rows[0].get("reason"))
        if changed := proposals.changed(gw.scenario, p):
            return ended(conn, p, "changed", rows, now, ", ".join(changed))
        if (why := allowed_now(conn, p)) is not None:
            return ended(conn, p, "refused", rows, now, why)
        by = [r["person"] for r in rows]
        conn.execute("update proposals set status = 'making', decided_by = %s, decided_at = %s "
                     "where id = %s", (", ".join(by), max(r["decided_at"] for r in rows), p["id"]))
        ledger.append(conn, {"kind": "proposal", "action": "decide", "run": str(p["run_id"]),
                             "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                             "decision": "allow", "of": p["seq"],
                             "args": {"proposal": proposals.key(p), "by": by,
                                      "decided": "approve", "decisions": [r["id"] for r in rows]}})
        return {"make": (p, proposals.values(conn, p), rows)}

    def allowed_now(conn: psycopg.Connection, p: dict) -> str | None:
        """Why an approved change can't be made now, if it can't: the instance may no longer
        act, the tool has changed since, or policy would deny the call."""
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
                             **parts.about(gw.scenario, row, list(p["records"]), tool.action,
                                           gw.approvers_in_force(conn), gw.caps(conn, row["release"])))
        if not (decision.allowed or decision.held):
            return "; ".join(decision.explanations) or "policy denies it now"
        return None

    def making(p: dict, values: dict, rows: list[dict]) -> list:
        """Make an approved change, record what happened in a transaction of its own, then
        tell people. It's marked as making first, so it's never made twice: if a5s stops part
        way, it stays marked, for someone to see (`a5s proposals`)."""
        tool = gw.scenario.tools()[p["tool"]]
        try:
            result = tool.run(ToolCall(args=proposals.resolved(p["args"], values),
                                       instance=p["instance_id"], run=str(p["run_id"]),
                                       acts_for=tuple(p["acts_for"]),
                                       key=counts.key(str(p["run_id"]), p["change"] or p["digest"])))
            failed = result.get("error") if isinstance(result, dict) else None
            outcome = ({"status": "error", "error": str(failed)[:200]} if failed
                       else {"status": "ok", "result_sha256": ledger.digest(result)})
        except Exception as exc:  # noqa: BLE001 - the system's own failure, recorded and told
            outcome = {"status": "error", "error": f"{type(exc).__name__}"}
        with db.transaction(gw.url) as conn:  # what happened, first, whatever comes after
            ledger.append(conn, {"kind": "tool", "action": p["tool"], "run": str(p["run_id"]),
                                 "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                                 "decision": "record", "of": p["seq"], "outcome": outcome,
                                 "args": {"proposal": proposals.key(p)}})
            conn.execute("update proposals set status = %s, ended_at = %s where id = %s",
                         ("made" if outcome["status"] == "ok" else "not made", gw.clock(), p["id"]))
        with db.transaction(gw.url) as conn:
            if outcome["status"] == "ok":
                going = ended(conn, p, "made", rows, gw.clock())
            else:
                going = ended(conn, p, "failed", rows, gw.clock(), outcome["error"])
        return going["sends"]

    def ended(conn: psycopg.Connection, p: dict, became: str, rows: list[dict],
              now: datetime, extra: str = "", reason: str | None = None) -> dict:
        """End a held change, let go of the values it kept, and tell whoever it was for, in the
        conversation with its agent, so its next run knows too, and, in their digest, everyone
        who decided it. Its records as they stood when it was asked for go to graders."""
        deciders_ = [r["person"] for r in rows]
        names = approvals.names_of([who.name if (who := gw.scenario.person(d)) else d
                                    for d in deciders_]) if deciders_ else None
        text = proposals.told(p, became, names, extra, reason)
        conn.execute("update proposals set status = %s, decided_by = coalesce(decided_by, %s), "
                     "ended_at = %s, outcome = %s where id = %s",
                     ("made" if became == "made" else "not made" if became in (
                         "changed", "refused", "failed") else became,
                      ", ".join(deciders_) or None, now, text, p["id"]))
        conn.execute("delete from proposal_values where proposal_id = %s", (p["id"],))
        if became != "lapsed":  # someone decided it: a sample of the agent's work, for grading
            for part in p["parts"]:
                samples.draw(conn, gw.cfg.seal_keys, gw.scenario.name, "proposal", p["release"],
                             p["definition"],
                             p["instance_id"], str(p["run_id"]), part, p["action"], p["said"],
                             p["standing"] or {r: None for r in p["records"]},
                             list(p["acts_for"]), now, proposal=p["id"],
                             decided="reject" if became == "rejected" else "approve",
                             decided_by=deciders_[0] if deciders_ else None, flags=p["flags"])
        ledger.append(conn, {"kind": "proposal", "action": became, "run": str(p["run_id"]),
                             "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                             "decision": "record", "of": p["seq"],
                             "args": {"proposal": proposals.key(p), "by": deciders_}})
        asked = conn.execute("select trigger, acts_for from runs where id = %s",
                             (p["run_id"],)).fetchone()
        group = asked["trigger"].get("conversation") if asked and groups.of(
            asked["trigger"].get("conversation")) else None
        told_to = [asked["trigger"]["sender"]] if group and asked["trigger"].get("sender") \
            else list(p["acts_for"])  # in a group chat, whoever asked: a5s never writes there first
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
        if group:  # and the group's next run knows, as everyone there then heard it asked
            noted(conn, group, p["definition"], text, next(iter(p["records"]), None),
                  heard_by=list(asked["acts_for"]))
        for person in dict.fromkeys(deciders_):  # and those who decided it, in their digest
            if person not in told_to:
                digests.keep(conn, person, p["definition"], p["instance_id"], str(p["run_id"]),
                             f"What became of {proposals.key(p)}, which you decided: {text}",
                             now)
        return {"sends": sends}

    def chasing(conn: psycopg.Connection, p: dict, now: datetime) -> dict:
        """Remind each of a held change's deciders once, in their own working hours, after
        two working days. After five, and only once they've been reminded, tell their
        managers, each in their own hours, or the instance's owner if nobody is above them:
        they can see what waits, and nudge, but only its deciders decide it."""
        later = now + timedelta(hours=1)  # when to look again for someone off shift
        by_part = proposals.deciders(gw.scenario, list(p["records"]), list(p["acts_for"]))
        current = proposals.everyone(by_part)
        sends: list = []
        if p["remind_at"] is not None and now >= p["remind_at"]:
            due = [d for d in current if d.id not in p["reminded"]]
            working = [d for d in due if obligations.working(d, now)]
            for d in working:
                sends.append(ask(conn, p, d.id, again=True))
            reminded = [*p["reminded"], *(d.id for d in working)]
            conn.execute("update proposals set reminded = %s, remind_at = %s where id = %s",
                         (reminded, later if len(working) < len(due) else None, p["id"]))
            if working:
                ledger.append(conn, {"kind": "proposal", "action": "remind",
                                     "run": str(p["run_id"]), "instance": p["instance_id"],
                                     "acts_for": list(p["acts_for"]), "decision": "record",
                                     "of": p["seq"], "args": {"proposal": proposals.key(p),
                                                              "to": [d.id for d in working]}})
            p = {**p, "reminded": reminded}
        if p["escalate_at"] is not None and now >= p["escalate_at"] and (p["reminded"] or not current):
            above: dict[str, Person] = {}  # each decider's manager, who may hear of the record
            for decider in current:
                boss = gw.scenario.person(decider.manager) if decider.manager else None
                if (boss is not None and boss.in_audience and boss.id not in p["acts_for"]
                        and all(gw.scenario.sees(boss.id, r) for r in p["records"])):
                    above.setdefault(boss.id, boss)
            if not above:  # nobody above them: the instance's owner hears instead
                inst = conn.execute("select owner from instances where id = %s",
                                    (p["instance_id"],)).fetchone()
                owner = gw.scenario.person(inst["owner"]) if inst and inst["owner"] else None
                if owner is not None and all(gw.scenario.sees(owner.id, r) for r in p["records"]):
                    above[owner.id] = owner
            due = [b for b in above.values() if b.id not in (p["escalated"] or [])]
            working = [b for b in due if obligations.working(b, now)]
            names = approvals.names_of([d.name for d in current]) or "its deciders"
            for boss in working:
                text = (f"{proposals.key(p)} has waited {proposals.ESCALATE} working days for "
                        f"{names} to decide it.\n{p['said']}\nIt lapses on "
                        f"{obligations.day(boss, p['lapses_at'])} unless one of them decides it, "
                        f"on a5s's page. You can see it there, though only they decide it: "
                        f"{gw.public_url}/decide/?proposal={p['digest']}")
                route = gw.at_once(conn, boss.id, p["definition"])
                if route["channel"] == "batch":
                    urgent.hold(conn, boss.id, None, p["instance_id"], None, text, now)
                else:
                    sends.append(outbound(conn, route, boss.id, text, instance=p["instance_id"],
                                          agent=p["definition"]))
            escalated = [*(p["escalated"] or []), *(b.id for b in working)]
            conn.execute("update proposals set escalated = %s, escalated_at = coalesce("
                         "escalated_at, %s), escalate_at = %s where id = %s",
                         (escalated, now if working else None,
                          later if len(working) < len(due) else None, p["id"]))
            if working:
                ledger.append(conn, {"kind": "proposal", "action": "escalate",
                                     "run": str(p["run_id"]), "instance": p["instance_id"],
                                     "acts_for": list(p["acts_for"]), "decision": "record",
                                     "of": p["seq"], "args": {"proposal": proposals.key(p),
                                                              "to": [b.id for b in working]}})
        elif p["escalate_at"] is not None and now >= p["escalate_at"]:
            conn.execute("update proposals set escalate_at = %s where id = %s", (later, p["id"]))
        return {"sends": sends}


    @app.post("/samples/sweep", dependencies=[Depends(service)])
    def sweep_samples() -> dict:
        """Weigh the sealed grades of each behaviour's samples, for each part and type of
        action, and raise or lower a5s's cap where they now show it should (core/samples.py),
        telling the owners of the instances it governs. Samples nobody graded in a quarter
        lapse. While the settings in force don't check out, nothing is weighed."""
        changed, now = [], gw.clock()
        if not gw.cfg.seal_keys:  # a cap counts only as the core sealed it
            return {"changed": [], "weighed": "nothing, since the core has no key to seal caps"}
        with db.transaction(gw.url) as conn:
            if not conn.execute("select pg_try_advisory_xact_lock(hashtext('a5s samples')) as got"
                                ).fetchone()["got"]:
                return {"changed": []}  # another sweep is at work
            gw.seal_pending(conn)  # the grades the channels app recorded, sealed first
            lapsed = samples.lapse(conn, now)
            settings, problem = gw.settings_in_force(conn)
            if settings is None:
                return {"changed": [], "lapsed": lapsed, "weighed": f"nothing, since {problem}"}
            for row in conn.execute(
                    "select distinct b.behaviour, s.part, s.action from samples s join behaviours b "
                    "on b.release = s.release and b.action = s.action where s.grade is not null"
                    ).fetchall():
                found = samples.assess(conn, gw.cfg.seal_keys, row["behaviour"], row["part"],
                                       row["action"], settings.thresholds.get(row["part"]), now)
                if found:
                    changed.append(found)
                    capped(conn, found, now)
        return {"changed": changed, "lapsed": lapsed}

    def capped(conn: psycopg.Connection, found: dict, now: datetime) -> None:
        """Tell the owners and deputies of the instances a cap governs that it changed, in
        their digest."""
        rows = conn.execute(
            "select i.id, i.definition, i.owner, i.deputy from instances i join behaviours b on "
            "b.release = i.release where b.behaviour = %s and b.action = %s and i.status = 'active'",
            (found["behaviour"], found["action"])).fetchall()
        for inst in rows:
            text = (f"a5s's cap on {inst['id']} for {found['action']} in {found['part']} is now "
                    f"{found['cap']}: {found['why']}" + (
                        f", on {found['graded']} grades, {found['errors']} of them wrong."
                        if "graded" in found else "."))
            for person in dict.fromkeys(p for p in (inst["owner"], inst["deputy"]) if p):
                digests.keep(conn, person, inst["definition"], inst["id"], None, text, now)

    @app.get("/proposals", dependencies=[Depends(service)])
    def list_proposals() -> dict:
        """The held changes that wait, or that a5s stopped part way through making, for the
        team that runs it: what each does, whom it's for, and since when."""
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select * from proposals where scenario = %s and status in "
                                "('waiting', 'making') order by id", (gw.scenario.name,)).fetchall()
        return {"proposals": [{"key": proposals.key(r), "status": r["status"],
                               "proposed_at": r["proposed_at"].isoformat(),
                               "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
                               "for": list(r["acts_for"]), "change": proposals.first(r)}
                              for r in rows]}

    @app.post("/proposals/{key}/end", dependencies=[Depends(service)])
    def end_proposal(key: str, body: StatusChange) -> dict:
        """End a held change a5s stopped part way through making, at the word of someone who
        may, once they've checked the records system for it: the instance's owner or deputy,
        an owner of a part it touches, an instance approver, or assurance. Whoever it was for
        is told."""
        by, identity = who_asks(body)
        number = key.removeprefix("P-")
        with db.transaction(gw.url) as conn:
            p = conn.execute("select * from proposals where id = %s and scenario = %s for update",
                             (int(number) if number.isdigit() else -1, gw.scenario.name)).fetchone()
            if p is None or p["status"] != "making":
                raise HTTPException(409, f"{key} isn't a change a5s stopped part way through making")
            inst = conn.execute("select owner, deputy from instances where id = %s",
                                (p["instance_id"],)).fetchone()
            person = gw.scenario.person(by)
            may = {*(f"{PART_OWNER}:{part}" for part in p["parts"]), INSTANCE_APPROVER, ASSURANCE}
            minders = (inst["owner"], inst["deputy"]) if inst else ()
            if person is None or not (may & set(person.roles) or by in minders):
                raise HTTPException(403, f"{by} may not end {key}")
            going = ended(conn, p, "stopped", [{"person": by}], gw.clock())
            ledger.append(conn, {"kind": "admin", "action": "end-change", "run": str(p["run_id"]),
                                 "instance": p["instance_id"], "acts_for": list(p["acts_for"]),
                                 "decision": "record", "args": {"proposal": key, "by": by,
                                                                "identity": identity}})
        push(going["sends"])
        return {"ended": key, "by": by}

    @app.post("/caps/lower", dependencies=[Depends(service)])
    def lower_cap(body: CapChange) -> dict:
        """Lower an agent's cap for a type of action in a part to 1, at the word of someone who
        may: the part's owners, the instance approvers, the agent's owners, or assurance.
        Anyone with the role makes a5s safer alone; only graded samples raise a cap."""
        by, identity = who_asks(body)
        person = gw.scenario.person(by)
        may = {f"{PART_OWNER}:{body.part}", INSTANCE_APPROVER, f"agent-owner:{body.agent}",
               ASSURANCE}
        if person is None or not may & set(person.roles):
            raise HTTPException(403, f"{by} may not lower the {body.agent}'s cap in {body.part}")
        definition = gw.definitions.get(body.agent)
        if definition is None:
            raise HTTPException(404, f"no release here has an agent called {body.agent}")
        if not gw.cfg.seal_keys:
            raise HTTPException(503, "the core has no key to seal caps with: see A5S_SEAL_KEYS")
        with db.transaction(gw.url) as conn:
            found = samples.lower(conn, gw.cfg.seal_keys, definition.release_id, body.part,
                                  body.action, by, gw.clock())
            if found:
                found["identity"] = identity
                capped(conn, found, gw.clock())
        return {"lowered": bool(found), "cap": 1}

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
                "returning person, agent, channel, reply_to, members", (inbound,)).fetchone()
            if row is not None:
                ledger.append(conn, {"kind": "notice", "action": "send", "run": None,
                                     "instance": body.instance,
                                     "acts_for": list(row["members"] or [row["person"]]),
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
                row["trigger"].get("kind"), row["tokens"], gw.clock(), row["trigger"])
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
                                                gw.clock(), data.get("usage"), alias):
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
