"""Round 15, the grader's finding (C1): graders and the judge graded a change without what was
asked of the run that made it, so a change to the wrong record couldn't be seen. A sample now
keeps what the people its run answered said to it, with its digest in the core's seal: graders
read it masked until the officer agrees to names, the judge reads it as said, an export gives
it to whom the change was for, and an erasure takes it out, leaving the sample counting."""

from __future__ import annotations

import json

import httpx

from a5s import db
from a5s.core import judging, samples
from test_erase import erase
from test_export import export
from test_officer import asked as officer_asked
from test_proposals import asked, decide, held, sweep
from test_r6_b_pages import signed_in
from test_samples import drawn

SAID = "Please move Q-1001 out a week, and copy pat@example.com in."


def sampled(stack, approving, provider) -> dict:
    """Ben asks about Q-1001, the agent moves Q-1002, and Ana approves it: its sample."""
    asked(stack, said=SAID)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    sweep(stack)
    [s] = drawn(stack)
    return s


def reviewed(approving, provider) -> dict:
    review = httpx.post(f"{approving}/grade/review", headers=signed_in(provider, "dana"))
    assert review.status_code == 200, review.text
    [shown] = review.json()["samples"]
    return shown


def judged(stack) -> str:
    with db.transaction(stack.admin) as conn:
        [pending] = judging.pending(conn, {"assistant": "judge"})
    return json.dumps(judging.asked("openai", "judge", "", pending))


def test_graders_read_what_was_asked_masked_and_the_judge_as_it_was_said(stack, approving,
                                                                          provider):
    s = sampled(stack, approving, provider)
    assert samples.asked_of(s) == SAID
    assert reviewed(approving, provider)["asked"] == (
        "Please move Q-1001 out a week, and copy [an email] in.")
    assert SAID in judged(stack)


def test_what_was_asked_rewritten_in_the_database_reaches_nobody(stack, approving, provider):
    sampled(stack, approving, provider)
    with db.transaction(stack.admin) as conn:
        conn.execute("update samples set asked = 'Please move Q-1002 out a week.'")
    assert reviewed(approving, provider)["asked"] is None
    assert "Q-1002 out a week" not in judged(stack)


def test_an_export_gives_it_and_an_erasure_takes_it_out_leaving_the_sample_counting(
        stack, approving, provider):
    sampled(stack, approving, provider)
    officer_asked(approving, provider, "export", "ben")  # on the core's page, signed in
    [given] = export(stack, "ben").json()["samples"]
    assert given["asked"] == SAID
    officer_asked(approving, provider, "erase", "ben")
    r = erase(stack, "ben")
    assert r.status_code == 200, r.text
    assert r.json()["gone"]["asked_in_samples"] == 1
    [s] = drawn(stack)
    assert s["asked"] is None and samples.drawn_by_core(stack.gateway.cfg.seal_keys, s)
    assert "a5s no longer keeps it" in judged(stack)


def test_the_judge_hears_when_nobody_asked():
    sample = {"action": "change-due-date", "said": "a change", "records": {}}
    assert "Nobody asked for it" in json.dumps(judging.asked("openai", "judge", "", sample))
