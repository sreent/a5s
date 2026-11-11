"""Round 9, reviewer B: the task engine (core/tasks.py) when slices fail, leases lapse, and
parents and children share a budget. Each test states what docs/phase-4.md promises, and
fails while the engine doesn't keep it."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import psycopg

from a5s import db
from a5s.core.tasks import TaskError, TaskService, TaskSpec


def service(database: str, lease_seconds: float = 60) -> TaskService:
    with db.transaction(database) as conn:
        conn.execute("insert into instances (id, definition, release, model) "
                     "values ('assistant-finance', 'assistant', 'test', 'fake') "
                     "on conflict do nothing")
    return TaskService(database, lease_seconds=lease_seconds)


def spec(task: str = "Review the open records", budget: int = 1000, **changes) -> TaskSpec:
    deadline = changes.pop("deadline", datetime.now(UTC) + timedelta(hours=1))
    return TaskSpec(instance="assistant-finance", owner="ana", task=task,
                    token_budget=budget, deadline=deadline, **changes)


def test_a_checkpoint_past_the_budget_ends_the_task_and_counts_what_was_spent(database):
    """phase-4: 'The core counts all runs against the task's total budget', and budget
    exhaustion stops future work. A checkpoint that reports tokens past the budget is
    refused without counting them, and the task goes back to waiting, so it runs again and
    again, each slice spending tokens nothing counts."""
    tasks = service(database)
    task_id = tasks.create(spec(budget=100))
    spent = 0

    def work(task, checkpoint):
        nonlocal spent
        if task["tokens"] == 0:
            spent += 60
            checkpoint({"step": 1, "progress": 0.2, "tokens": 60})
        spent += 60  # the model calls this slice made, as the worker reports them
        checkpoint({"step": 2, "progress": 0.4, "tokens": 60})
        return {"status": "done"}

    for _ in range(5):  # the scheduler offers whatever due() lists
        if task_id not in tasks.due():
            break
        tasks.run_next(task_id, work)
    found = tasks.get(task_id)
    # What happens now: still 'waiting', 60 tokens counted, 5 slices run, 360 spent.
    assert found["status"] == "failed", (found["status"], found["tokens"], found["attempts"], spent)
    assert found["tokens"] >= 120


def test_a_slice_that_fails_counts_what_it_spent_and_isnt_offered_forever(database):
    """A slice that raises after its model calls reports nothing, so its tokens never count,
    and due() offers the task again at once, with no limit on attempts and no wait, until its
    deadline (a day, by default)."""
    tasks = service(database)
    task_id = tasks.create(spec(budget=100))

    def work(task, checkpoint):
        raise RuntimeError("the model answered something the worker can't parse")

    runs = 0
    while task_id in tasks.due() and runs < 25:
        tasks.run_next(task_id, work)
        runs += 1
    found = tasks.get(task_id)
    # What happens now: 25 attempts in a row, each offered at once, 0 tokens counted.
    assert runs < 25, (found["status"], found["attempts"], found["tokens"])


def test_one_failed_heartbeat_doesnt_let_a_second_worker_take_a_live_slice(database, monkeypatch):
    """phase-4: 'A stalled lease expires, but one with a live heartbeat does not.' One
    database error (a failover, a restart) ends the heartbeat thread for good, so the lease of
    a worker that's still at work lapses, and a second worker takes the task alongside it."""
    tasks = service(database, lease_seconds=0.3)
    task_id = tasks.create(spec())
    real, beats = TaskService.heartbeat, {"n": 0}

    def flaky(self, task, lease):
        beats["n"] += 1
        if beats["n"] == 1:
            raise psycopg.OperationalError("the database restarted")
        return real(self, task, lease)

    monkeypatch.setattr(TaskService, "heartbeat", flaky)
    effects: list[str] = []
    second: list[dict] = []

    def first(task, checkpoint):
        effects.append("first worker's effect")
        time.sleep(0.8)  # still at work: a model call, a slow tool
        if task_id in tasks.due():  # a second scheduler sees it free, and runs it
            second.append(tasks.run_next(task_id, lambda t, c: (
                effects.append("second worker's effect") or {"status": "done"})))
        return {"status": "done"}

    tasks.run_next(task_id, first)
    # What happens now: both workers ran the slice: ['first...', 'second...'].
    assert effects == ["first worker's effect"], effects


def test_after_a_cancel_the_heartbeat_stops_without_an_unhandled_exception(database, monkeypatch):
    """Cancelling a running task makes its heartbeat thread die on an uncaught TaskStopped,
    which threading reports as an unhandled exception (a traceback in the log) each time."""
    tasks = service(database, lease_seconds=0.06)
    task_id = tasks.create(spec())
    unhandled: list[BaseException] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: unhandled.append(args.exc_value))

    def work(task, checkpoint):
        tasks.cancel(task_id, "ana")
        time.sleep(0.1)  # a heartbeat falls due meanwhile
        return {"status": "done"}

    assert tasks.run_next(task_id, work)["status"] == "cancelled"
    assert unhandled == [], [type(e).__name__ for e in unhandled]


def test_cancelling_a_parent_stops_its_children(database):
    """phase-4: 'Cancellation ... stops future runs.' Cancelling a task leaves its children
    queued, offered by due() and run as before."""
    tasks = service(database)
    parent = tasks.create(spec(budget=100))
    deadline = tasks.get(parent)["deadline"]
    child = tasks.create(spec("A part of it", budget=50, parent=parent, deadline=deadline))
    tasks.cancel(parent, "ana")
    assert child not in tasks.due()
    assert tasks.get(child)["status"] == "cancelled"


def test_a_parent_and_its_children_spend_no_more_than_the_parents_budget(database):
    """phase-4: children have a 'shared budget' with their parent. A child's budget is
    checked against the parent's when it's made, but the parent's own spending isn't checked
    against what its children hold, nor their spending added to its."""
    tasks = service(database)
    parent = tasks.create(spec(budget=100))
    deadline = tasks.get(parent)["deadline"]
    child = tasks.create(spec("A part of it", budget=60, parent=parent, deadline=deadline))
    tasks.run_next(parent, lambda t, c: {"status": "waiting", "tokens": 100})  # allowed: 100
    tasks.run_next(child, lambda t, c: {"status": "done", "tokens": 60})  # allowed: 60
    spent = tasks.get(parent)["tokens"] + tasks.get(child)["tokens"]
    assert spent <= 100, spent  # what happens now: 160


def test_a_result_the_core_refuses_isnt_lost_and_done_again(database):
    """A worker's final result that fails a check, such as a plan that rewords a completed
    step, raises out of _finish: the task stays 'running' under a lease nothing renews, its
    tokens and its 'done' are lost, and once the lease lapses the next worker does the work
    again from the last checkpoint."""
    tasks = service(database, lease_seconds=0.2)
    task_id = tasks.create(spec())
    effects: list[str] = []
    plan = [{"content": "Send Ana the summary", "status": "completed"}]

    def work(task, checkpoint):
        if not task["plan"]:
            checkpoint({"step": 1, "progress": 0.5, "plan": plan})
        effects.append("sent Ana the summary")  # an effect, such as a message
        return {"status": "done", "tokens": 50,  # the model tidied its wording, as models do
                "plan": [{"content": "Sent Ana the summary", "status": "completed"}]}

    try:
        tasks.run_next(task_id, work)
    except TaskError:
        pass
    found = tasks.get(task_id)
    time.sleep(0.3)
    if task_id in tasks.due():
        try:
            tasks.run_next(task_id, work)
        except TaskError:
            pass
    # What happens now: 'running', 0 tokens, then the effect again: 2 effects.
    assert (found["status"], found["tokens"], len(effects)) != ("running", 0, 2), (
        found["status"], found["tokens"], effects)
    assert effects == ["sent Ana the summary"], effects


def test_a_cancel_mid_slice_keeps_what_that_slice_did(database):
    """phase-4: cancellation stops future work 'and tell[s] the owner what was done'. A
    cancel that lands while a slice works discards the slice's result whole: what it did
    after its last checkpoint, and the tokens it spent, are never recorded."""
    tasks = service(database)
    task_id = tasks.create(spec())

    def work(task, checkpoint):
        checkpoint({"step": 1, "progress": 0.3, "partial": ["read the open records"],
                    "tokens": 10})
        tasks.cancel(task_id, "ana")  # Ana stops it from the task's page, meanwhile
        return {"status": "done", "tokens": 40,  # the slice had already sent the summary
                "partial": ["read the open records", "sent Ana the summary"]}

    found = tasks.run_next(task_id, work)
    assert found["status"] == "cancelled"
    assert (found["partial"], found["tokens"]) == (
        ["read the open records", "sent Ana the summary"], 50), (found["partial"], found["tokens"])


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
