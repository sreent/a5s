"""Round 10, as the author of another scenario: the service desk, plugged in through the
contract alone, with its own agent taking on long tasks and repeats by its
release (`tasks:` in agent.yaml), as docs/agent-model.md says, and nothing changed in a5s."""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from a5s import db, definitions
from a5s.config import Config, load_models
from a5s.core import inbox, registry
from a5s.core.gateway import Gateway, create_app
from a5s.core.policy import PolicyEngine
from conftest import (
    FAKE_MODELS,
    PROVIDER_KEY,
    QUIET,
    ROOT,
    SEAL_KEY,
    SERVICE_TOKEN,
    FakeModel,
    Stack,
    build_root,
    free_port,
    serve,
)

TASKS = "tasks:\n  budget_tokens: 60000\n  days: 2\n"
LINES = ("- When someone asks for work that takes more than one sitting, offer it as a task with "
         "`offer_task`, and start it with `confirm_task` once they say yes in a later message.\n")


@contextmanager
def desk_with_tasks(database: str, root: Path, model: FakeModel) -> Iterator[Stack]:
    """The service desk, its own agent's release naming `tasks`, as its author would write it."""
    port = free_port()
    agents = root / "scenario-agents"
    shutil.copytree(ROOT / "scenarios" / "service-desk" / "agents", agents)
    for spec in agents.glob("*/agent.yaml"):
        lines = [("model: fake" if line.startswith("model:") else line)
                 for line in spec.read_text().splitlines()]
        spec.write_text("\n".join(lines) + "\n" + TASKS)
    for told in agents.glob("*/AGENTS.md"):
        told.write_text(told.read_text() + LINES)
    cfg = Config(database_url=db.as_role(database, "gateway"),
                 gateway_url=f"http://127.0.0.1:{port}", service_token=SERVICE_TOKEN,
                 root=root, development=True, seal_keys=(SEAL_KEY,),
                 scenario="a5s.service_desk:ServiceDeskScenario",
                 scenario_folder=ROOT / "scenarios" / "service-desk", agents_folder=agents)
    module, name = cfg.scenario.split(":")
    found = getattr(importlib.import_module(module), name)(cfg.scenario_dir, cfg.database_url)
    for agent in agents.iterdir():
        definitions.pin(agent, {n: t.schema_hash for n, t in found.tools().items()})
    http = httpx.Client(transport=httpx.MockTransport(model.handler))
    gw = Gateway(cfg, found, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http, clock=lambda: QUIET)
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, found.settings(), found.tools(),
                                 found.person, found.name)
    assert not applied.refused, applied.refused
    channels = replace(gw, cfg=replace(cfg, database_url=db.as_role(database, "channels")))
    with serve(create_app(gw), port), serve(inbox.create_app(channels), free_port()) as url:
        yield Stack(cfg, gw, model, database, url)


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with desk_with_tasks(database, root, model) as stack:
        yield stack


def test_the_desks_own_agent_takes_on_a_task_through_the_contract_alone(desk):
    asked = "Go through my open tickets and say what each waits on"
    desk.model.reply(None, ("offer_task", {"task": asked}))
    desk.model.reply("I can take that on as a task: shall I start it?")
    desk.say("Could you go through my open tickets?", person="sam", agent="desk-assistant")
    desk.model.reply(None, ("confirm_task", {}))
    desk.model.reply("Started.")
    desk.say("Yes please", person="sam", agent="desk-assistant")
    with db.transaction(desk.admin) as conn:
        [task] = conn.execute("select * from tasks").fetchall()
    assert task["status"] == "queued" and task["token_budget"] == 60_000
    desk.model.reply(None, ("search_records", {"query": "VPN"}),
                     ("finish_task", {"status": "done", "result": {"INC0000001": "the VPN"}}))
    desk.model.reply("Sam, your task is done: INC0000001 waits on the VPN team.")
    assert desk.scheduler().work_due() == 1
    with db.transaction(desk.admin) as conn:
        [task] = conn.execute("select * from tasks").fetchall()
        sent = [r["text"] for r in conn.execute(
            "select text from outbox where person = 'sam' and inbound_id is null")]
    assert task["status"] == "done", task["last_error"]
    assert sent and sent[0].startswith("Sam, your task is done"), sent
