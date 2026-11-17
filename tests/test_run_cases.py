"""A run kept as one of its agent's test cases (core/run_cases.py): what someone said to it,
masked by code and checked by the agent's author, in their draft, once the data protection
officer agrees."""

from dataclasses import replace

import httpx
import yaml

from a5s import db
from a5s.core import run_cases
from conftest import accessible

SAID = ("Hi, I'm Ana Ortiz (ana.ortiz@example.com, +44 20 7946 0958). My account is "
        "12345678: which questions mention an invoice? See https://intranet.example/x")


def owning(stack, person: str = "ana") -> None:
    """Make someone an owner of the assistant too, in the directory: who watches its instance
    and sees billing's records, so may see its runs, and author it."""
    found = stack.gateway.scenario._people[person]
    stack.gateway.scenario._people[person] = replace(
        found, roles=(*found.roles, "agent-owner:assistant"))


def agreed(stack, cases: bool = True) -> None:
    """The data protection officer agrees to test cases from real runs, and to the studio
    naming people, so it shows the runs of an instance serving as few as the sample's does."""
    assert not stack.settle(data_protection={"cases_from_runs": cases, "studio_names": True},
                            signers=("ana", "noor")).refused


def a_run(stack) -> str:
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    stack.say(SAID)
    with db.transaction(stack.admin) as conn:
        return conn.execute("select id::text as id from runs order by opened_at desc "
                            "limit 1").fetchone()["id"]


def as_person(approving: str, provider, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.request(method, f"{approving}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token}"})


def test_code_masks_what_could_say_who_anyone_is_and_keeps_keys_amounts_and_dates(stack):
    said, masked = run_cases.mask(
        "Ana Ortiz (ana.ortiz@example.com, +44 20 7946 0958, account 12345678) asks about "
        "Q-1001: £860.00, due 2026-11-06. ana says see https://intranet.example/x",
        stack.gateway.scenario, ["ana"])
    assert said == ("[someone] [someone] ([an email], [a number], account [a number]) asks about "
                    "Q-1001: £860.00, due 2026-11-06. [someone] says see [a link]")
    assert masked == {"emails": 1, "links": 1, "names": 3, "numbers": 2}


def test_no_run_becomes_a_test_case_until_the_officer_agrees(stack, approving, provider):
    owning(stack)
    agreed(stack, cases=False)
    run = a_run(stack)
    refused = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case")
    assert refused.status_code == 403
    assert "data protection officer hasn't agreed" in refused.json()["detail"]


def test_its_author_keeps_a_run_masked_in_their_draft(stack, approving, provider):
    owning(stack)
    agreed(stack)
    run = a_run(stack)
    offered = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case")
    assert offered.status_code == 200, offered.text
    found = offered.json()
    assert found["say"].startswith("Hi, I'm [someone] [someone] ([an email], [a number]).")
    assert "[a link]" in found["say"] and found["uses"] == ["search_records"]
    assert found["answer"] == "Q-1001 mentions an invoice." and found["agent"] == "assistant"
    unchecked = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case",
                          {"name": "Invoices", "speaker": "ben", "say": found["say"]})
    assert unchecked.status_code == 409 and "says nothing about anyone" in unchecked.json()["detail"]
    kept = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case", {
        "name": "Invoices", "speaker": "ben", "say": SAID,  # unmasked: it's masked again
        "judged": "It names Q-1001.", "checked": True})
    assert kept.status_code == 200, kept.text
    body = kept.json()
    assert body["file"] == run_cases.FILE and body["case"]["speaker"] == "ben"
    with db.transaction(stack.admin) as conn:
        draft = conn.execute("select files, person, agent from agent_drafts where id = %s",
                             (body["draft"],)).fetchone()
    assert (draft["person"], draft["agent"]) == ("ana", "assistant")
    [case] = yaml.safe_load(draft["files"][run_cases.FILE])
    assert case["name"] == "Invoices" and case["as"] == "ben"
    assert case["from_run"] is True  # so only models approved for the deployment's data read it
    [step] = case["steps"]
    assert "Ortiz" not in step["say"] and "ana.ortiz@" not in step["say"]
    assert (step["uses"], step["judged"]) == (["search_records"], "It names Q-1001.")
    again = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case", {
        "name": "Invoices", "speaker": "ben", "say": "x", "checked": True})
    assert again.status_code == 409 and "already" in again.json()["detail"]
    [noted] = [e for e in stack.ledger() if e["action"] == "case from run"]
    assert noted["run"] == run and "Ortiz" not in str(noted)  # the ledger keeps no words


def test_only_its_authors_keep_one_and_only_of_a_run_that_answered_a_message(stack, approving,
                                                                             provider):
    owning(stack)
    agreed(stack)
    run = a_run(stack)
    ben = as_person(approving, provider, "ben", "GET", f"/studio/api/runs/{run}/case")
    assert ben.status_code == 403 and "owners and authors" in ben.json()["detail"]
    with db.transaction(stack.admin) as conn:  # as a schedule's run would be
        conn.execute("update runs set trigger = '{\"kind\": \"schedule\"}' where id = %s", (run,))
    scheduled = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case")
    assert scheduled.status_code == 403 and "answered someone's message" in scheduled.json()["detail"]


def test_the_runs_page_keeps_it_with_its_author_checking_it(stack, approving, provider, browser):
    owning(stack)
    agreed(stack)
    run = a_run(stack)
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/runs/{run}")
    page.wait_for_selector("#keep-case #case-say", timeout=30000)
    assert "Code masked" in page.inner_text("#keep-case")
    accessible(page)
    page.fill("#case-name", "Invoices from a real run")
    speaker = page.locator("#case-speaker")
    if speaker.evaluate("e => e.tagName") == "SELECT":
        speaker.select_option(index=1)
    else:
        speaker.fill("ben")
    page.check("#case-checked")
    page.click("#keep-case-button")
    page.wait_for_selector("#keep-case [role=status] >> text=Invoices from a real run", timeout=30000)
    with db.transaction(stack.admin) as conn:
        [draft] = conn.execute("select files from agent_drafts where person = 'ana'").fetchall()
    assert "Invoices from a real run" in draft["files"][run_cases.FILE]


def test_a_run_of_an_instance_serving_too_few_people_to_show_stays_unkept(stack, approving,
                                                                          provider):
    owning(stack)
    assert not stack.settle(data_protection={"cases_from_runs": True},  # names stay off
                            signers=("ana", "noor")).refused
    run = a_run(stack)  # the sample's instance serves two people, fewer than five
    hidden = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case")
    assert hidden.status_code == 404 and "no such run" in hidden.json()["detail"]
