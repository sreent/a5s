"""Round 9, reviewer A: the service desk classifies a ticket's contact as personal and hands it
over as a handle, but what a requester wrote comes with their address as "from", neither a
handle nor classified, so it reaches the model in clear (a5s/service_desk.py)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, FakeModel, Stack, build_root
from test_service_desk import running_desk


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_desk(database, root, model,
                      httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def test_a_requesters_personal_address_reaches_the_model_through_their_message(desk):
    with desk.client() as client:
        opened = client.post("/runs", json={"instance": "desk-access", "trigger": {
            "kind": "message", "inbound": desk.send("Hello", "sam", agent="desk-assistant")}})
    token = opened.json()["token"]
    desk.model.reply(json.dumps({"asks_for": "access"}))  # a5s's reader's form
    with desk.client(token) as client:  # the run reads what Sam wrote before the ticket
        said = client.post("/run/tools/get_messages", json={"args": {"key": "INC0000001"}})
        ticket = client.post("/run/tools/get_record", json={"args": {"key": "INC0000001"}})
    assert "sam.home@mail.test" not in ticket.text  # a ticket's contact is a handle
    # FAILS NOW: the same personal address, as the message's sender, in clear
    assert "sam.home@mail.test" not in said.text, said.json()


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
