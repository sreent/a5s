"""Round 9, reviewer C: a supplier's country, in master data governance.

A supplier's postcode is sensitive, and its owner confirms a change to it, but its country
isn't, though the country decides which VAT rule applies (master_data.VAT). So a request that
moves a supplier with a bad VAT number to a country with no VAT rule passes every check, touches
no sensitive field, and goes through SAP's workflow with no owner's confirmation; and the agent
may propose such a country for any request, as a correction that isn't sensitive."""

from __future__ import annotations

from a5s.master_data import CORRECTABLE, SENSITIVE, MasterDataScenario, failures
from conftest import ROOT


def test_moving_a_supplier_to_another_country_waits_for_its_owner():
    scenario = MasterDataScenario(ROOT / "scenarios" / "master-data", "postgresql://unused")
    fabrikam = scenario._records["S-100077"]
    assert failures("supplier", fabrikam)  # its GB VAT number isn't in GB's form
    scenario._requests["CR0000199"] = {
        "key": "CR0000199", "object": "supplier", "kind": "change", "record": "S-100077",
        "title": "Change Fabrikam Trading's country", "values": {"country": "US"},
        "status": "submitted", "requester": "bea", "steward": "tess",
        "opened": "2026-11-05", "due": "2026-11-09"}
    found = scenario.check("CR0000199")
    print(found["route"], SENSITIVE["supplier"], CORRECTABLE)
    assert found["passed"]  # with country US, its VAT number is checked by no rule at all
    # FAILS: no sensitive field, so SAP approves it with no owner's confirmation, though the
    # postcode beside it is sensitive, and the country switched its VAT rule off.
    assert found["route"].startswith("Una Novak"), found["route"]


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
