"""Round 9 of the critique: the service desk. A ticket with no status no longer stops every
sweep of what the tickets owe, and whom a requester's message is from reaches the agent as a
handle, as a ticket's contact does (a5s/service_desk.py; docs/critique.md, round 9)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, FakeModel, Stack, build_root
from scenario_stack import opened, running_scenario

SCENARIO = "a5s.service_desk:ServiceDeskScenario"


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "service-desk",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def test_the_desk_follows_up_on_tickets_that_fall_due(desk):
    desk.at("2026-11-02T10:00:00+00:00")  # past half of INC0000001's time, in Rae's hours
    with desk.client() as client:
        swept = client.post("/obligations/sweep")
    assert swept.status_code == 200, swept.text
    owed = {o.record for o in desk.gateway.scenario.obligations()}
    assert {"INC0000001", "INC0000002"} <= owed


def test_a_requesters_message_reaches_the_agent_without_their_address(desk):
    desk.model.reply(json.dumps({"asks_for": "access"}))  # a5s's reader fills its form
    token = opened(desk, "desk-access", "rae", "desk-assistant")  # Rae resolves it
    with desk.client(token) as client:
        got = client.post("/run/tools/get_messages", json={"args": {"key": "INC0000001"}})
        ticket = client.post("/run/tools/get_record", json={"args": {"key": "INC0000001"}})
    assert got.status_code == 200, got.text
    seen = json.dumps(got.json()["result"])
    assert "times out" not in seen  # what Sam wrote never reaches the agent: only the form
    assert "sam.home@mail.test" not in seen and "[h:" in seen, seen  # whom it's from: a handle
    assert "sam.home@mail.test" not in ticket.text  # as a ticket's contact is
    assert desk.gateway.scenario.settings().classified == {"contact": "personal",
                                                           "from": "personal"}
