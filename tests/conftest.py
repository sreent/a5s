"""Test fixtures: a real Postgres, a real gateway, and a scripted model provider."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
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
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

import httpx
import jwt
import psycopg
import pytest
import uvicorn
import yaml
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jwt.algorithms import RSAAlgorithm

from a5s import db, definitions, devdb
from a5s.config import Config, load_models
from a5s.core import inbox, ledger, memberships, registry, signing
from a5s.core.gateway import Gateway, create_app
from a5s.core.identity import IdentityConfig, Verifier
from a5s.core.policy import PolicyEngine
from a5s.sample import SampleScenario
from a5s.services.scheduler import Scheduler

ROOT = Path(__file__).resolve().parents[1]
SERVICE_TOKEN = "test-service-token"
SEAL_KEY = "test-seal-key"  # the core's own, which seals the approvals it checked
CLIENT = "a5s-web"  # the web chat's client at the provider, which the approval page uses too
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


# The pages' redirects, as the first day's app registration lists them (docs/first-day.md):
# the provider refuses any other, as the organisation's does
REGISTERED = frozenset(re.findall(r"https://\$host(/[a-z]+/)",
                                  (ROOT / "docs" / "first-day.md").read_text()))


@dataclass
class FakeModel:
    """An OpenAI-compatible provider that answers from a script and records what it's sent."""

    script: list[tuple[str | None, list[tuple[str, dict]]]] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    on_request: Callable[[int], None] | None = None
    reports: str | None = None  # the model it says answered, if not the one asked for; "" for none
    tokens: int = 15  # what it says each call took
    failing: int = 0  # how many calls in a row it fails, from now

    def reply(self, content: str | None = None, *tools: tuple[str, dict]) -> None:
        self.script.append((content, list(tools)))

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body})
        if self.on_request:
            self.on_request(len(self.requests))
        if self.failing:
            self.failing -= 1
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
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
            "usage": {"prompt_tokens": self.tokens - 5, "completion_tokens": 5,
                      "total_tokens": self.tokens},
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


class Provider:
    """An OpenID Connect provider that signs someone in at once, Ana unless a test says, and
    checks PKCE as a real one does. Asked for a fresh sign-in, it says when it was."""

    def __init__(self) -> None:
        self.keys = {"k1": rsa.generate_private_key(public_exponent=65537, key_size=2048)}
        self.kid = "k1"
        self.person = "ana"
        self.names = {"ana": "Ana Ortiz", "ben": "Ben Okafor"}
        self.codes: dict[str, tuple] = {}
        self.refreshes: dict[str, str] = {}
        self.forms: list[dict] = []
        self.asked: list[dict] = []  # what each sign-in asked for
        self.claims: dict[str, Any] = {}  # more claims for each ID token, such as amr
        self.url = ""

    def rotate(self) -> None:
        """Sign with a new key, and withdraw the old ones, as providers do."""
        self.kid = f"k{len(self.keys) + 1}"
        self.keys = {self.kid: rsa.generate_private_key(public_exponent=65537, key_size=2048)}

    def id_token(self, nonce: str | None = None, person: str | None = None,
                 signed_in_at: int | None = None, **claims: Any) -> str:
        now, who = int(time.time()), person or self.person
        body = {"iss": self.url, "aud": CLIENT, "iat": now, "exp": now + 300, "sub": f"u-{who}",
                "preferred_username": who, "name": self.names.get(who, who), "nonce": nonce,
                "auth_time": signed_in_at, **claims}
        return jwt.encode({k: v for k, v in body.items() if v is not None}, self.keys[self.kid],
                          algorithm="RS256", headers={"kid": self.kid})

    def app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/.well-known/openid-configuration")
        def discovery() -> dict:
            return {"issuer": self.url, "authorization_endpoint": f"{self.url}/auth",
                    "token_endpoint": f"{self.url}/token", "jwks_uri": f"{self.url}/certs",
                    "end_session_endpoint": f"{self.url}/logout"}

        @app.get("/certs")
        def certs() -> dict:
            return {"keys": [{**RSAAlgorithm.to_jwk(key.public_key(), as_dict=True),
                              "kid": kid, "use": "sig", "alg": "RS256"}
                             for kid, key in self.keys.items()]}

        @app.get("/auth")
        def auth(request: Request, client_id: str, redirect_uri: str, state: str, nonce: str,
                 code_challenge: str, code_challenge_method: str) -> Any:
            self.asked.append(dict(request.query_params))
            if urlparse(redirect_uri).path not in REGISTERED:  # as Entra ID refuses one
                return JSONResponse(status_code=400, content={  # its app doesn't list
                    "error": "invalid_request", "error_description": "redirect_uri mismatch"})
            code = secrets.token_urlsafe(16)
            fresh = int(time.time()) if "max_age" in request.query_params else None
            self.codes[code] = (client_id, redirect_uri, code_challenge, code_challenge_method,
                                nonce, self.person, fresh)
            return RedirectResponse(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}")

        @app.post("/token")
        async def token(request: Request) -> JSONResponse:
            form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
            self.forms.append(form)
            if form.get("grant_type") == "refresh_token":
                if self.refreshes.pop(form.get("refresh_token", ""), None) != form.get("client_id"):
                    return JSONResponse(status_code=400, content={"error": "invalid_grant"})
                nonce, person, fresh = None, self.person, None
            else:
                client, back, challenge, method, nonce, person, fresh = self.codes.pop(
                    form.get("code", ""), (None,) * 7)
                digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
                proof = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
                if (client, back, method, challenge) != (form.get("client_id"), form.get("redirect_uri"),
                                                         "S256", proof):
                    return JSONResponse(status_code=400, content={"error": "invalid_grant"})
            refresh = secrets.token_urlsafe(16)
            self.refreshes[refresh] = form["client_id"]
            return JSONResponse({"id_token": self.id_token(nonce, person, fresh, **self.claims),
                                 "refresh_token": refresh, "access_token": "for-the-provider-only",
                                 "token_type": "Bearer"})

        return app


@pytest.fixture
def provider() -> Iterator[Provider]:
    fake = Provider()
    port = free_port()
    fake.url = f"http://127.0.0.1:{port}"
    with serve(fake.app(), port):
        yield fake


@pytest.fixture
def approving(stack: Stack, provider: Provider) -> Iterator[str]:
    """The core, signing people in through the provider: the channels, where approvers
    decide and the settings app is, and the gateway, which asks them and applies what they
    approve."""
    with deciding(stack, provider) as url:
        yield url


@contextmanager
def deciding(stack: Stack, provider: Provider) -> Iterator[str]:
    """The channels app where a stack's approvers decide, signing them in through the
    provider, and the stack's gateway, which asks them: its address."""
    verifier = Verifier(IdentityConfig(issuer=provider.url, audience=("a5s", CLIENT)))
    port = free_port()
    stack.gateway.identity = verifier
    stack.gateway.cfg = replace(stack.gateway.cfg, webchat_client_id=CLIENT,
                                public_url=f"http://127.0.0.1:{port}")
    cfg = replace(stack.as_role("channels"), webchat_client_id=CLIENT, development=False,
                  seal_keys=())  # the channels app never holds the core's seal key
    with serve(inbox.create_app(replace(stack.gateway, cfg=cfg, identity=verifier)), port) as url:
        yield url


@pytest.fixture
def browser() -> Iterator[Any]:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception as exc:  # no browser installed here: CI insists on one
            if os.environ.get("A5S_TEST_BROWSER") == "required":
                raise
            pytest.skip(f"needs Chromium, from `uv run playwright install chromium`: {exc}")
        yield chromium
        chromium.close()


@contextmanager
def serve(app: Any, port: int, host: str = "127.0.0.1") -> Iterator[str]:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the gateway didn't start")
        time.sleep(0.02)
    try:
        yield f"http://{host}:{port}"
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
    worker: Any = None  # where the scheduler hands its runs, if not to a worker in this process

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
        if self.worker is not None:
            kwargs.setdefault("worker", self.worker)
        return Scheduler(self.as_role("scheduler"), self.gateway.scenario, **kwargs)

    def settle(self, instances: dict | None = None, signers: tuple[str, ...] = ("ana",),
               **changes: Any) -> registry.Applied:
        """Sign a new version of the settings as Ana, an instance approver who owns billing,
        or as `signers`, and apply it.

        `changes`, such as level=0, apply to assistant-finance; `instances` replaces them all.
        """
        folder = self.cfg.scenario_dir
        settings = yaml.safe_load((folder / "settings.yaml").read_text())
        if instances is not None:
            settings["instances"] = instances
        else:
            settings["instances"]["assistant-finance"].update(changes)
        signed(folder, settings, signers)
        scenario = self.gateway.scenario
        with db.transaction(self.admin) as conn:
            return registry.apply(conn, self.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name)

    def with_watcher(self, serves: tuple[str, ...] = ("ana", "ben"),
                     signers: tuple[str, ...] = ("ana",), **changes: Any) -> None:
        """The sample's watcher, which the tests leave out unless they ask, as its settings
        name it, with `changes`: it tells its people each working morning what changed in
        their records."""
        settings = yaml.safe_load((self.cfg.scenario_dir / "settings.yaml").read_text())
        assert not self.settle(instances={**settings["instances"], "watcher-finance": {
            **WATCHER, "serves": list(serves), **changes}}, signers=signers).refused


def signed(folder: Path, settings: dict, signers: tuple[str, ...] = ("ana",)) -> None:
    """A new version of the settings, with its serial raised, signed by Ana, an instance
    approver who owns billing, or by `signers`."""
    raw = yaml.safe_dump({**settings, "serial": settings["serial"] + 1}).encode()
    (folder / "settings.yaml").write_bytes(raw)
    (folder / "settings.sig").write_text(yaml.safe_dump({"signatures": [
        {"signer": who, "value": signing.sign((folder / "keys" / f"{who}.key").read_text().strip(),
                                               raw)}
        for who in signers]}))


SAMPLE_SETTINGS = yaml.safe_load((ROOT / "scenarios" / "sample" / "settings.yaml").read_text())
WATCHER = SAMPLE_SETTINGS["instances"]["watcher-finance"]


def build_root(tmp: Path, model_alias: str, models_yaml: str) -> Path:
    """The agents and the sample, each agent on the model under test. The watcher is left
    out of the settings, so its reports don't run in tests that aren't about it."""
    root = tmp / "root"
    shutil.copytree(ROOT / "agents", root / "agents")
    shutil.copytree(ROOT / "scenarios" / "sample", root / "scenarios" / "sample")
    (root / "config").mkdir()
    (root / "config" / "models.yaml").write_text(models_yaml)
    for spec in (root / "agents").glob("*/agent.yaml"):
        lines = [f"model: {model_alias}" if line.startswith("model:") else line
                 for line in spec.read_text().splitlines()]
        spec.write_text("\n".join(lines) + "\n")
    instances = {k: v for k, v in SAMPLE_SETTINGS["instances"].items() if k != "watcher-finance"}
    signed(root / "scenarios" / "sample", {**SAMPLE_SETTINGS, "instances": instances})
    return root


# Docker's bridge, as the host sees it: a worker in a container reaches the core there
BRIDGE = os.environ.get("A5S_TEST_BRIDGE", "172.17.0.1")


def live_image() -> str | None:
    """The image a live suite hands each run to a worker from, in a container of its own, as
    a release's suites do (.github/workflows/release.yml): A5S_TEST_WORKER_IMAGE, such as
    a5s:dev. Unset, each run goes to a worker in this process."""
    return os.environ.get("A5S_TEST_WORKER_IMAGE") or None


@contextmanager
def contained(app: Any, image: str) -> Iterator[Any]:
    """A worker from a5s's image, in a container of its own on Docker's bridge, as a pool's
    pods run: it holds no secrets, and reaches the core at the bridge's address, which the
    core is served on for it alone. The scheduler hands it each run over HTTP, as it hands a
    pool's (services/scheduler.py's remote_worker). What it yields counts the runs it took,
    and a test that hands it none fails: it would have tested the worker in this process."""
    import subprocess
    import uuid

    from a5s.services.scheduler import remote_worker

    port, name = free_port(), f"a5s-test-worker-{uuid.uuid4().hex[:8]}"
    with serve(app, port, host=BRIDGE):
        subprocess.run(["docker", "run", "-d", "--rm", "--name", name,
                        "--add-host", "host.docker.internal:host-gateway",
                        "-p", "127.0.0.1::8702",  # for the scheduler, on this machine alone
                        "-e", f"A5S_GATEWAY_URL=http://host.docker.internal:{port}",
                        image, "worker", "--host", "0.0.0.0"],
                       check=True, capture_output=True, timeout=120)
        try:
            mapped = subprocess.run(["docker", "port", name, "8702/tcp"], check=True,
                                    capture_output=True, text=True).stdout.split()[0]
            url = f"http://{mapped}"
            deadline = time.monotonic() + 60
            while True:  # it starts in a couple of seconds
                try:
                    if httpx.get(f"{url}/openapi.json", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError(f"the worker container {name} didn't start")
                time.sleep(0.5)
            pool = remote_worker(url)

            def work(gateway_url: str, token: str, history: list[dict]) -> str:
                work.runs += 1
                return pool(gateway_url, token, history)

            work.runs = 0
            yield work
            assert work.runs, f"no run went to the worker container {name}"
        finally:
            logs = subprocess.run(["docker", "logs", "--tail", "30", name], check=False,
                                  capture_output=True, text=True).stdout
            print(f"\n[the worker container's last lines]\n{logs}")
            subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)


@contextmanager
def worker_for(app: Any, image: str | None) -> Iterator[Any]:
    """Where the scheduler hands each run: with `image`, a worker from it in a container of
    its own (`contained`); without, None, and each run goes to a worker in this process."""
    if image is None:
        yield None
        return
    with contained(app, image) as worker:
        yield worker


@contextmanager
def running(database: str, root: Path, http: httpx.Client, model: FakeModel,
            worker_image: str | None = None) -> Iterator[Stack]:
    """a5s, running: with each run in a worker in this process, or, with `worker_image`, in
    a worker from that image, in a container of its own (`contained`)."""
    port = free_port()
    cfg = Config(database_url=db.as_role(database, "gateway"),
                 gateway_url=f"http://127.0.0.1:{port}", service_token=SERVICE_TOKEN, root=root,
                 development=True, seal_keys=(SEAL_KEY,))
    scenario = SampleScenario(cfg.scenario_dir, cfg.database_url)  # its tools run in the gateway
    for agent in ("assistant", "watcher"):
        definitions.pin(root / "agents" / agent, {n: t.schema_hash for n, t in scenario.tools().items()})
    # Its directory, with the roles groups give, as a5s builds it (core/memberships.py)
    directory = memberships.grouped(scenario, cfg.database_url, lambda conn: gw.groups_in_force(conn))
    gw = Gateway(cfg, directory, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http, clock=lambda: QUIET)
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    channels = replace(gw, cfg=replace(cfg, database_url=db.as_role(database, "channels")))
    app = create_app(gw)
    with (serve(app, port), serve(inbox.create_app(channels), free_port()) as channels_url,
          worker_for(app, worker_image) as worker):
        yield Stack(cfg, gw, model, database, channels_url, worker=worker)


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


def raise_cap(stack: Stack, part: str = "billing", action: str = "change-due-date",
              cap: int = 2, instance: str = "assistant-finance") -> None:
    """a5s's cap for an instance's release, as graded samples raise it: sealed by the core,
    with the ledger entry that set it."""
    from a5s.core import samples
    with db.transaction(stack.admin) as conn:
        release = conn.execute("select release from instances where id = %s",
                               (instance,)).fetchone()["release"]
        kind = samples.behaviour_of(conn, release, action)
        assert kind, f"no behaviour for {release} and {action}"
        samples.set_cap(conn, (SEAL_KEY,), kind, part, action, cap, "samples passed",
                        stack.gateway.clock(), threshold=0.98)


def seal_grades(stack: Stack) -> None:
    """Seal the grades written straight into the database, as the grading page has the core
    seal each grade it checked."""
    from a5s.core import samples
    with db.transaction(stack.admin) as conn:
        for row in conn.execute("select * from samples where grade is not null "
                                "and grade_seal is null").fetchall():
            conn.execute("update samples set grade_seal = %s where id = %s",
                         (samples.seal((SEAL_KEY,), row), row["id"]))


# The sandbox (a5s/sandbox.py): a deployment of its own, on a database of its own beside the
# tests', for the sample's agents and scenario

@pytest.fixture
def sandbox_database(database_url: str) -> Iterator[str]:
    """A database of the sandbox's own, beside the tests' own, on the same server."""
    name = f"a5s_sandbox_{secrets.token_hex(4)}"
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(f'create database "{name}"')
    try:
        yield urlunsplit(urlsplit(database_url)._replace(path=f"/{name}"))
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(f'drop database "{name}" with (force)')


def deployment(root: Path = ROOT) -> Config:
    """A deployment's config, as the sandbox reads it: its scenario, agents and models."""
    return Config(database_url="postgresql://unused", gateway_url="http://unused",
                  service_token="", root=root)


@pytest.fixture
def box(sandbox_database: str, tmp_path: Path) -> Iterator[Any]:
    from a5s import sandbox
    with sandbox.opened(deployment(), sandbox_database, tmp_path / "sandbox") as opened:
        yield opened


@pytest.fixture
def with_sandbox(stack: Stack, box: Any) -> Iterator[str]:
    """The stack's studio with a sandbox at hand, by the token they share. Ask for it before
    the channels app, as `approving`, so the app knows where the sandbox is."""
    from a5s import sandbox
    with serve(sandbox.create_app(box, "shared-token"), free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="shared-token")
        yield url
