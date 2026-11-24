"""The drift canaries (core/canaries.py): a fixed set of cases every approved model must
answer exactly, scored into canary_scores, so what drifts behind a model's name shows first."""

import httpx
import pytest
import yaml

from a5s import db
from a5s.config import ModelConfig
from a5s.core import canaries


def fake(answers):
    """An approved stand-in that answers with `answers` in turn, whatever it's asked."""
    def handler(request):
        return httpx.Response(200, json=answers.pop(0))
    return (ModelConfig(alias="fake", provider="test", api="openai",
                        base_url="https://fake.test/v1", model="fake-1",
                        reported_model="fake-1", key_env=None, region="test",
                        data_classes=("synthetic",)), handler)


def test_a_canary_passes_exactly_and_is_scored(database):
    found, handler = fake([{"choices": [{"message": {"content": "hello"}}]}] * 2)
    canary = {"name": "echo", "model": "fake", "messages": [{"role": "user", "content": "hi"}],
              "expect": "hello"}
    assert canaries.ask(found, canary, httpx.Client(transport=httpx.MockTransport(handler)))[0]
    failed = canaries.run(database, "sample", {"fake": found}, [canary],
                          http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert failed == 0
    with db.connect(database) as conn:
        [row] = conn.execute("select canary, model, passed from canary_scores").fetchall()
    assert (row["canary"], row["model"], row["passed"]) == ("echo", "fake", True)


def test_a_canary_that_says_other_words_fails(database):
    found, handler = fake([{"choices": [{"message": {"content": "goodbye"}}]}] * 2)
    canary = {"name": "echo", "model": "fake", "messages": [{"role": "user", "content": "hi"}],
              "expect": "hello"}
    passed, said, _ = canaries.ask(found, canary,
                                   httpx.Client(transport=httpx.MockTransport(handler)))
    assert not passed and said == "goodbye"
    assert canaries.run(database, "sample", {"fake": found}, [canary],
                          http=httpx.Client(transport=httpx.MockTransport(handler))) == 1


def test_a_canary_the_provider_wont_answer_is_a_failure(database):
    found, _ = fake([])

    def broken(request):
        return httpx.Response(503, json={"error": {"message": "down"}})

    canary = {"name": "echo", "model": "fake", "messages": [{"role": "user", "content": "hi"}],
              "expect": "hello"}
    assert not canaries.ask(found, canary, httpx.Client(transport=httpx.MockTransport(broken)))[0]


def test_an_answer_is_compared_case_insensitively():
    found, handler = fake([{"choices": [{"message": {"content": "  HELLO "}}]}])
    canary = {"name": "echo", "model": "fake", "messages": [{"role": "user", "content": "hi"}],
              "expect": "hello"}
    assert canaries.ask(found, canary, httpx.Client(transport=httpx.MockTransport(handler)))[0]


def test_a_model_whose_key_isnt_set_is_skipped_not_failed(database, monkeypatch):
    monkeypatch.delenv("QWEN_API_KEY", raising=False)  # wherever the tests run, it isn't set
    found = ModelConfig(alias="qwen", provider="test", api="openai",
                        base_url="https://fake.test/v1", model="qwen-1",
                        reported_model="qwen-1", key_env="QWEN_API_KEY", region="test",
                        data_classes=("synthetic",))
    canary = {"name": "echo", "model": "qwen", "messages": [{"role": "user", "content": "hi"}],
              "expect": "hello"}
    assert canaries.run(database, "sample", {"qwen": found}, [canary]) == 0
    with db.connect(database) as conn:
        rows = conn.execute("select * from canary_scores").fetchall()
    assert rows == []






def test_a_canary_may_require_only_the_value_however_worded():
    found, handler = fake([{"choices": [{"message": {"content": "2+2 = 4."}}]}])
    canary = {"name": "sum", "model": "fake", "messages": [{"role": "user", "content": "x"}],
              "expect": "4", "contains": True}
    assert canaries.ask(found, canary, httpx.Client(transport=httpx.MockTransport(handler)))[0]

    found, handler = fake([{"choices": [{"message": {"content": "2+2 = 5."}}]}])
    assert not canaries.ask(found, canary,
                            httpx.Client(transport=httpx.MockTransport(handler)))[0]


def test_a_canary_may_require_a_pattern_never_to_appear():
    found, handler = fake([{"choices": [{"message": {"content": "I don't know that issue."}}]}])
    canary = {"name": "refuse", "model": "fake", "messages": [{"role": "user", "content": "x"}],
              "not": "[A-Z]{1,12}-\\d+"}
    assert canaries.ask(found, canary, httpx.Client(transport=httpx.MockTransport(handler)))[0]

    found, handler = fake([{"choices": [{"message": {"content": "The issue is Q-9999."}}]}])
    assert not canaries.ask(found, canary,
                            httpx.Client(transport=httpx.MockTransport(handler)))[0]


def test_load_refuses_a_canary_without_an_expected_answer(tmp_path):
    file = tmp_path / "canaries.yaml"
    file.write_text(yaml.safe_dump({"canaries": [{"name": "none", "messages": [
        {"role": "user", "content": "hi"}]}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="expect"):
        canaries.load(file)