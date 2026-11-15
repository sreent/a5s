"""Round 11, reviewers B and E (B-3, E-1): every choice a version of the settings makes is in
the words its approvers read, the data protection officer's own among them. A version that
changes only her choices said "It changes nothing the agents do", and the whole version in words
never named them, so she approved blind (core/approvals.py)."""

import copy

import pytest
import yaml

from a5s import definitions
from a5s.contract import parse_settings
from a5s.core import approvals, registry
from a5s.core.approvals import changes, described
from a5s.sample import SampleScenario
from conftest import ROOT, SAMPLE_SETTINGS

NOTHING = "It changes nothing the agents do: only its number or its notes."
AGENTS = definitions.load_all(ROOT / "agents")
PEOPLE = SampleScenario(ROOT / "scenarios" / "sample", "postgresql://unused/a5s").person


def version(data: dict):
    return parse_settings(yaml.safe_dump(data).encode())


# For each choice a version makes, one way to make it otherwise: the guard below fails once the
# settings' format has a choice these don't, until its words say it
TOP = {
    "data_class": lambda v: v.update(data_class="internal"),
    "classified": lambda v: v.update(classified={"contact": "personal"}),
    "limits": lambda v: v["limits"]["close-question"].update(per_run=9),
    "thresholds": lambda v: v["thresholds"].update(billing=0.9),
    "instances": lambda v: v["instances"].pop("watcher-finance"),
    "groups": lambda v: v.update(groups={"graders": ["grader"]}),
}
INSTANCE = {
    "definition": lambda i: i.update(definition="watcher"),
    "serves": lambda i: i.update(serves=["ana"]),
    "level": lambda i: i.update(level=0),
    "owner": lambda i: i.update(owner="ben"),
    "deputy": lambda i: i.update(deputy="ana"),
    "parts": lambda i: i.update(parts=["billing", "orders"]),
    "asks": lambda i: i.update(asks=["watcher-finance"]),
}
PROTECTION = {
    "kept_for": "120 months",
    "fewest_people": 3,
    "studio_names": True,
    "audit_names": True,
    "flag_rubber_stamps": True,
}


def test_every_choice_of_the_settings_format_is_one_these_tests_change():
    from a5s.contract import _DataProtection, _Instance, _Version
    assert set(_Version.model_fields) - {"serial"} == set(TOP) | {"data_protection"}
    assert set(_Instance.model_fields) == set(INSTANCE)
    assert set(_DataProtection.model_fields) == set(PROTECTION)


@pytest.mark.parametrize("choice", sorted(TOP))
def test_a_version_that_makes_a_choice_otherwise_says_so(choice):
    before = copy.deepcopy(SAMPLE_SETTINGS)
    after = copy.deepcopy(before)
    TOP[choice](after)
    said = changes(version(before), version(after), AGENTS, PEOPLE)
    assert said and said[0]["text"] != NOTHING, choice
    assert described(version(before), AGENTS, PEOPLE) != described(version(after), AGENTS, PEOPLE)


@pytest.mark.parametrize("choice", sorted(INSTANCE))
def test_an_instance_made_otherwise_is_said_so(choice):
    before = copy.deepcopy(SAMPLE_SETTINGS)
    after = copy.deepcopy(before)
    INSTANCE[choice](after["instances"]["assistant-finance"])
    said = changes(version(before), version(after), AGENTS, PEOPLE)
    assert said and said[0]["text"] != NOTHING, choice
    assert described(version(before), AGENTS, PEOPLE) != described(version(after), AGENTS, PEOPLE)


@pytest.mark.parametrize("choice", sorted(PROTECTION))
def test_each_of_the_officers_choices_is_said_and_whether_it_widens(choice):
    before = copy.deepcopy(SAMPLE_SETTINGS)
    after = copy.deepcopy(before)
    after["data_protection"] = {choice: PROTECTION[choice]}
    said = changes(version(before), version(after), AGENTS, PEOPLE)
    assert len(said) == 1 and said[0]["widens"], said  # each names people or keeps more
    back = changes(version(after), version(before), AGENTS, PEOPLE)
    assert len(back) == 1 and not back[0]["widens"], back
    assert described(version(before), AGENTS, PEOPLE) != described(version(after), AGENTS, PEOPLE)


def test_the_officers_choices_are_in_the_whole_version():
    after = copy.deepcopy(SAMPLE_SETTINGS)
    after["data_protection"] = {"kept_for": "120 months", "studio_names": True,
                                "audit_names": True, "flag_rubber_stamps": True}
    whole = described(version(after), AGENTS, PEOPLE)
    assert "a5s keeps what's said for 120 months after a conversation's last message, and what " \
           "goes with it." in whole
    for name, (on, _) in approvals.NAMING.items():
        assert on in whole, name
    said = [c["text"] for c in changes(version(SAMPLE_SETTINGS), version(after), AGENTS, PEOPLE)]
    assert NOTHING not in said and len(said) == 4


def test_what_a_version_of_the_officers_choices_still_needs_names_her_from_the_start():
    """Before anyone has approved it, it said only that nobody who approves instances had."""
    after = copy.deepcopy(SAMPLE_SETTINGS)
    after["data_protection"] = {"audit_names": True}
    needs = registry.missing(version(after), PEOPLE, [], version(SAMPLE_SETTINGS))
    assert any("data-protection-officer" in n for n in needs), needs
    unchanged = registry.missing(version(SAMPLE_SETTINGS), PEOPLE, [], version(SAMPLE_SETTINGS))
    assert unchanged  # a version always needs someone's approval
