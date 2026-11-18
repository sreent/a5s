"""Round 15, the auditor's finding: a cap's change says in the ledger what it rested on, the
samples, the releases and instances they came from, how many people graded them, and from
when, and the auditors' report lists it beside the administrative acts (E7)."""

from __future__ import annotations

from a5s import db
from a5s.core import audit
from test_samples import cap, graded, release, weigh


def test_a_cap_raised_says_what_it_rested_on_and_the_report_lists_it(stack):
    graded(stack, 224)
    weigh(stack)
    assert cap(stack) == 2
    [raised] = [e for e in stack.ledger() if e["kind"] == "cap" and e["action"] == "raise"]
    rested = raised["args"]
    assert rested["graded"] == 224 and len(rested["samples"]) == 64  # their ids, by a digest
    assert (rested["releases"], rested["instances"]) == ([release(stack)], ["assistant-finance"])
    assert rested["graders"] >= 1
    with db.transaction(stack.admin) as conn:
        found = audit.report(conn, stack.gateway.scenario, ["assistant"])
    [act] = [a for a in found["acts"] if a["action"] == "raise"]
    assert act["what"] == "let an agent act on its own, from graded samples"
    assert act["about"]["samples"] == rested["samples"]
