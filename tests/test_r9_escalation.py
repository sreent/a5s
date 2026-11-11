"""Round 9 of the critique: escalation and need-to-know (core/obligations.py). An obligation
goes up the line to whoever may see its record; when nobody up the line may, to the owners of
its part who may; and when nobody may, the person's manager hears that something they owe is
late, and nothing of what it is (docs/critique.md, round 9)."""

from __future__ import annotations

import dataclasses
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


def a_week_and_more(dev: Stack) -> None:
    for day in ("02", "03", "04", "05", "06", "09", "10"):
        for hour in ("10", "15"):
            for _ in range(6):
                dev.model.reply("Here's what's due for you.")
            dev.at(f"2026-11-{day}T{hour}:00:00+00:00")
            dev.scheduler().work_due()


def test_a_late_critical_security_fix_goes_to_someone_who_hears_it_cant_go_up(dev):
    a_week_and_more(dev)
    scenario = dev.gateway.scenario
    assert scenario.person("sol").manager == "mia" and not scenario.sees("mia", "DEV-103")
    assert not scenario.sees("leo", "DEV-103")  # nor its part's owner: the security team's
    up = escalations(dev)
    assert ("DEV-101", "leo") in up  # Raj's high bug went to his lead, a day after it was due
    assert ("DEV-103", "mia") in up  # and Sol's manager heard it can't go up
    [told] = [e for e in dev.ledger() if e["kind"] == "notice" and e["action"] == "escalate"
              and e["args"]["record"] == "DEV-103"]
    assert told["args"]["as"] == "unseen"
    with db.transaction(dev.admin) as conn:
        said = [r["content"] for r in conn.execute(
            "select content from turns where person = 'mia' and role = 'notice'")]
    unseen = [s for s in said if "Nobody up their reporting line may see" in s]
    assert unseen and not any("DEV-103" in s or "Session tokens" in s for s in unseen), said


def test_a_part_owner_who_may_see_it_hears_when_nobody_up_the_line_may(dev):
    scenario = dev.gateway.scenario
    scenario._people["leo"] = dataclasses.replace(
        scenario._people["leo"], team="security-team")  # the backend's owner, in security now
    assert scenario.sees("leo", "DEV-103") and not scenario.sees("mia", "DEV-103")
    a_week_and_more(dev)
    told = [e["args"] for e in dev.ledger() if e["kind"] == "notice"
            and e["action"] == "escalate" and e["args"]["record"] == "DEV-103"]
    assert [(t["to"], t["as"]) for t in told] == [("leo", "part")]
    with db.transaction(dev.admin) as conn:
        said = [r["content"] for r in conn.execute(
            "select content from turns where person = 'leo' and role = 'notice'")]
    assert any("DEV-103" in s and "You own its part" in s for s in said), said
