"""Round 9, reviewer C: what a requester wrote on a ticket, as the desk assistant gets it.

The service desk's get_messages returns each message with whom it's from, and the body as a5s's
reader's form: what it asks for, one of four choices, and nothing else. Two things follow:

- whom it's from is the requester's own address, such as sam.home@mail.test, which the desk
  hands over as a handle on a ticket ("contact") and its settings classify as personal, but
  here it's neither, so the model reads it, unlike the other two scenarios' letters, which hand
  "from" over as a handle and classify it;
- the agent can't say what the requester wrote, such as that the VPN times out after MFA,
  though tests/test_service_desk.py scripts the fake model to say just that."""

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


def test_a_requesters_message_reaches_the_agent_without_their_address(desk):
    desk.model.reply(json.dumps({"asks_for": "access"}))  # a5s's reader fills its form
    token = opened(desk, "desk-access", "rae", "desk-assistant")  # Rae resolves it
    with desk.client(token) as client:
        got = client.post("/run/tools/get_messages", json={"args": {"key": "INC0000001"}})
    assert got.status_code == 200, got.text
    seen = json.dumps(got.json()["result"])
    print(seen)
    assert "times out" not in seen  # what Sam wrote never reaches the agent: only the form
    assert desk.gateway.scenario.settings().classified == {"contact": "personal"}
    # FAILS: whom it's from is Sam's own address, in plain, to the model
    assert "sam.home@mail.test" not in seen, seen


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
