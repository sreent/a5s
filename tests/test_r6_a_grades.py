"""Round 6, reviewer a: grades and the cap.

- A critical error lowers a release's cap for one sweep only. The sweep that lowers it sets the
  cap's `since` to its own clock, after the critical grade, so the next sweep no longer counts
  that grade as critical, and raises the cap again on the same pooled evidence.
- The test pools every grade since the release began, so a fall in accuracy at level 2 is
  slow to lower the cap.
- Grades are neither signed for the grade nor sealed: the channels' database role can write
  them straight into `samples`, and the sweep counts them, so editing the database raises a
  cap; and a sign-in the grader's browser kept grades, though one decision needs a fresh one.
  Nor is a cap checked against the ledger: a row the gateway's role writes into `caps` counts.
- The grading page reads only the 200 oldest samples waiting, then keeps those the grader may
  grade, so 200 a grader may not grade hide every later one from them, for good.
- A grader may grade the approvals of the manager they report to: the sample's only grader,
  Dana, reports to Ana, who owns billing, decides its changes and signs its level 2.
"""

import time
from dataclasses import replace

import httpx
from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import samples
from conftest import seal_grades
from test_levels import asked, due_of, levelled
from test_samples import cap, graded, release, weigh


def graded_at(stack, when: str, n: int, grade: str = "right", part: str = "billing") -> None:
    """n samples of the assistant's changes of due dates, graded at `when`, as the grading page
    grades them, by the core's clock."""
    with db.transaction(stack.admin) as conn:
        for _ in range(n):
            conn.execute(
                "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
                "part, action, said, records, acts_for, drawn_at, grade, graded_by, graded_at) "
                "values ('sample', 'action', gen_random_uuid(), 'assistant-finance', %s, "
                "'assistant', %s, 'change-due-date', 'a change', '{}', '{ben}', %s, %s, 'dana', %s)",
                (release(stack), part, when, grade, when))
    seal_grades(stack)  # as the grading page has the core seal them


def drawn(stack, n: int, records: dict, part: str = "billing", decided_by: str | None = None) -> None:
    """n samples waiting for a grade, as the gateway draws them."""
    with db.transaction(stack.admin) as conn:
        for _ in range(n):
            conn.execute(
                "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
                "part, action, said, records, acts_for, decided, decided_by, drawn_at) values "
                "('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, 'assistant', "
                "%s, 'change-due-date', 'a change', %s, '{ben}', 'approve', %s, now())",
                (release(stack), part, Jsonb(records), decided_by))


def test_a_critical_error_keeps_the_cap_down_past_the_next_sweep(stack):
    stack.at("2026-11-02T10:00:00+00:00")
    graded_at(stack, "2026-11-02T09:00:00+00:00", 400)
    weigh(stack)
    assert cap(stack) == 2
    stack.at("2026-11-02T10:05:00+00:00")
    graded_at(stack, "2026-11-02T10:04:00+00:00", 1, "critical")  # graded before the sweep
    [lowered] = weigh(stack)
    assert lowered["why"] == "a critical error" and cap(stack) == 1
    stack.at("2026-11-02T10:06:00+00:00")  # the next sweep, a minute on
    raised = weigh(stack)
    assert raised == [] and cap(stack) == 1, raised


def test_a_fall_in_accuracy_at_level_2_lowers_the_cap_within_a_quarter(stack):
    """The test pools every grade since the release began, so the grades that earned level 2
    shield it from a fall after: at 90% against 98%, a quarter's 100 samples, 10 of them wrong,
    lower nothing, and it takes three quarters."""
    graded(stack, 224)  # level 2, earned
    weigh(stack)
    assert cap(stack) == 2
    stack.at("2027-01-20T10:00:00+00:00")
    graded(stack, 100, wrong=10)  # the next quarter's samples, made at level 2
    weigh(stack)
    assert cap(stack) == 1


def test_grades_written_straight_into_the_database_raise_no_cap(stack):
    drawn(stack, 224, {"Q-1002": None})
    with db.transaction(db.as_role(stack.admin, "channels")) as conn:  # nobody signed in
        conn.execute("update samples set grade = 'right', graded_by = 'dana', graded_at = now()")
    changed = weigh(stack)
    assert cap(stack) == 1, changed


def test_a_cap_written_straight_into_the_database_doesnt_count(stack, approving):
    levelled(stack, cap=0)  # level 2 for changes of due dates in billing, and no samples yet
    with db.transaction(db.as_role(stack.admin, "gateway")) as conn:  # no grades, no ledger entry
        conn.execute("insert into caps (release, part, action, cap, since, why) select release, "
                     "'billing', 'change-due-date', 2, now(), 'samples passed' from instances "
                     "where id = 'assistant-finance'")
    asked(stack)
    assert due_of(stack) == "2026-11-06"  # it waits for Ana


def test_a_sign_in_the_browser_kept_doesnt_grade(stack, approving, provider):
    drawn(stack, 1, {"Q-1002": None}, decided_by="ana")
    with db.transaction(stack.admin) as conn:
        sample = conn.execute("select id from samples").fetchone()["id"]
    kept = provider.id_token(person="dana", signed_in_at=int(time.time()) - 3 * 3600)
    r = httpx.post(f"{approving}/grade/samples/{sample}", json={"grade": "right"},
                   headers={"Authorization": f"Bearer {kept}"})
    assert r.status_code == 401, r.text


def test_a_grader_sees_what_they_may_grade_behind_what_they_may_not(stack, approving, provider):
    drawn(stack, 200, {"Q-1003": None}, part="orders")  # orders': Dana, in finance, may not see them
    drawn(stack, 1, {"Q-1002": None}, decided_by="ana")  # billing's: hers to grade
    review = httpx.post(f"{approving}/grade/review",
                        headers={"Authorization": f"Bearer {provider.id_token(person='dana')}"})
    assert review.status_code == 200, review.text
    assert len(review.json()["samples"]) == 1, review.json()


def test_nobody_grades_the_approvals_of_the_manager_they_report_to(stack):
    scenario = stack.gateway.scenario  # (the sample's Dana reports to someone else now)
    dana = replace(scenario.person("dana"), manager="ana")
    assert "part-owner:billing" in scenario.person("ana").roles
    sample = {"definition": "assistant", "instance_id": "assistant-finance", "acts_for": ["ben"],
              "decided_by": "ana", "records": {"Q-1002": None}}
    assert samples.may_grade(scenario, sample, dana) is not None
