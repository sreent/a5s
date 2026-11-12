from __future__ import annotations

import json
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
from a5s.service_desk import ServiceDeskScenario
from conftest import (
    FAKE_MODELS,
    ROOT,
    SEAL_KEY,
    SERVICE_TOKEN,
    FakeModel,
    Stack,
    build_root,
    free_port,
    serve,
)


@contextmanager
def running_desk(database: str, root: Path, model: FakeModel,
                 http: httpx.Client | None = None, alias: str = "fake") -> Iterator[Stack]:
    import shutil
    port = free_port()
    agents = root / "scenario-agents"
    shutil.copytree(ROOT / "scenarios" / "service-desk" / "agents", agents)
    for spec in agents.glob("*/agent.yaml"):
        spec.write_text("\n".join(f"model: {alias}" if line.startswith("model:") else line
                                  for line in spec.read_text().splitlines()) + "\n")
    cfg = Config(database_url=db.as_role(database, "gateway"),
                 gateway_url=f"http://127.0.0.1:{port}", service_token=SERVICE_TOKEN,
                 root=root, development=True, seal_keys=(SEAL_KEY,),
                 scenario="a5s.service_desk:ServiceDeskScenario",
                 scenario_folder=ROOT / "scenarios" / "service-desk", agents_folder=agents)
    scenario = ServiceDeskScenario(cfg.scenario_dir, cfg.database_url)
    definitions.pin(agents / "desk-assistant",
                    {name: tool.schema_hash for name, tool in scenario.tools().items()})
    gw = Gateway(cfg, scenario, PolicyEngine(), load_models(cfg.models_file),
                 definitions.load_all(cfg.agents_dir), http or httpx.Client())
    with db.transaction(database) as conn:
        applied = registry.apply(conn, gw.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    channels = replace(gw, cfg=replace(cfg, database_url=db.as_role(database, "channels")))
    with serve(create_app(gw), port), serve(inbox.create_app(channels), free_port()) as url:
        yield Stack(cfg, gw, model, database, url)


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_desk(database, root, model, httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def say(stack: Stack, text: str, person: str = "sam") -> str:
    return stack.say(text, person=person, agent="desk-assistant")


def open_desk(stack: Stack, person: str) -> tuple[str, str]:
    with stack.client() as client:
        response = client.post("/runs", json={"instance": "desk-access", "trigger": {
            "kind": "message", "inbound": stack.send("Hello", person, agent="desk-assistant")}})
    assert response.status_code == 200, response.text
    return response.json()["run"], response.json()["token"]


def test_an_employee_gets_a_ticket_answer(desk):
    desk.model.reply(None, ("get_record", {"key": "INC0000001"}))
    desk.model.reply("INC0000001 is open, with Rae.")
    assert say(desk, "What's happening with INC0000001?") == "INC0000001 is open, with Rae."
    assert desk.verify().ok


def test_an_employee_gets_guidance_from_the_markdown_vault(desk):
    desk.model.reply(None, ("search_knowledge", {"query": "VPN"}))
    desk.model.reply(None, ("read_knowledge", {"id": "access/vpn-setup.md"}))
    desk.model.reply("Install the approved client, sign in with MFA, and use the internal gateway. "
                     "Source: access/vpn-setup.md.")
    answer = say(desk, "How do I set up the VPN?")
    assert "internal gateway" in answer and "access/vpn-setup.md" in answer
    assert desk.verify().ok


def test_ticket_and_knowledge_permissions_are_enforced(desk):
    _, sam = open_desk(desk, "sam")
    with desk.client(sam) as client:
        other = client.post("/run/tools/get_record", json={"args": {"key": "INC0000004"}})
        assert other.status_code == 403
        restricted = client.post("/run/tools/read_knowledge", json={"args": {
            "id": "hardware/battery-replacement.md"}})
    assert "no readable" in restricted.json()["result"]["error"]
    _, hal = open_desk(desk, "hal")
    with desk.client(hal) as client:
        allowed = client.post("/run/tools/read_knowledge", json={"args": {
            "id": "hardware/battery-replacement.md"}})
    assert "approved hardware supplier" in allowed.json()["result"]["text"]


def test_a_requester_comment_is_content_not_an_instruction(desk):
    desk.model.reply(None, ("get_messages", {"key": "INC0000001"}))
    desk.model.reply(json.dumps({"asks_for": "access"}))
    desk.model.reply("Sam says the VPN times out after MFA. I haven't closed or changed the ticket.")
    answer = say(desk, "What did Sam write on INC0000001?")
    assert "VPN times out" in answer and "haven't closed" in answer
    assert not desk.gateway.scenario.drafts
    assert desk.verify().ok


def test_a_reply_is_saved_as_a_draft_not_sent(desk):
    desk.model.reply(None, ("create_draft", {"title": "VPN troubleshooting", "body": "Try MFA again.",
                                             "record": "INC0000001"}))
    desk.model.reply("I've saved a draft for you.")
    answer = say(desk, "Draft a reply to my VPN ticket.")
    assert answer == "I've saved a draft for you."
    assert desk.gateway.scenario.drafts[0]["record"] == "INC0000001"


def test_a_new_joiner_is_served_through_their_team(desk):
    desk.model.reply("Welcome, Jo. Your equipment is on its way.")
    assert say(desk, "When does my laptop arrive?", person="jo") == (
        "Welcome, Jo. Your equipment is on its way.")


def test_scenario_agents_stay_out_of_the_default_release():
    import yaml

    from a5s.core import releases

    default = releases.running(ROOT, ROOT / "scenarios" / "sample")
    custom = releases.running(ROOT, ROOT / "scenarios" / "service-desk",
                              ROOT / "scenarios" / "service-desk" / "agents")
    assert set(yaml.safe_load(default.raw)["agents"]) == {"assistant", "watcher"}
    assert set(yaml.safe_load(custom.raw)["agents"]) == {"desk-assistant"}


@pytest.mark.live
def test_service_desk_answers_with_a_real_model(database: str, tmp_path: Path):
    import os
    if not os.environ.get("DEEPSEEK_API_KEY"):
        if os.environ.get("A5S_REGRESSION") == "required":  # a release covers its agents
            pytest.fail("DEEPSEEK_API_KEY isn't set, and a release needs its scenarios' suites")
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running_desk(database, root, FakeModel(), alias="deepseek-v4-pro") as found:
        ticket = say(found, "What's happening with INC0000001?")
        assert "INC0000001" in ticket and "open" in ticket.casefold()
        guidance = say(found, "How do I set up the VPN? Name the knowledge article you used.")
        assert "internal" in guidance.casefold() and "vpn-setup.md" in guidance
        assert found.verify().ok
