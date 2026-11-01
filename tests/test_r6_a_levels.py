"""Round 6, reviewer a: level 2 without the evidence.

A change to a record in no part works at the instance's own level, the lowest of its parts'
levels, in parts.about: no type of action set to 2, no cap raised by graded samples, and no
owner who approved it are asked for, and no sample is drawn. So once an approver sets a part's
own level to 2, which the docs say applies to drafts and requests, a change to any record in
no part is made at level 2. The contract has such records: their changes go to the instance
approvers (proposals.deciders).

A tool with no type of action that can't be undone or sends outside works at the part's own
level too, and the base pack's forbid for marked runs covers only tools that write: so a run
that has read a customer's email can still send outside at level 2.
"""

import pytest

from a5s import db
from a5s.core.policy import PolicyEngine
from test_levels import asked, decisions, due_of, levelled
from test_policy import call, instance, tool


def test_a_change_to_a_record_in_no_part_needs_its_type_set_and_the_cap_raised(stack, approving,
                                                                               monkeypatch):
    scenario = stack.gateway.scenario
    records = dict(scenario._records)
    records["Q-1005"] = {"key": "Q-1005", "title": "Account review", "status": "open",
                         "customer": "Tailspin", "owner": "ben", "opened": "2026-10-26",
                         "due": "2026-11-09", "contact": "accounts@tailspin.test"}  # in no part
    monkeypatch.setattr(scenario, "_records", records)
    assert scenario.part_of("Q-1005") is None and scenario.sees("ben", "Q-1005")
    assert not stack.settle(parts={"billing": 2}).refused  # billing's own level: no type of action
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        r = c.post("/run/tools/change_due_date", json={"args": {"key": "Q-1005", "due": "2026-12-31"}})
    assert r.status_code == 200, r.text
    with db.transaction(stack.admin) as conn:
        caps = conn.execute("select count(*) as n from caps").fetchone()["n"]
    assert caps == 0  # no samples have raised any cap
    assert due_of(stack, "Q-1005") == "2026-11-09", decisions(stack)  # so it waits for a person


def test_a_change_made_at_level_2_always_tells_someone(stack, approving):
    """An instance with neither owner nor deputy applies and runs, and a change made at level 2
    is reported only in its owner's digest: so nobody is told."""
    assert not stack.settle(owner=None, deputy=None).refused
    levelled(stack)
    asked(stack)  # Ben asks for MOVE, made at level 2
    assert due_of(stack) == "2026-11-13"
    with db.transaction(stack.admin) as conn:
        told = conn.execute("select count(*) as n from digest_items").fetchone()["n"]
    assert told >= 1


@pytest.mark.parametrize("risk", [{"destructive": True}, {"sends_outside": True}])
def test_a_marked_run_never_sends_outside_or_destroys_at_level_2(risk):
    grants = ("search_records", "send_email")
    d = call(PolicyEngine(), instance(level=2, grants=grants), tool("send_email", **risk),
             read_outside=True)
    assert not d.allowed, d
