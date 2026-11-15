"""The judge (core/judging.py): an approved model an agent's definition names, which grades each
sample of its work beside people, never instead of them. People's grades stay the evidence, so
its verdict never moves a cap, and graders never see it before they grade; what a5s measures is
how far it agrees with them."""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import judging
from a5s.definitions import Evaluation
from conftest import raise_cap
from test_samples import cap, release, weigh

RUBRIC = "A due date moves only to a date the customer asked for, and never into the past."
RECORDS = {"Q-1002": {"key": "Q-1002", "due date": "2026-11-06", "status": "waiting on finance"}}


@pytest.fixture
def judged(stack, monkeypatch):
    """The assistant, with its judge: the stack's one approved model, which is its own too."""
    found = stack.gateway.definitions["assistant"]
    monkeypatch.setitem(stack.gateway.definitions, "assistant", found.model_copy(
        update={"evaluation": Evaluation(judge="fake", rubric=RUBRIC)}))
    return stack


def drawn(stack, n: int = 1, grade: str | None = None) -> list[int]:
    """n samples of the assistant's changes, as the gateway draws them: graded, if `grade`."""
    with db.transaction(stack.admin) as conn:
        made = [conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, part, "
            "action, said, records, acts_for, decided, decided_by, drawn_at, flags) values "
            "('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, 'assistant', "
            "'billing', 'change-due-date', 'Change Q-1002''s due date to 2026-11-13', %s, "
            "'{ben}', 'approve', 'ana', now(), %s) returning id",
            (release(stack), Jsonb(RECORDS), Jsonb(["the date came from the agent itself"]))
        ).fetchone()["id"] for _ in range(n)]
        if grade:
            conn.execute("update samples set grade = %s, graded_by = 'dana', graded_at = now() "
                         "where id = any(%s)", (grade, made))
        return made


def judge(stack) -> dict:
    with stack.client() as c:
        r = c.post("/samples/judge")
    r.raise_for_status()
    return r.json()


def verdicts(stack) -> dict[int, tuple]:
    with db.transaction(stack.admin) as conn:
        return {r["sample_id"]: (r["judge"], r["verdict"], r["why"]) for r in conn.execute(
            "select * from judgments order by sample_id")}


def test_the_judge_grades_a_sample_as_people_are_shown_it(judged):
    [sample] = drawn(judged)
    judged.model.reply(json.dumps({"grade": "wrong", "why": "The customer asked for the 20th."}))
    assert judge(judged)["judged"] == [{"sample": sample, "verdict": "wrong"}]
    assert verdicts(judged) == {sample: ("fake", "wrong", "The customer asked for the 20th.")}
    asked = json.dumps(judged.model.requests[-1]["body"])
    for shown in (RUBRIC, "change-due-date", "Change Q-1002's due date to 2026-11-13",
                  "the date came from the agent itself", "waiting on finance",
                  "its decider approved it"):
        assert shown in asked, shown
    [entry] = [e for e in judged.ledger() if e["kind"] == "model" and e["args"].get("judging")]
    assert (entry["args"]["judging"], entry["outcome"]["verdict"]) == (sample, "wrong")
    assert judge(judged)["judged"] == []  # once


def test_an_answer_that_isnt_a_grade_is_kept_as_none_and_not_asked_again(judged):
    [sample] = drawn(judged)
    judged.model.reply("I think it looks fine, mostly.")
    assert judge(judged)["judged"] == []
    assert verdicts(judged)[sample][1] is None
    asked = len(judged.model.requests)
    judge(judged)
    assert len(judged.model.requests) == asked


def test_the_judge_never_moves_a_cap(judged):
    raise_cap(judged)  # level 2 for billing's changes of due dates, from people's grades
    drawn(judged, 3)
    for _ in range(2):
        judged.model.reply(json.dumps({"grade": "critical", "why": "It harms the customer."}))
    judge(judged)
    judged.model.reply(json.dumps({"grade": "critical", "why": "It harms the customer."}))
    judge(judged)
    weigh(judged)
    assert cap(judged) == 2  # three critical verdicts, and no critical grade from people


def test_graders_never_see_a_verdict_before_they_grade(judged, database):
    [sample] = drawn(judged)
    judged.model.reply(json.dumps({"grade": "critical", "why": "It harms the customer."}))
    judge(judged)
    with (pytest.raises(psycopg.errors.InsufficientPrivilege),
          db.transaction(db.as_role(database, "channels")) as conn):
        conn.execute("select verdict from judgments")  # what serves the grading page
    with db.transaction(db.as_role(database, "channels")) as conn:
        assert conn.execute("select count(*) as n from judged_samples").fetchone()["n"] == 0
        conn.execute("update samples set grade = 'right', graded_by = 'dana', graded_at = now() "
                     "where id = %s", (sample,))
        assert [r["verdict"] for r in conn.execute("select verdict from judged_samples")] == [
            "critical"]  # once people graded it


def test_a5s_measures_how_far_the_judge_agrees_with_people(judged):
    for grade, said in (("right", "right"), ("right", "right"), ("wrong", "right"),
                        ("critical", "critical")):
        [sample] = drawn(judged, grade=grade)
        with db.transaction(judged.admin) as conn:
            judging.keep(conn, sample, "fake", said, "because", 10)
    with judged.client() as c:
        found = c.get("/measures", params={"days": 7}).json()
    assert found["judge"] == {"both": 4, "agreed": 3, "missed": 1, "false_alarms": 0,
                              "agreed_share": 0.75, "kappa": 0.556}


def test_a_judge_not_approved_for_all_its_agent_may_see_judges_nothing(judged, monkeypatch):
    fake = judged.gateway.models["fake"]
    monkeypatch.setitem(judged.gateway.models, "narrow", type(fake)(**{
        **{f: getattr(fake, f) for f in fake.__dataclass_fields__}, "alias": "narrow",
        "data_classes": ()}))
    found = judged.gateway.definitions["assistant"]
    monkeypatch.setitem(judged.gateway.definitions, "assistant", found.model_copy(
        update={"evaluation": Evaluation(judge="narrow")}))
    drawn(judged)
    asked = len(judged.model.requests)
    assert judge(judged)["judged"] == [] and len(judged.model.requests) == asked


def test_its_reply_is_read_strictly():
    assert judging.verdict('```json\n{"grade": "right", "why": " Fine.\\n "}\n```') == (
        "right", "Fine.")
    assert judging.verdict('{"grade": "mostly right", "why": "x"}') is None
    assert judging.verdict('{"grade": "wrong", "why": "' + "y" * 500 + '"}')[1] == "y" * 200
    assert judging.agreement({}) == {"both": 0, "agreed": 0, "missed": 0, "false_alarms": 0,
                                     "agreed_share": None, "kappa": None}
    assert judging.agreement({("right", "right"): 5})["kappa"] is None  # chance explains it all


def test_a_new_judge_needs_the_release_approver():
    from a5s.core import releases
    was = {"tools": [], "pins": {}, "model": "fake", "triggers": [], "schedules": [],
           "reports": [], "obligations": [], "autonomy": {"start": 1, "max": 1}, "channels": [],
           "reminders": False, "preferences": [], "budget": {}, "context": {}, "scope": "none",
           "judge": None}
    assert releases._widens_agent(was, {**was, "judge": "other"}) == [
        "has its work judged by another model"]  # its samples go to another model
    assert releases._widens_agent({**was, "judge": "other"}, was) == []  # nor any, now
    assert releases._widens_agent({k: v for k, v in was.items() if k != "judge"}, was) == []
