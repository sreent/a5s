"""Round 9, reviewer C: the Markdown knowledge adapter's search (a5s/knowledge.py) scores an
article by how often each word of the question occurs in it as a substring, short words such
as "a", "is" and "how" included: so the longest articles come first, whatever is asked, and in
a vault of more than ten, the one that answers falls out of the ten it returns."""

from __future__ import annotations

from a5s.contract import ToolCall
from a5s.master_data import MasterDataScenario
from conftest import ROOT


def first(who: str, question: str) -> str:
    scenario = MasterDataScenario(ROOT / "scenarios" / "master-data", "postgresql://unused")
    found = scenario.tools()["search_knowledge"].run(ToolCall(
        args={"query": question}, instance="mdg-desk", run="r", acts_for=(who,)))
    return found["matches"][0]["id"]


def test_the_article_that_answers_comes_first():
    assert first("pia", "bank change callback") == "supplier-bank/bank-change-policy.md"
    # FAILS: governance/data-quality.md first, for the question the live test asks, as people do
    assert first("pia", "How is a supplier's bank change confirmed?") == (
        "supplier-bank/bank-change-policy.md")
    assert first("raf", "what base unit for a nut") == "material/units-of-measure.md"


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
