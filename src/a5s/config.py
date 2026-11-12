"""Where a5s finds its database, gateway, models and scenario."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import yaml

DEFAULT_DATABASE_URL = "postgresql://a5s@127.0.0.1:54329/postgres"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8700"
DEFAULT_CHANNELS_URL = "http://127.0.0.1:8703"


class Prices(NamedTuple):
    """What a million tokens cost: in, out, and in from the provider's cache, read or written,
    which providers price apart, at the price in when they don't say."""

    input: float
    output: float
    cached_input: float | None = None
    cache_write: float | None = None


@dataclass(frozen=True)
class ModelConfig:
    """An approved model: who serves it, where, and which exact version."""

    alias: str
    provider: str
    api: str  # "openai" or "anthropic": the API style the provider speaks
    base_url: str
    model: str  # the provider's model id, dated where the provider offers one
    key_env: str | None = None  # where its key is; a server on the organisation's network may need none
    region: str = "[TBC]"
    data_classes: tuple[str, ...] = ("synthetic",)
    reported_model: str | None = None  # what every response must report, if not `model`
    # What a million tokens cost, as the provider charges, in the deployment's currency, for
    # what a run costs (core/measures.py); none if not given
    prices: Prices | None = None

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.key_env) if self.key_env else None


def load_models(path: Path) -> dict[str, ModelConfig]:
    data = yaml.safe_load(path.read_text())
    models = {}
    for alias, m in data["models"].items():
        if m["api"] not in ("openai", "anthropic"):
            raise ValueError(f"model {alias}: api must be openai or anthropic, not {m['api']}")
        if not re.search(r"\d{4}-?\d{2}-?\d{2}", m["model"]) and not m.get("reported_model"):
            raise ValueError(f"model {alias}: {m['model']} isn't a dated version, so set "
                             "reported_model to what the provider reports for it")
        models[alias] = ModelConfig(
            alias=alias,
            provider=m["provider"],
            api=m["api"],
            base_url=m["base_url"].rstrip("/"),
            model=m["model"],
            key_env=m.get("key_env"),
            region=m.get("region", "[TBC]"),
            data_classes=tuple(m.get("data_classes", ["synthetic"])),
            reported_model=m.get("reported_model"),
            prices=Prices(float(p["input"]), float(p["output"]),
                          *(None if p.get(k) is None else float(p[k])
                            for k in ("cached_input", "cache_write")))
            if (p := m.get("prices")) else None,
        )
    return models


def pools(given: str, name: str = "A5S_WORKER_URLS") -> dict[str, str]:
    """What each agent's own worker pool is, by its name: as A5S_WORKER_URLS gives their
    URLs, such as assistant=http://a5s-worker-assistant:8702,watcher=http://..., and
    A5S_WORKER_SLOTS how many runs each takes at once, such as assistant=4."""
    found: dict[str, str] = {}
    for item in (i.strip() for i in given.split(",")):
        agent, sep, url = item.partition("=")
        if not item:
            continue
        if not sep or not agent.strip() or not url.strip():
            raise ValueError(f"{name}: {item!r} isn't an agent and its pool's, "
                             "such as assistant=http://a5s-worker-assistant:8702")
        found[agent.strip()] = url.strip().rstrip("/")
    return found


def names(given: str) -> frozenset[str]:
    return frozenset(n.strip() for n in given.split(",") if n.strip())


@dataclass(frozen=True)
class Config:
    database_url: str
    gateway_url: str
    service_token: str
    root: Path
    channels_url: str = DEFAULT_CHANNELS_URL  # where people's messages arrive, in the core
    worker_url: str | None = None  # set when workers run as a service: the shared pool
    # Each agent's own worker pool, by its name, such as assistant: an agent named here runs
    # in its pool alone, and any other in the shared one, at worker_url (A5S_WORKER_URLS)
    worker_urls: dict[str, str] = field(default_factory=dict)
    # and how many of its runs the scheduler works on at once there (A5S_WORKER_SLOTS)
    worker_slots: dict[str, int] = field(default_factory=dict)
    # In a worker: the agents its pool runs, if it's one agent's (A5S_WORKER_AGENTS), and
    # in the shared pool, those with pools of their own, which it refuses (A5S_WORKER_POOLED)
    worker_agents: frozenset[str] = frozenset()
    worker_pooled: frozenset[str] = frozenset()
    # Without an identity provider, the local channel takes people's word for who they are.
    # That's for development only, so it has to be asked for.
    development: bool = False
    anchor_store: str | None = None  # where the ledger's locked copies go, such as s3://bucket/a5s
    # The web chat's client at the identity provider: a public client, with PKCE.
    webchat_client_id: str | None = None
    anchor_retain_days: int = 365  # how long each copy stays locked: assurance's to set [TBC]
    # The directory's team that runs a5s. Its approvals of a release count as an engineer's,
    # and never as the release approver's.
    team: str = "platform"
    # The scenario a5s serves: a class built from its folder and a5s's database URL.
    scenario: str = "a5s.sample:SampleScenario"
    scenario_folder: Path | None = None  # by default, scenarios/sample
    agents_folder: Path | None = None  # by default, the reference agents in root/agents
    # The core's own keys, which seal the approvals it has checked, such as of settings. Only
    # the core holds them. The first seals; any others are ones it's moving away from.
    seal_keys: tuple[str, ...] = ()
    public_url: str | None = None  # where people reach the channels, for links: else channels_url
    # Whether the status names deciders whose approvals are graded wrong far more often than
    # others': profiling people, so only once the data protection officer agrees [TBC: O6].
    flag_rubber_stamps: bool = False
    # Whether the studio's pages name whom each run acted for: off until the data protection
    # officer agrees (docs/data-protection.md); until then a run says how many people
    studio_names: bool = False

    @property
    def agents_dir(self) -> Path:
        return self.agents_folder or self.root / "agents"

    @property
    def models_file(self) -> Path:
        return self.root / "config" / "models.yaml"

    @property
    def scenario_dir(self) -> Path:
        return self.scenario_folder or self.root / "scenarios" / "sample"

    @classmethod
    def from_env(cls) -> Config:
        root = Path(os.environ.get("A5S_ROOT", Path.cwd()))
        token = os.environ.get("A5S_SERVICE_TOKEN")
        if not token:
            token_file = root / ".a5s" / "service-token"
            token = token_file.read_text().strip() if token_file.exists() else ""
        seal = os.environ.get("A5S_SEAL_KEYS")
        if not seal:
            seal_file = root / ".a5s" / "seal-key"
            seal = seal_file.read_text().strip() if seal_file.exists() else ""
        return cls(
            database_url=os.environ.get("A5S_DATABASE_URL", DEFAULT_DATABASE_URL),
            gateway_url=os.environ.get("A5S_GATEWAY_URL", DEFAULT_GATEWAY_URL),
            service_token=token or "",
            root=root,
            channels_url=os.environ.get("A5S_CHANNELS_URL", DEFAULT_CHANNELS_URL),
            worker_url=os.environ.get("A5S_WORKER_URL"),
            worker_urls=pools(os.environ.get("A5S_WORKER_URLS", "")),
            worker_slots={agent: int(n) for agent, n in pools(
                os.environ.get("A5S_WORKER_SLOTS", ""), "A5S_WORKER_SLOTS").items()},
            worker_agents=names(os.environ.get("A5S_WORKER_AGENTS", "")),
            worker_pooled=names(os.environ.get("A5S_WORKER_POOLED", "")),
            development=os.environ.get("A5S_DEVELOPMENT", "").lower() in ("1", "true", "yes"),
            anchor_store=os.environ.get("A5S_ANCHOR_STORE"),
            webchat_client_id=os.environ.get("A5S_WEBCHAT_CLIENT_ID") or None,
            anchor_retain_days=int(os.environ.get("A5S_ANCHOR_RETAIN_DAYS", "365")),
            team=os.environ.get("A5S_TEAM") or "platform",  # set but empty, as compose may pass it
            scenario=os.environ.get("A5S_SCENARIO") or "a5s.sample:SampleScenario",
            scenario_folder=Path(os.environ["A5S_SCENARIO_DIR"]) if os.environ.get("A5S_SCENARIO_DIR")
            else None,
            agents_folder=Path(os.environ["A5S_AGENTS_DIR"]) if os.environ.get("A5S_AGENTS_DIR")
            else None,
            seal_keys=tuple(k.strip() for k in seal.split(",") if k.strip()),
            public_url=os.environ.get("A5S_PUBLIC_URL", "").rstrip("/") or None,
            flag_rubber_stamps=os.environ.get("A5S_FLAG_RUBBER_STAMPS", "").lower()
            in ("1", "true", "yes"),
            studio_names=os.environ.get("A5S_STUDIO_NAMES", "").lower() in ("1", "true", "yes"),
        )
