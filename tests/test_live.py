"""Calls a real provider. Run with `pytest -m live`, with the provider's key set."""

import os

import httpx
import pytest

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
