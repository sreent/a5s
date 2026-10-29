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
from a5s.core.policy import Decision, PolicyEngine
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

    @property
    def url(self) -> str:
        return self.cfg.database_url

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
        token = secrets.token_urlsafe(32)
        run_id = str(uuid.uuid4())
        with db.transaction(gw.url) as conn:
            inst = conn.execute("select * from instances where id = %s", (body.instance,)).fetchone()
            if inst is None:
                raise HTTPException(404, f"no instance {body.instance}")
            reasons = []
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
                    (run_id, body.instance, token_hash(token), Jsonb(body.trigger), acts_for),
                )
            ledger.append(conn, {
                "kind": "run", "action": "open", "run": None if reasons else run_id,
                "instance": body.instance, "acts_for": acts_for,
                "decision": "deny" if reasons else "allow", "reasons": reasons,
                "args": {"trigger": body.trigger.get("kind"), "channel": body.trigger.get("channel")},
            })
        if reasons:
            raise HTTPException(409, {"reasons": reasons, "status": inst["status"], "owner": inst["owner"]})
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
            decision = gw.decide(row, "send_message", recipient, [])
            ledger.append(conn, gw.entry(row, "message", "send", decision, args={
                "to": body.to, "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "links_removed": removed,
            }))
            if decision.allowed:
                conn.execute(
                    "insert into outbox (run_id, instance_id, person, channel, text) "
                    "values (%s, %s, %s, %s, %s)",
                    (row["run"], row["id"], body.to, row["trigger"].get("channel", "local"), text),
                )
        if not decision.allowed:
            return JSONResponse(status_code=403,
                                content={"denied": True, **decision.as_dict(explain=True)})
        return {"sent": True, "text": text, "links_removed": removed}

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
