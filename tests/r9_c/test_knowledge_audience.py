"""Round 9, reviewer C: who may read a knowledge article (a5s/knowledge.py).

An article names its readers as people, by id, or as parts, through the scenario's callback,
and "an unmarked document is denied": there's no way to say everyone the instance serves, a
team, or a role. So the service desk's VPN guide for employees names four people by id, and a
new joiner in sales, whom the desk serves through their team with no new settings (round 5's
point), can't read the guide every employee needs; the software delivery's guide to handling
secrets names only Sol, so no engineer can be told what to do with a token they pasted."""

from __future__ import annotations

from dataclasses import replace

from a5s.contract import ToolCall
from a5s.service_desk import ServiceDeskScenario
from a5s.software_delivery import SoftwareDeliveryScenario
from conftest import ROOT


def read(scenario, who: str, article: str) -> dict:
    return scenario.tools()["read_knowledge"].run(ToolCall(
        args={"id": article}, instance="i", run="r", acts_for=(who,)))


def test_a_new_joiner_reads_the_employees_vpn_guide():
    desk = ServiceDeskScenario(ROOT / "scenarios" / "service-desk", "postgresql://unused")
    desk._people["kim"] = replace(desk._people["jo"], id="kim", name="Kim Lee",
                                  identities=())  # joined sales today, as Jo did
    assert "text" in read(desk, "jo", "access/vpn-setup.md")  # Jo is named in it
    # FAILS: "no readable knowledge document has that id", for every employee not named
    assert "text" in read(desk, "kim", "access/vpn-setup.md")


def test_an_engineer_reads_how_to_handle_a_secret():
    dev = SoftwareDeliveryScenario(ROOT / "scenarios" / "software-delivery", "postgresql://unused")
    # FAILS: only Sol may read "Never paste a password, token or key into an issue..."
    assert "text" in read(dev, "raj", "security/secrets-handling.md")


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
