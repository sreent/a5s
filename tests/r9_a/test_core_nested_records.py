"""Round 9, reviewer A, outside this round's diff: the gateway withholds records a run may not
see "at any depth" (core/parts.py), but only in lists and at the top: a record nested as a
dict's value passes, as a tool answering with an object, as MCP tools do, would nest it."""

from a5s.core import parts
from a5s.sample import SampleScenario
from conftest import ROOT


def test_a_record_nested_in_an_object_reaches_a_run_that_may_not_see_it(database):
    scenario = SampleScenario(ROOT / "scenarios" / "sample", database)
    run = {"parts": {"billing": 1}, "level": 1, "acts_for": ["ana"]}  # assistant-finance's
    assert not parts.workable(scenario, run, "Q-1003")
    answer = {"key": "Q-1001", "title": "Invoice sent to the wrong address",
              "related": {"key": "Q-1003", "title": "Delivery date for order 7781"}}
    kept, withheld = parts.kept(scenario, run, "key", answer)
    # FAILS NOW: Q-1003, in orders, which Ana may not see, comes through whole
    assert "Q-1003" not in str(kept) and withheld == 1, (kept, withheld)


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
