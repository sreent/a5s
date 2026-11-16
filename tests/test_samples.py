"""Samples, grades and the cap. Code draws samples of each release's changes; people outside
the team that built the agent grade them; and an anytime-valid sequential test raises a5s's
cap on its level to 2 once the grades show it meets the part's threshold, and lowers it when
they show it falls short, or at once on a critical error."""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs

import httpx
import pytest

from a5s import db
from a5s.contract import record_of
from a5s.core import samples
from conftest import CLIENT, accessible, seal_grades
from test_levels import asked, levelled
from test_proposals import decide, held, sweep
from test_ui_pages import shot


def drawn(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from samples order by id").fetchall()


def release(stack) -> str:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select release from instances where id = 'assistant-finance'"
                            ).fetchone()["release"]


def graded(stack, n: int, wrong: int = 0, critical: int = 0, part: str = "billing") -> None:
    """n graded samples of the assistant's changes of due dates, as graders would grade them."""
    with db.transaction(stack.admin) as conn:
        for i in range(n):
            grade = "critical" if i < critical else "wrong" if i < critical + wrong else "right"
            conn.execute(
                "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
                "part, action, said, records, acts_for, drawn_at, grade, graded_by, graded_at) "
                "values ('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, "
                "'assistant', %s, 'change-due-date', 'a change', '{}', '{ben}', now(), %s, "
                "'dana', %s)", (release(stack), part, grade, stack.gateway.clock()))
    seal_grades(stack)


def weigh(stack) -> list[dict]:
    with stack.client() as c:
        r = c.post("/samples/sweep")
    r.raise_for_status()
    return r.json()["changed"]


def cap(stack, part: str = "billing") -> int:
    with db.transaction(stack.admin) as conn:
        return samples.caps(conn, stack.gateway.cfg.seal_keys, release(stack)).get(
            (part, "change-due-date"), 1)


def grade(url: str, provider, sample: int, how: str, person: str = "dana") -> httpx.Response:
    """A grade, given as the studio gives it, with a sign-in made afresh to give it."""
    salt, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = person
    query = {"client_id": CLIENT, "redirect_uri": f"{url}/studio/", "state": "s",
             "nonce": samples.nonce({sample: how}, salt), "code_challenge": challenge.decode(),
             "code_challenge_method": "S256", "max_age": "0"}
    went = httpx.get(f"{provider.url}/auth", params=query)
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    token = httpx.post(f"{url}/studio/sign-in/token", json={  # as the studio signs in
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/studio/"}).json()["id_token"]
    return httpx.post(f"{url}/grade/samples", json={"grades": {str(sample): how}, "salt": salt},
                      headers={"Authorization": f"Bearer {token}"})


@pytest.mark.parametrize("threshold, errors, items", [(0.98, 0, 224), (0.95, 0, 88),
                                                       (0.98, 1, 340), (0.95, 1, 134)])
def test_the_items_a_level_up_needs(threshold, errors, items):
    assert samples.needed(threshold, errors) == items
    assert not samples.shows(items - 1, errors, threshold, "up")


def test_the_test_tells_falling_short_too():
    assert samples.shows(40, 10, 0.95, "down") and not samples.shows(40, 1, 0.95, "down")
    assert not samples.shows(0, 0, 0.95, "up")


def test_a_decided_change_is_drawn_for_grading_and_a_lapsed_one_isnt(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    [s] = drawn(stack)
    assert (s["kind"], s["part"], s["action"], s["decided"], s["decided_by"], s["grade"]) == (
        "proposal", "billing", "change-due-date", "approve", "ana", None)
    assert s["records"]["Q-1002"]["fields"]["status"] == "waiting on finance"
    stack.at("2026-11-02T09:30:00+00:00")
    asked(stack)
    stack.at("2026-11-20T10:00:00+00:00")
    sweep(stack)  # it lapses: nobody decided it, so it's no evidence
    assert len(drawn(stack)) == 1


def test_a_change_made_at_level_2_is_drawn_until_a_quarter_has_100(stack, approving):
    levelled(stack)
    asked(stack)
    [s] = drawn(stack)
    assert (s["kind"], s["decided"]) == ("action", None)
    assert s["records"]["Q-1002"]["fields"]["due date"] == "2026-11-06"  # as it stood before
    with db.transaction(stack.admin) as conn:  # a quarter's 100 drawn already
        conn.execute("update samples set drawn_at = %s", (stack.gateway.clock(),))
        for _ in range(99):
            conn.execute("insert into samples (scenario, kind, run_id, instance_id, release, "
                         "definition, part, action, said, records, acts_for, drawn_at) select "
                         "scenario, kind, run_id, instance_id, release, definition, part, action, "
                         "said, records, acts_for, drawn_at from samples limit 1")
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
          said="Move Q-1002 to 2026-11-20.")
    assert len(drawn(stack)) == 100 and record_of(stack.gateway.scenario, "Q-1002").fields[
        "due date"] == "2026-11-20"


def test_only_graders_from_outside_the_team_who_had_no_part_in_it_grade(stack, approving,
                                                                        provider):
    asked(stack)
    [p] = held(stack)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    [s] = drawn(stack)
    review = httpx.post(f"{approving}/grade/review",
                        headers={"Authorization": f"Bearer {provider.id_token(person='dana')}"})
    assert [x["id"] for x in review.json()["samples"]] == [s["id"]]
    assert grade(approving, provider, s["id"], "right", "priya").status_code == 403  # not a grader
    scenario = stack.gateway.scenario
    for who, why in (("ben", "asked for or decided"), ("ana", "asked for or decided")):
        person = scenario.person(who)
        assert why in samples.may_grade(scenario, s, person.__class__(
            **{**person.__dict__, "roles": (*person.roles, "grader")}))
    builder = scenario.person("priya")
    assert "outside the team that built" in samples.may_grade(scenario, s, builder.__class__(
        **{**builder.__dict__, "roles": (*builder.roles, "grader")}))
    auditor = scenario.person("kofi")
    assert "may not see" in samples.may_grade(scenario, s, auditor.__class__(
        **{**auditor.__dict__, "roles": (*auditor.roles, "grader")}))
    assert grade(approving, provider, s["id"], "brilliant").status_code == 400
    assert grade(approving, provider, s["id"], "right").status_code == 200
    assert grade(approving, provider, s["id"], "wrong").status_code == 409  # once
    [s] = drawn(stack)
    assert (s["grade"], s["graded_by"]) == ("right", "dana")


def test_grades_that_meet_the_threshold_raise_the_cap_and_level_2_acts(stack, approving):
    levelled(stack, cap=0)
    asked(stack)
    assert record_of(stack.gateway.scenario, "Q-1002").fields["due date"] == "2026-11-06"  # held
    graded(stack, 223)
    assert weigh(stack) == [] and cap(stack) == 1  # one short of 224, for 98%
    graded(stack, 1)
    [raised] = weigh(stack)
    assert (raised["cap"], raised["graded"], raised["errors"], raised["threshold"]) == (2, 224, 0, 0.98)
    assert cap(stack) == 2
    [entry] = [e for e in stack.ledger() if e["kind"] == "cap"]
    assert entry["action"] == "raise" and entry["args"]["why"].startswith("graded samples show")
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
          said="Move Q-1002 to 2026-11-20.")
    assert record_of(stack.gateway.scenario, "Q-1002").fields["due date"] == "2026-11-20"


def test_a_critical_error_lowers_the_cap_at_once(stack):
    graded(stack, 224)
    weigh(stack)
    assert cap(stack) == 2
    stack.at("2026-10-28T12:05:00+00:00")  # graded after the cap rose
    graded(stack, 1, critical=1)
    [lowered] = weigh(stack)
    assert (lowered["cap"], lowered["why"]) == (1, "a critical error")
    assert cap(stack) == 1


def test_grades_that_fall_short_lower_the_cap(stack):
    graded(stack, 224)
    weigh(stack)
    stack.at("2026-10-28T12:05:00+00:00")  # graded after the cap rose: a fresh test
    graded(stack, 60, wrong=30)
    [lowered] = weigh(stack)
    assert lowered["cap"] == 1 and lowered["why"] == "graded samples show it falls short"


def test_a_part_with_no_threshold_never_earns_level_2(stack):
    graded(stack, 400, part="orders")  # the sample's settings give orders 95%: take it away
    weigh(stack)
    assert cap(stack, "orders") == 2
    graded(stack, 400, part="refunds")  # a part the settings give no threshold
    weigh(stack)
    assert cap(stack, "refunds") == 1


def test_a_decider_whose_approvals_are_graded_wrong_far_more_is_flagged(stack):
    """Only once the data protection officer agrees, which the deployment says (O6)."""
    with stack.client() as c:
        assert c.get("/status").json()["samples"]["rubber_stamps"] is None  # off, by default
    assert not stack.settle(data_protection={"flag_rubber_stamps": True},
                            signers=("ana", "noor")).refused
    with db.transaction(stack.admin) as conn:
        for who, wrong, right in (("ana", 4, 2), ("omar", 1, 30)):
            for i in range(wrong + right):
                conn.execute(
                    "insert into samples (scenario, kind, run_id, instance_id, release, "
                    "definition, part, action, said, records, acts_for, decided, decided_by, "
                    "drawn_at, grade, graded_by, graded_at) values ('sample', 'proposal', "
                    "gen_random_uuid(), 'assistant-finance', 'r', 'assistant', 'billing', "
                    "'change-due-date', 'a change', '{}', '{ben}', 'approve', %s, now(), %s, "
                    "'dana', now())", (who, "wrong" if i < wrong else "right"))
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["samples"]["rubber_stamps"] == [{"person": "ana", "approved": 6, "graded_wrong": 4}]


def test_the_grading_page_runs_only_its_own_script_and_shows_only_text(approving):
    went = httpx.get(f"{approving}/grade/")  # a link, as it was
    assert (went.status_code, went.headers["location"]) == (303, "/studio/grade")
    page = httpx.get(f"{approving}/studio/grade")  # the studio's, now
    assert page.status_code == 200 and httpx.get(f"{approving}/grade/grade.js").status_code == 404
    policy = page.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe" not in policy


def test_a_grader_grades_in_the_browser(stack, approving, provider, browser):
    asked(stack)
    [p] = held(stack)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    provider.person = "dana"
    page = browser.new_page()
    page.goto(f"{approving}/studio/grade")
    page.wait_for_selector("[data-sample] >> text=Q-1002", timeout=30000)
    assert page.inner_text("#me").endswith("Dana Price")
    # On the card decisions are made on: who did it, what it did in code's words, and how it went
    sample = page.locator("[data-sample]")
    assert sample.locator(".who-name").inner_text() == "The assistant asked"
    assert sample.locator(".who-about").inner_text().startswith("change-due-date in billing · sampled ")
    assert sample.locator("h2").inner_text().startswith("Change a customer question's due date: Q-1002")
    assert sample.locator(".badge").inner_text() == "approved"
    assert sample.get_by_role("link", name="Open Q-1002").get_attribute("href").endswith("/Q-1002")
    # The grade chosen shows, and choosing it again takes it back
    right = sample.get_by_role("button", name="Right")
    right.click()
    assert right.get_attribute("aria-pressed") == "true"
    accessible(page)
    shot(page, "grade")
    right.click()
    assert right.get_attribute("aria-pressed") == "false"
    right.click()
    page.click("#send")
    page.wait_for_selector("#status >> text=Graded right", timeout=30000)
    assert drawn(stack)[0]["grade"] == "right"
