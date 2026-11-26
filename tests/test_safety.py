"""Risk, and the friction it earns (docs/design.md; Ocean's EnvironmentBand, ActingAs and
ActionZone): what a press will do, said where it happens, on whichever page.

Which deployment this is, across the top of every page, whoever's signed in and before anyone
is: production in the change's colour, filled, a staging, a test or someone's own machine in
amber, with its name and what that means. The classic mistake isn't made on an administrator's
page: it's doing in production what was meant for a test. A deployment nobody named is taken as
production until someone does, and the doctor says to name it (core/environment.py).

Whose power a page uses, first on each page that changes things while it holds an act a role
gives someone: the role its acts count as, by the rules that let them, and what that lets them
do there. A page that only shows says none, nor one whose acts are someone's own, so the line
always means a role's power is in use (core/acting.py)."""

from __future__ import annotations

import httpx
import pytest

from a5s import config, doctor
from a5s.contract import Person
from a5s.core import acting, environment, suspension
from a5s.core import studio_models as shapes
from conftest import accessible
from test_agent_asks import send
from test_personas import arrive
from test_proposals import asked


def named(monkeypatch, kind: str | None, name: str | None = None) -> None:
    for var, value in (("A5S_ENVIRONMENT", kind), ("A5S_ENVIRONMENT_NAME", name)):
        if value is None:
            monkeypatch.delenv(var, raising=False)
        else:
            monkeypatch.setenv(var, value)


def test_a_deployment_says_its_kind_and_name_and_one_nobody_named_is_taken_as_production(
        monkeypatch):
    named(monkeypatch, None)
    assert environment.here(development=True) == {
        "kind": "development", "name": "Development", "named": True,
        "about": "On this machine, for development: a5s takes people's word for who they are."}
    unnamed = environment.here(development=False)
    assert (unnamed["kind"], unnamed["name"], unnamed["named"]) == (
        "production", "Unnamed deployment", False)
    assert unnamed["about"].startswith("Treat what you do here as real")
    named(monkeypatch, "test", "Pilot test")
    assert environment.here(development=False) == {
        "kind": "test", "name": "Pilot test", "named": True,
        "about": "A test: what you do here reaches its test accounts and made-up records alone."}
    named(monkeypatch, "production")  # named, even beside `a5s dev`
    assert environment.here(development=True)["name"] == "Production"
    named(monkeypatch, "live")
    with pytest.raises(config.ConfigError, match="production, staging or test"):
        environment.here(development=False)


def test_the_band_asks_no_sign_in_and_says_nothing_more(approving, monkeypatch):
    named(monkeypatch, "staging", "Pilot staging")
    answer = httpx.get(f"{approving}/shell/environment", timeout=30)
    assert answer.status_code == 200
    assert answer.json() == {"kind": "staging", "name": "Pilot staging", "named": True,
                             "about": environment.ABOUT["staging"]}


def test_the_doctor_says_to_name_a_deployment_nobody_named(monkeypatch):
    named(monkeypatch, None)
    [unnamed] = doctor._deployment(development=False)
    assert unnamed.state == "look" and "set A5S_ENVIRONMENT to production, staging or test" \
        in unnamed.said
    named(monkeypatch, "production", "Production")
    [found] = doctor._deployment(development=False)
    assert found.state == "ok" and found.said == (
        "Every page's band says this is Production, a production deployment.")


def test_every_page_says_which_deployment_this_is_from_before_sign_in(approving, provider,
                                                                      browser, monkeypatch):
    named(monkeypatch, "production")
    before = browser.new_page()
    before.goto(f"{approving}/studio/")  # before anyone signs in: the band is there already
    before.wait_for_selector("#environment", timeout=30000)
    assert before.get_attribute("#environment", "class") == "env-band production"
    before.close()
    page, broken = arrive(browser, approving, provider, "priya")
    band = page.locator("#environment")
    assert band.get_attribute("class") == "env-band production"
    assert band.inner_text().split("\n")[0].startswith("Production")
    assert "Real people and records: what you do here reaches them." in band.inner_text()
    page.mouse.wheel(0, 2000)  # still across the top as the page scrolls, the sidebar below it
    page.wait_for_timeout(200)
    assert band.bounding_box()["y"] == 0
    assert page.locator(".sidebar").bounding_box()["y"] >= band.bounding_box()["height"]
    accessible(page)
    page.goto(f"{approving}/chat/")  # and the web chat's, which the plain shell frames
    page.wait_for_selector("#environment", timeout=30000)
    assert page.get_attribute("#environment", "class") == "env-band production"
    assert not broken, broken


def test_a_test_says_so_in_amber_and_development_says_its_machine(approving, provider, browser,
                                                                  monkeypatch):
    named(monkeypatch, "test", "Pilot test")
    page, broken = arrive(browser, approving, provider, "ana")
    assert page.get_attribute("#environment", "class") == "env-band test"
    assert page.locator("#environment strong").inner_text() == "Pilot test"
    accessible(page)
    assert not broken, broken


# Whose power a page uses

def someone(*roles: str, id: str = "sam", team: str = "sales") -> Person:
    return Person(id=id, name="Sam Lee", team=team, roles=roles)


def test_the_line_names_the_roles_a_pages_acts_count_as_and_none_without_one():
    ana = someone("instance-approver", "part-owner:billing", id="ana")
    assert acting.deciding(ana, [["billing"]]) == {"role": "Owner of billing",
                                                   "lets": acting.DECIDES}
    assert acting.deciding(ana, [["billing"], []])["role"] == (
        "Owner of billing and Instance approver")  # a change in no part is the approver's
    assert acting.deciding(someone("part-delegate:orders"), [["orders"]])["role"] == (
        "Delegate in orders")
    assert acting.deciding(someone(), [["billing"]]) is None  # told of it, as a manager
    grader = someone("grader")
    assert acting.grading(grader) == {"role": "Grader", "lets": acting.GRADES}
    assert acting.grading(grader, shadows=True)["lets"] == acting.SHADOWS
    assert acting.grading(ana) is None
    assert acting.officer(someone("data-protection-officer"))["role"] == "Data protection officer"
    assert acting.officer(ana) is None
    assert acting.undoing(ana, "billing")["role"] == "Owner of billing"
    assert acting.undoing(ana, None)["role"] == "Instance approver"
    assert acting.undoing(grader, "billing") is None
    assert acting.answering("service-desk", "Ben Okafor") == {
        "role": "one of the service-desk team",
        "lets": "what you write here goes to Ben Okafor in their chat, with your name"}


def test_approving_names_the_roles_a_version_needs_of_them_else_those_they_approve_by():
    ana = someone("instance-approver", "part-owner:billing", id="ana")
    assert acting.approving(ana, ["part-owner:billing", "part-owner:orders"])["role"] == (
        "Owner of billing")  # what it needs of hers, never what it needs of others
    assert acting.approving(ana, [])["role"] == "Instance approver and Owner of billing"
    assert acting.approving(someone("grader"), []) is None


class Nobody:
    """A directory with nobody in it, for whom suspended an instance."""

    @staticmethod
    def person(_: str) -> None:
        return None


def test_suspending_says_why_its_theirs_by_the_rules_that_let_them():
    inst = {"id": "assistant-finance", "definition": "assistant", "owner": "ana", "deputy": "ben",
            "parts": {"billing": {}}, "status": "active", "suspended_by": None}
    suspended = {**inst, "status": "suspended", "suspended_by": "sam"}
    cases = [
        (someone(id="ana"), inst, "suspend", "Owner of this instance"),
        (someone("agent-owner:assistant", id="ben"), inst, "suspend",
         "Deputy for this instance and Owner of the assistant"),
        (someone("part-delegate:billing"), inst, "suspend", "Delegate in billing"),
        (someone(team="platform"), inst, "suspend", "one of the team that runs a5s"),
        (someone("grader"), inst, "suspend", None),
        (someone(), suspended, "resume", "the one who suspended it"),
        (someone("release-approver", id="rosa", team="risk"), suspended, "resume",
         "Release approver"),
        (someone(id="ana"), suspended, "resume", None),  # not hers to lift
    ]
    for person, stands, action, role in cases:
        line = acting.suspending(person, stands, action, "platform")
        assert (line and line["role"]) == role, (person.id, person.roles, action)
        # and the line is there exactly where the rules let them do it
        assert (line is not None) == (suspension.may(Nobody, person, stands, action,
                                                     "platform") is None)


ACTS = {"DecideNow", "GradeNow", "Shadows", "VersionReview", "Standing", "ChangeMade",
        "Handover", "NotebookNow", "OfficerNow"}


def test_only_the_answers_of_pages_that_change_things_carry_the_line():
    carrying = {name for name, shape in vars(shapes).items()
                if isinstance(shape, type) and issubclass(shape, shapes.Shape)
                and "acting" in shape.model_fields}
    assert carrying == ACTS  # never Home, Agents, Administration, Audit, Spending or Status


def test_the_officers_page_says_they_act_as_the_officer_and_turns_others_away(approving,
                                                                              provider):
    found = send(approving, provider, "noor", "GET", "/officer/api")
    assert found.status_code == 200
    assert found.json() == {"you": "Noor Rahman", "acting": {
        "role": "Data protection officer", "lets": acting.OFFICER}}
    refused = send(approving, provider, "ana", "GET", "/officer/api")
    assert refused.status_code == 403
    assert "only the data protection officer" in refused.json()["detail"]


def test_an_instances_page_says_why_its_theirs_to_suspend_and_says_none_to_others(
        approving, provider):
    path = "/studio/api/instances/assistant-finance/standing"
    owner = send(approving, provider, "ana", "GET", path).json()
    assert owner["may"] == "suspend"
    assert owner["acting"] == {"role": "Owner of this instance and Owner of billing",
                               "lets": acting.SUSPENDS}
    agents = send(approving, provider, "priya", "GET", path).json()
    assert agents["acting"]["role"] == "Owner of the assistant and one of the team that runs a5s"


def test_a_page_that_changes_things_says_whose_power_it_uses_and_one_that_shows_doesnt(
        stack, approving, provider, browser):
    asked(stack)  # Ben asks for a change in billing, which Ana owns and decides
    page, broken = arrive(browser, approving, provider, "ana")
    assert page.locator("#acting-as").count() == 0  # Home only shows
    page.goto(f"{approving}/studio/decide")
    page.wait_for_selector(".approval", timeout=30000)
    line = page.locator("#acting-as")
    line.wait_for(timeout=30000)
    assert ("Acting as Owner of billing: what you approve here, the agent that asked for it "
            "does in its records") in line.inner_text()
    page.wait_for_function("document.querySelector('#acting-as .avatar').textContent === 'AO'",
                           timeout=30000)
    assert line.bounding_box()["y"] < page.locator("h1").bounding_box()["y"]  # before its head
    accessible(page)
    page.goto(f"{approving}/studio/admin")  # a page that only shows
    page.wait_for_selector("#roles", timeout=30000)
    assert page.locator("#acting-as").count() == 0
    page.goto(f"{approving}/studio/officer")  # not hers: refused, and no form to fill
    page.wait_for_selector("p.problem", timeout=30000)
    assert page.locator("#acting-as").count() == 0 and page.locator("#ask").count() == 0
    assert not broken, broken


def test_the_officer_reads_whose_power_their_page_uses(approving, provider, browser):
    page, broken = arrive(browser, approving, provider, "noor")
    page.goto(f"{approving}/studio/officer")
    page.wait_for_selector("#ask", timeout=30000)
    assert "Acting as Data protection officer: what you ask here, a5s exports, or erases for " \
        "good, about one person" in page.inner_text("#acting-as")
    accessible(page)
    assert not broken, broken
