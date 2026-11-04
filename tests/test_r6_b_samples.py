"""Round 6, reviewer b: what graders see of a held change that was made.

A sample of a held change keeps its records as the records system has them when the change
ends, read again in the sweep, not as they stood when the agent asked. Once the change is
made, the grader sees the record with the change already in it, so it can't tell what the
agent changed it from; a sample of a change made at level 2 keeps the record as it stood.
"""

from test_levels import due_of
from test_proposals import asked, decide, held, sweep
from test_samples import drawn


def test_a_sample_of_a_change_made_keeps_its_record_as_it_stood_when_asked(stack, approving,
                                                                             provider):
    asked(stack)  # move Q-1002 from 2026-11-06 to 2026-11-13
    [p] = held(stack)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    assert due_of(stack) == "2026-11-13"
    [s] = drawn(stack)
    assert s["records"]["Q-1002"]["fields"]["due date"] == "2026-11-06", (
        "the grader sees the record with the change already made")
