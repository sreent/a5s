"""Round 9 of the critique: the task engine (core/tasks.py) when slices fail, leases lapse,
and a task and its children share a budget. Every token a slice reports counts, a report
past a budget ends the task, the tree spends no more than its root's budget, a failing slice
waits longer each time and then fails, a refused result blocks its task for a person to
decide, a heartbeat outlives a database's moment, a stale worker can't end a live one's lease,
cancelling stops a task's children and keeps what its slice did, and only the core writes a
task (docs/critique.md, round 9)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from a5s import db
from a5s.core import tasks as engine
from a5s.core.tasks import TaskError, TaskService, TaskSpec, TaskStopped


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
    tasks = service(database)
    task_id = tasks.create(spec(budget=100))

    def work(task, checkpoint):
        assert task["tokens_left"] == 100 - task["tokens"]  # the most its slice may spend
        if task["tokens"] == 0:
            checkpoint({"step": 1, "progress": 0.2, "tokens": 60})
        checkpoint({"step": 2, "progress": 0.4, "tokens": 60})
        return {"status": "done"}

    for _ in range(5):  # the scheduler offers whatever due() lists
        if task_id not in tasks.due():
            break
        tasks.run_next(task_id, work)
    found = tasks.get(task_id)
    assert (found["status"], found["tokens"], found["attempts"]) == ("failed", 120, 1)
    assert "budget" in found["last_error"]


def test_a_slice_that_fails_waits_longer_each_time_and_then_fails(database):
    tasks = service(database)
    task_id = tasks.create(spec(budget=100))

    def work(task, checkpoint):
        raise RuntimeError("the model answered something the worker can't parse")

    tasks.run_next(task_id, work)
    found = tasks.get(task_id)
    assert found["status"] == "waiting" and task_id not in tasks.due()  # it waits a while
    assert task_id in tasks.due(found["not_before"] + timedelta(seconds=1))
    waits = [found["not_before"] - found["updated_at"]]
    for _ in range(engine.MAX_FAILURES - 1):
        found = tasks.run_next(task_id, work)
        if found["not_before"]:
            waits.append(found["not_before"] - found["updated_at"])
    assert found["status"] == "failed" and "5 times in a row" in found["last_error"]
    assert waits == sorted(waits) and waits[-1] > waits[0]  # longer each time


def test_one_failed_heartbeat_doesnt_let_a_second_worker_take_a_live_slice(database, monkeypatch):
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

    def first(task, checkpoint):
        effects.append("first worker's effect")
        time.sleep(0.8)  # still at work: a model call, a slow tool
        if task_id in tasks.due():  # a second scheduler would see it free, and run it
            tasks.run_next(task_id, lambda t, c: (
                effects.append("second worker's effect") or {"status": "done"}))
        return {"status": "done"}

    tasks.run_next(task_id, first)
    assert effects == ["first worker's effect"], effects


def test_after_a_cancel_the_heartbeat_stops_quietly(database, monkeypatch):
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


def test_cancelling_a_task_cancels_its_children(database):
    tasks = service(database)
    parent = tasks.create(spec(budget=100))
    deadline = tasks.get(parent)["deadline"]
    child = tasks.create(spec("A part of it", budget=50, parent=parent, deadline=deadline))
    grandchild = tasks.create(spec("A part of that", budget=20, parent=child, deadline=deadline))
    tasks.cancel(parent, "ana")
    assert not {child, grandchild} & set(tasks.due())
    assert {tasks.get(t)["status"] for t in (child, grandchild)} == {"cancelled"}
    with pytest.raises(TaskError, match="cancelled"):
        tasks.run_next(child, lambda task, checkpoint: {"status": "done", "tokens": 50})


def test_a_task_and_its_children_spend_no_more_than_the_roots_budget(database):
    tasks = service(database)
    parent = tasks.create(spec(budget=100))
    deadline = tasks.get(parent)["deadline"]
    child = tasks.create(spec("A part of it", budget=60, parent=parent, deadline=deadline))
    tasks.run_next(parent, lambda t, c: {"status": "waiting", "tokens": 100})
    found = tasks.run_next(child, lambda t, c: {"status": "done", "tokens": 60})
    assert found["status"] == "failed" and "tree" in found["last_error"]  # never ran
    assert tasks.get(parent)["tokens"] + found["tokens"] == 100


def test_a_chain_of_children_shares_one_budget(database):
    tasks = service(database)
    root = tasks.create(spec(budget=100))
    deadline = tasks.get(root)["deadline"]
    chain = [root]
    for _ in range(3):  # each makes a child with all of its budget before spending any
        chain.append(tasks.create(spec("A child", budget=100, parent=chain[-1],
                                       deadline=deadline)))
    ran = [tasks.run_next(t, lambda task, checkpoint: {"status": "done", "tokens": 100})
           for t in chain]
    assert [r["status"] for r in ran] == ["done", "failed", "failed", "failed"]
    assert sum(r["tokens"] for r in ran) <= tasks.get(root)["token_budget"]


def test_a_result_the_core_refuses_blocks_the_task_rather_than_do_it_again(database):
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

    found = tasks.run_next(task_id, work)
    time.sleep(0.3)
    assert task_id not in tasks.due()
    assert (found["status"], found["tokens"], found["lease_id"]) == ("blocked", 50, None)
    assert "refused" in found["last_error"] and found["plan"] == plan  # as it was kept
    assert effects == ["sent Ana the summary"], effects


def test_a_cancel_mid_slice_keeps_what_that_slice_did(database):
    tasks = service(database)
    task_id = tasks.create(spec())

    def work(task, checkpoint):
        checkpoint({"step": 1, "progress": 0.3, "partial": ["read the open records"],
                    "tokens": 10})
        tasks.cancel(task_id, "ana")  # Ana stops it from the task's page, meanwhile
        return {"status": "done", "tokens": 40,  # the slice had already sent the summary
                "partial": ["read the open records", "sent Ana the summary"]}

    found = tasks.run_next(task_id, work)
    assert found["status"] == "cancelled" and found["lease_id"] is None
    assert (found["partial"], found["tokens"]) == (
        ["read the open records", "sent Ana the summary"], 50)


def test_a_stale_worker_doesnt_end_the_live_workers_lease(database):
    tasks = service(database)
    task_id = tasks.create(spec(budget=1000))
    live_started, go_on, live_result = threading.Event(), threading.Event(), {}

    def live(task, checkpoint):
        live_started.set()
        go_on.wait(30)
        checkpoint({"step": 2, "progress": 0.6})  # its lease is still good
        return {"status": "done", "tokens": 10}

    def stale(task, checkpoint):
        with db.transaction(database) as conn:  # it stalls past its lease, say in a long pause
            conn.execute("update tasks set lease_expires_at = now() - interval '1 second' "
                         "where id = %s", (task_id,))
        other = threading.Thread(target=lambda: live_result.update(
            tasks.run_next(task_id, live)), daemon=True)
        other.start()  # a fresh worker takes the task over, under a lease of its own
        assert live_started.wait(30)
        checkpoint({"step": 1, "progress": 0.5, "tokens": 7})  # no longer its lease
        raise AssertionError("unreachable")

    tasks.run_next(task_id, stale)
    between = tasks.get(task_id)
    go_on.set()
    for _ in range(300):
        if live_result:
            break
        threading.Event().wait(0.1)
    assert between["status"] == "running" and live_result.get("status") == "done", (
        between["status"], live_result.get("status"))
    assert live_result["tokens"] == 17  # what the stale one spent counts too


def test_only_the_core_writes_a_task(database):
    tasks = service(database)
    task_id = tasks.create(spec(budget=100, audience=("ana",)))
    with (pytest.raises(psycopg.errors.InsufficientPrivilege),
          db.transaction(db.as_role(database, "scheduler")) as conn):
        conn.execute("update tasks set token_budget = 1000000000, audience = '{ana,mallory}', "
                     "deadline = now() + interval '1 year', owner = 'mallory' where id = %s",
                     (task_id,))
    found = tasks.run_next(task_id, lambda task, checkpoint: {"status": "done", "tokens": 5000})
    assert (found["status"], found["audience"], found["owner"]) == ("failed", ["ana"], "ana")


def test_a_checkpoint_after_the_lease_was_taken_stops_the_slice(database):
    tasks = service(database)
    task_id = tasks.create(spec())

    def work(task, checkpoint):
        with db.transaction(database) as conn:  # another worker took it over meanwhile
            conn.execute("update tasks set lease_id = gen_random_uuid() where id = %s",
                         (task_id,))
        with pytest.raises(TaskStopped):
            checkpoint({"step": 1, "progress": 0.5})
        return {"status": "done"}

    assert tasks.run_next(task_id, work)["status"] == "running"  # the other's, untouched
