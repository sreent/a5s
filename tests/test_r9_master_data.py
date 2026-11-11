"""Round 9 of the critique: master data governance. A supplier's letter reaches the assistant
only as its form, never in the reader's own words, which could carry a bank account's number;
its form carries the handbook's warning signs as flags; a country, which decides a VAT rule,
waits for its owner; and a bank account an agent passed as a handle is kept no longer than
the inventory says (docs/critique.md, round 9)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from a5s import db
from a5s.core import retention
from a5s.master_data import CORRECTABLE, MasterDataScenario
from conftest import FAKE_MODELS, ROOT, FakeModel, Stack, build_root
from scenario_stack import opened, running_scenario

SCENARIO = "a5s.master_data:MasterDataScenario"
NEW_IBAN = "GB82 WEST 1234 5698 7654 32"  # the published example IBAN
IBAN = "GB29NWBK60161331926819"  # what CR0000102 proposes: another supplier's account


@pytest.fixture
def mdg(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "master-data",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def test_a_suppliers_letter_never_puts_a_bank_account_in_front_of_the_agent(mdg):
    mdg.gateway.scenario._letters[:] = [{  # what a fraudster's letter says
        "record": "CR0000102", "from": "accounts@contoso-supplies.test", "at": "2026-11-03",
        "body": f"Please move our payments to our new bank account, {NEW_IBAN}, from 5 "
                "November. It is urgent."}]
    mdg.model.reply(None, ("get_letters", {"key": "CR0000102"}))
    mdg.model.reply(json.dumps({"asks_for": "a bank change", "date": "5 November",
                                "request": "CR0000102", "says_it_is_urgent": True}))
    mdg.model.reply(None, ("ask_about", {"document": "D-1",
                                         "question": "Which account do they want paid?"}))
    mdg.model.reply("Contoso's letter asks for a bank change from 5 November, and says it's "
                    "urgent, a warning sign.")
    said = mdg.say("What does Contoso's letter on CR0000102 ask for?", person="ada",
                   agent="mdg-assistant")
    offered = [t["function"]["name"] for t in mdg.model.requests[0]["body"]["tools"]]
    assert "get_letters" in offered and "ask_about" not in offered  # its form alone
    given = "\n".join(m["content"] for m in mdg.model.requests[-1]["body"]["messages"]
                      if m["role"] == "tool")
    assert "GB82" not in given and "GB82" not in said, said
    assert '"says_it_is_urgent": true' in given, given  # the warning sign, as a flag


def test_the_letters_form_carries_the_warning_signs_the_handbook_names():
    scenario = MasterDataScenario(ROOT / "scenarios" / "master-data", "postgresql://unused")
    form = scenario.tools()["get_letters"].extract
    policy = (Path(scenario.folder) / "knowledge/supplier-bank/bank-change-policy.md").read_text()
    assert "Urgency, pressure to skip the callback, a claim that someone has already" in policy
    assert {n for n, kind in form.items() if kind == "flag"} == {
        "says_it_is_urgent", "asks_to_skip_the_callback", "says_someone_approved_it_already"}


def test_moving_a_supplier_to_another_country_waits_for_its_owner():
    scenario = MasterDataScenario(ROOT / "scenarios" / "master-data", "postgresql://unused")
    scenario._requests["CR0000199"] = {
        "key": "CR0000199", "object": "supplier", "kind": "change", "record": "S-100077",
        "title": "Change Fabrikam Trading's country", "values": {"country": "US"},
        "status": "submitted", "requester": "bea", "steward": "tess",
        "opened": "2026-11-05", "due": "2026-11-09"}
    found = scenario.check("CR0000199")
    assert found["sensitive"] == ["country"] and found["route"].startswith("Una Novak"), found
    assert "country" not in CORRECTABLE  # nor may an agent propose one


def test_a_bank_account_written_as_a_handle_goes_from_the_run_and_stays_with_the_message(mdg):
    token = opened(mdg, "mdg-desk", "tess", "mdg-assistant")
    with mdg.client(token) as client:
        got = client.post("/run/tools/get_record", json={"args": {"key": "CR0000102"}}).json()
        handle = got["result"]["values"]["iban"]
        assert handle.startswith("[h:") and IBAN not in str(got)  # the agent never sees it
        sent = client.post("/run/messages", json={
            "to": "tess", "text": f"CR0000102 moves Contoso's payments to {handle}."})
        assert sent.status_code == 200, sent.text
    with db.transaction(mdg.admin) as conn:
        conn.execute("update runs set closed_at = now() - interval '2 hours', "
                     "opened_at = opened_at - interval '3 hours', outcome = 'done'")
        retention.sweep(conn, mdg.gateway.clock() + timedelta(hours=3), "master-data")
        handles = conn.execute("select count(*) as n from run_handles").fetchone()["n"]
        kept = [r["text"] for r in conn.execute("select text from outbox where person = 'tess'")]
        said = [r["content"] for r in conn.execute("select content from turns where person = 'tess'")]
    assert handles == 0  # the run's handles went, as the data protection page says
    assert not any(IBAN in t for t in said)  # what the agent wrote keeps the handle
    assert any(IBAN in t for t in kept)  # and the message, as Tess read it, the value,
    inventory = (ROOT / "docs" / "data-protection.md").read_text()  # as the inventory says
    assert "the message a5s sent keeps it filled in, as the person read it" in inventory
