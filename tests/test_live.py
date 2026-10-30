"""Calls a real provider. Run with `pytest -m live`, with the provider's key set."""

import json
import os

import httpx
import pytest

from a5s import db
from a5s.services import context
from conftest import ROOT, FakeModel, build_root, running


@pytest.mark.live
@pytest.mark.parametrize("alias, key", [
    ("deepseek-v4-pro", "DEEPSEEK_API_KEY"),
    ("deepseek-v4-pro-anthropic", "DEEPSEEK_API_KEY"),
    ("qwen3.7-max", "QWEN_API_KEY"),
])
def test_a_real_model_answers_through_the_gateway(database, tmp_path, alias, key):
    if not os.environ.get(key):
        pytest.skip(f"{key} isn't set")
    root = build_root(tmp_path, alias, (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        reply = stack.say(
            "What's the key of the customer question about an invoice? Reply with the key.")
        assert "Q-1001" in reply
        assert stack.verify().ok
        models = [e for e in stack.ledger() if e["kind"] == "model" and e["decision"] == "record"]
        assert models and all(e["outcome"]["status"] == 200 for e in models)


@pytest.mark.live
def test_a_real_model_reminds_someone_of_what_falls_due(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's Q-1001 has passed
        assert stack.scheduler().work_due() == 2  # Ana's and Ben's
        [reminder] = stack.inbox("ana")
        assert "Q-1001" in reminder["text"] and reminder["from"] == "assistant"
        print(reminder["text"])
        assert stack.verify().ok


@pytest.mark.live
def test_a_real_model_tells_someone_what_changed_in_their_records(database, tmp_path, monkeypatch):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        stack.with_watcher(serves=("ana",))
        stack.at("2026-10-29T09:30:00+00:00")  # Thursday: the watcher's first morning
        assert stack.scheduler().work_due() == 1
        [first] = stack.inbox("ana")
        assert "Q-1001" in first["text"] and first["from"] == "watcher"

        records = stack.gateway.scenario._records
        monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer"})
        stack.at("2026-10-30T09:30:00+00:00")
        assert stack.scheduler().work_due() == 1
        [changed] = stack.inbox("ana")
        assert "Q-1001" in changed["text"] and "waiting on" in changed["text"].lower()
        print(first["text"], changed["text"], sep="\n---\n")
        assert stack.verify().ok


@pytest.mark.live
def test_a_real_model_offers_a_reminder_and_keeps_it_once_its_person_says_yes(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        offered = stack.say("Please remind me on 2026-10-30 to check whether Northwind has "
                            "answered about Q-1001.")
        with db.transaction(stack.admin) as conn:
            [row] = conn.execute("select * from reminders").fetchall()
        assert row["confirmed_at"] is None and row["record"] == "Q-1001"
        confirmed = stack.say("Yes please.")
        with db.transaction(stack.admin) as conn:
            [row] = conn.execute("select * from reminders").fetchall()
        assert row["confirmed_at"] is not None

        stack.at("2026-10-30T09:30:00+00:00")
        assert stack.scheduler().work_due() == 1
        [reminder] = stack.inbox("ana")
        assert "Northwind" in reminder["text"] or "Q-1001" in reminder["text"]
        print(offered, confirmed, reminder["text"], sep="\n---\n")
        assert stack.verify().ok


@pytest.mark.live
def test_a_real_model_notes_how_someone_works_and_goes_by_what_they_said(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        offered = stack.say("Please note that I like answers in one sentence, no lists.")
        confirmed = stack.say("Yes, keep that note.")
        print(offered, confirmed, *[f"{e['run'][:8]} {e['action']} {e['outcome']}" for e in stack.ledger()
                                    if e["kind"] == "tool" and e["decision"] == "record"], sep="\n")
        with db.transaction(stack.admin) as conn:
            [note] = conn.execute("select * from profile_notes").fetchall()
        assert note["confirmed_at"] is not None and "sentence" in note["text"]

        stack.say("For Q-1001, Northwind wants the corrected invoice sent to their Leeds office.")
        found = stack.say("Remind me: which office did I say Northwind wants the invoice sent to?")
        assert "Leeds" in found
        print(offered, confirmed, found, sep="\n---\n")
        assert stack.verify().ok


@pytest.mark.live
def test_a_real_model_searches_for_what_its_context_no_longer_holds(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        with db.transaction(stack.admin) as conn:  # what Ana said a while ago, and much since
            context.add_turn(conn, person="ana", agent="assistant", role="person",
                             content="Northwind wants the corrected invoice sent to their Leeds office.")
            context.add_turn(conn, person="ana", agent="assistant", role="agent", content="Noted.")
            for n in range(6):
                context.add_turn(conn, person="ana", agent="assistant", role="person",
                                 content=f"Note {n} from the weekly sync: " + "We went through the "
                                 "open invoices, the refunds and the next payment run. " * 12)
                context.add_turn(conn, person="ana", agent="assistant", role="agent", content="Noted.")
        stack.gateway.definitions["assistant"].context.budget_tokens = 1000  # 4,000 characters
        found = stack.say("Which office did I say Northwind wants the invoice sent to?")
        searched = [e for e in stack.ledger()
                    if e["action"] == "search_conversation" and e["decision"] == "allow"]
        print(found, [e["args"] for e in searched], sep="\n---\n")
        assert searched and "Leeds" in found
        assert stack.verify().ok


@pytest.mark.live
def test_a_real_model_folds_what_no_longer_fits_into_a_checked_summary(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        with db.transaction(stack.admin) as conn:  # what Ana agreed a while ago, and much since
            context.add_turn(conn, person="ana", agent="assistant", role="person",
                             content="We agreed: Contoso's refund for Q-1002 is £1,240.50, and it "
                                     "goes out by 2026-11-06. Can you chase finance on Monday?")
            context.add_turn(conn, person="ana", agent="assistant", role="agent",
                             content="Yes, I'll chase finance about the refund on Monday.")
            for n in range(6):
                context.add_turn(conn, person="ana", agent="assistant", role="person",
                                 content=f"Note {n} from the weekly sync: " + "We went through the "
                                 "open invoices and the next payment run. " * 12)
        stack.gateway.definitions["assistant"].context.budget_tokens = 1000  # 4,000 characters
        stack.say("Thanks for all that.")
        with db.transaction(stack.admin) as conn:
            [summary] = conn.execute("select * from summaries").fetchall()
        print(json.dumps(summary["body"], indent=1, ensure_ascii=False))
        assert {"GBP 1240.50", "2026-11-06", "Q-1002"} <= {f["norm"] for f in summary["body"]["facts"]}
        assert summary["body"]["decisions"] or summary["body"]["commitments"]
        found = stack.say("How much is Contoso's refund, and when does it go out?")
        assert "1,240.50" in found
        assert stack.verify().ok
