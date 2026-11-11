"""Round 9, reviewer C: the studio shows each run's ledger entries, "where what was said is only
by hash" (docs/data-protection.md, docs/studio.md, studio.html: "What was said is kept by its
hash alone"). But the ledger keeps, beside each message's hash, the keys, amounts and dates the
agent wrote that came from nothing it read (gateway.values_of), as written: so what an agent
told someone, such as a sum and a date, reaches everyone who may watch the instance."""

from __future__ import annotations

from test_studio_pages import signed_in


def test_what_an_agent_said_shows_only_by_hash(stack, approving, provider):
    stack.model.reply("Ana, your advance of £2,750.00 is due back on 19 December.")
    stack.say("When do I repay my salary advance?", person="ana")
    api = signed_in(approving, provider)
    [run] = api("/studio/api/instances/assistant-finance/runs", "ben").json()["runs"]
    shown = api(f"/studio/api/runs/{run['run']}", "ben").json()  # Ben, its deputy
    entries = str(shown["entries"])
    print([e.get("values") for e in shown["entries"] if e.get("values")])
    assert "salary advance" not in entries  # what Ana said, by its hash
    # FAILS: what the agent said, in part, in its words: the ledger's values.own
    assert "2,750.00" not in entries and "19 December" not in entries, entries


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
