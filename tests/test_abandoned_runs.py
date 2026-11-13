"""A run whose scheduler stopped without closing it, as when it's killed part way, is closed at
the core's next sweep once the scheduler's lease on its work is gone, or lapsed as long ago as
a lease lasts, and its person is told, unless they had an answer: not an hour on, when the
run's time is up. A task's slice ends with it, so the task goes on rather than wait out the
hour (core/gateway.py's /runs/sweep, services/scheduler.py)."""

from __future__ import annotations

from datetime import timedelta

from a5s import db
from a5s.worker import run_agent
from test_task_runs import a_task, tasks_of

STOPPED = "I couldn't finish your last message, so I stopped. Send it again if you still need it."


def stopped(stack) -> tuple[str, dict]:
    """A message, claimed and its run opened as the scheduler does, which then stops before it
    answers: the message, and the run, with its token."""
    message = stack.send("Which questions mention an invoice?")
    claim = stack.scheduler()._claim()
    assert claim["id"] == message
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": message, "holder": claim["holder"]}})
    assert opened.status_code == 200, opened.text
    return message, opened.json()


def lapsed(stack, seconds: int = 121) -> None:
    """The scheduler's leases, past their time by `seconds`, as once it stopped renewing them."""
    with db.transaction(stack.admin) as conn:
        conn.execute("update leases set expires_at = now() - make_interval(secs => %s)",
                     (seconds,))


def open_runs(stack) -> list[str]:
    with db.transaction(stack.admin) as conn:
        return [r["id"] for r in conn.execute("select id::text from runs where closed_at is null")]


def test_a_run_whose_scheduler_stopped_is_closed_at_the_next_sweep_and_its_person_told(stack):
    message, run = stopped(stack)
    stack.scheduler().sweep()  # its scheduler's lease is live: it may be at work on it still
    assert open_runs(stack) == [run["run"]]
    lapsed(stack, seconds=30)  # nor does a moment it couldn't renew its lease cost it the run
    stack.scheduler().sweep()
    assert open_runs(stack) == [run["run"]]
    lapsed(stack)  # lapsed as long ago as a lease lasts: its scheduler stopped
    stack.scheduler().sweep()
    assert open_runs(stack) == []
    assert [e["outcome"] for e in stack.ledger(run["run"])
            if e["action"] == "close"] == ["abandoned"]
    assert stack.answers(message) == [STOPPED]
    with stack.client(run["token"]) as c:  # and its token died with it
        assert c.get("/run").status_code == 401
    stack.scheduler().sweep()  # and they're told once
    assert stack.answers(message) == [STOPPED]


def test_a_run_that_answered_before_its_scheduler_stopped_tells_its_person_nothing_more(stack):
    message, run = stopped(stack)
    with stack.client(run["token"]) as c:  # its answer went, and then its scheduler stopped
        sent = c.post("/run/messages", json={"to": "ana", "text": "Nothing mentions one."})
    assert sent.status_code == 200, sent.text
    lapsed(stack)
    stack.scheduler().sweep()
    assert open_runs(stack) == []
    assert stack.answers(message) == ["Nothing mentions one."]


def test_a_run_that_names_no_lease_waits_for_its_time_as_before(stack):
    run, _ = stack.open_run()  # as a scheduler from before this release opened it
    lapsed(stack)
    stack.scheduler().sweep()
    assert open_runs(stack) == [run]


def test_a_slice_whose_scheduler_was_killed_ends_at_the_next_sweep_and_its_task_goes_on(stack):
    a_task(stack)
    stack.model.reply(None, ("checkpoint_task", {"step": 1, "progress": 0.5,
                                                 "partial": ["Q-1001 waits on an address"]}))
    stack.model.reply("Going on.")
    killed = stack.scheduler(worker=lambda url, token, history: (run_agent(
        url, token, history), (_ for _ in ()).throw(SystemExit))[0])  # killed part way:
    killed._close = lambda run, outcome: None  # it never closes its run,
    killed._release = lambda claim: None  # nor lets its lease go
    try:
        killed.work_due()
    except SystemExit:
        pass
    stack.scheduler().sweep()  # while its lease is live, the slice may be at work still
    assert tasks_of(stack)[0]["status"] == "running"
    lapsed(stack)
    stack.scheduler().sweep()  # then the slice ends, as abandoned, not an hour on
    [waiting] = tasks_of(stack)
    assert (waiting["status"], waiting["failures"], waiting["step"]) == ("waiting", 1, 1)
    assert waiting["lease_id"] is None
    stack.at((stack.gateway.clock() + timedelta(minutes=1)).isoformat())  # past its backoff
    stack.model.reply(None, ("finish_task", {"status": "done", "result": {"Q-1001": "an address"}}))
    stack.model.reply("Ana, your task is done: Q-1001 waits on an address.")
    assert stack.scheduler().work_due() == 1  # a fresh slice, from what the task kept
    assert "Q-1001 waits on an address" in str(stack.model.requests[-2]["body"]["messages"])
    [done] = tasks_of(stack)
    assert (done["status"], done["attempts"]) == ("done", 2)
