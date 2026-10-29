"""The gateway: every tool call, model call and outgoing message passes through here.

For each call, in one Postgres transaction, it reads the run's envelope, asks
policy, and writes the ledger. Only then does it make the call. Workers hold
only a run token. Provider keys and tool implementations stay on this side.

It also opens and closes runs, for the scheduler: to answer a message, to
remind someone of an obligation, or to work on a schedule. And it works out
what falls due, escalating overdue obligations itself.
"""

from __future__ import annotations

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
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.config import Config, ModelConfig
from a5s.contract import Scenario, Signature, Tool, ToolCall, parse_settings
from a5s.core import ledger, models, obligations, registry, releases, schedules
from a5s.core.identity import IdentityError, UnknownPerson, Verifier, signed_in
from a5s.core.policy import Decision, PolicyEngine
from a5s.core.teams import Teams
from a5s.definitions import Definition

log = logging.getLogger(__name__)
RUN_MINUTES = 60  # the longest a run may last [TBC]; its token dies with it
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
        if not registry.signers(settings, self.scenario.person)[0]:
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
        expected = (signed.definition, sorted(signed.serves), level, sorted(release.tool_names),
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

    @staticmethod
    def reach(conn: psycopg.Connection, person: str, agent: str | None) -> dict:
        """How to write to someone who isn't waiting for an answer: in the conversation they
        last wrote in, to this agent if they have. Otherwise they collect it from the local
        channel's inbox."""
        row = conn.execute("select channel, reply_to from inbound where person = %s "
                           "order by (agent = %s) desc nulls last, received_at desc limit 1",
                           (person, agent)).fetchone()
        if row is None or row["channel"] != "teams":
            return {"channel": "local", "reply_to": {}}
        return {"channel": "teams",  # a new message in that conversation, not a reply to one
                "reply_to": {k: v for k, v in row["reply_to"].items() if k != "activity"}}

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
        if person is None or not obligations.working(person, now):
            opening.reasons.append(f"it's outside {row['person']}'s working hours")
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
    due: datetime | None = None  # the time a schedule fires for


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
    # or {"kind": "schedule", "schedule": <name>}
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
        opens = {"message": gw.answering, "obligation": gw.reminding, "schedule": gw.scheduled}
        if kind not in opens:
            raise HTTPException(400, "a run answers a message, reminds someone of an obligation, "
                                     "or works on a schedule")
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
            if opening.due and not opening.used:  # a schedule fires once for each time, run or not
                fired = conn.execute(
                    "insert into schedule_fires (instance_id, schedule, due_at, fired_at, run_id, "
                    "outcome) values (%s, %s, %s, %s, %s, %s) on conflict do nothing returning 1",
                    (body.instance, opening.trigger["schedule"], opening.due, now,
                     None if reasons else run_id, "; ".join(reasons) or "run")).fetchone()
                if fired is None:
                    reasons.append(f"{opening.trigger['schedule']} has fired already")
                    opening.used = True
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
            runs = not gw.release_problems(conn)  # else no agent can act, and code escalates
            able = {iid: runs and inst["status"] == "active" and not gw.check_instance(conn, inst)
                    for iid, inst in instances.items()}
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
                if route["channel"] == "teams":
                    sends.append((route["reply_to"], text, row["instance_id"]))
                else:  # people collect it from the local channel's inbox
                    conn.execute("insert into outbox (instance_id, agent, person, channel, text) "
                                 "values (%s, %s, %s, 'local', %s)",
                                 (row["instance_id"], row["agent"], to.id, text))
                escalated.add(row["id"])
            due = [d for d in obligations.to_chase(rows, gw.scenario, now, able)
                   if d["obligation"] not in escalated]
        for reply_to, text, instance in sends:
            deliver(reply_to, text, None, instance)
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
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
        definition = gw.definitions.get(row["definition"])
        if definition is None or definition.release_id != row["release"]:
            raise HTTPException(409, f"release {row['release']} isn't loaded in this gateway")
        model = gw.models.get(row["model"])
        tools = gw.scenario.tools()
        return {
            "run": row["run"],
            "instance": row["id"],
            "acts_for": list(row["acts_for"]),
            "instructions": definition.instructions,
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
        tool = gw.scenario.tools().get(name)
        args, removed = dict(body.args), 0
        for field_name in tool.text_fields if tool else ():
            if isinstance(args.get(field_name), str):
                args[field_name], dropped = sanitize(args[field_name], gw.scenario.record_links)
                removed += dropped
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            decision = gw.decide(row, "call_tool", gw.tool_entity(name, tool, row["pins"]), [])
            seq = ledger.append(conn, gw.entry(row, "tool", name, decision, args=ledger.mask(args),
                                               links_removed=removed))
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
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
                         else gw.reach(conn, body.to, row["definition"]))
            ledger.append(conn, gw.entry(row, "message", "send", decision, args={
                "to": body.to, "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "links_removed": removed,
            }))
            if decision.allowed and route["channel"] != "teams":  # people collect it from here
                conn.execute(
                    "insert into outbox (run_id, instance_id, agent, inbound_id, person, channel, "
                    "text) values (%s, %s, %s, %s, %s, %s, %s)",
                    (row["run"], row["id"], row["definition"], inbound, body.to, route["channel"],
                     text))
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if route["channel"] == "teams":
            problem = deliver(route["reply_to"], text, row["run"], row["id"])
            if problem:
                return JSONResponse(status_code=502, content={"error": problem})
        return {"sent": True, "text": text, "links_removed": removed}

    def deliver(reply_to: dict, text: str, run: str | None, instance: str | None) -> str | None:
        """Send text to Teams, and record whether it got there. The problem, if not."""
        problem = None
        if gw.teams is None:
            problem = "Teams isn't set up in this gateway"
        else:
            try:
                gw.teams.send(reply_to, text)
            except (httpx.HTTPError, ValueError) as exc:
                problem = f"Teams didn't take it: {type(exc).__name__}: {exc}"[:200]
        record({"kind": "message", "action": "deliver", "run": run, "instance": instance,
                "decision": "record", "outcome": {"status": "error", "error": problem} if problem
                else {"status": "ok", "channel": "teams"}})
        return problem

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
                if row["channel"] != "teams":
                    conn.execute(
                        "insert into outbox (instance_id, agent, inbound_id, person, channel, text) "
                        "values (%s, %s, %s, %s, %s, %s)",
                        (body.instance, row["agent"], inbound, row["person"], row["channel"], text))
        if row is None:
            raise HTTPException(403, "a5s only answers a message someone sent, and briefly")
        if row["channel"] == "teams":
            problem = deliver(row["reply_to"], text, None, body.instance)
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
