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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn

from a5s import db, definitions, devdb
from a5s.config import Config, load_models
from a5s.core import ledger, registry
from a5s.core.gateway import Gateway, create_app
from a5s.core.policy import PolicyEngine
from a5s.sample import SampleScenario
from a5s.services.scheduler import Scheduler

ROOT = Path(__file__).resolve().parents[1]
SERVICE_TOKEN = "test-service-token"
PROVIDER_KEY = "provider-secret"


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
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade")
        conn.execute("drop schema if exists sample cascade")
        conn.execute("create schema public")
    db.migrate(database_url)
    return database_url


@dataclass
class FakeModel:
    """An OpenAI-compatible provider that answers from a script and records what it's sent."""

    script: list[tuple[str | None, list[tuple[str, dict]]]] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    on_request: Callable[[int], None] | None = None

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
        return httpx.Response(200, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if tools else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    def tool_names(self, request: int = 0) -> set[str]:
        return {t["function"]["name"] for t in self.requests[request]["body"].get("tools", [])}


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
    """a5s, running: its database, gateway, sample scenario and a fake model."""

    cfg: Config
    gateway: Gateway
    model: FakeModel

    @property
    def url(self) -> str:
        return self.cfg.gateway_url

    def client(self, token: str | None = None) -> httpx.Client:
        headers = {"Authorization": f"Bearer {token or SERVICE_TOKEN}"}
        return httpx.Client(base_url=self.url, headers=headers, timeout=60)

    def open_run(self, sender: str = "ana", instance: str = "assistant-finance") -> tuple[str, str]:
        with self.client() as c:
            r = c.post("/runs", json={"instance": instance,
                                      "trigger": {"kind": "message", "channel": "local", "sender": sender}})
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

    def scheduler(self) -> Scheduler:
        return Scheduler(self.cfg, self.gateway.scenario)


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
    cfg = Config(database_url=database, gateway_url=f"http://127.0.0.1:{port}",
                 service_token=SERVICE_TOKEN, root=root)
    scenario = SampleScenario(cfg.scenario_dir, database)
    definitions.pin(root / "agents" / "assistant",
                    {n: t.schema_hash for n, t in scenario.tools().items()})
    gw = Gateway(cfg, scenario, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http)
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    with serve(create_app(gw), port):
        yield Stack(cfg, gw, model)


FAKE_MODELS = """
models:
  fake:
    provider: test
    api: openai
    base_url: https://fake.test/v1
    model: fake-1
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
