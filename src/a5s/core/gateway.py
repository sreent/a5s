"""The gateway: every tool call, model call and outgoing message passes through here.

For each call, in one Postgres transaction, it reads the run's envelope, asks
policy, and writes the ledger. Only then does it make the call. Workers hold
only a run token. Provider keys and tool implementations stay on this side.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from a5s import db
from a5s.config import Config, ModelConfig
from a5s.contract import Scenario, Tool, ToolCall
from a5s.core import ledger, models, registry
from a5s.core.identity import IdentityError, Verifier
from a5s.core.policy import Decision, PolicyEngine
from a5s.core.teams import Teams
from a5s.definitions import Definition

_LINK = re.compile(r"https?://[^\s)>\]]+")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def sanitize(text: str, allowed: tuple[str, ...]) -> tuple[str, int]:
    """Keep text and the scenario's own record links. Drop images and other links."""
    removed = 0

    def drop(match: re.Match) -> str:
        nonlocal removed
        if any(match.group(0).startswith(prefix) for prefix in allowed):
            return match.group(0)
        removed += 1
        return "[link removed]"

    without_images, images = _IMAGE.subn("[image removed]", text)
    return _LINK.sub(drop, without_images), removed + images


@dataclass
class Gateway:
    cfg: Config
    scenario: Scenario
    policy: PolicyEngine
    models: dict[str, ModelConfig]
    definitions: dict[str, Definition]
    http: httpx.Client
    identity: Verifier | None = None  # without one, senders go unverified: development only
    teams: Teams | None = None

    @property
    def url(self) -> str:
        return self.cfg.database_url

    def check_sender(self, conn: psycopg.Connection, trigger: dict) -> tuple[str, str | None]:
        """Whether a message's sender is who the scheduler says, and if not, why."""
        sender, token = trigger.get("sender"), trigger.get("identity")
        if sender is None:
            return "none", None
        if trigger.get("inbound") is not None:
            return self._check_inbound(conn, sender, trigger)
        if self.identity is None:
            return "unverified (development)", None
        if not token:
            return "missing", "the sender's identity wasn't given"
        try:
            person = self.identity.person(token)
        except IdentityError as exc:
            return "refused", f"the sender's identity doesn't check out: {exc}"
        if person != sender:
            return "refused", f"the identity is {person}'s, not {sender}'s"
        return "verified", None

    @staticmethod
    def _check_inbound(conn: psycopg.Connection, sender: str, trigger: dict) -> tuple[str, str | None]:
        """A message the core received itself, from a channel that signs them, answered once."""
        try:
            inbound = str(uuid.UUID(str(trigger["inbound"])))
        except ValueError:
            return "refused", "the message it answers isn't one the core received"
        taken = conn.execute(
            "update inbound set answered_at = now() where id = %s and person = %s and channel = %s "
            "and answered_at is null returning id",
            (inbound, sender, trigger.get("channel")),
        ).fetchone()
        if taken:
            return f"verified by {trigger.get('channel')}", None
        row = conn.execute("select person, answered_at from inbound where id = %s",
                           (inbound,)).fetchone()
        if row is None:
            return "refused", "the message it answers isn't one the core received"
        if row["person"] != sender:
            return "refused", f"the message it answers came from {row['person']}, not {sender}"
        return "refused", "the message it answers has been answered already"

    def reply_to(self, conn: psycopg.Connection, inbound: str | None) -> tuple[str, dict] | None:
        """Who wrote the message a run answers, and where answers to it go."""
        if inbound is None:
            return None
        row = conn.execute("select person, reply_to from inbound where id = %s", (inbound,)).fetchone()
        return (row["person"], row["reply_to"]) if row else None

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
            "policy": self.policy.version,
            "settings": row["settings_version"],
            **decision.as_dict(),
            **fields,
        }


def load_run(conn: psycopg.Connection, token: str) -> dict:
    row = conn.execute(
        """
        select r.id::text as run, r.acts_for, r.read_outside, r.trigger, i.*
        from runs r join instances i on i.id = r.instance_id
        where r.token_hash = %s and r.closed_at is null
        """,
        (token_hash(token),),
    ).fetchone()
    if row is None:
        raise HTTPException(401, "unknown or closed run")
    return row


class OpenRun(BaseModel):
    instance: str
    trigger: dict[str, Any]


class CloseRun(BaseModel):
    outcome: str


class StatusChange(BaseModel):
    by: str


class ToolArgs(BaseModel):
    args: dict[str, Any] = {}


class Explain(BaseModel):
    action: str
    name: str


class Message(BaseModel):
    to: str
    text: str


class Notice(BaseModel):
    person: str
    text: str
    inbound: str
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
        sender = body.trigger.get("sender")
        acts_for = [sender] if sender else []
        trigger = {k: v for k, v in body.trigger.items() if k != "identity"}  # never stored
        token = secrets.token_urlsafe(32)
        run_id = str(uuid.uuid4())
        with db.transaction(gw.url) as conn:
            inst = conn.execute("select * from instances where id = %s", (body.instance,)).fetchone()
            if inst is None:
                raise HTTPException(404, f"no instance {body.instance}")
            identity, problem = gw.check_sender(conn, body.trigger)
            reasons = [problem] if problem else []
            if inst["status"] != "active":
                reasons.append(f"{body.instance} is {inst['status']}")
            if any(p not in inst["serves"] for p in acts_for):
                reasons.append(f"{body.instance} doesn't serve {sender}")
            signed = conn.execute("select 1 from settings_versions where version = %s",
                                  (inst["settings_version"],)).fetchone()
            if signed is None:
                reasons.append(f"{body.instance}'s settings aren't a signed version")
            if not reasons:
                conn.execute(
                    "insert into runs (id, instance_id, token_hash, trigger, acts_for) "
                    "values (%s, %s, %s, %s, %s)",
                    (run_id, body.instance, token_hash(token), Jsonb(trigger), acts_for),
                )
            ledger.append(conn, {
                "kind": "run", "action": "open", "run": None if reasons else run_id,
                "instance": body.instance, "acts_for": acts_for,
                "decision": "deny" if reasons else "allow", "reasons": reasons,
                "args": {"trigger": trigger.get("kind"), "channel": trigger.get("channel"),
                         "identity": identity},
            })
        if reasons:
            raise HTTPException(409, {"reasons": reasons, "status": inst["status"],
                                      "owner": inst["owner"], "identity": identity})
        return {"run": run_id, "token": token}

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

    # Instances: anyone with the role can make a5s safer alone.

    @app.post("/instances/{instance}/suspend", dependencies=[Depends(service)])
    def suspend(instance: str, body: StatusChange) -> dict:
        with db.transaction(gw.url) as conn:
            problem = registry.set_status(conn, instance, by=body.by, suspend=True)
        if problem:
            raise HTTPException(404, problem)
        return {"suspended": instance}

    @app.post("/instances/{instance}/resume", dependencies=[Depends(service)])
    def resume(instance: str, body: StatusChange) -> dict:
        with db.transaction(gw.url) as conn:
            problem = registry.set_status(conn, instance, by=body.by, suspend=False)
        if problem:
            raise HTTPException(403, problem)
        return {"resumed": instance}

    @app.get("/ledger", dependencies=[Depends(service)])
    def read_ledger(run: str | None = None, limit: int = 100) -> list[dict]:
        with db.transaction(gw.url) as conn:
            return ledger.entries(conn, run=run, limit=limit)

    @app.get("/ledger/verify", dependencies=[Depends(service)])
    def verify_ledger() -> dict:
        with db.transaction(gw.url) as conn:
            result = ledger.verify(conn)
        return result.__dict__

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

    @app.post("/run/explain")
    def explain(body: Explain, token: str = Depends(run_token)) -> dict:
        """What policy would say about a call, without making it. Denials are recorded."""
        if body.action != "call_tool":
            raise HTTPException(400, "phase 1 explains tool calls only")
        tool = gw.scenario.tools().get(body.name)
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            decision = gw.decide(row, "call_tool", gw.tool_entity(body.name, tool, row["pins"]), [])
            if not decision.allowed:
                ledger.append(conn, gw.entry(row, "explain", body.name, decision))
        return decision.as_dict(explain=True)

    @app.post("/run/tools/{name}")
    def call_tool(name: str, body: ToolArgs, token: str = Depends(run_token)) -> Any:
        tool = gw.scenario.tools().get(name)
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            decision = gw.decide(row, "call_tool", gw.tool_entity(name, tool, row["pins"]), [])
            seq = ledger.append(conn, gw.entry(row, "tool", name, decision, args=ledger.mask(body.args)))
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        try:
            result = tool.run(ToolCall(args=body.args, instance=row["id"], run=row["run"],
                                       acts_for=tuple(row["acts_for"])))
            outcome = {"status": "ok", "result_sha256": ledger.digest(result)}
        except Exception as exc:  # noqa: BLE001 - the tool's own failure, recorded and reported
            result, outcome = None, {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:200]}
        with db.transaction(gw.url) as conn:
            ledger.append(conn, {"kind": "tool", "action": name, "run": row["run"],
                                 "instance": row["id"], "decision": "record", "of": seq,
                                 "outcome": outcome})
        if outcome["status"] != "ok":
            return JSONResponse(status_code=502, content={"error": outcome["error"]})
        return {"result": result}

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
            channel = row["trigger"].get("channel", "local")
            answers = gw.reply_to(conn, row["trigger"].get("inbound"))
            if channel == "teams" and (answers is None or answers[0] != body.to):
                why = "in Teams, a run writes only to the person whose message it answers"
                decision = Decision(False, ("teams-answers-the-sender",), explanations=(why,))
            else:
                decision = gw.decide(row, "send_message", recipient, [])
            ledger.append(conn, gw.entry(row, "message", "send", decision, args={
                "to": body.to, "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "links_removed": removed,
            }))
            if decision.allowed:
                outbox = conn.execute(
                    "insert into outbox (run_id, instance_id, person, channel, text) "
                    "values (%s, %s, %s, %s, %s) returning id",
                    (row["run"], row["id"], body.to, channel, text),
                ).fetchone()["id"]
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        if channel == "teams":
            problem = deliver(answers[1], text, outbox, row["run"], row["id"])
            if problem:
                return JSONResponse(status_code=502, content={"error": problem})
        return {"sent": True, "text": text, "links_removed": removed}

    def deliver(reply_to: dict, text: str, outbox: int | None, run: str | None,
                instance: str | None) -> str | None:
        """Send text to Teams, and record whether it got there. The problem, if not."""
        problem = None
        if gw.teams is None:
            problem = "Teams isn't set up in this gateway"
        else:
            try:
                gw.teams.send(reply_to, text)
            except (httpx.HTTPError, ValueError) as exc:
                problem = f"Teams didn't take it: {type(exc).__name__}: {exc}"[:200]
        with db.transaction(gw.url) as conn:
            if outbox is not None and problem is None:
                conn.execute("update outbox set delivered_at = now() where id = %s", (outbox,))
            ledger.append(conn, {"kind": "message", "action": "deliver", "run": run,
                                 "instance": instance, "decision": "record",
                                 "outcome": {"status": "error", "error": problem} if problem
                                 else {"status": "ok", "channel": "teams"}})
        return problem

    @app.post("/channels/teams/notices", dependencies=[Depends(service)])
    def notice(body: Notice) -> dict:
        """a5s's own words, such as "the assistant is suspended", only ever in answer to someone."""
        text, _ = sanitize(body.text, ())
        try:
            inbound = str(uuid.UUID(body.inbound))
        except ValueError:
            raise HTTPException(404, "no such message from Teams") from None
        with db.transaction(gw.url) as conn:
            row = conn.execute(
                "update inbound set notices = notices + 1 where id = %s and person = %s "
                "and notices < 3 returning reply_to", (inbound, body.person)).fetchone()
            if row is not None:
                ledger.append(conn, {"kind": "notice", "action": "send", "run": None,
                                     "instance": body.instance, "acts_for": [body.person],
                                     "decision": "allow", "args": {
                                         "inbound": inbound, "chars": len(text),
                                         "sha256": hashlib.sha256(text.encode()).hexdigest()}})
        if row is None:
            raise HTTPException(403, "a5s only answers a message from that person, and briefly")
        problem = deliver(row["reply_to"], text, None, None, body.instance)
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
        with db.transaction(gw.url) as conn:
            row = load_run(conn, token)
            decision = gw.decide(row, "call_model", approved, [])
            seq = ledger.append(conn, gw.entry(row, "model", alias, decision, args={
                "prompt_sha256": ledger.digest(prompt),
                "messages": len(body.get("messages") or []),
                "tools": len(body.get("tools") or []),
            }, provider=model.provider if model else None))
        if not decision.allowed:
            return JSONResponse(status_code=403, content=models.error_body(
                api, "denied by policy: " + "; ".join(decision.explanations)))
        try:
            status, data = models.forward(model, body, gw.http)
        except models.ModelUnavailable as exc:
            status, data = 503, models.error_body(api, str(exc), "model_unavailable")
        reported = data.get("model") if isinstance(data, dict) else None
        if status < 400 and model.reported_model and reported != model.reported_model:
            status, data = 502, models.error_body(
                api, f"the provider reported {reported}, not the approved {model.reported_model}",
                "model_mismatch")
        with db.transaction(gw.url) as conn:
            ledger.append(conn, {"kind": "model", "action": alias, "run": row["run"],
                                 "instance": row["id"], "decision": "record", "of": seq,
                                 "outcome": {"status": status, "reported_model": reported,
                                             "usage": data.get("usage") if isinstance(data, dict) else None}})
        return JSONResponse(status_code=status, content=data)

    @app.post("/v1/chat/completions")
    def openai_style(body: dict[str, Any], token: str = Depends(run_token)) -> JSONResponse:
        return model_call("openai", body, token)

    @app.post("/v1/messages")
    def anthropic_style(body: dict[str, Any], token: str = Depends(run_token)) -> JSONResponse:
        return model_call("anthropic", body, token)

    return app
