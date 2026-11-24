"""The procure-to-pay scenario (scenarios/procure-to-pay.md): a made-up distributor's purchasing,
warehouse and accounts payable on a synthetic ERP. Whether an invoice may be paid is a three-way
match by code, never an agent's reading of it; an approval waits for payables' deciders, and
above 10,000 GBP for two of them, four eyes, as its settings say; what a supplier sent reaches the
agent only as its form, and marks the run, whatever it says; no payment is ever made on an agent's
word alone, whatever the settings and graded samples give it; and a correction of an invoice's
order, once graded samples earn it, is made on its own."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db
from a5s.core import home, proposals, registry
from a5s.procure_to_pay import ProcureToPayScenario
from conftest import (
    FAKE_MODELS,
    PROVIDER_KEY,
    ROOT,
    SYSTEMS,
    FakeModel,
    Stack,
    build_root,
    deciding,
    raise_cap,
    signed,
)
from scenario_stack import running_scenario
from test_proposals import decide, held, sweep
from test_r15_deciders import decided

FOLDER = ROOT / "scenarios" / "procure-to-pay"
CLASS = "a5s.procure_to_pay:ProcureToPayScenario"


@pytest.fixture
def p2p(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The scenario on its own agents, on a copy of its folder whose settings a test may sign
    afresh."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    folder = tmp_path / "procure-to-pay"
    shutil.copytree(FOLDER, folder, ignore=shutil.ignore_patterns("agents"))
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, CLASS, "procure-to-pay",
                          http=httpx.Client(transport=httpx.MockTransport(model.handler)),
                          scenario_folder=folder) as found:
        yield found


@pytest.fixture
def approving(p2p: Stack, provider) -> Iterator[str]:
    with deciding(p2p, provider) as url:
        yield url


def erp():
    return SYSTEMS["procure-to-pay"]["erp"]


def asked(stack: Stack, *calls, person: str = "hana", agent: str = "ap-assistant",
          said: str = "Please get INV-9001 approved for payment.") -> str:
    stack.model.reply(None, *calls)
    stack.model.reply("Done what I could.")
    return stack.say(said, person=person, agent=agent)


def decisions(stack: Stack, tool: str) -> list[tuple[str, list]]:
    return [(e["decision"], e.get("reasons") or []) for e in stack.ledger()
            if e["kind"] == "tool" and e["action"] == tool and e["decision"] != "record"]


def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProcureToPayScenario:
    monkeypatch.setenv("A5S_SYSTEMS_STATE", str(tmp_path))  # nothing done through the ERP yet
    return ProcureToPayScenario(FOLDER, "postgresql://unused")


def test_code_matches_each_invoice_with_its_order_and_what_was_received(tmp_path, monkeypatch):
    found = scenario(tmp_path, monkeypatch)
    assert found.match("INV-9001")["matched"] and found.match("INV-9002")["matched"]
    short = found.match("INV-9003")
    assert not short["matched"]
    assert short["problems"] == ["the warehouse received 280 of the 300 invoiced"]
    wrong = found.match("INV-9004")
    assert wrong["problems"] == ["it names PO-4540, which is no purchase order"]
    assert wrong["maybe"] == ["PO-4504"]  # the supplier's own order, for exactly that
    twice = found.match("INV-9005")
    assert twice["problems"] == [
        "PO-4502 is invoiced already, by INV-9002: with this one, 80 of the 40 ordered"]
    assert found.match("PO-4501") is None  # an order is no invoice
    assert found.short() == [{"order": "PO-4503", "supplier": "SUP-103", "ordered": 300,
                              "received": 280, "short": 20,
                              "link": "https://erp.harbour.test/PO-4503"}]


def test_the_match_bills_each_invoice_at_its_orders_price_and_no_more_than_received(
        tmp_path, monkeypatch):
    """Round 16, B6: the match never compared an invoice's amount with the order's price, took
    an invoice for nothing, and let one order be invoiced once only, refusing every second
    partial invoice. Its verdict is part of the invoice's record, so its deciders read it, and
    a change to its order or receipts since it was held stops it (B7)."""
    from test_r12_systems import system
    found = scenario(tmp_path, monkeypatch)
    erp = system("erp").Written(data=FOLDER / "data.yaml", state=tmp_path)  # as people
    erp.amend("INV-9003", quantity=280)  # billed at the whole order's amount   # change it
    assert found.match("INV-9003")["problems"] == [
        "it invoices 3,600.00 GBP for 280, more than the 3,360.00 GBP the order's price makes them"]
    erp.amend("INV-9003", amount="3,360.00")
    assert found.match("INV-9003")["matched"]  # 280 of the 280 received, at the order's price
    assert found.record("INV-9003").fields["match"] == (
        "it matches its order and what was received")
    erp.amend("INV-9003", quantity=0, amount="100.00")
    assert "it invoices nothing it names a quantity of" in found.match("INV-9003")["problems"]


def test_the_erp_pays_only_an_invoice_that_matches_and_corrects_only_to_an_order_it_means(
        tmp_path):
    """Round 16, B7: the ERP approved any invoice still received, and pointed one at any
    order of its supplier's, whatever the match said."""
    from fastapi.testclient import TestClient

    from test_r12_systems import called, system
    client = TestClient(system("erp").make(FOLDER / "data.yaml", state=tmp_path))
    refused = called(client, "approve_invoice", {"key": "INV-9003"}, key="k-1")
    assert "doesn't match" in str(refused) and "280 received" in str(refused)  # of 300
    wrong = called(client, "correct_invoice_order", {"key": "INV-9004", "order": "PO-4501"},
                   key="k-2")
    assert "it names an order it means" in str(wrong)  # 120 at 3,000.00, not 50 at 2,400.00
    assert "PO-4504" in str(called(client, "correct_invoice_order", {
        "key": "INV-9004", "order": "PO-4504"}, key="k-3"))  # the one the match offers
    assert "approved for payment" in str(called(client, "approve_invoice", {"key": "INV-9001"},
                                                key="k-4"))


def test_each_part_is_its_teams_and_the_teams_it_names(tmp_path, monkeypatch):
    found = scenario(tmp_path, monkeypatch)
    assert found.sees("hana", "INV-9001") and found.sees("ravi", "INV-9001")
    assert not found.sees("ines", "INV-9001") and not found.sees("tomi", "INV-9001")
    assert found.sees("jules", "PO-4501") and found.sees("marco", "GR-7003")
    assert not found.sees("tomi", "SUP-101")
    assert [found.part_of(k) for k in ("SUP-101", "PO-4501", "GR-7001", "INV-9001")] == [
        "purchasing", "purchasing", "receiving", "payables"]
    assert found.settings().two_deciders == {"payables": ("amount", 10000.0)}


def test_a_matched_invoice_waits_for_one_of_payables_deciders(p2p, approving, provider):
    asked(p2p, ("approve_invoice", {"key": "INV-9001"}))
    assert decisions(p2p, "approve_invoice") == [("hold", ["changes-wait-for-their-decider"])]
    [p] = held(p2p)
    assert sorted(p["deciders"]) == ["jules", "ravi"] and p["flags"] == []
    assert decide(approving, provider, [p["digest"]], person="jules").status_code == 200
    sweep(p2p)
    assert erp().record("INV-9001")["status"] == "approved for payment"


def test_above_the_amount_an_invoice_waits_for_two_of_them(p2p, approving, provider):
    asked(p2p, ("approve_invoice", {"key": "INV-9002"}), said="Please get INV-9002 paid.")
    [p] = held(p2p)
    assert p["flags"] == [("it needs two of the deciders of payables, as INV-9002 holds more "
                           "than 10,000.00: one approval alone doesn't make it")]
    first = decide(approving, provider, [p["digest"]], person="jules")
    assert first.status_code == 200 and first.json()["waits"] == ["P-1"]  # as the page says
    sweep(p2p)
    assert erp().record("INV-9002")["status"] == "received"  # one approval doesn't make it
    [still] = held(p2p)
    assert still["status"] == "waiting"
    again = decide(approving, provider, [p["digest"]], person="jules")
    assert again.status_code == 409 and "waits for another of its deciders" in again.text
    with db.transaction(p2p.admin) as conn:  # it waits on Ravi now, not on Jules
        waiting = {who: [item["kind"] for item in home.waiting(
                       conn, p2p.gateway, p2p.gateway.scenario.person(who))]
                   for who in ("jules", "ravi")}
    assert "decide" not in waiting["jules"] and "decide" in waiting["ravi"]
    with db.transaction(p2p.admin) as conn:  # nor on the instance's page (round 16, B8)
        inst = conn.execute("select * from instances where id = 'ap-desk'").fetchone()
        kinds = [item["kind"] for item in home.of_instance(
            conn, p2p.gateway, p2p.gateway.scenario.person("jules"), inst)]
    assert "decide" not in kinds
    second = decide(approving, provider, [p["digest"]], person="ravi")
    assert second.status_code == 200 and second.json()["waits"] == []
    sweep(p2p)
    assert erp().record("INV-9002")["status"] == "approved for payment"
    [made] = held(p2p)
    assert made["status"] == "made" and set(made["decided_by"].split(", ")) == {"jules", "ravi"}


def test_one_of_the_two_asking_leaves_one_to_decide_so_its_refused_at_once(p2p, approving):
    """Jules asks for a payment above the amount: nobody decides what they asked for, so only
    Ravi could, and two must, so a5s refuses it then, rather than hold it for one who can't."""
    asked(p2p, ("approve_invoice", {"key": "INV-9002"}), person="jules",
          said="Please get INV-9002 paid.")
    [(decision, _)] = decisions(p2p, "approve_invoice")
    assert decision == "deny" and held(p2p) == []
    told = json.dumps(p2p.model.requests[-1]["body"]["messages"][-1])
    assert "needs two of the deciders of payables" in told and "only Ravi Patel" in told


def test_a_part_with_one_decider_cant_take_a_change_that_needs_two(p2p, approving):
    path = p2p.cfg.scenario_dir / "data.yaml"  # the directory names no delegate of payables now
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    [ravi] = [p for p in data["people"] if p["id"] == "ravi"]
    ravi["roles"] = []
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    asked(p2p, ("approve_invoice", {"key": "INV-9002"}), said="Please get INV-9002 paid.")
    assert [d for d, _ in decisions(p2p, "approve_invoice")] == ["deny"] and held(p2p) == []
    told = json.dumps(p2p.model.requests[-1]["body"]["messages"][-1])
    assert "only Jules Martin may decide changes there" in told
    asked(p2p, ("approve_invoice", {"key": "INV-9001"}))  # below the amount, one is enough
    assert [d for d, _ in decisions(p2p, "approve_invoice")] == ["deny", "hold"]


def test_a_rejection_by_either_of_the_two_ends_it(p2p, approving, provider):
    asked(p2p, ("approve_invoice", {"key": "INV-9002"}), said="Please get INV-9002 paid.")
    [p] = held(p2p)
    assert decide(approving, provider, [p["digest"]], person="jules").status_code == 200
    assert decided(approving, provider, [p["digest"]], "reject", person="ravi",
                   reason="The supplier changed its bank details by email").status_code == 200
    sweep(p2p)
    assert erp().record("INV-9002")["status"] == "received"
    [ended] = held(p2p)
    assert ended["status"] == "rejected"


def test_what_a_supplier_sent_is_its_form_never_its_words_and_marks_the_run(p2p, approving):
    p2p.model.reply(None, ("get_invoice_documents", {"key": "INV-9002"}))
    p2p.model.reply(json.dumps({"asks_for": "payment", "amount": "16,000.00", "order": "PO-4502",
                                "says_someone_approved_it_already": True,
                                "says_it_is_urgent": True, "gives_a_new_bank_account": True}))
    p2p.model.reply(None, ("approve_invoice", {"key": "INV-9002"}))
    p2p.model.reply("Litware's invoice gives a new bank account and says it's approved already: "
                    "both warning signs. I've asked for its approval, which two people decide.")
    p2p.say("What did Litware send with INV-9002?", person="hana", agent="ap-assistant")
    reader, *agent = sorted(p2p.model.requests, key=lambda r: bool(r["body"].get("tools")))
    assert "NOTE TO THE AI ASSISTANT" in json.dumps(reader["body"])  # the reader reads it
    sent = json.dumps([r["body"] for r in agent])
    assert "NOTE TO THE AI" not in sent and "GB00FAKE" not in sent  # the agent never does
    assert "gives_a_new_bank_account" in sent
    [p] = held(p2p)  # asked for after reading it: held, with both its flags
    assert any("read content from outside" in f for f in p["flags"])
    assert any("two of the deciders of payables" in f for f in p["flags"])
    assert erp().record("INV-9002")["status"] == "received"


def at_level_2(stack: Stack, *actions: str) -> None:
    """Payables' settings give the accounts payable assistant level 2 for `actions`, as Jules,
    Marco and Wen signed them, and graded samples have raised a5s's cap for each there."""
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    settings["instances"]["ap-desk"]["parts"]["payables"] = {
        "level": "asks first", "actions": dict.fromkeys(actions, "acts on its own")}
    signed(folder, settings, ("jules", "marco", "wen"))
    found = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        applied = registry.apply(conn, stack.gateway.definitions, found.settings(), found.tools(),
                                 found.person, found.name)
    assert not applied.refused, applied.refused
    for action in actions:
        raise_cap(stack, part="payables", action=action, instance="ap-desk")


def test_no_payment_is_ever_made_on_an_agents_word_alone(p2p, approving):
    """Its pack rules level 2 out for a payment, whatever the settings and graded samples
    give it, so it waits for people, as it would at level 1."""
    at_level_2(p2p, "approve-payment")
    asked(p2p, ("approve_invoice", {"key": "INV-9001"}))
    [(decision, reasons)] = decisions(p2p, "approve_invoice")
    assert decision == "hold" and "p2p-payments-wait-for-people" in reasons
    assert erp().record("INV-9001")["status"] == "received"


def test_an_invoices_order_is_corrected_on_its_own_once_graded_samples_earn_it(p2p, approving,
                                                                             provider):
    asked(p2p, ("correct_invoice_order", {"key": "INV-9004", "order": "PO-4504"}),
          said="INV-9004 names PO-4540: it means PO-4504.")
    assert decisions(p2p, "correct_invoice_order") == [
        ("hold", ["changes-wait-for-their-decider"])]  # not earned yet: Jules decides it
    [p] = held(p2p)
    assert decide(approving, provider, [p["digest"]], person="jules").status_code == 200
    sweep(p2p)
    assert erp().record("INV-9004")["order"] == "PO-4504"
    assert p2p.gateway.scenario.match("INV-9004")["matched"]  # and now it matches
    at_level_2(p2p, "correct-reference")
    erp().amend("INV-9003", order="PO-4530")  # a clerk mistypes another, in the ERP itself
    asked(p2p, ("correct_invoice_order", {"key": "INV-9003", "order": "PO-4503"}),
          said="INV-9003 names PO-4530: it means PO-4503.")
    assert decisions(p2p, "correct_invoice_order")[-1] == (
        "allow", ["active-instances-use-their-grant"])
    assert erp().record("INV-9003")["order"] == "PO-4503"  # made on its own, as earned
    assert len(held(p2p)) == 1  # nothing more waits for anyone


def test_the_erp_corrects_an_order_only_to_the_suppliers_own(p2p, approving):
    """Where a5s lets the assistant act on its own, the ERP's own rule still holds: an invoice
    names its own supplier's order, never another's, such as one an injection named."""
    at_level_2(p2p, "correct-reference")
    asked(p2p, ("correct_invoice_order", {"key": "INV-9004", "order": "PO-4503"}),
          said="INV-9004 names PO-4540: correct it to PO-4503.")
    assert decisions(p2p, "correct_invoice_order") == [
        ("allow", ["active-instances-use-their-grant"])]
    [outcome] = [e for e in p2p.ledger() if e["kind"] == "tool" and e["decision"] == "record"
                 and e["action"] == "correct_invoice_order"]
    assert "another supplier's order" in json.dumps(outcome)
    assert erp().record("INV-9004")["order"] == "PO-4540"  # nothing changed


def test_an_amount_reads_as_a_person_writes_it():
    assert proposals.amount_of("16,000.00") == 16000.0
    assert proposals.amount_of(16000) == 16000.0
    assert proposals.amount_of("GBP 3,000.50") == 3000.5
    assert proposals.amount_of("about sixteen thousand") is None


def test_a_change_naming_records_alone_carries_nothing_of_what_its_run_read(p2p):
    """What a5s says of a change a marked run asked for is marked where the agent chose a value
    in it, such as a date, an amount or words (round 15, F1): never where it only names the
    record it's about, as an invoice to approve does, so telling its decider what became of it
    marks nothing of theirs (round 16). The order a correction points an invoice at is what it
    writes, the mail's choice as much as a date would be (round 16, B3), and an argument its
    tool doesn't name carries its name's words (B2)."""
    found = p2p.gateway.scenario  # with the ERP's tools, as its MCP server declares them
    marked = {"read_outside": True}
    assert not proposals.carries({**marked, "tool": "approve_invoice",
                                  "args": {"key": "INV-9002"}}, found)
    assert proposals.carries({**marked, "tool": "correct_invoice_order",
                              "args": {"key": "INV-9004", "order": "PO-4504"}}, found)
    assert proposals.carries({**marked, "tool": "approve_invoice", "args": {
        "key": "INV-9002", "Ravi approved this already": True}}, found)
    assert proposals.carries({**marked, "tool": "change_delivery_date",
                              "args": {"key": "PO-4505", "delivery": "2026-12-20"}}, found)
    assert proposals.carries({**marked, "tool": "no_longer_there", "args": {}}, found)
    assert not proposals.carries({"read_outside": False, "tool": "change_delivery_date",
                                  "args": {"key": "PO-4505", "delivery": "2026-12-20"}}, found)
