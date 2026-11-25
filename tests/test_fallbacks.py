"""Model fallbacks (core/gateway.py's model_for, services/scheduler.py): when a run's model
isn't answering, a message is tried again on the next model its release names, each tried once,
and only once every one has failed does the person hear a5s's words for it. A fallback the
models file doesn't approve is never called, and a model whose breaker is open is passed over
for the next, so one provider's outage costs a retry, not the work."""

from __future__ import annotations

from a5s import db


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
    message = stack.send("What's the key of the open question Q-1001?")  # named, so it's read
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
    message = stack.send("What's the key of the open question Q-1001?")  # named, so it's read
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
    message = stack.send("What's the key of the open question Q-1001?")  # named, so it's read
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


def test_a_gated_model_is_passed_over_for_its_fallback(fallback_stack):
    """The reliability ledger's gate (core/health.py): a model whose SLO was breached is
    stopped from answering, without a word to the person, and its fallback serves the run."""
    from a5s.core import health
    stack, _, spare = fallback_stack
    with db.transaction(stack.admin) as conn:
        for i in range(20):
            health.record(conn, stack.gateway.scenario.name, "fake", 503 if i < 11 else 200, 0.5)
    spare.reply("On spare: Q-1001 is open.")
    message = stack.send("What's the key of the open question Q-1001?")  # named, so it's read
    assert stack.scheduler().answer_waiting() == 1
    [said] = stack.answers(message)
    assert said.startswith("On spare: Q-1001 is open.")  # the gated model was never called


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
    message = stack.send("What's the key of the open question Q-1001?")  # named, so it's read
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == ["On spare, from the start."]
    assert set(models_called(stack)) == {"spare"}  # never the open one, though nothing failed


def test_a_run_goes_on_on_its_own_model_after_a_call_fell_back(fallback_stack):
    """A call its fallback answered leaves the run on its own model: its next call, after the
    tool the fallback asked for, is its own model's again, and policy lets it, so the run
    answers rather than dying on its next call (round 16)."""
    stack, primary, spare = fallback_stack
    primary.failing = 2  # its first call falls back
    spare.reply(None, ("get_record", {"key": "Q-1002"}))
    primary.reply("Q-1002 is waiting on finance.")
    message = stack.send("What's Q-1002's status?")
    assert stack.scheduler().answer_waiting() == 1
    [said] = stack.answers(message)
    assert said.startswith("Q-1002 is waiting on finance.")
    called = [(e["action"], e["decision"]) for e in stack.ledger()
              if e["kind"] == "model" and e["decision"] != "record"]
    assert called == [("fake", "allow"), ("fake", "allow")]  # each call its own model's
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select model from runs").fetchall()
    assert run["model"] == "fake"  # the model it opened on, whichever answered a call


def test_a_message_to_a_suspended_instance_is_answered_once_though_it_names_a_fallback(
        fallback_stack):
    """A message is kept open, while its release names models not tried, only for a model
    that isn't answering, never for a run a5s refused: refused, as for a suspended instance,
    it's answered once, with why, and not taken again at once, for ever (round 16)."""
    stack, _, _ = fallback_stack
    stack.suspend()
    message = stack.send("Hello")
    scheduler = stack.scheduler()
    claim = scheduler._claim()  # one message, one claim: the loop never spins on it
    assert claim is not None and claim["id"] == message
    scheduler._answer(claim)
    assert scheduler._claim() is None  # nothing waits: it's answered
    [said] = stack.answers(message)
    assert "suspended" in said
