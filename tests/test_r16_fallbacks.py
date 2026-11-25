"""Round 16, reviewer A: model fallbacks (core/gateway.py, services/scheduler.py, worker.py).

- A1: a run that opened on its release's fallback could see what its own model may not.
- A2: a message whose run made a draft before its model stopped answering ran again from the
  start on the next model, making a second draft and writing their words twice.
- A3: a call's fallback was sent the images its own model was approved for.
- A6: the calls a5s skipped, for an open breaker, counted as the model's stalls.
- A7: a model that timed out was asked again, though that took as long again, and the worker's
  own timeout counted as a failed run rather than a model not answering.
- A8: another model's answer counted where a5s couldn't record that it answered.
- A9: the one correction for keys a reply never read was only on a message's path, and a 409
  in words crashed the scheduler."""

from __future__ import annotations

import dataclasses

import httpx
import openai
import psycopg
import pytest

from a5s import db, worker
from a5s.core import health, notices
from a5s.services import scheduler
from test_fallbacks import soon

DRAFT = ("create_draft", {"title": "Re: Q-1001", "body": "Sorry about that."})


def person_turns(stack) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select count(*) as n from turns where role = 'person'"
                            ).fetchone()["n"]


def test_a_run_that_did_something_isnt_run_again_on_the_next_model(fallback_stack):
    stack, primary, spare = fallback_stack
    primary.reply(None, DRAFT)  # its first call makes a draft, and every call after fails

    def down_after_first(n: int) -> None:
        if n == 2:
            primary.failing = 99
    primary.on_request = down_after_first
    spare.failing = 99  # the call's fallback can't take it either
    message = stack.send("Draft a reply to Q-1001, please")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == [notices.STOPPED]  # told at once, not left waiting
    soon(stack)
    assert stack.scheduler().answer_waiting() == 0  # and never run again: one draft
    drafted = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "create_draft"
               and e["decision"] == "allow"]
    assert len(drafted) == 1 and person_turns(stack) == 1


def test_a_run_that_did_nothing_goes_to_the_next_model_with_their_words_once(fallback_stack):
    stack, primary, spare = fallback_stack
    primary.failing, spare.failing = 2, 1  # this run's model and its call's fallback fail
    spare.reply("On spare: Q-1001 is open.")
    message = stack.send("What's the key of the open question Q-1001?")
    assert stack.scheduler().answer_waiting() == 1
    soon(stack)
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message)[0].startswith("On spare: Q-1001 is open.")
    assert person_turns(stack) == 1  # each run read them, but a5s wrote them once


def test_a_runs_fallback_never_sees_more_than_its_own_model_may(fallback_stack):
    stack, _, _ = fallback_stack
    for _ in range(3):  # its own model's breaker is open
        stack.gateway.breakers.failed("fake")
    models = stack.gateway.models
    models["fake"] = dataclasses.replace(models["fake"], data_classes=("synthetic", "internal"))
    with stack.client() as c:  # spare is approved for synthetic data alone
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello")}})
    r.raise_for_status()
    assert r.json()["model"] == "fake"  # its own, whose breaker says so at each call


def test_a_calls_fallback_isnt_sent_an_image_it_isnt_approved_for(fallback_stack):
    stack, primary, spare = fallback_stack
    models = stack.gateway.models
    models["fake"] = dataclasses.replace(models["fake"], images=True)
    primary.failing = 2
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions", json={"model": "fake", "messages": [{
            "role": "user", "content": [
                {"type": "text", "text": "What does this show?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0K"}}]}]})
    assert r.status_code == 503 and not spare.requests


def test_a_call_a5s_skipped_isnt_counted_as_the_models(fallback_stack):
    stack, _, spare = fallback_stack
    spare.reply("On spare.")
    run, token = stack.open_run()  # on its own model, whose breaker then opens
    for _ in range(3):
        stack.gateway.breakers.failed("fake")
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions", json={"model": "fake", "messages": [
            {"role": "user", "content": "Q-1001?"}]})
    assert r.status_code == 200
    skipped = [e["outcome"].get("skipped") for e in stack.ledger(run)
               if e["kind"] == "model" and e["action"] == "fake" and e["decision"] == "record"]
    assert skipped == ["breaker open", "breaker open"]  # in the ledger, each attempt,
    with db.transaction(stack.admin) as conn:  # but not in how fake did today
        counted = {r["model"]: r["calls"] for r in conn.execute(
            "select model, calls from model_health").fetchall()}
    assert counted == {"spare": 1}


def test_a_model_that_timed_out_isnt_asked_again_in_the_same_call(fallback_stack):
    stack, primary, spare = fallback_stack

    def times_out(_: int) -> None:
        raise httpx.ReadTimeout("no answer")
    primary.on_request = times_out
    spare.reply("On spare: Q-1001 is open.")
    message = stack.send("What's the key of the open question Q-1001?")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message)[0].startswith("On spare: Q-1001 is open.")
    assert len(primary.requests) == 1  # asked once: a timeout isn't a moment's slowness


def test_the_workers_own_timeout_means_its_model_isnt_answering():
    timed_out = openai.APITimeoutError(request=httpx.Request("POST", "http://gateway/v1"))
    assert isinstance(worker.stopped(timed_out), worker.ModelDown)


def test_another_models_answer_goes_only_once_a5s_recorded_it(fallback_stack, monkeypatch):
    stack, primary, spare = fallback_stack
    real = health.record

    def unrecorded(conn, scenario, alias, status, seconds):
        if alias == "spare":
            raise psycopg.errors.LockNotAvailable("the ledger's lock timed out")
        return real(conn, scenario, alias, status, seconds)
    monkeypatch.setattr(health, "record", unrecorded)
    primary.failing = 2
    spare.reply("On spare: Q-1001 is open.")
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions", json={"model": "fake", "messages": [
            {"role": "user", "content": "Q-1001?"}]})
    assert r.status_code == 503 and "couldn't record that spare answered" in r.text


@pytest.mark.parametrize(("status", "body", "keys"), [
    (409, {"detail": {"error": "unknown_keys", "keys": ["Q-9"]}}, ["Q-9"]),
    (409, {"detail": "the message this answers is gone: a5s answers nothing in its place"}, []),
    (403, {"detail": {"keys": ["Q-9"]}}, []),
])
def test_only_a_refusal_for_keys_asks_for_the_correction(status, body, keys):
    assert scheduler.unread_keys(httpx.Response(status, json=body)) == keys
