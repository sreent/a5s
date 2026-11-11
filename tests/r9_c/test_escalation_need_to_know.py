"""Round 9, reviewer C: escalation and need-to-know, in the software delivery scenario.

The ladder skips anyone up the line who may not see the record (core/obligations.py, chain),
and when that leaves nobody, it stops as if the top of the line had heard. In software
delivery, a security issue is for the security team and its assignee alone, and nobody up the
security engineer's line is in it: so a critical security fix that's late goes up to nobody,
and nothing says so, while a low-stakes backend bug goes to its lead."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from a5s import db
from conftest import FAKE_MODELS, FakeModel, Stack, build_root
from scenario_stack import running_scenario
from test_obligations import escalations

SCENARIO = "a5s.software_delivery:SoftwareDeliveryScenario"


@pytest.fixture
def dev(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "software-delivery",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def test_a_late_critical_security_fix_goes_up_the_line_or_someone_hears_it_cant(dev):
    for day in ("02", "03", "04", "05", "06", "09", "10"):
        for hour in ("10", "15"):
            for _ in range(6):
                dev.model.reply("Here's what's due for you.")
            dev.at(f"2026-11-{day}T{hour}:00:00+00:00")
            dev.scheduler().work_due()
    up = escalations(dev)
    scenario = dev.gateway.scenario
    assert scenario.person("sol").manager == "mia" and not scenario.sees("mia", "DEV-103")
    assert ("DEV-101", "leo") in up  # Raj's high bug went to his lead, a day after it was due
    with db.transaction(dev.admin) as conn:
        row = conn.execute("select chased_at, escalations, done_at from obligations "
                           "where record = 'DEV-103'").fetchone()
    print(up, row)
    noticed = [e for e in dev.ledger() if "DEV-103" in str(e.get("args"))]
    print([(e["kind"], e["action"]) for e in noticed])
    # FAILS: DEV-103, a critical security issue eight days late, went up to nobody: Sol's
    # manager may not see it, so the ladder is empty and stops as if the top had heard, and
    # neither the instance's owner nor the backend's lead, who owns its part, is told.
    assert any(record == "DEV-103" for record, _ in up), up


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
