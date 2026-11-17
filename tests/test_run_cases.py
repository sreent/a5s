"""A run kept as one of its agent's test cases (core/run_cases.py): what someone said to it,
masked by code and checked by the agent's author, in their draft, once the data protection
officer agrees."""

import uuid
from dataclasses import replace

import httpx
import yaml

from a5s import cases, db
from a5s.core import departures, erasure, export, run_cases
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


def a_run(stack, person: str = "ana", said: str = SAID) -> str:
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    stack.say(said, person=person)
    with db.transaction(stack.admin) as conn:
        return conn.execute("select id::text as id from runs order by opened_at desc "
                            "limit 1").fetchone()["id"]


def as_person(approving: str, provider, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    token = provider.id_token(person=person)
    return httpx.request(method, f"{approving}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token}"})


def test_code_masks_what_could_say_who_anyone_is_and_numbers_the_records_it_names(stack):
    text = ("Ana Ortiz (ana.ortiz@example.com, +44 20 7946 0958, account 12345678) asks about "
            "Q-1001: £860.00, due 2026-11-06. ana says see https://intranet.example/x, and ask "
            "Ben about Q-1001 and Q-1002")
    with db.transaction(stack.admin) as conn:  # whom the run acted for, and everyone a5s serves
        masked_by = run_cases.mask(conn, stack.gateway.scenario, {"acts_for": ["ana"]}, text)
    said, masked = masked_by(text)
    assert said == ("[someone] [someone] ([an email], [a number], account [a number]) asks about "
                    "[record 1]: £860.00, due 2026-11-06. [someone] says see [a link] and ask "
                    "[someone] about [record 1] and [record 2]")
    assert masked == {"emails": 1, "links": 1, "names": 4, "numbers": 2, "records": 3}
    assert masked_by("Q-1003, the sandbox's, stays")[0] == "Q-1003, the sandbox's, stays"


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
    assert found["answer"] == "[record 1] mentions an invoice." and found["agent"] == "assistant"
    assert found["masked"]["names"] == 2 and found["read_outside"] is False
    unchecked = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case",
                          {"name": "Invoices", "speaker": "ben", "say": found["say"]})
    assert unchecked.status_code == 409 and "says nothing about anyone" in unchecked.json()["detail"]
    kept = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case", {
        "name": "Invoices", "speaker": "ben", "say": SAID,  # unmasked: it's masked again
        "judged": "It names Q-1001, as Ana Ortiz asked.", "checked": True})
    assert kept.status_code == 200, kept.text
    body = kept.json()
    assert body["file"] == run_cases.FILE and body["case"]["speaker"] == "ben"
    with db.transaction(stack.admin) as conn:
        draft = conn.execute("select files, person, agent from agent_drafts where id = %s",
                             (body["draft"],)).fetchone()
    assert (draft["person"], draft["agent"]) == ("ana", "assistant")
    [case] = yaml.safe_load(draft["files"][run_cases.FILE])
    assert case["name"] == "Invoices" and case["as"] == "ben"
    assert run_cases.TOKEN.fullmatch(case["from_run"])  # so only models approved for the
    # deployment's data read it, and a5s knows whose words it holds, which the case doesn't say
    [step] = case["steps"]
    assert "Ortiz" not in step["say"] and "ana.ortiz@" not in step["say"]
    assert (step["uses"], step["judged"]) == (["search_records"],
                                              "It names [record 1], as [someone] [someone] asked.")
    with db.transaction(stack.admin) as conn:
        [whose] = conn.execute("select * from kept_cases").fetchall()
    assert (whose["token"], whose["person"], whose["acts_for"], whose["kept_by"], whose["run_id"]
            ) == (case["from_run"], "ana", ["ana"], "ana", uuid.UUID(run))
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


def test_a_record_its_words_name_keeps_a_run_from_whoever_may_not_see_it(stack, approving,
                                                                        provider):
    owning(stack)
    agreed(stack)
    run = a_run(stack, said="And what of Q-1003?")  # orders', which Ana may not see
    hidden = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case")
    assert hidden.status_code == 404 and "no such run" in hidden.json()["detail"]
    kept = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case", {
        "name": "Orders", "speaker": "ben", "say": "x", "checked": True})
    assert kept.status_code == 404


def kept_from(stack, approving, provider, run: str, name: str = "Invoices") -> dict:
    kept = as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case", {
        "name": name, "speaker": "ana", "say": "Which questions mention an invoice?",
        "checked": True})
    assert kept.status_code == 200, kept.text
    return kept.json()


def cases_in(stack, draft: str) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        files = conn.execute("select files from agent_drafts where id = %s",
                             (draft,)).fetchone()["files"]
    return yaml.safe_load(files[run_cases.FILE]) or []


def test_whose_words_a_case_holds_are_exported_erased_and_archived(stack, approving, provider):
    owning(stack)
    agreed(stack)
    body = kept_from(stack, approving, provider, a_run(stack, person="ben"))  # Ben's words
    with db.transaction(stack.cfg.database_url) as conn:  # as the core, with its grants
        [held] = export.gather(conn, "ben")["cases_from_runs"]
    assert (held["agent"], held["case"], held["says"]) == (
        "assistant", "Invoices", ["Which questions mention an invoice?"])
    with db.transaction(stack.cfg.database_url) as conn:
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert gone["kept_cases"] == 1
    assert cases_in(stack, body["draft"]) == []  # out of Ana's draft, which stays hers
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from kept_cases").fetchone()["n"] == 0
    kept_from(stack, approving, provider, a_run(stack), "Again")  # Ana's own words, this time
    with db.transaction(stack.cfg.database_url) as conn:  # as Ana leaves
        name = departures.rename(conn, "ana", stack.gateway.clock())
        [whose] = conn.execute("select person, acts_for, kept_by from kept_cases").fetchall()
    assert (whose["person"], whose["acts_for"], whose["kept_by"]) == (name, [name], name)
    with stack.client() as c:  # her drafts went as she left, so no draft holds it now
        assert c.post("/retention/sweep").json()["deleted"]["cases"] == 1


def test_a_case_from_a_run_that_read_outside_content_marks_its_runs_as_that_run_was(
        stack, approving, provider):
    owning(stack)
    agreed(stack)
    run = a_run(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set read_outside = true where id = %s", (run,))
    offered = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case").json()
    assert offered["read_outside"] is True
    [case] = cases_in(stack, kept_from(stack, approving, provider, run)["draft"])
    assert case["read_outside"] is True
    assert cases.sent_with(case) == [cases.OUTSIDE] and cases.sent_with({"name": "x"}) == []
    stack.model.reply("Q-1001 mentions an invoice.")
    stack.say(case["steps"][0]["say"], files=cases.sent_with(case))  # as the sandbox sends it
    with db.transaction(stack.admin) as conn:
        last = conn.execute("select read_outside from runs order by opened_at desc limit 1"
                            ).fetchone()
    assert last["read_outside"] is True
