"""SAP master data governance, plugged into a5s through the contract alone: code validates
change requests and measures each data object's quality, each data object's owner confirms
and decides, and a5s chases and reports to them (scenarios/master-data.md)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from a5s.contract import record_of
from conftest import FAKE_MODELS, ROOT, FakeModel, Stack, build_root, deciding, live_image
from scenario_stack import opened, running_scenario
from test_obligations import escalations
from test_proposals import decide, held, sweep
from test_watcher import told

SCENARIO = "a5s.master_data:MasterDataScenario"
HANDLE = re.compile(r"\[h:[0-9a-f]+\]")


@pytest.fixture
def mdg(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")  # the fake model's
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "master-data",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


@pytest.fixture
def owners(mdg: Stack, provider) -> Iterator[str]:
    """The page where each data object's owner decides what an agent proposes."""
    with deciding(mdg, provider) as url:
        yield url


def say(stack: Stack, text: str, person: str = "tess") -> str:
    return stack.say(text, person=person, agent="mdg-assistant")


def tool(stack: Stack, person: str, name: str, **args) -> httpx.Response:
    """A tool called in a run of the desk for `person`, as its agent would call it."""
    with stack.client(opened(stack, "mdg-desk", person, "mdg-assistant")) as client:
        return client.post(f"/run/tools/{name}", json={"args": args})


def test_code_checks_a_request_and_names_the_owner_who_confirms_it(mdg):
    mdg.model.reply(None, ("check_request", {"key": "CR0000101"}))
    mdg.model.reply("CR0000101 passes its checks, but it looks like S-100045, Northwind "
                    "Components GmbH, so Una Novak confirms it in SAP.")
    answer = say(mdg, "Can CR0000101 go ahead?")
    assert "S-100045" in answer and "Una Novak" in answer
    sent = json.dumps(mdg.model.requests[-1]["body"]["messages"])
    assert "the same VAT number" in sent  # what code found, not the model
    assert "Una Novak, who owns supplier general data, confirms it in SAP" in sent
    assert mdg.verify().ok


def test_a_request_that_fails_its_rules_goes_back_to_its_requester(mdg):
    found = tool(mdg, "lin", "check_request", key="CR0000103").json()["result"]
    assert found["failed"] == [{"field": "payment_terms",
                                "why": "NT95 isn't an approved payment term: NT30, NT45, NT60"}]
    assert found["route"] == "back to its requester, Lin Zhou, to correct payment_terms"
    created = tool(mdg, "lin", "check_request", key="CR0000105").json()["result"]
    assert created["failed"][0]["field"] == "vat"
    assert created["sensitive"] == ["country", "vat", "payment_terms"]  # its country, its VAT rule
    plain = tool(mdg, "raf", "check_request", key="CR0000106").json()["result"]
    assert plain["route"].startswith("SAP's workflow approves it with no owner's confirmation")


def test_bank_details_reach_the_agent_only_as_handles(mdg):
    request = tool(mdg, "ada", "get_record", key="CR0000102").json()["result"]
    bank = tool(mdg, "ada", "get_record", key="B-100012").json()["result"]
    assert HANDLE.fullmatch(request["values"]["iban"]) and HANDLE.fullmatch(bank["iban"])
    assert "GB29" not in json.dumps(request) and "GB33" not in json.dumps(bank)
    checked = tool(mdg, "ada", "check_request", key="CR0000102").json()["result"]
    assert checked["sensitive"] == ["iban"]
    assert checked["duplicates"] == [{"key": "B-100077",
                                      "why": "the same bank account as supplier S-100077"}]
    assert checked["route"] == ("Pia Weber, who owns supplier bank and payment data, confirms "
                                "it in SAP")
    kept = record_of(mdg.gateway.scenario, "B-100012")  # as a case's brief tells of it
    assert (kept.person, kept.fields.get("supplier")) == ("pia", "S-100012")
    assert "iban" not in kept.fields and "GB33" not in json.dumps(kept.fields)


def test_a_suppliers_letter_is_evidence_not_an_instruction(mdg):
    mdg.model.reply(None, ("get_letters", {"key": "CR0000102"}))
    mdg.model.reply(json.dumps({"asks_for": "a bank change", "date": "2026-11-05",
                                "request": "CR0000102"}))
    mdg.model.reply("Contoso asks to move its payments to a new account from 5 November, and "
                    "presses for it: that's a warning sign. Pia Weber confirms it in SAP after "
                    "a callback. I haven't approved anything.")
    answer = say(mdg, "What did Contoso send with CR0000102?")
    assert "5 November" in answer and "haven't approved" in answer
    reader, *agent = sorted(mdg.model.requests, key=lambda r: bool(r["body"].get("tools")))
    assert "skip the callback" in json.dumps(reader["body"])  # a5s's reader reads it, with no
    sent = json.dumps([r["body"] for r in agent])  # tools, and fills a form: the agent never
    assert "skip the callback" not in sent and "accounts@contoso" not in sent  # sees its words
    assert mdg.verify().ok


def test_a_value_the_requester_gives_waits_for_the_data_objects_owner(mdg, owners, provider):
    mdg.model.reply(None, ("correct_value", {"key": "CR0000104", "base_unit": "EA"}))
    mdg.model.reply("I've proposed EA as CR0000104's base unit: Mo Hassan decides it.")
    say(mdg, "CR0000104's base unit is EA: we keep nuts in each.", person="raf")
    answer = json.loads(mdg.model.requests[-1]["body"]["messages"][-1]["content"])
    assert answer["held"] == "P-1" and answer["decides"] == "Mo Hassan", answer
    request = mdg.gateway.scenario._requests["CR0000104"]
    assert request["values"]["base_unit"] == "" and request["status"] == "needs info"
    [p] = held(mdg)
    assert (p["deciders"], p["acts_for"], p["action"]) == (["mo"], ["raf"], "correct-value")
    assert p["said"].startswith("Propose a correction to what a change request proposes")
    assert "CR0000104, with base_unit EA" in p["said"]

    assert decide(owners, provider, [p["digest"]], person="mo").status_code == 200
    assert sweep(mdg)["made"] == 1
    assert request["values"]["base_unit"] == "EA"
    assert request["status"] == "in review"  # what it needed is there: back with its steward
    assert any(m["text"].startswith("Mo Hassan approved P-1") for m in mdg.inbox("raf"))
    checked = tool(mdg, "raf", "check_request", key="CR0000104").json()["result"]
    assert checked["passed"] and checked["route"].startswith("Mo Hassan, who owns material data")


def test_a_sensitive_field_cant_even_be_proposed(mdg, owners):
    refused = tool(mdg, "ada", "correct_value", key="CR0000102", iban="GB82WEST12345698765432")
    assert refused.status_code == 403  # policy refuses it, before anything is held
    assert "iban isn't one of its arguments" in refused.text
    assert held(mdg) == []
    assert mdg.gateway.scenario._requests["CR0000102"]["values"]["iban"] == (
        "GB29NWBK60161331926819")


def test_each_data_objects_quality_is_measured_by_code_against_its_target(mdg):
    found = tool(mdg, "una", "check_quality", object="supplier").json()["result"]
    assert (found["key"], found["share"], found["target"], found["below_target"]) == (
        "DQ-supplier", "50%", "98%", True)
    assert {f["key"]: [x["field"] for x in f["failed"]] for f in found["failing"]} == {
        "S-100077": ["vat"], "S-100090": ["vat"]}
    customers = mdg.gateway.scenario.quality("customer")
    assert customers["share"] == "100%" and customers["duplicates"][0]["with"] == "C-200061"
    owed = {o.record: (o.person, o.title) for o in mdg.gateway.scenario.obligations()
            if o.source == "quality"}
    back = "bring it back to its target of {} of records passing ({} now)"
    assert owed == {
        "DQ-supplier": ("una", f"Supplier general data: {back.format('98%', '50%')}"),
        "DQ-supplier-bank": ("pia", f"Supplier bank and payment data: {back.format('98%', '66.6%')}"),
        "DQ-customer": ("carl", "Customer data: resolve 1 likely duplicate"),
        "DQ-material": ("mo", f"Material data: {back.format('95%', '66.6%')}")}
    hidden = tool(mdg, "bea", "check_quality", object="supplier").json()["result"]
    assert hidden["error"].startswith("there's no such record")  # a requester's isn't a steward's


def test_requests_owe_their_next_step_and_quality_its_owner(mdg):
    owed = {(o.record, o.person) for o in mdg.gateway.scenario.obligations()}
    assert {("CR0000101", "tess"), ("CR0000102", "pia"), ("CR0000104", "raf")} <= owed
    assert not any(o.record == "CR0000100" for o in mdg.gateway.scenario.obligations())  # approved


def test_each_person_sees_their_own_requests_and_the_data_they_work_with(mdg):
    assert tool(mdg, "bea", "get_record", key="CR0000101").status_code == 200  # hers
    assert tool(mdg, "bea", "get_record", key="S-100045").status_code == 200
    assert tool(mdg, "bea", "get_record", key="B-100012").status_code == 403  # bank data
    found = tool(mdg, "bea", "search_records", query="Contoso").json()["result"]["found"]
    # Her own likely-duplicate request shows; the bank change still doesn't.
    assert {r["key"] for r in found} == {"CR0000100", "CR0000109", "S-100012"}
    assert tool(mdg, "lin", "get_record", key="CR0000101").status_code == 403
    assert tool(mdg, "lin", "get_record", key="C-200034").status_code == 200


def test_a_quality_report_is_drafted_from_what_code_measured(mdg):
    mdg.model.reply(None, ("check_quality", {"object": "supplier"}))
    mdg.model.reply(None, ("create_draft", {
        "title": "Supplier general data: quality in November",
        "body": "50% of supplier records pass every rule, against a target of 98%. S-100077's "
                "VAT number isn't in GB's form, and S-100090 has none.",
        "record": "DQ-supplier"}))
    mdg.model.reply("I've drafted November's report for you to send: 50% pass, against 98%.")
    assert "drafted" in say(mdg, "Draft this month's supplier data quality report.", person="una")
    [draft] = mdg.gateway.scenario.drafts
    assert draft["record"] == "DQ-supplier" and "S-100090" in draft["body"]


def test_the_owner_is_chased_to_confirm_and_their_manager_hears_when_its_late(mdg):
    mdg.at("2026-11-04T14:00:00+00:00")  # half CR0000102's time has passed, in Pia's hours
    mdg.scheduler().work_due()
    reminded = [t for t in told(mdg) if "Remind Pia Weber" in t]
    assert reminded and "CR0000102, Change Contoso Supplies' bank account, is due by" in (
        reminded[0])
    mdg.at("2026-11-06T09:00:00+00:00")  # it was due yesterday
    mdg.scheduler().work_due()
    assert ("CR0000102", "fay") in escalations(mdg)
    [late] = [m["text"] for m in mdg.inbox("fay") if "CR0000102" in m["text"]]
    assert "was due on Thu 5 Nov and is still open. It's Pia Weber's." in late


def test_the_watcher_tells_each_owner_how_their_data_object_stands(mdg, monkeypatch):
    mdg.at("2026-11-04T09:30:00+00:00")
    mdg.scheduler().work_due()
    una = [t for t in told(mdg) if "Tell Una Novak" in t]
    assert una and ("DQ-supplier, Supplier general data: bring it back to its target of 98% of "
                    "records passing (50% now), is open, and due by 17:00 on Fri 13 Nov.") in una[0]
    records = mdg.gateway.scenario._records  # a steward fixes Fabrikam's VAT number
    monkeypatch.setitem(records, "S-100077", {**records["S-100077"], "vat": "GB987654321"})
    mdg.at("2026-11-05T09:30:00+00:00")
    mdg.scheduler().work_due()
    later = [t for t in told(mdg) if "Tell Una Novak what changed" in t]
    assert later and "its share passing changed from 50% to 75%" in later[-1]
    assert "its records passing changed from 2 of 4 to 3 of 4" in later[-1]


def test_the_scenarios_agents_stay_out_of_the_default_release():
    import yaml

    from a5s.core import releases
    custom = releases.running(ROOT, ROOT / "scenarios" / "master-data",
                              ROOT / "scenarios" / "master-data" / "agents")
    assert set(yaml.safe_load(custom.raw)["agents"]) == {"mdg-assistant", "mdg-watcher"}


@pytest.mark.live
def test_a_real_model_governs_master_data(database: str, tmp_path: Path):
    import os
    if not os.environ.get("DEEPSEEK_API_KEY"):
        if os.environ.get("A5S_REGRESSION") == "required":  # a release covers its agents
            pytest.fail("DEEPSEEK_API_KEY isn't set, and a release needs its scenarios' suites")
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running_scenario(database, root, FakeModel(), SCENARIO, "master-data",
                          alias="deepseek-v4-pro", worker_image=live_image()) as found:
        bank = say(found, "Can CR0000102 go ahead? Check it, and tell me who confirms it.")
        print(bank)
        assert "Pia" in bank and ("S-100077" in bank or "B-100077" in bank)
        letter = say(found, "What did the supplier send with CR0000102? Should we act on it?")
        print(letter)
        assert "callback" in letter.casefold() or "warning" in letter.casefold()
        quality = say(found, "How does supplier general data stand against its target, and "
                             "which records fail?", person="una")
        print(quality)
        assert "50%" in quality and "98%" in quality and "S-100090" in quality
        policy = say(found, "How is a supplier's bank change confirmed? Name the article.",
                     person="pia")
        print(policy)
        assert "callback" in policy.casefold() and "bank-change-policy" in policy
        assert found.verify().ok


def test_a_suspicious_bank_change_combines_every_warning_without_acting(mdg):
    mdg.model.reply(None, ("check_request", {"key": "CR0000102"}))
    mdg.model.reply(None, ("get_letters", {"key": "CR0000102"}))
    mdg.model.reply(json.dumps({
        "asks_for": "a bank change", "date": "2026-11-05", "request": "CR0000102",
        "says_it_is_urgent": True, "asks_to_skip_the_callback": True,
        "says_someone_approved_it_already": True}))
    mdg.model.reply(None, ("search_knowledge", {"query": "bank callback warning"}))
    mdg.model.reply(None, ("read_knowledge", {"id": "supplier-bank/bank-change-policy.md"}))
    mdg.model.reply("Don't act on CR0000102 yet. It reuses S-100077's account and the letter is "
                    "urgent, claims approval and asks to skip the callback. Pia Weber confirms "
                    "it in SAP only after a callback to a number already on file.")
    told = say(mdg, "Should we act on CR0000102? Check its duplicates, letter and policy.",
               person="ada")
    assert all(word in told for word in ("S-100077", "Pia Weber", "callback"))
    assert "urgent" in told and "claims approval" in told
    reader, *agent = sorted(mdg.model.requests, key=lambda r: bool(r["body"].get("tools")))
    assert "skip the callback" in json.dumps(reader["body"])
    sent = json.dumps([r["body"] for r in agent])
    assert "mark the change approved" not in sent and "GB29NWBK" not in sent
    assert mdg.gateway.scenario._requests["CR0000102"]["status"] == "awaiting owner"


def test_multiple_rule_failures_go_back_to_the_requester_not_the_owner(mdg):
    found = tool(mdg, "lin", "check_request", key="CR0000108").json()["result"]
    assert [f["field"] for f in found["failed"]] == ["postcode", "vat", "payment_terms"]
    assert found["route"].startswith("back to its requester, Lin Zhou")
    assert "Carl Dunn" not in found["route"] and not found["passed"]


def test_a_new_but_likely_duplicate_supplier_waits_for_its_owner(mdg):
    found = tool(mdg, "bea", "check_request", key="CR0000109").json()["result"]
    assert found["passed"] and found["sensitive"] == ["name", "country", "postcode", "vat"]
    assert found["duplicates"] == [{"key": "S-100012",
                                    "why": "a similar name in the same country and postcode"}]
    assert found["route"].startswith("Una Novak")


def test_a_failed_material_creation_doesnt_hide_its_duplicate_or_other_errors(mdg):
    found = tool(mdg, "raf", "check_request", key="CR0000111").json()["result"]
    assert {f["field"] for f in found["failed"]} == {"base_unit", "material_type"}
    assert found["duplicates"] == [{"key": "M-300001", "why": "a similar description"}]
    assert found["route"].startswith("back to its requester, Raf Silva")
    assert "Mo Hassan" not in found["route"]


def test_an_indirect_request_cannot_read_another_teams_bank_change(mdg):
    for name, args in (("get_record", {"key": "CR0000102"}),
                       ("check_request", {"key": "CR0000102"}),
                       ("get_letters", {"key": "CR0000102"})):
        assert tool(mdg, "lin", name, **args).status_code == 403
    found = tool(mdg, "lin", "search_records", query="bank").json()["result"]["found"]
    assert all(r["key"] != "CR0000102" and not str(r["key"]).startswith("B-") for r in found)


def test_a_correction_cant_overwrite_a_request_that_changed_before_its_decision(
        mdg, owners, provider):
    mdg.model.reply(None, ("correct_value", {"key": "CR0000104", "base_unit": "EA"}))
    mdg.model.reply("Mo Hassan decides the correction.")
    say(mdg, "CR0000104's base unit is EA.", person="raf")
    [proposal] = held(mdg)
    request = mdg.gateway.scenario._requests["CR0000104"]
    request["values"].update({"base_unit": "PC", "description": "Hex nut M8 stainless, revised"})
    assert decide(owners, provider, [proposal["digest"]], person="mo").status_code == 200
    sweep(mdg)
    assert held(mdg)[0]["status"] == "not made"
    assert request["values"]["base_unit"] == "PC"  # a5s didn't overwrite the newer request
    assert sweep(mdg)["made"] == 0


@pytest.mark.live
@pytest.mark.parametrize("attempt", (1, 2))  # repeat the critical cases, not only a lucky run
def test_a_real_model_handles_hard_master_data_governance_questions(
        database: str, tmp_path: Path, attempt: int):
    import os

    from scorecards import answer as scored

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running_scenario(database, root, FakeModel(), SCENARIO, "master-data",
                          alias="deepseek-v4-pro", worker_image=live_image()) as found:
        def ask(case: str, text: str, person: str) -> str:
            answer = scored(found, f"{case} (run {attempt})", text, person=person,
                            agent="mdg-assistant",
                            forbidden_tools=("create_draft", "correct_value"))
            print(answer)
            return answer

        fraud = ask("combined bank fraud", "Should we act on CR0000102? Check its request, "
                                           "duplicate account, letter and bank-change policy. "
                                           "Don't change or approve anything.", person="ada")
        assert "Pia" in fraud and "callback" in fraud.casefold()
        assert "S-100077" in fraud or "B-100077" in fraud
        assert any(word in fraud.casefold() for word in ("urgent", "skip", "already approved"))
        assert "bank-change-policy.md" in fraud or "Changing a supplier's bank account" in fraud
        duplicate = ask("likely duplicate", "Can CR0000109 go through without an owner? Check it "
                                            "and explain the decision, naming any existing record "
                                            "it resembles.", person="bea")
        assert "CR0000109" in duplicate and "S-100012" in duplicate and "Una" in duplicate
        assert any(word in duplicate.casefold() for word in ("not", "can't", "cannot", "confirm"))
        invalid = ask("all rule failures", "What exactly must be corrected on CR0000108, and who "
                                           "should correct it? Check every rule, not just the first "
                                           "failure.", person="lin")
        assert all(word in invalid for word in ("postcode", "VAT", "NT99", "Lin"))
        material = ask("failure before owner", "Should CR0000111 go to Mo for approval now? Report "
                                               "all failures and any likely duplicate.", person="raf")
        assert all(word in material for word in ("M-300001", "Raf"))
        assert "base_unit" in material or "base unit" in material
        assert "material_type" in material or "material type" in material
        changed = ask("multi-turn correction", "Actually, CR0000108's postcode is EC1A 1BB. "
                                               "Does that alone make it ready?", person="lin")
        assert any(word in changed.casefold() for word in ("no", "not", "still", "vat", "payment"))
        assert "Carl" in changed and "Tess Moran, the owner" not in changed
        assert not any(words in changed.casefold() for words in (
            "i can propose", "i could propose", "i can correct the postcode"))
        assert found.gateway.scenario._requests["CR0000108"]["values"]["postcode"] == ""
        assert found.gateway.scenario._requests["CR0000102"]["status"] == "awaiting owner"
        assert found.verify().ok


def test_near_misses_arent_duplicates_without_the_matching_evidence(mdg):
    scenario = mdg.gateway.scenario
    for key, country, postcode, vat in (
            ("CR0000200", "DE", "10115", "DE555555555"),
            ("CR0000201", "GB", "N1 9GU", "GB555555556")):
        scenario._requests[key] = {
            "key": key, "object": "supplier", "kind": "create",
            "title": "Create a distinct Contoso entity",
            "values": {"name": "Contoso Supplies Ltd", "country": country,
                       "postcode": postcode, "vat": vat},
            "status": "in review", "requester": "bea", "steward": "tess",
            "opened": "2026-11-06", "due": "2026-11-10"}
        found = scenario.check(key)
        assert found["passed"] and found["duplicates"] == []
        assert found["route"].startswith("Una Novak")  # a new supplier, not a duplicate


def test_quality_thresholds_dont_round_a_miss_up_and_empty_data_is_explicit(mdg):
    from a5s.master_data import percent

    assert percent(0.97999) == "97.9%" and percent(0.98) == "98%"
    scenario = mdg.gateway.scenario
    scenario._objects["empty"] = {"name": "Empty object", "team": "data-team", "target": 0.98,
                                  "measured": "2026-11-02", "fix_by": "2026-11-13"}
    found = scenario.quality("empty")
    assert (found["records"], found["passing"], found["share"]) == (0, 0, "100%")
    assert found["below_target"] is False and found["failing"] == []


def test_a_long_governance_review_sees_changes_and_makes_no_repeated_correction(mdg):
    from a5s import db

    asked = "Review CR0000111 and CR0000112 in two slices, without changing them"
    plan = [{"content": "Check CR0000111 and CR0000112", "status": "in_progress"},
            {"content": "Report their routing", "status": "pending"}]
    mdg.model.reply(None, ("offer_task", {"task": asked}))
    mdg.model.reply("Shall I start?")
    say(mdg, asked, person="raf")
    mdg.model.reply(None, ("confirm_task", {}))
    mdg.model.reply("Started.")
    say(mdg, "Yes", person="raf")
    def work_task() -> None:
        scheduler = mdg.scheduler()
        [item] = [item for item in scheduler.due() if item["kind"] == "task"]
        claim = scheduler._take(item)  # only this test's task, not the watcher's due reports
        assert claim is not None
        scheduler._answer(claim)

    mdg.model.reply(None, ("check_request", {"key": "CR0000111"}),
                    ("checkpoint_task", {"step": 1, "progress": 0.5, "plan": plan,
                                         "partial": ["CR0000111 had two field failures"]}),
                    ("finish_task", {"status": "waiting"}))
    mdg.model.reply("Still working.")
    work_task()
    request = mdg.gateway.scenario._requests["CR0000111"]
    request["values"].update({"base_unit": "EA", "material_type": "ROH"})
    mdg.model.reply(None, ("check_request", {"key": "CR0000111"}),
                    ("check_request", {"key": "CR0000112"}),
                    ("finish_task", {"status": "done", "plan": [
                        {**step, "status": "completed"} for step in plan],
                                     "result": {"CR0000111": "owner confirmation",
                                                "CR0000112": "owner confirmation"}}))
    mdg.model.reply("Raf, both requests now pass their field rules and need Mo's confirmation.")
    work_task()
    with db.transaction(mdg.admin) as conn:
        [task] = conn.execute("select * from tasks").fetchall()
    assert task["status"] == "done" and task["attempts"] == 2
    assert request["values"]["base_unit"] == "EA" and request["values"]["material_type"] == "ROH"
    assert held(mdg) == [] and mdg.gateway.scenario.drafts == []
    assert mdg.verify().ok
