from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from a5s import db
from a5s.core import ledger
from a5s.core.tasks import TaskError, TaskService, TaskSpec, TaskStopped


def service(database: str, lease_seconds: float = 60) -> TaskService:
    with db.transaction(database) as conn:
        conn.execute("insert into instances (id, definition, release, model) "
                     "values ('assistant-finance', 'assistant', 'test', 'fake') on conflict do nothing")
    return TaskService(database, lease_seconds=lease_seconds)


def spec(task: str = "Review the open records", budget: int = 1000,
         **changes) -> TaskSpec:
    deadline = changes.pop("deadline", datetime.now(UTC) + timedelta(hours=1))
    return TaskSpec(instance="assistant-finance", owner="ana", task=task,
                    token_budget=budget, deadline=deadline, **changes)


def test_a_task_is_durable_and_its_text_is_hashed_in_the_ledger(database):
    tasks = service(database)
    task_id = tasks.create(spec())
    found = tasks.get(task_id)
    assert found["status"] == "queued" and found["step"] == 0 and found["owner"] == "ana"
    assert [t["id"] for t in tasks.list_for("ana")] == [task_id]
    with db.transaction(database) as conn:
        entry = ledger.entries(conn)[-1]
        assert (entry["kind"], entry["action"], entry["task"]) == ("task", "start", task_id)
        assert entry["args"]["task"]["chars"] == len("Review the open records")
        assert "Review the open records" not in str(entry)
        assert ledger.verify(conn).ok


def test_a_fresh_worker_resumes_from_a_checkpoint_without_repeating_effects(database):
    tasks = service(database)
    task_id = tasks.create(spec())

    def first(task, checkpoint):
        checkpoint({"step": 1, "progress": 0.5, "partial": ["checked once"]})
        raise RuntimeError("the worker stopped")

    found = tasks.run_next(task_id, first)
    assert found["status"] == "waiting" and found["step"] == 1 and found["attempts"] == 1

    def second(task, checkpoint):
        assert task["step"] == 1 and task["partial"] == ["checked once"]
        return {"status": "done", "tokens": 25}

    found = tasks.run_next(task_id, second)
    assert found["status"] == "done" and found["attempts"] == 2
    assert found["partial"] == ["checked once"] and found["tokens"] == 25
    with db.transaction(database) as conn:
        assert ledger.verify(conn).ok


def test_an_active_worker_renews_its_lease(database):
    tasks = service(database, lease_seconds=0.06)
    task_id = tasks.create(spec())

    def work(task, checkpoint):
        time.sleep(0.15)
        checkpoint({"step": 1, "progress": 0.5})
        return {"status": "done", "tokens": 10}

    found = tasks.run_next(task_id, work)
    assert found["status"] == "done"
    assert found["last_heartbeat_at"] > found["created_at"]


def test_a_stalled_lease_is_reclaimed_by_a_fresh_worker(database):
    tasks = service(database)
    task_id = tasks.create(spec())
    stale = str(uuid.uuid4())
    with db.transaction(database) as conn:
        conn.execute("update tasks set status = 'running', lease_id = %s, lease_expires_at = %s "
                     "where id = %s", (stale, datetime.now(UTC) - timedelta(seconds=1), task_id))
    assert tasks.due() == [task_id]
    found = tasks.run_next(task_id, lambda task, checkpoint: {"status": "done"})
    assert found["status"] == "done" and found["attempts"] == 1


def test_cancellation_is_owner_only_and_stops_future_work(database):
    tasks = service(database)
    task_id = tasks.create(spec())
    with pytest.raises(TaskError, match="owner"):
        tasks.cancel(task_id, "ben")
    assert tasks.cancel(task_id, "ana")["status"] == "cancelled"
    with pytest.raises(TaskError, match="cancelled"):
        tasks.run_next(task_id, lambda task, checkpoint: {"status": "done"})


def test_cancellation_wins_over_a_workers_later_result(database):
    tasks = service(database)
    task_id = tasks.create(spec())

    def work(task, checkpoint):
        tasks.cancel(task_id, "ana")
        with pytest.raises(TaskStopped):
            checkpoint({"step": 1, "progress": 0.5})
        return {"status": "done"}

    assert tasks.run_next(task_id, work)["status"] == "cancelled"


def test_budgets_and_deadlines_stop_future_work(database):
    tasks = service(database)
    over = tasks.create(spec(budget=10))
    found = tasks.run_next(over, lambda task, checkpoint: {"status": "done", "tokens": 11})
    assert found["status"] == "failed" and "budget" in found["last_error"]
    past = tasks.create(spec())
    with db.transaction(database) as conn:
        conn.execute("update tasks set deadline = %s where id = %s",
                     (datetime.now(UTC) - timedelta(seconds=1), past))
    found = tasks.run_next(past, lambda task, checkpoint: {"status": "done"})
    assert found["status"] == "failed" and "deadline" in found["last_error"]


def test_a_blocked_task_resumes_only_with_its_owner(database):
    tasks = service(database)
    task_id = tasks.create(spec())
    found = tasks.run_next(task_id, lambda task, checkpoint: {
        "status": "blocked", "reason": "a person needs to decide", "step": 1, "progress": 0.5})
    assert found["status"] == "blocked"
    with pytest.raises(TaskError, match="owner"):
        tasks.resume(task_id, "ben")
    assert tasks.resume(task_id, "ana")["status"] == "waiting"
    assert tasks.run_next(task_id, lambda task, checkpoint: {"status": "done"})["status"] == "done"


def test_a_child_cannot_widen_its_parents_audience_instance_or_budget(database):
    tasks = service(database)
    parent = tasks.create(spec(budget=100, audience=("ana", "ben")))
    deadline = tasks.get(parent)["deadline"]
    child = tasks.create(spec("A narrower child task", budget=60, audience=("ana",), parent=parent,
                              deadline=deadline))
    assert tasks.get(child)["depth"] == 1
    with pytest.raises(TaskError, match="budget"):
        tasks.create(spec("Too much reserved work", budget=50, audience=("ana",), parent=parent,
                          deadline=deadline))
    with pytest.raises(TaskError, match="audience"):
        tasks.create(spec("A wider audience", budget=10, audience=("ana", "mallory"), parent=parent,
                          deadline=deadline))
    with db.transaction(database) as conn:
        assert ledger.verify(conn).ok
