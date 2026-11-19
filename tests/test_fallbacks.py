"""Model fallbacks (core/gateway.py's model_for, services/scheduler.py): when a run's model
isn't answering, a message is tried again on the next model its release names, each tried once,
and only once every one has failed does the person hear a5s's words for it. A fallback the
models file doesn't approve is never called, and a model whose breaker is open is passed over
for the next, so one provider's outage costs a retry, not the work."""

from __future__ import annotations

import httpx
import pytest

from a5s import db
from conftest import PROVIDER_KEY, FakeModel, build_root, running

TWO_MODELS = """
models:
  fake:
    provider: test
    api: openai
    base_url: https://fake.test/v1
    model: fake-1
    reported_model: fake-1
    key_env: A5S_TEST_PROVIDER_KEY
  spare:
    provider: test
    api: openai
    base_url: https://fake.test/v2
    model: spare-1
    reported_model: spare-1
    key_env: A5S_TEST_PROVIDER_KEY
"""


@pytest.fixture
def models() -> tuple[FakeModel, FakeModel]:
    return FakeModel(), FakeModel()


def routed(primary: FakeModel, spare: FakeModel):
    """Both providers behind one transport, each answering its own model's calls alone."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/v1/chat" in str(request.url):
            return primary.handler(request)
        if "/v2/chat" in str(request.url):
            return spare.handler(request)
        raise AssertionError(f"no model route for {request.url}")

    return handler


@pytest.fixture
def fallback_stack(database, tmp_path, monkeypatch, models):
    """a5s running, its assistant on 'fake' with 'spare' to fall back to, each its own model."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    primary, spare = models
    root = build_root(tmp_path, "fake", TWO_MODELS)
    for spec in (root / "agents").glob("*/agent.yaml"):
        lines = [line for line in spec.read_text(encoding="utf-8").splitlines()
                 if not line.startswith("fallbacks:")]
        if spec.parent.name == "assistant":
            lines.append("fallbacks: [spare]")
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with running(database, root,
                 httpx.Client(transport=httpx.MockTransport(routed(primary, spare))),
                 primary) as s:
        yield s, primary, spare


def soon(stack) -> None:
    """A while on, as the scheduler's backoff, so the next sweep takes the message again."""
    with db.transaction(stack.admin) as conn:
        conn.execute("update inbound set retry_at = now() - interval '1 second'")


def models_called(stack) -> list[str]:
    """The model each call went to, in order, as the ledger records them."""
    return [e["action"] for e in stack.ledger() if e["kind"] == "model"]


def test_a_message_runs_on_its_fallback_once_its_model_isnt_answering(fallback_stack):
    """The run-level retry, for when every model failed a run's calls: the next attempt takes
    the next model. A single call's failure is already recovered within the run, below."""
    stack, primary, spare = fallback_stack
    primary.failing = 2  # its calls fail, this run and the next attempt's
    spare.failing = 1  # the fallback fails once, then answers
    spare.reply("On spare: Q-1001 is open.")
    message = stack.send("What's the key of the open question?")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == []  # nothing told yet: the next attempt gets a go
    soon(stack)
    assert stack.scheduler().answer_waiting() == 1
    [said] = stack.answers(message)  # with a5s's note on where the key came from
    assert said.startswith("On spare: Q-1001 is open.")
    with db.transaction(stack.admin) as conn:
        [kept] = conn.execute("select attempts, tried_models from inbound where id = %s",
                              (message,)).fetchall()
        served = {r["model"] for r in conn.execute(
            "select model from runs where model is not null").fetchall()}
    assert kept["attempts"] == 1 and kept["tried_models"] == ["fake"]  # kept, and named
    assert served == {"fake", "spare"}


def test_only_once_every_model_has_failed_does_the_person_hear_a5s_words(fallback_stack):
    stack, primary, spare = fallback_stack
    primary.failing, spare.failing = 6, 6  # both down, run after run
    message = stack.send("What's the key of the open question?")
    assert stack.scheduler().answer_waiting() == 1
    soon(stack)
    assert stack.scheduler().answer_waiting() == 1
    said = "\n".join(stack.answers(message))
    assert "isn't answering" in said  # a5s's own words, once every model was tried
    soon(stack)  # and it is not tried again: each model had its go
    assert stack.scheduler().answer_waiting() == 0
    with db.transaction(stack.admin) as conn:
        [kept] = conn.execute("select attempts, tried_models from inbound where id = %s",
                              (message,)).fetchall()
    assert kept["attempts"] == 2 and kept["tried_models"] == ["fake", "spare"]


def test_a_run_survives_its_model_stalling_on_one_call(fallback_stack):
    """The bug this fixes: a model call that isn't answered used to kill the run and lose its
    state. Now the same call is re-issued on the next model in the run itself, so the person
    is answered once, the run is the same one, and the ledger shows each attempt."""
    stack, primary, spare = fallback_stack
    primary.failing = 2  # asked once more on its own model, then the next one takes the call
    spare.reply("On spare: Q-1001 is open.")
    message = stack.send("What's the key of the open question?")
    assert stack.scheduler().answer_waiting() == 1
    [said] = stack.answers(message)  # answered once, in the same run, on the next model
    assert said.startswith("On spare: Q-1001 is open.")
    with db.transaction(stack.admin) as conn:
        [count] = conn.execute("select count(*) as n from runs").fetchall()
        [kept] = conn.execute("select attempts, tried_models from inbound where id = %s",
                              (message,)).fetchall()
    assert count["n"] == 1 and kept["attempts"] == 0 and kept["tried_models"] == []
    served = {e["action"] for e in stack.ledger() if e["kind"] == "model"}
    assert served == {"fake", "spare"}  # the same call, on each in its turn


def test_a_fallback_the_models_file_doesnt_approve_is_never_called(fallback_stack):
    stack, _, _ = fallback_stack  # only the gateway's choice matters here
    assistant = stack.gateway.definitions["assistant"]
    stack.gateway.definitions["assistant"] = assistant.model_copy(
        update={"fallbacks": ["nobody-approved"]})
    with stack.client() as c:  # its own model was tried: the rest aren't models a5s knows
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello"), "tried_models": ["fake"]}})
    r.raise_for_status()
    assert r.json()["model"] == "fake"  # the run keeps its own model, never the unknown one


def test_a_model_whose_breaker_is_open_is_passed_over_for_the_next(fallback_stack):
    stack, _, spare = fallback_stack  # the open one is never called
    for _ in range(3):  # three failures in a row: its breaker is open (core/breakers.py)
        stack.gateway.breakers.failed("fake")
    spare.reply("On spare, from the start.")
    message = stack.send("What's the key of the open question?")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == ["On spare, from the start."]
    assert set(models_called(stack)) == {"spare"}  # never the open one, though nothing failed
