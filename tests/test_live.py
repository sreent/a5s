"""Calls a real provider. Run with `pytest -m live`, with the provider's key set."""

import json
import os

import httpx
import pytest

from a5s import db
from a5s.core import measures
from a5s.services import context
from conftest import ROOT, FakeModel, build_root, running
from test_agents import dated


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
    due = dated("{in 7 days}")  # ahead, by the clock its turns are written with
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        offered = stack.say(f"Please remind me on {due} to check whether Northwind has "
                            "answered about Q-1001.")
        with db.transaction(stack.admin) as conn:
            [row] = conn.execute("select * from reminders").fetchall()
        assert row["confirmed_at"] is None and row["record"] == "Q-1001"
        confirmed = stack.say("Yes please.")
        with db.transaction(stack.admin) as conn:
            [row] = conn.execute("select * from reminders").fetchall()
        assert row["confirmed_at"] is not None

        stack.at(f"{due}T09:30:00+00:00")
        assert stack.scheduler().work_due() >= 1  # the reminder, and any chase due by then
        with db.transaction(stack.admin) as conn:
            [row] = conn.execute("select * from reminders").fetchall()
        assert row["reminded_at"] is not None
        told = "\n\n".join(m["text"] for m in stack.inbox("ana"))
        assert "Northwind" in told or "Q-1001" in told
        print(offered, confirmed, told, sep="\n---\n")
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


@pytest.mark.live
def test_a_real_model_passes_on_a_contact_it_never_sees(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    model_calls = []
    with running(database, root, httpx.Client(event_hooks={"request": [model_calls.append]}),
                 FakeModel()) as stack:
        told = stack.say("Who should I email about Q-1001? Give me the address.")
        print(told)
        assert "accounts@northwind.test" in told
        assert not any(b"accounts@northwind.test" in (r.content or b"") for r in model_calls)
        assert stack.verify().ok


REFUNDS = """---
name: refunds
description: How to answer a question about when a customer's refund is paid.
---

# Refunds

1. Look up the question's record. Say its status, and when it's due, as the record says.
2. End your answer with this line, as it is: "Finance's refund desk: extension 4417."
"""


@pytest.mark.live
def test_a_real_model_reads_a_skill_when_it_needs_it_and_goes_by_it(database, tmp_path):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    folder = root / "agents" / "assistant" / "skills" / "refunds"  # the release brings it
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(REFUNDS)
    calls = []
    with running(database, root, httpx.Client(event_hooks={"request": [calls.append]}),
                 FakeModel()) as stack:
        told = stack.say("When will Contoso's refund for Q-1002 be paid?", person="ben")
        print(told)
        sent = [r.content or b"" for r in calls if r.url.host == "api.deepseek.com"]
        assert b"/skills/refunds/SKILL.md" in sent[0]  # told of it by name and purpose,
        assert b"extension 4417" not in sent[0]  # and read it once it needed it
        assert any(b"extension 4417" in body for body in sent[1:])
        assert "4417" in told and "2026-11-06" in told
        assert stack.verify().ok


@pytest.mark.live
@pytest.mark.parametrize("alias", ["deepseek-v4-pro", "deepseek-v4-pro-anthropic"])
def test_what_a_real_model_reads_from_its_providers_cache_is_counted(database, tmp_path, alias):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, alias, (ROOT / "config" / "models.yaml").read_text())
    with running(database, root, httpx.Client(), FakeModel()) as stack:
        asked = ("What's the key of the customer question about an invoice? Reply with the key.",
                 "And when is it due? Reply with the date.")
        for question in asked:  # each call starts as the one before did: its instructions, tools
            stack.say(question)
        usage = [e["outcome"]["usage"] for e in stack.ledger()
                 if e["kind"] == "model" and e["decision"] == "record"]
        with db.transaction(stack.admin) as conn:
            runs = conn.execute("select tokens, tokens_in, tokens_out, tokens_cached, model "
                                "from runs order by opened_at").fetchall()
            [measured] = measures.report(conn, "sample", stack.gateway.models, 1,
                                         stack.gateway.clock())["runs"]
        print(*usage, *runs, measured, sep="\n")
        assert sum(r["tokens_cached"] for r in runs) > 0
        assert all(r["tokens"] == r["tokens_in"] + r["tokens_out"]  # in either API's words
                   and r["tokens_cached"] <= r["tokens_in"] and r["model"] == alias for r in runs)
        assert measured["cached_share"] > 0
        assert stack.verify().ok
