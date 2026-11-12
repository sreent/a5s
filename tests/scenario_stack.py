"""a5s running a scenario of its own, with its own agents, through the contract alone, as
tests/test_service_desk.py runs the service desk: for the scenarios that bring their agents."""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import httpx

from a5s import db, definitions
from a5s.config import Config, load_models
from a5s.core import inbox, memberships, registry
from a5s.core.gateway import Gateway, create_app
from a5s.core.policy import PolicyEngine
from conftest import QUIET, ROOT, SEAL_KEY, SERVICE_TOKEN, FakeModel, Stack, free_port, serve


@contextmanager
def running_scenario(database: str, root: Path, model: FakeModel, scenario: str, folder: str,
                     http: httpx.Client | None = None, alias: str = "fake") -> Iterator[Stack]:
    """The core, the channels and the scenario's agents, each agent on the model `alias`, with
    the core's clock where the sample's is, until a test sets it."""
    port = free_port()
    agents = root / "scenario-agents"
    shutil.copytree(ROOT / "scenarios" / folder / "agents", agents)
    for spec in agents.glob("*/agent.yaml"):
        spec.write_text("\n".join(f"model: {alias}" if line.startswith("model:") else line
                                  for line in spec.read_text().splitlines()) + "\n")
    cfg = Config(database_url=db.as_role(database, "gateway"),
                 gateway_url=f"http://127.0.0.1:{port}", service_token=SERVICE_TOKEN,
                 root=root, development=True, seal_keys=(SEAL_KEY,), scenario=scenario,
                 scenario_folder=ROOT / "scenarios" / folder, agents_folder=agents)
    module, name = scenario.split(":")
    found = getattr(importlib.import_module(module), name)(cfg.scenario_dir, cfg.database_url)
    hashes = {n: t.schema_hash for n, t in found.tools().items()}
    for agent in agents.iterdir():
        definitions.pin(agent, hashes)
    directory = memberships.grouped(found, cfg.database_url, lambda conn: gw.groups_in_force(conn))
    gw = Gateway(cfg, directory, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http or httpx.Client(),
                 clock=lambda: QUIET)
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, found.settings(), found.tools(),
                                 found.person, found.name)
    assert not applied.refused, applied.refused
    channels = replace(gw, cfg=replace(cfg, database_url=db.as_role(database, "channels")))
    with serve(create_app(gw), port), serve(inbox.create_app(channels), free_port()) as url:
        yield Stack(cfg, gw, model, database, url)


def opened(stack: Stack, instance: str, person: str, agent: str) -> str:
    """A run of the instance, for a message from `person`: its token, to call tools as it."""
    with stack.client() as client:
        response = client.post("/runs", json={"instance": instance, "trigger": {
            "kind": "message", "inbound": stack.send("Hello", person, agent=agent)}})
    assert response.status_code == 200, response.text
    return response.json()["token"]
