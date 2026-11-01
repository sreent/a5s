"""Round 6, reviewer c: what a grader sees. Graders' grades decide whether an agent acts on
its own, and a grade is "right" if the change is what a careful colleague would have done
with what they knew. A sample keeps a5s's words for the change and the record, but not what
code flagged to its decider, such as a date the agent wrote itself, which is what a grader
most needs to judge it.

The test fails now and says what a5s should do instead.
"""

from __future__ import annotations

import json

import httpx

from a5s import db
from test_proposals import asked, decide, held, sweep


def test_a_grader_sees_what_code_flagged_to_the_decider(stack, approving, provider):
    asked(stack, said="Please move Q-1002 out a week.")  # Ben named no date
    [p] = held(stack)
    assert p["flags"] == [("2026-11-13 came from the assistant itself, not from the records or "
                           "from Ben Okafor")]
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    review = httpx.post(f"{approving}/grade/review",
                        headers={"Authorization": f"Bearer {provider.id_token(person='dana')}"})
    [sample] = review.json()["samples"]
    assert "came from the assistant itself" in json.dumps(sample), sample


def test_a_backlog_a_grader_may_not_grade_doesnt_hide_what_they_may(stack, approving, provider):
    """The page reads the 200 oldest samples waiting, then keeps those the grader may grade.
    Level 2 needs 224 grades at 98%, so a backlog builds. With 200 of orders' waiting, Dana,
    who grades billing, is told nothing waits for her, though a billing sample does."""
    with db.transaction(stack.admin) as conn:
        for key, part in [*[("Q-1003", "orders")] * 200, ("Q-1002", "billing")]:
            conn.execute(
                "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
                "part, action, said, records, acts_for, drawn_at) values ('sample', 'proposal', "
                "gen_random_uuid(), 'assistant-finance', 'r', 'assistant', %s, "
                "'change-due-date', 'a change', %s, '{ben}', now())",
                (part, json.dumps({key: None})))
    review = httpx.post(f"{approving}/grade/review",
                        headers={"Authorization": f"Bearer {provider.id_token(person='dana')}"})
    assert [s["part"] for s in review.json()["samples"]] == ["billing"], review.json()


def test_a_samples_record_is_as_it_stood_when_the_change_was_asked_for(stack, approving,
                                                                       provider):
    """A held change is drawn once it ends, with its records read then: for one a5s made, the
    record after the change. The grading page is given Q-1002 due on 2026-11-13, the date the
    agent asked for, as the record it judged."""
    asked(stack)
    [p] = held(stack)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    review = httpx.post(f"{approving}/grade/review",
                        headers={"Authorization": f"Bearer {provider.id_token(person='dana')}"})
    [sample] = review.json()["samples"]
    assert sample["records"]["Q-1002"]["fields"]["due date"] == "2026-11-06", sample["records"]
