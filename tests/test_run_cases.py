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


AUTHORING = ("agent-owner:assistant", "agent-author:assistant")


def owning(stack, person: str = "ana", *others: str) -> None:
    """Make someone the assistant's owner, in the directory: who watches its instance and sees
    billing's records, so may see its runs and author it; and nobody else its owner or author but
    `others`, since everyone who authors it reads a case kept in a draft of it (round 14)."""
    people = stack.gateway.scenario._people
    for who, found in list(people.items()):
        roles = tuple(r for r in found.roles if r not in AUTHORING)
        people[who] = replace(found, roles=(*roles, "agent-owner:assistant")
                              if who in (person, *others) else roles)


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
    with db.transaction(stack.admin) as conn:  # known as erased, with nothing of whose it was
        [erased] = conn.execute("select person, acts_for, kept_by, run_id, erased_at from "
                                "kept_cases").fetchall()
    assert (erased["person"], erased["acts_for"], erased["kept_by"], erased["run_id"]) == (
        None, [], None, None)
    assert erased["erased_at"] is not None
    kept_from(stack, approving, provider, a_run(stack), "Again")  # Ana's own words, this time
    with db.transaction(stack.cfg.database_url) as conn:  # as Ana leaves
        name = departures.rename(conn, "ana", stack.gateway.clock())
        [whose] = conn.execute("select person, acts_for, kept_by from kept_cases where "
                               "erased_at is null").fetchall()
    assert (whose["person"], whose["acts_for"], whose["kept_by"]) == (name, [name], name)
    with stack.client() as c:  # her drafts went as she left, so no draft holds either now
        assert c.post("/retention/sweep").json()["deleted"]["cases"] == 2


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


# Round 14

BEN_SAID = "Which questions mention an invoice?"  # what's kept of Ben's run, as kept_from keeps it


def files_of(stack, draft: str) -> dict:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select files from agent_drafts where id = %s", (draft,)).fetchone()["files"]


def released_with(stack, files: dict) -> None:
    """A draft of the assistant, published and merged: its folder as released holds its cases."""
    tests = stack.cfg.agents_dir / "assistant" / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "from-runs.yaml").write_text(files[run_cases.FILE])


def test_a_case_is_kept_only_where_everyone_who_authors_its_agent_may_see_the_run(
        stack, approving, provider):
    """D2: everyone who authors the assistant reads a case kept in a draft of it, so a run whose
    records Priya may not see, as she owns the assistant too, is kept by nobody; once she
    doesn't, Ana keeps it."""
    owning(stack, "ana", "priya")
    agreed(stack)
    run = a_run(stack, person="ben")
    assert not stack.gateway.scenario.sees("priya", "Q-1001")
    refused = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case")
    assert refused.status_code == 403 and "not everyone who authors" in refused.json()["detail"]
    owning(stack, "ana")
    assert as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case"
                     ).status_code == 200


def test_erased_words_stay_out_of_a_draft_started_from_a_release_that_holds_them(
        stack, approving, provider):
    """D5: erasure takes Ben's words out of every draft, and keeps that they were erased, so a
    draft started from the release, which still holds them, leaves them out; his export and a
    second erasure find nothing of his."""
    from test_drafts import as_
    owning(stack)
    agreed(stack)
    body = kept_from(stack, approving, provider, a_run(stack, person="ben"))
    released_with(stack, files_of(stack, body["draft"]))
    with db.transaction(stack.cfg.database_url) as conn:
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert gone["kept_cases"] == 1 and cases_in(stack, body["draft"]) == []
    ana = as_(approving, provider, "ana")
    assert ana("DELETE", f"/studio/api/drafts/{body['draft']}").status_code == 200
    started = ana("POST", "/studio/api/drafts", {"agent": "assistant"})
    assert started.status_code == 200, started.text
    assert BEN_SAID not in started.json()["files"].get(run_cases.FILE, "")
    with db.transaction(stack.cfg.database_url) as conn:
        assert export.gather(conn, "ben")["cases_from_runs"] == []
        again, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert "kept_cases" not in again


def test_whose_words_a_case_holds_is_kept_while_a_release_holds_it(stack, approving, provider):
    """D5: the retention sweep keeps knowing whose words a case holds while the release at work
    holds it, though no draft does, so Ben's export finds it, and erasure keeps it out of the
    next draft."""
    from test_drafts import as_
    owning(stack)
    agreed(stack)
    body = kept_from(stack, approving, provider, a_run(stack, person="ben"))
    released_with(stack, files_of(stack, body["draft"]))
    assert as_(approving, provider, "ana")("DELETE", f"/studio/api/drafts/{body['draft']}"
                                           ).status_code == 200
    with stack.client() as c:
        assert "cases" not in c.post("/retention/sweep").json()["deleted"]
    with db.transaction(stack.cfg.database_url) as conn:
        [held] = export.gather(conn, "ben")["cases_from_runs"]
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert held["case"] and gone["kept_cases"] == 1


def test_erasure_takes_a_case_out_of_any_file_and_counts_only_what_it_took(
        stack, approving, provider):
    """D6: a case moved to another file of the draft is still found and taken out; one in a file
    that doesn't read as YAML is left, said to be left, and still known as Ben's."""
    from test_drafts import as_
    owning(stack)
    agreed(stack)
    ana = as_(approving, provider, "ana")
    body = kept_from(stack, approving, provider, a_run(stack, person="ben"))
    files = dict(files_of(stack, body["draft"]))
    files["tests/cases.yaml"] = files.pop(run_cases.FILE)  # her cases, in one file
    assert ana("PUT", f"/studio/api/drafts/{body['draft']}", {"files": files}).status_code == 200
    with stack.client() as c:
        assert "cases" not in c.post("/retention/sweep").json()["deleted"]
    with db.transaction(stack.cfg.database_url) as conn:
        assert export.gather(conn, "ben")["cases_from_runs"][0]["says"] == [BEN_SAID]
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert gone["kept_cases"] == 1 and BEN_SAID not in files_of(stack, body["draft"])["tests/cases.yaml"]
    second = kept_from(stack, approving, provider, a_run(stack, person="ben"))
    files = files_of(stack, second["draft"])
    half = {**files, run_cases.FILE: files[run_cases.FILE] + "- name: [a case she's writing\n"}
    assert ana("PUT", f"/studio/api/drafts/{second['draft']}", {"files": half}).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert "kept_cases" not in gone and gone["kept_cases_left"] == 1
    with db.transaction(stack.admin) as conn:  # still known as his, under his archive's name
        assert conn.execute("select person from kept_cases where erased_at is null").fetchone()[
            "person"].startswith("former:")


def test_a_case_kept_while_its_draft_is_open_stays_at_the_designers_next_keep(
        stack, approving, provider):
    """D7: the designer keeps the draft whole, as the tab had it; a case kept from a run's page
    since then is kept with it, while one the tab took out itself stays out."""
    from test_drafts import as_
    owning(stack)
    agreed(stack)
    ana = as_(approving, provider, "ana")
    opened = ana("POST", "/studio/api/drafts", {"agent": "assistant"}).json()  # open in a tab
    body = kept_from(stack, approving, provider, a_run(stack, person="ben"))  # from the run's page
    assert body["draft"] == opened["id"] and cases_in(stack, opened["id"])
    edited = {**opened["files"], "AGENTS.md": opened["files"].get("AGENTS.md", "") + "\nBe brief."}
    saved = ana("PUT", f"/studio/api/drafts/{opened['id']}",
                {"files": edited, "loaded": opened["updated_at"]})
    assert saved.status_code == 200 and BEN_SAID in saved.json()["files"][run_cases.FILE]
    gone = {k: v for k, v in saved.json()["files"].items() if k != run_cases.FILE}
    dropped = ana("PUT", f"/studio/api/drafts/{opened['id']}",
                  {"files": gone, "loaded": saved.json()["updated_at"]})
    assert run_cases.FILE not in dropped.json()["files"]  # theirs to take out, having had it


def test_a_group_members_export_gives_no_one_elses_words(stack, approving, provider):
    """D8: a case kept from a group chat's run holds what one of them said: the others' exports
    count it, never with the words."""
    owning(stack)
    agreed(stack)
    run = a_run(stack, person="ben", said="Which questions mention my invoice to the Lisbon office?")
    with db.transaction(stack.admin) as conn:  # as a group chat's run, for everyone in it
        conn.execute("update runs set acts_for = array['ben', 'chen'] where id = %s", (run,))
    offered = as_person(approving, provider, "ana", "GET", f"/studio/api/runs/{run}/case").json()
    assert as_person(approving, provider, "ana", "POST", f"/studio/api/runs/{run}/case", {
        "name": "Ben's", "speaker": "ana", "say": offered["say"], "checked": True}).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:
        [chens] = export.gather(conn, "chen")["cases_from_runs"]
        [bens] = export.gather(conn, "ben")["cases_from_runs"]
    assert chens["says"] == [] and chens["said_by"] and "Lisbon office" in bens["says"][0]
