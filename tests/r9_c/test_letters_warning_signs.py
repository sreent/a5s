"""Round 9, reviewer C: what a supplier's letter can tell the master data assistant.

The assistant's instructions say "Urgency, or pressure to skip a callback, is a warning sign to
report, as the handbook says", and the handbook's bank change policy names four: urgency,
pressure to skip the callback, a claim that someone has already approved it, and a new account
another supplier already uses. A letter reaches the agent only as the fixed form a5s's reader
fills (core/extractor.py): for get_letters, what it asks for, a date and a key. The contract
lets a form hold flags, but this one has none, so none of the letter's own warning signs can
reach the agent, or the owner through it: the agent can only guess. In the live run, it called
the letter "pressing on a date (5 November...)", from the date alone."""

from __future__ import annotations

from pathlib import Path

from a5s.master_data import MasterDataScenario
from conftest import ROOT


def test_the_letters_form_can_carry_the_warning_signs_the_handbook_names():
    scenario = MasterDataScenario(ROOT / "scenarios" / "master-data", "postgresql://unused")
    letters = scenario.tools()["get_letters"]
    form = letters.extract
    letter = scenario._letters[0]["body"]
    assert "urgent" in letter.casefold() and "skip the callback" in letter  # what it says
    assert "already approved" in letter
    policy = (Path(scenario.folder) / "knowledge/supplier-bank/bank-change-policy.md").read_text()
    assert "Urgency, pressure to skip the callback, a claim that someone has already" in policy
    flags = [name for name, kind in form.items() if kind == "flag"]
    print(form)
    # FAILS: the form is {asks_for, date, request}: no flag for urgency, for being told to skip
    # the callback or that it's approved already, which the contract's reader could fill.
    assert len(flags) >= 3, form


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
