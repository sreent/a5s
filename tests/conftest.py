"""Test fixtures: a real Postgres, a real gateway, and a scripted model provider."""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
import psycopg
import pytest
import uvicorn
import yaml
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from a5s import db, definitions, devdb
from a5s.config import Config, load_models
from a5s.core import inbox, ledger, registry, signing
from a5s.core.gateway import Gateway, create_app
from a5s.core.identity import IdentityConfig, Verifier
from a5s.core.policy import PolicyEngine
from a5s.sample import SampleScenario
from a5s.services.scheduler import Scheduler

ROOT = Path(__file__).resolve().parents[1]
SERVICE_TOKEN = "test-service-token"
PROVIDER_KEY = "provider-secret"
# The core's clock in tests, unless a test sets it: before anything in the sample falls due,
# so a scheduler left running never reminds anyone, whatever the date really is.
QUIET = datetime(2026, 10, 28, 12, tzinfo=UTC)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = os.environ.get("A5S_TEST_DATABASE_URL")
    if url:
        yield url
        return
    folder = Path(tempfile.mkdtemp(prefix="a5s-pg-"))
    try:
        yield devdb.start(folder, free_port())
    finally:
        devdb.stop(folder)
        shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
def database(database_url: str) -> str:
    """A fresh database, migrated. The URL is its administrator's."""
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade")
        conn.execute("drop schema if exists sample cascade")
        conn.execute("create schema public")
    db.migrate(database_url)
    with db.transaction(database_url) as conn:
        SampleScenario(ROOT / "scenarios" / "sample", database_url).setup(conn, db.ROLES["gateway"])
    return database_url


@dataclass
class FakeModel:
    """An OpenAI-compatible provider that answers from a script and records what it's sent."""

    script: list[tuple[str | None, list[tuple[str, dict]]]] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    on_request: Callable[[int], None] | None = None
    reports: str | None = None  # the model it says answered, if not the one asked for; "" for none

    def reply(self, content: str | None = None, *tools: tuple[str, dict]) -> None:
        self.script.append((content, list(tools)))

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body})
        if self.on_request:
            self.on_request(len(self.requests))
        content, tools = self.script.pop(0) if self.script else ("(the script ran out)", [])
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tools:
            message["tool_calls"] = [
                {"id": f"call_{len(self.requests)}_{i}", "type": "function",
                 "function": {"name": name, "arguments": json.dumps(args)}}
                for i, (name, args) in enumerate(tools)
            ]
        reported = {} if self.reports == "" else {"model": self.reports or body["model"]}
        return httpx.Response(200, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 0, **reported,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if tools else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    def tool_names(self, request: int = 0) -> set[str]:
        return {t["function"]["name"] for t in self.requests[request]["body"].get("tools", [])}


class FakeIssuer:
    """An OpenID Connect provider that signs tokens, publishes its keys and can rotate them."""

    url = "https://id.test/realms/a5s"

    def __init__(self) -> None:
        self.keys: dict[str, rsa.RSAPrivateKey] = {}
        self.published: list[str] = []
        self.fetches = 0
        self.rotate()

    def rotate(self) -> str:
        kid = f"key-{len(self.keys) + 1}"
        self.keys[kid] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.published = [kid]
        return kid

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": self.url, "jwks_uri": f"{self.url}/certs"})
        if request.url.path.endswith("/certs"):
            self.fetches += 1
            keys = []
            for kid in self.published:
                jwk = RSAAlgorithm.to_jwk(self.keys[kid].public_key(), as_dict=True)
                keys.append({**jwk, "kid": kid, "use": "sig", "alg": "RS256"})
            return httpx.Response(200, json={"keys": keys})
        return httpx.Response(404)

    def token(self, person: str | None = "ana", *, kid: str | None = None, **claims: Any) -> str:
        now = int(time.time())
        body = {"iss": self.url, "aud": "a5s", "iat": now, "exp": now + 300,
                "preferred_username": person, **claims}
        kid = kid or self.published[-1]
        return jwt.encode({k: v for k, v in body.items() if v is not None}, self.keys[kid],
                          algorithm="RS256", headers={"kid": kid})

    def verifier(self, **kwargs: Any) -> Verifier:
        return Verifier(IdentityConfig(issuer=self.url, audience="a5s"),
                        httpx.Client(transport=httpx.MockTransport(self.handler)), **kwargs)


@contextmanager
def serve(app: Any, port: int) -> Iterator[str]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the gateway didn't start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)


@dataclass
class Stack:
    """a5s, running: its database, gateway, sample scenario and a fake model.

    Each part connects as its own role, as it does when deployed. `admin` is the
    database's administrator, for setting up and for tests that tamper.
    """

    cfg: Config  # the gateway's
    gateway: Gateway
    model: FakeModel
    admin: str
    channels_url: str  # the core's endpoints, where messages arrive

    def as_role(self, part: str) -> Config:
        return replace(self.cfg, database_url=db.as_role(self.admin, part))

    def send(self, text: str, person: str = "ana", agent: str = "assistant") -> str:
        """A message through the local channel, in development, recorded by the core. Its id."""
        r = httpx.post(f"{self.channels_url}/channels/local/messages",
                       json={"person": person, "agent": agent, "text": text}, timeout=30)
        r.raise_for_status()
        return r.json()["message"]

    def answers(self, message: str, person: str = "ana") -> list[str]:
        r = httpx.get(f"{self.channels_url}/channels/local/messages/{message}",
                      params={"person": person}, timeout=30)
        r.raise_for_status()
        return r.json()["replies"]

    def say(self, text: str, person: str = "ana", agent: str = "assistant",
            scheduler: Scheduler | None = None) -> str:
        """What a person is told, once the scheduler has answered their message."""
        r = httpx.post(f"{self.channels_url}/channels/local/messages",
                       json={"person": person, "agent": agent, "text": text}, timeout=30)
        if r.status_code != 202:
            return r.json()["detail"]
        (scheduler or self.scheduler()).answer_waiting()
        return "\n".join(self.answers(r.json()["message"], person))

    def inbox(self, person: str = "ana") -> list[dict]:
        """What's been written to someone without answering them, such as reminders."""
        r = httpx.get(f"{self.channels_url}/channels/local/inbox", params={"person": person},
                      timeout=30)
        r.raise_for_status()
        return r.json()["messages"]

    def at(self, when: str) -> None:
        """Set the core's clock, by which obligations and schedules fall due."""
        moment = datetime.fromisoformat(when)
        self.gateway.clock = lambda: moment

    @property
    def url(self) -> str:
        return self.cfg.gateway_url

    def client(self, token: str | None = None) -> httpx.Client:
        headers = {"Authorization": f"Bearer {token or SERVICE_TOKEN}"}
        return httpx.Client(base_url=self.url, headers=headers, timeout=60)

    def open_run(self, sender: str = "ana", instance: str = "assistant-finance") -> tuple[str, str]:
        """A run answering a message from `sender`, opened as the scheduler would."""
        with self.client() as c:
            r = c.post("/runs", json={"instance": instance, "trigger": {
                "kind": "message", "inbound": self.send("Hello", sender)}})
        r.raise_for_status()
        return r.json()["run"], r.json()["token"]

    def ledger(self, run: str | None = None) -> list[dict]:
        with db.transaction(self.cfg.database_url) as conn:
            return ledger.entries(conn, run=run, limit=1000)

    def verify(self) -> ledger.Verification:
        with db.transaction(self.cfg.database_url) as conn:
            return ledger.verify(conn)

    def suspend(self, by: str = "ben") -> None:
        with db.transaction(self.cfg.database_url) as conn:
            registry.set_status(conn, "assistant-finance", by=by, suspend=True)

    def scheduler(self, **kwargs: Any) -> Scheduler:
        return Scheduler(self.as_role("scheduler"), self.gateway.scenario, **kwargs)

    def settle(self, instances: dict | None = None, **changes: Any) -> registry.Applied:
        """Sign a new version of the settings as Ana, an instance approver, and apply it.

        `changes`, such as level=0, apply to assistant-finance; `instances` replaces them all.
        """
        folder = self.cfg.scenario_dir
        settings = yaml.safe_load((folder / "settings.yaml").read_text())
        settings["serial"] += 1
        if instances is not None:
            settings["instances"] = instances
        else:
            settings["instances"]["assistant-finance"].update(changes)
        raw = yaml.safe_dump(settings).encode()
        (folder / "settings.yaml").write_bytes(raw)
        value = signing.sign((folder / "keys" / "ana.key").read_text().strip(), raw)
        (folder / "settings.sig").write_text(
            yaml.safe_dump({"signatures": [{"signer": "ana", "value": value}]}))
        scenario = self.gateway.scenario
        with db.transaction(self.admin) as conn:
            return registry.apply(conn, self.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name)


def build_root(tmp: Path, model_alias: str, models_yaml: str) -> Path:
    root = tmp / "root"
    shutil.copytree(ROOT / "agents", root / "agents")
    shutil.copytree(ROOT / "scenarios" / "sample", root / "scenarios" / "sample")
    (root / "config").mkdir()
    (root / "config" / "models.yaml").write_text(models_yaml)
    spec = root / "agents" / "assistant" / "agent.yaml"
    lines = [f"model: {model_alias}" if line.startswith("model:") else line
             for line in spec.read_text().splitlines()]
    spec.write_text("\n".join(lines) + "\n")
    return root


@contextmanager
def running(database: str, root: Path, http: httpx.Client, model: FakeModel) -> Iterator[Stack]:
    port = free_port()
    cfg = Config(database_url=db.as_role(database, "gateway"),
                 gateway_url=f"http://127.0.0.1:{port}", service_token=SERVICE_TOKEN, root=root,
                 development=True)
    scenario = SampleScenario(cfg.scenario_dir, cfg.database_url)  # its tools run in the gateway
    definitions.pin(root / "agents" / "assistant",
                    {n: t.schema_hash for n, t in scenario.tools().items()})
    gw = Gateway(cfg, scenario, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http, clock=lambda: QUIET)
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    channels = replace(gw, cfg=replace(cfg, database_url=db.as_role(database, "channels")))
    with serve(create_app(gw), port), serve(inbox.create_app(channels), free_port()) as channels_url:
        yield Stack(cfg, gw, model, database, channels_url)


FAKE_MODELS = """
models:
  fake:
    provider: test
    api: openai
    base_url: https://fake.test/v1
    model: fake-1
    reported_model: fake-1
    key_env: A5S_TEST_PROVIDER_KEY
"""


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s
