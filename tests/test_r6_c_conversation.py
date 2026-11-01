"""Round 6, reviewer c: the conversation around a held change. While a change waits, nothing a
later run is given says so: not the case's brief, which is built from records, nor a5s's
notices, which come only once it ends. So when the person asks again, or asks what became of
it, the agent can't tell them, and asks for the same change a second time.

Each test fails now and says what a5s should do instead.
"""

from __future__ import annotations

from test_proposals import MOVE, asked, held


def test_asking_again_in_a_later_run_answers_with_the_change_that_waits(stack, approving):
    """Ben asks again a day later. The run is new, so the gateway holds the same change a
    second time: Ana gets two cards for one change, and if she approves both, Ben is told the
    second wasn't made, since Q-1002 changed after he asked for it, by the first."""
    first = asked(stack)
    again = asked(stack, MOVE, said="Did you move Q-1002 to 2026-11-13? Please do.")
    assert first["held"] == "P-1"
    assert again["held"] == "P-1" and len(held(stack)) == 1, (
        f"the same change is held twice: {[p['said'].splitlines()[0] for p in held(stack)]}")


def test_a_later_run_is_told_what_waits_for_a_decision_on_its_record(stack, approving):
    """The case's brief comes from records, and a held change is one of a5s's own, but the
    brief leaves it out. Asked what's happening with Q-1002, the agent can't say that a change
    of its due date waits for Ana, unless its own earlier words still fit its context."""
    asked(stack)
    stack.model.reply("Q-1002 is waiting on finance.")
    stack.say("What's happening with Q-1002?", person="ben")
    told = stack.model.requests[-1]["body"]["messages"][0]["content"]
    brief = told[told.find("## The case: Q-1002"):]
    assert "P-1" in brief, f"the run's brief of Q-1002 says nothing of P-1: {brief[:400]}"
