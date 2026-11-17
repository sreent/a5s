"""Round 15, the smaller findings: a flagged change is decided on its own (B5); a draft's pull
request says what its agent may do (C7); a shadow's grader comes from outside the teams that
built either agent compared (C8); nobody grades a
change made for their own team, or for someone they report to (C9); the auditors' report says
which, a suspension or a resumption (D15); and someone who leaves goes from others' drafts
(E9), with the versions of the settings they asked for, which go after the officer's kept_for
too (E10)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from a5s import db
from a5s.core import audit, samples, shadows
from test_departures import MONDAY, TUESDAY
from test_departures import sweep as departures_sweep
from test_drafts import as_
from test_proposals import asked, decide, held, invented
from test_retention import sweep as retention_sweep

NOT_THEIRS = "nobody grades a change made for their own team, or for someone they report to"


def test_a_flagged_change_is_decided_on_its_own(stack, approving, provider):
    """The assistant wrote the date itself, which its deciders are told to look at: ticked
    with another, it would be approved in a blink (B5)."""
    call, _ = invented()
    asked(stack, call, said="Please move Q-1002 out a week.")
    asked(stack, ("close_question", {"key": "Q-1001"}), said="And close Q-1001.")
    flagged, plain = held(stack)
    assert flagged["flags"] and flagged["sensitive"] and not plain["sensitive"]
    together = decide(approving, provider, [flagged["digest"], plain["digest"]])
    assert together.status_code == 409 and "on its own" in together.json()["detail"]
    assert decide(approving, provider, [flagged["digest"]]).status_code == 200


def test_nobody_grades_a_change_made_for_their_team_or_someone_above_them(stack):
    """Dana grades; the change was made for Ben, of finance (C9)."""
    scenario = stack.gateway.scenario
    dana = scenario.person("dana")
    sample = {"definition": "assistant", "acts_for": ["ben"], "records": {}, "deciders": [],
              "decided_by": None}
    assert samples.may_grade(scenario, sample, dana) is None
    assert samples.may_grade(scenario, sample, replace(dana, team="finance")) == NOT_THEIRS
    assert samples.may_grade(scenario, sample, replace(dana, manager="ben")) == NOT_THEIRS


def test_who_built_the_version_at_work_never_grades_its_challenger(stack, monkeypatch):
    """Tomas works with Priya, who owns the assistant: he grades nothing of a shadow that
    answers beside it, whose agent his team didn't build (C8)."""
    people = stack.gateway.scenario._people
    tomas = replace(people["tomas"], roles=(*people["tomas"].roles, samples.GRADER))
    monkeypatch.setitem(people, "tomas", tomas)
    pair = {"definition": "assistant-next", "agent": "assistant", "acts_for": ["ben"],
            "records": [], "instance_id": "assistant-next-finance",
            "shadows": "assistant-finance", "live_run_id": uuid.uuid4(), "run_id": uuid.uuid4()}
    with db.transaction(stack.admin) as conn:
        why = shadows.why_not(conn, stack.gateway.scenario, pair, tomas)
    assert why == "graders come from outside the team that built the assistant"


def test_the_report_says_whether_an_instance_was_suspended_or_resumed():
    assert (audit.ADMIN["suspend"], audit.ADMIN["resume"]) == (
        "suspended an instance", "resumed an instance")  # (D15)


def test_someone_who_left_goes_from_others_drafts_and_their_asks_of_the_settings(
        stack, approving, provider, monkeypatch):
    """Priya plans her draft to serve Ana and Ben; Ben asked for a version of the settings.
    He leaves: her draft serves Ana alone, and what he asked for goes (E9, E10)."""
    stack.model.reply("Noted, Ben.")
    stack.say("I'm Ben, and I'm leaving on Friday.", person="ben")
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    plan = {"parts": ["billing"], "serves": ["ana", "ben"]}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}",
                 {"files": draft["files"], "plan": plan}).status_code == 200
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into settings_requests (scenario, person, raw) values "
                     "('sample', 'ben', 'serial: 99'), ('sample', 'ana', 'serial: 98')")
    people = dict(stack.gateway.scenario._people)
    del people["ben"]  # he leaves
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    stack.at(MONDAY)
    departures_sweep(stack)
    stack.at(TUESDAY)
    assert departures_sweep(stack)["archived"] == 1
    assert priya("GET", f"/studio/api/drafts/{draft['id']}").json()["plan"]["serves"] == ["ana"]
    with db.transaction(stack.admin) as conn:
        assert [r["person"] for r in conn.execute("select person from settings_requests")] == [
            "ana"]
        conn.execute("update settings_requests set asked_at = now() - interval '13 months'")
    assert retention_sweep(stack).get("asks") == 1  # Ana's, after kept_for


def test_a_drafts_pull_request_says_what_the_agent_may_do(stack, approving, provider):
    """Its reviewers read who must sign, and what the agent may do: its tools, how far it
    acts, and what starts it besides people (C7)."""
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    body = priya("GET", f"/studio/api/drafts/{draft['id']}/pull-request").json()["body"]
    may = body.split("## What it may do", 1)[1]
    assert "- It uses change_due_date, close_question in changes." in may
    assert "- It uses create_draft in documents." in may
    assert "- It may work at level 2, making a type of change on its own" in may
    assert "- It takes on long tasks, over days, once someone says yes." in may
