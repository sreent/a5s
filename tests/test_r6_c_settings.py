"""Round 6, reviewer c: the scenario's limits and per-type levels, as a part owner writes them.
A type of action is a word the settings and the tools must spell alike. A limit for a type no
tool takes is accepted without a word, and leaves the real type with no limit at all, which
counts never stop, even at level 2.

The test fails now and says what a5s should do instead.
"""

from __future__ import annotations

import yaml

from a5s import db
from a5s.contract import parse_settings
from a5s.core import approvals


def test_a_limit_for_a_type_of_action_no_tool_takes_is_refused(stack):
    raw = yaml.safe_load(stack.gateway.scenario.settings().raw)
    raw["serial"] += 1
    raw["limits"] = {"change-duedate": {"per_run": 1, "per_person_30_days": 5},  # a slip
                     "close-question": {"per_run": 5, "per_person_30_days": 20}}
    raw["instances"]["assistant-finance"]["parts"] = {
        "billing": {"level": 1, "actions": {"change-due-date": 2}}}
    wrong = parse_settings(yaml.safe_dump(raw).encode())
    with db.transaction(stack.admin) as conn:
        last = approvals.latest(conn, stack.gateway.scenario.name)
    problems = stack.gateway.unusable(wrong, last)
    assert any("change-duedate" in p for p in problems), (
        f"a5s would ask Ana to approve a version whose limit names no type of action, so "
        f"change-due-date, at level 2, has no limit: {problems}")
