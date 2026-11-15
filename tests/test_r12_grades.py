"""Round 12 of the critique: who grades an agent's work, and what its judge reads (docs/critique.md,
round 12, B1-B3, B7, B8). The gateway seals a grade only once it has checked, itself, that its
grader may give it, at most 20 a sign-in, whatever the channels app recorded; an agent's authors
and those who drafted it built it, as its owners did; a grade counts from when the core sealed
it, so one given before a cap changed but sealed after is weighed; everyone who decided a change
is kept on each of its samples; and a judge reads a sample only if it's approved for every class
of data the settings name."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import replace
from datetime import timedelta

import pytest
from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import approvals, drafts, samples
from conftest import SEAL_KEY
from test_classes import resettle
from test_judging import judge, judged  # noqa: F401 - judged is the fixture
from test_samples import cap, graded, release, weigh


def ungraded(stack, n: int) -> list[int]:
    """n samples of the assistant's changes of due dates in billing, which Ana decided."""
    with db.transaction(stack.admin) as conn:
        return [conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, part, "
            "action, said, records, acts_for, decided, decided_by, drawn_at) values "
            "('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, 'assistant', "
            "'billing', 'change-due-date', 'a change', '{}', '{ben}', 'approve', 'ana', now()) "
            "returning id", (release(stack),)).fetchone()["id"] for _ in range(n)]


def recorded(stack, provider, database, ids: list[int], person: str, grade: str = "right",
             at=None) -> None:
    """What the channels app records, as its role may write it, when `person` really signs in
    to give `grade` to each of `ids`: whatever its page would have refused."""
    salt = secrets.token_urlsafe(32)
    grades = dict.fromkeys(ids, grade)
    token = provider.id_token(samples.nonce(grades, salt), person, int(time.time()))
    hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
    with db.transaction(db.as_role(database, "channels")) as conn:
        conn.execute(
            "update samples set grade = %s, graded_by = %s, graded_at = %s, grade_token = %s, "
            "grade_nonce = %s, grade_salt = %s, grade_issuer = %s, grade_subject = %s, "
            "grade_proof = %s where id = any(%s)",
            (grade, person, at or stack.gateway.clock(), hashed, samples.nonce(grades, salt), salt,
             provider.url, f"u-{person}", token, ids))


def sealed(stack) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select count(*) as n from samples where grade_seal is not null"
                            ).fetchone()["n"]


def refusals(stack) -> list[str]:
    return [e["args"]["what"] for e in stack.ledger() if e["action"] == "refuse-sign-in"]


def test_the_gateway_seals_no_grade_its_grader_may_not_give(stack, approving, provider, database):
    """Priya owns the assistant, and grades nobody's work: a sign-in of hers, recorded by a
    channels app broken into, for 224 grades of right, raises nothing."""
    recorded(stack, provider, database, ungraded(stack, 20), "priya")
    weigh(stack)  # seals what the channels app recorded, then weighs it
    assert sealed(stack) == 0 and cap(stack) == 1
    assert any("Priya" in why and "doesn't grade agents' work" in why for why in refusals(stack))


def test_one_sign_in_gives_twenty_grades_at_most(stack, approving, provider, database):
    recorded(stack, provider, database, ungraded(stack, 224), "dana")  # a grader, from quality
    weigh(stack)
    assert sealed(stack) == 0 and cap(stack) == 1
    assert any("from one to 20 grades, not 224" in why for why in refusals(stack))
    recorded(stack, provider, database, ungraded(stack, 20), "dana")
    weigh(stack)
    assert sealed(stack) == 20  # as the page gives them


def test_a_sign_in_s_grades_are_all_its_own_person_s(stack, approving, provider, database):
    ids = ungraded(stack, 2)
    recorded(stack, provider, database, ids, "dana")
    with db.transaction(db.as_role(database, "channels")) as conn:
        conn.execute("update samples set graded_by = 'priya' where id = %s", (ids[1],))
    weigh(stack)
    assert sealed(stack) == 0
    assert any("aren't all by one person" in why for why in refusals(stack))


def test_an_agent_s_authors_and_drafters_built_it(stack):
    scenario = stack.gateway.scenario
    dana = scenario.person("dana")
    sample = {"definition": "assistant", "acts_for": ["ben"], "decided_by": "ana",
              "records": {"Q-1002": None}}
    assert samples.may_grade(scenario, sample, dana) is None
    author = replace(dana, roles=(*dana.roles, f"{drafts.AGENT_AUTHOR}:assistant"))
    assert "outside the team that built the assistant" in samples.may_grade(
        scenario, sample, author)
    with db.transaction(stack.admin) as conn:  # Dana drafted it, then handed it to Priya
        conn.execute("insert into agent_drafts (person, agent, based_on, files, before) values "
                     "('priya', 'assistant', 'blank', '{}', %s)",
                     (Jsonb([{"person": "dana", "at": "2026-11-01T09:00:00+00:00",
                              "how": "handed"}]),))
        drafters = samples.drafted(conn, "assistant")
    assert drafters == {"priya", "dana"}
    assert "outside the team that built" in samples.may_grade(scenario, sample, dana, (), drafters)


def test_everyone_who_decided_a_change_is_kept_on_its_samples(stack):
    """A change in billing and orders, approved by Ana for billing and Omar for orders: neither
    grades its samples, nor anyone who reports to either."""
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        for part in ("billing", "orders"):
            assert samples.draw(conn, (SEAL_KEY,), "sample", "proposal", release(stack),
                                "assistant", "assistant-finance", "00000000-0000-0000-0000-000000000001",
                                part, "change-due-date", "a change", {}, ["ben"],
                                stack.gateway.clock(), decided="approve", decided_by=["ana", "omar"])
        drawn = conn.execute("select decided_by, deciders from samples order by id").fetchall()
    assert [(r["decided_by"], r["deciders"]) for r in drawn] == [("ana", ["ana", "omar"])] * 2
    omar = scenario.person("omar")
    grader = replace(omar, roles=(*omar.roles, samples.GRADER), team="quality")
    assert samples.may_grade(scenario, dict(drawn[1], definition="assistant", acts_for=["ben"],
                                            records={}), grader) == (
        "nobody grades a change they asked for or decided")
    below = replace(scenario.person("dana"), manager="omar")
    assert samples.may_grade(scenario, dict(drawn[1], definition="assistant", acts_for=["ben"],
                                            records={}), below) == (
        "nobody grades the decisions of someone they report to")


def test_a_grade_given_before_a_cap_rose_but_sealed_after_is_weighed(stack, approving, provider,
                                                                     database):
    graded(stack, 224)
    weigh(stack)
    assert cap(stack) == 2
    rose = stack.gateway.clock()
    [late] = ungraded(stack, 1)  # recorded a minute before the cap rose, sealed after it
    recorded(stack, provider, database, [late], "dana", "critical", at=rose - timedelta(minutes=1))
    stack.at((rose + timedelta(minutes=1)).isoformat())  # the next sweep's
    weigh(stack)
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select sealed_at, graded_at from samples where id = %s",
                           (late,)).fetchone()
    assert row["sealed_at"] > row["graded_at"]
    assert cap(stack) == 1  # a critical error, weighed


@pytest.fixture
def classified(judged):  # noqa: F811 - the fixture, by name
    """The sample's settings with whom a record is for as personal: the agent's own model, for
    made-up data, never sees it."""
    resettle(judged, classified={"customer": "personal"})
    return judged


def drawn(stack) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, part, "
            "action, said, records, acts_for, decided, decided_by, drawn_at) values "
            "('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, 'assistant', "
            "'billing', 'change-due-date', 'Change Q-1002''s due date: tell ben@northwind.test', "
            "%s, '{ben}', 'approve', 'ana', now()) returning id",
            (release(stack), Jsonb({"Q-1002": {"key": "Q-1002", "customer": "Northwind"}}))
        ).fetchone()["id"]


def test_a_judge_reads_no_sample_with_data_of_a_class_it_isnt_approved_for(classified):
    """A sample's change, and its records, as its decider read them: with the values its
    handles stood for, and every field."""
    drawn(classified)
    asked = len(classified.model.requests)
    assert judge(classified)["judged"] == [] and len(classified.model.requests) == asked
    fake = classified.gateway.models["fake"]
    classified.gateway.models["fake"] = replace(fake, data_classes=(*fake.data_classes, "personal"))
    classified.model.reply(json.dumps({"grade": "right", "why": "As the customer asked."}))
    assert [v["verdict"] for v in judge(classified)["judged"]] == ["right"]
