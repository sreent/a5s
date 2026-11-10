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


PLAN = [{"content": "Read the open records", "status": "completed"},  # as LangChain's todos
        {"content": "Draft the summary for Ana", "status": "in_progress"},
        {"content": "Send it to Ana", "status": "pending"}]


def test_a_tasks_plan_is_kept_with_it_and_shown_to_the_next_run(database):
    tasks = service(database)
    task_id = tasks.create(spec())

    def first(task, checkpoint):
        assert task["plan"] == []  # nothing planned yet
        checkpoint({"step": 1, "progress": 0.3, "plan": PLAN})
        raise RuntimeError("the worker stopped")

    assert tasks.run_next(task_id, first)["plan"] == PLAN  # what its owner sees

    def second(task, checkpoint):  # a fresh worker, shown the plan from the task's record
        assert task["plan"] == PLAN
        return {"status": "done", "tokens": 25,
                "plan": [{**s, "status": "completed"} for s in PLAN]}

    done = tasks.run_next(task_id, second)
    assert done["status"] == "done" and {s["status"] for s in done["plan"]} == {"completed"}
    with db.transaction(database) as conn:
        [entry] = [e for e in ledger.entries(conn) if e["action"] == "done"]
        assert (entry["args"]["steps"], entry["args"]["completed"]) == (3, 3)
        assert "Draft the summary" not in str(ledger.entries(conn))  # by hash, as all text is


def test_a_plan_is_short_and_keeps_what_was_completed(database):
    tasks = service(database)
    task_id = tasks.create(spec())
    refused: list[str] = []

    def worker(task, checkpoint):
        checkpoint({"plan": PLAN})
        for plan in ([{"content": f"Step {n}", "status": "pending"} for n in range(21)],  # many
                     [{"content": "x" * 201, "status": "pending"}],  # too long
                     [{"content": "Read", "status": "started"}],  # not a status
                     [{"content": "One", "status": "in_progress"},
                      {"content": "Two", "status": "in_progress"}],  # one at a time
                     PLAN[1:],  # what was completed, gone
                     [{**PLAN[0], "status": "pending"}, *PLAN[1:]],  # completed, undone
                     [{**PLAN[0], "content": "Read the records"}, *PLAN[1:]]):  # reworded
            with pytest.raises(TaskError) as why:
                checkpoint({"plan": plan})
            refused.append(str(why.value))
        checkpoint({"plan": [PLAN[0], {"content": "Ask finance first", "status": "completed"},
                             {"content": "Send it to Ana", "status": "in_progress"}]})  # revised
        return {"status": "waiting"}

    found = tasks.run_next(task_id, worker)
    assert len(refused) == 7 and found["status"] == "waiting"
    assert [s["content"] for s in found["plan"]] == [
        "Read the open records", "Ask finance first", "Send it to Ana"]
