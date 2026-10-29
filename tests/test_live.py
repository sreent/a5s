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
