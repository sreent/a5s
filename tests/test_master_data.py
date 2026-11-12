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
    assert {r["key"] for r in found} == {"CR0000100", "S-100012"}  # not the bank change
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
