"""Round 9, reviewer C: the service desk's records, through the contract.

One of the desk's three tickets, INC0000002, has no status in scenarios/service-desk/data.yaml,
and the scenario reads each ticket's status with ticket["status"]: so obligations() and
watched() raise for every ticket, a5s takes it as "the records can't be read", and the desk
assistant, whose release says it "follows up on work that falls due", never chases anything.
Its tests never ask the records what's owed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, FakeModel, Stack, build_root
from scenario_stack import running_scenario

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
    print(swept.status_code, swept.text[:200])
    # FAILS: 503, "the records can't be read: KeyError", at every sweep, so nothing a ticket
    # owes is ever chased or escalated.
    assert swept.status_code == 200, swept.text



import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
