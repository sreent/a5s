"""Round 16, reviewer B (B1): four eyes in the settings. A version that took a part's four eyes
away while it raised the part's threshold counted as one that only narrows, so the part's owner
alone approved it, and its words never said four eyes went: Jules could then pay alone what
four eyes kept for two (core/registry.py, core/approvals.py)."""

from __future__ import annotations

import copy
from dataclasses import replace

import yaml

from a5s import definitions
from a5s.contract import INSTANCE_APPROVER, parse_settings
from a5s.core import approvals, registry
from a5s.procure_to_pay import ProcureToPayScenario
from conftest import ROOT

FOLDER = ROOT / "scenarios" / "procure-to-pay"
P2P = ProcureToPayScenario(FOLDER, "postgresql://unused/a5s")
AGENTS = definitions.load_all(FOLDER / "agents")
SETTINGS = yaml.safe_load((FOLDER / "settings.yaml").read_text(encoding="utf-8"))
EVERY_OWNER = ["jules", "marco", "wen"]


def version(data: dict):
    return parse_settings(yaml.safe_dump(data).encode())


def otherwise(change) -> tuple:
    """The settings in force, and a next version with `change` made to it."""
    before = copy.deepcopy(SETTINGS)
    after = copy.deepcopy(before)
    after["serial"] = before["serial"] + 1
    change(after)
    return version(before), version(after)


def stricter_and_without_four_eyes(v: dict) -> None:
    v.pop("two_deciders")
    v["thresholds"]["payables"] = 0.99  # alone, which payables' owner approves alone


def test_taking_four_eyes_away_never_counts_as_only_narrowing():
    before, after = otherwise(stricter_and_without_four_eyes)
    assert registry.narrowed(after, before) is None
    assert {p.id for p in registry.approvers(after, P2P.holders, before)} >= set(EVERY_OWNER)
    said = approvals.changes(before, after, AGENTS, P2P.person)
    gone = [c for c in said if "one of its deciders alone decides every change again" in c["text"]]
    assert gone and gone[0]["widens"], said


def test_it_needs_two_people_who_approve_settings_not_one_holding_two_roles():
    """Jules owns payables and approves instances: two roles, one person. Marco's and Wen's
    approvals are for their own parts, and Ravi, a delegate, approves no settings."""
    before, after = otherwise(stricter_and_without_four_eyes)
    needs = registry.missing(after, P2P.person, EVERY_OWNER, before)
    assert any("the four eyes in payables needs two people's approval" in n for n in needs), needs

    def directory(who: str):  # someone besides Jules approves instances
        if who == "meg":
            found = P2P.person("tara")
            assert found is not None
            return replace(found, id="meg", roles=(INSTANCE_APPROVER,))
        return P2P.person(who)

    assert registry.missing(after, directory, [*EVERY_OWNER, "meg"], before) == []


def test_a_higher_amount_or_another_field_loosens_it_and_a_lower_one_tightens_it():
    for above, field, loosens in ((20000, "amount", True), (5000, "amount", False),
                                  (10000, "total", True)):
        rule = {"payables": {"field": field, "above": above}}
        before, after = otherwise(lambda v, rule=rule: v.update(two_deciders=rule))
        assert registry.four_eyes_loosened(after, before) == ({"payables"} if loosens else set())
        said = approvals.changes(before, after, AGENTS, P2P.person)
        assert [c["widens"] for c in said if "two of the part's deciders" in c["text"]] == [
            loosens], said
        assert registry.narrowed(after, before) is None  # even tighter: its owner and the rest


def test_the_whole_version_names_four_eyes():
    whole = approvals.described(version(SETTINGS), AGENTS, P2P.person)
    assert ("In payables, a change to a record whose amount is more than 10,000 needs two of "
            "the part's deciders: one approval alone doesn't make it.") in whole


def test_an_amount_changed_in_the_database_after_its_hold_still_needs_two():
    """B4: four eyes read the amount from the held change's snapshot, which its digest doesn't
    bind, so whoever owns the database could lower it and let one approval make the change.
    Now a snapshot that isn't the one the digest bound counts as more than the amount."""
    from a5s.core import decide_api, proposals
    two = {"payables": ("amount", 10000.0)}
    snap = {"title": "Litware's invoice", "fields": {"amount": "16,000.00"}, "link": None,
            "person": "hana"}
    held = {"records": {"INV-9002": proposals.fingerprint_of(snap)},
            "standing": {"INV-9002": snap}}
    assert proposals.twice(two, P2P, held) == {"payables": ("INV-9002", 10000.0)}
    lowered = {**snap, "fields": {"amount": "9,000.00"}}
    assert proposals.twice(two, P2P, {**held, "standing": {"INV-9002": lowered}}) == {
        "payables": ("INV-9002", 10000.0)}  # as the digest its deciders signed binds it
    small = {"records": {"INV-9002": proposals.fingerprint_of(lowered)},
             "standing": {"INV-9002": lowered}}
    assert proposals.twice(two, P2P, small) == {}  # held at 9,000: one decider
    # B5: where the page can't read the settings in force, every part needs two there
    assert proposals.twice(decide_api.unknown(None), P2P, small) == {
        "payables": ("INV-9002", float("-inf"))}
