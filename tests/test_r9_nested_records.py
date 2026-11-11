"""Round 9 of the critique: a record a run may not see is withheld at any depth, in a list or
as an object's value, as tools answering with objects, MCP's among them, nest records
(core/parts.py; docs/critique.md, round 9)."""

from a5s.core import parts
from a5s.sample import SampleScenario
from conftest import ROOT

RUN = {"parts": {"billing": 1}, "level": 1, "acts_for": ["ana"]}  # assistant-finance's


def test_a_record_nested_in_an_object_is_withheld_from_a_run_that_may_not_see_it(database):
    scenario = SampleScenario(ROOT / "scenarios" / "sample", database)
    assert not parts.workable(scenario, RUN, "Q-1003")
    answer = {"key": "Q-1001", "title": "Invoice sent to the wrong address",
              "related": {"key": "Q-1003", "title": "Delivery date for order 7781"}}
    kept, withheld = parts.kept(scenario, RUN, "key", answer)
    assert "Q-1003" not in str(kept) and withheld >= 1, (kept, withheld)


def test_one_in_an_object_in_a_list_goes_and_the_rest_stays(database):
    scenario = SampleScenario(ROOT / "scenarios" / "sample", database)
    found = {"found": [{"key": "Q-1001", "next": {"key": "Q-1003", "title": "Delivery"}}]}
    kept, withheld = parts.kept(scenario, RUN, "key", found)
    assert (kept, withheld) == ({"found": [{"key": "Q-1001"}]}, 1)
