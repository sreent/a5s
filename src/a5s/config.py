"""Where a5s finds its database, gateway, models and scenario."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_DATABASE_URL = "postgresql://a5s@127.0.0.1:54329/postgres"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8700"
DEFAULT_CHANNELS_URL = "http://127.0.0.1:8703"


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
        )
    return models


@dataclass(frozen=True)
class Config:
    database_url: str
    gateway_url: str
    service_token: str
    root: Path
    channels_url: str = DEFAULT_CHANNELS_URL  # where people's messages arrive, in the core
    worker_url: str | None = None  # set when workers run as a service
    # Without an identity provider, the local channel takes people's word for who they are.
    # That's for development only, so it has to be asked for.
    development: bool = False
    anchor_store: str | None = None  # where the ledger's locked copies go, such as s3://bucket/a5s
    anchor_retain_days: int = 365  # how long each copy stays locked: assurance's to set [TBC]
    # The scenario a5s serves: a class built from its folder and a5s's database URL.
    scenario: str = "a5s.sample:SampleScenario"
    scenario_folder: Path | None = None  # by default, scenarios/sample

    @property
    def agents_dir(self) -> Path:
        return self.root / "agents"

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
        return cls(
            database_url=os.environ.get("A5S_DATABASE_URL", DEFAULT_DATABASE_URL),
            gateway_url=os.environ.get("A5S_GATEWAY_URL", DEFAULT_GATEWAY_URL),
            service_token=token or "",
            root=root,
            channels_url=os.environ.get("A5S_CHANNELS_URL", DEFAULT_CHANNELS_URL),
            worker_url=os.environ.get("A5S_WORKER_URL"),
            development=os.environ.get("A5S_DEVELOPMENT", "").lower() in ("1", "true", "yes"),
            anchor_store=os.environ.get("A5S_ANCHOR_STORE"),
            anchor_retain_days=int(os.environ.get("A5S_ANCHOR_RETAIN_DAYS", "365")),
            scenario=os.environ.get("A5S_SCENARIO", "a5s.sample:SampleScenario"),
            scenario_folder=Path(os.environ["A5S_SCENARIO_DIR"]) if os.environ.get("A5S_SCENARIO_DIR")
            else None,
        )
