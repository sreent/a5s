"""Round 9, reviewer A: "No task can widen its own permissions, budget, audience, or deadline"
and "the core alone writes its state through its own interfaces" (docs/phase-4.md), against the
task engine (core/tasks.py) and migration 0042."""

import threading
from datetime import UTC, datetime, timedelta

from a5s import db
from a5s.core.tasks import TaskService, TaskSpec, TaskStopped


def service(database: str, lease_seconds: float = 60) -> TaskService:
    with db.transaction(database) as conn:
        conn.execute("insert into instances (id, definition, release, model) "
                     "values ('assistant-finance', 'assistant', 'test', 'fake') "
                     "on conflict do nothing")
    return TaskService(database, lease_seconds=lease_seconds)


def spec(task: str = "Review the open records", budget: int = 100, **changes) -> TaskSpec:
    deadline = changes.pop("deadline", datetime.now(UTC) + timedelta(hours=1))
    return TaskSpec(instance="assistant-finance", owner="ana", task=task, token_budget=budget,
                    deadline=deadline, **changes)


def test_the_scheduler_writes_a_tasks_budget_audience_and_deadline_itself(database):
    """Migration 0042 grants the scheduler, a service outside the trusted core, update on every
    column of tasks: it widens any task, and the engine then runs it to its new limits."""
    tasks = service(database)
    task_id = tasks.create(spec(budget=100, audience=("ana",)))
    with db.transaction(db.as_role(database, "scheduler")) as conn:
        widened = conn.execute(
            "update tasks set token_budget = 1000000000, audience = '{ana,mallory}', "
            "deadline = now() + interval '1 year', owner = 'mallory' where id = %s",
            (task_id,)).rowcount
    found = tasks.run_next(task_id, lambda task, checkpoint: {"status": "done", "tokens": 5000})
    # FAILS NOW: the scheduler's role rewrote the task, and 5,000 tokens ran on a budget of 100
    assert widened == 0 and found["status"] == "failed", (widened, found["status"],
                                                           found["audience"], found["owner"])


def test_a_parent_and_its_children_spend_four_times_the_parents_budget(database):
    """A child reserves part of its parent's budget only against what the parent had spent when
    the child was made; the parent's own spending is never counted against its children."""
    tasks = service(database)
    root = tasks.create(spec(budget=100))
    deadline = tasks.get(root)["deadline"]
    chain = [root]
    for _ in range(3):  # each makes a child with all of its budget before spending any
        chain.append(tasks.create(spec("A child", budget=100, parent=chain[-1],
                                       deadline=deadline)))
    spent = 0
    for task_id in chain:  # then every one of them spends its whole budget
        found = tasks.run_next(task_id, lambda task, checkpoint: {"status": "done", "tokens": 100})
        assert found["status"] == "done"
        spent += found["tokens"]
    # FAILS NOW: 400 tokens spent under a parent with a total budget of 100
    assert spent <= tasks.get(root)["token_budget"], spent


def test_a_stale_worker_ends_the_live_workers_lease(database):
    """A worker whose lease expired, and was taken over, ends the slice of the worker that took
    it over, whose heartbeat is live: its finish sets the task waiting without its lease."""
    tasks = service(database)
    task_id = tasks.create(spec(budget=1000))
    live_started, go_on, live_result = threading.Event(), threading.Event(), {}

    def live(task, checkpoint):
        live_started.set()
        go_on.wait(30)
        checkpoint({"step": 2, "progress": 0.6})  # its lease ought still to be good
        return {"status": "done", "tokens": 10}

    def stale(task, checkpoint):
        with db.transaction(database) as conn:  # it stalls past its lease, say in a long pause
            conn.execute("update tasks set lease_expires_at = now() - interval '1 second' "
                         "where id = %s", (task_id,))
        other = threading.Thread(target=lambda: live_result.update(
            tasks.run_next(task_id, live)), daemon=True)
        other.start()  # a fresh worker takes the task over, under a lease of its own
        assert live_started.wait(30)
        checkpoint({"step": 1, "progress": 0.5})  # TaskStopped: no longer its lease
        raise AssertionError("unreachable")

    try:
        tasks.run_next(task_id, stale)
    except TaskStopped:
        pass
    between = tasks.get(task_id)
    go_on.set()
    for _ in range(300):
        if live_result:
            break
        threading.Event().wait(0.1)
    # FAILS NOW: the stale worker set the task waiting under the live one, which then stopped
    assert between["status"] == "running" and live_result.get("status") == "done", (
        between["status"], live_result.get("status"))


def test_cancelling_a_task_leaves_its_children_running(database):
    """Cancellation stops future runs (docs/phase-4.md), but only of the task cancelled: its
    children stay due and run on, with the budget they reserved, after their owner stopped it."""
    tasks = service(database)
    parent = tasks.create(spec(budget=100))
    child = tasks.create(spec("A child", budget=90, parent=parent,
                              deadline=tasks.get(parent)["deadline"]))
    assert tasks.cancel(parent, "ana")["status"] == "cancelled"
    due = tasks.due()
    ran = tasks.run_next(child, lambda task, checkpoint: {"status": "done", "tokens": 90})
    # FAILS NOW: the child of a cancelled task is still due, and runs
    assert child not in due and ran["status"] != "done", (due, ran["status"])


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
