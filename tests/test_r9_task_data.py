"""Round 9 of the critique: a task keeps its owner's words, what they asked for, its plan, its
partial results and its result, so it's under the rules for what a5s keeps
(docs/data-protection.md): an export gives it, an erasure erases it and waits for a slice at
work, archiving moves it, ending what's open, and retention lets it go 12 months after it
ended (docs/critique.md, round 9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from a5s import db
from a5s.core import departures, erasure, export, retention
from a5s.core.tasks import TaskService, TaskSpec

ASKED = "Find every invoice Ana Ortiz disputed with Northwind and draft her complaint"


def a_task(database: str, *, done: bool = True) -> tuple[TaskService, str]:
    with db.transaction(database) as conn:
        conn.execute("insert into instances (id, definition, release, model) "
                     "values ('assistant-finance', 'assistant', 'test', 'fake') "
                     "on conflict do nothing")
    tasks = TaskService(database)
    task_id = tasks.create(TaskSpec(instance="assistant-finance", owner="ana", task=ASKED,
                                    deadline=datetime.now(UTC) + timedelta(hours=1)))
    if done:
        tasks.run_next(task_id, lambda t, c: {
            "status": "done", "tokens": 10, "partial": ["Ana disputed INV-7 and INV-9"],
            "plan": [{"content": "List what Ana disputed", "status": "completed"}],
            "result": {"draft": "Dear Northwind, Ana Ortiz disputes..."}})
    return tasks, task_id


def test_an_export_of_someone_holds_the_tasks_they_asked_for(database):
    a_task(database)
    with db.transaction(database) as conn:
        found = export.gather(conn, "ana")
        other = export.gather(conn, "ben")
    [task] = found["tasks"]
    assert task["task"] == ASKED and task["status"] == "done"
    assert "Dear Northwind" in json.dumps(task["result"])
    assert export.counts(found)["tasks"] == 1 and other["tasks"] == []


def test_erasing_someone_erases_the_tasks_they_asked_for(database):
    _, task_id = a_task(database)
    with db.transaction(database) as conn:
        gone, _ = erasure.erase(conn, "ana", datetime.now(UTC), here=True)
        left = conn.execute("select 1 from tasks where id = %s", (task_id,)).fetchone()
    assert left is None and gone["tasks"] == 1


def test_an_erasure_waits_for_a_slice_at_work_for_them(database):
    tasks, task_id = a_task(database, done=False)

    def work(task, checkpoint):
        with pytest.raises(erasure.Busy), db.transaction(database) as conn:
            erasure.erase(conn, "ana", datetime.now(UTC), here=True)
        return {"status": "done"}

    assert tasks.run_next(task_id, work)["status"] == "done"


def test_archiving_someone_who_left_moves_their_tasks_and_ends_what_was_open(database):
    tasks, done = a_task(database)
    _, open_one = a_task(database, done=False)
    with db.transaction(database) as conn:
        name = departures.archive(conn, "ana", datetime.now(UTC))
        rows = {str(r["id"]): r for r in conn.execute(
            "select id, owner, audience, status from tasks where id = any(%s::uuid[])",
            ([done, open_one],))}
    assert {r["owner"] for r in rows.values()} == {name} and tasks.list_for("ana") == []
    assert all(r["audience"] == [name] for r in rows.values())
    assert (rows[done]["status"], rows[open_one]["status"]) == ("done", "cancelled")


def test_retention_lets_a_task_go_12_months_after_it_ended(database):
    _, old = a_task(database)
    _, recent = a_task(database)
    with db.transaction(database) as conn:
        conn.execute("update tasks set updated_at = now() - interval '13 months' where id = %s",
                     (old,))
        gone = retention.sweep(conn, datetime.now(UTC), "sample")
        left = {str(r["id"]) for r in conn.execute("select id from tasks")}
    assert left == {recent} and gone["tasks"] == 1


def test_retention_lets_a_task_go_12_months_after_its_deadline_whatever_it_was_waiting_for(
        database):
    tasks, task_id = a_task(database, done=False)
    tasks.run_next(task_id, lambda t, c: {"status": "blocked", "reason": "a person decides"})
    with db.transaction(database) as conn:  # nobody ever did
        conn.execute("update tasks set deadline = now() - interval '13 months', "
                     "updated_at = now() - interval '13 months' where id = %s", (task_id,))
        retention.sweep(conn, datetime.now(UTC), "sample")
        assert conn.execute("select 1 from tasks where id = %s", (task_id,)).fetchone() is None
