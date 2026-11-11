"""Round 9, reviewer B: a task's record holds its owner's words (what they asked for, its
plan, partial results and result), under their id. docs/phase-4.md keeps 'text ... under the
existing data-protection rules', but the tasks table is outside all of them: export, erasure,
archiving on departure, and retention."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from a5s import db
from a5s.core import departures, erasure, export, retention
from a5s.core.tasks import TaskService, TaskSpec

ASKED = "Find every invoice Ana Ortiz disputed with Northwind and draft her complaint"


def a_task(database: str) -> str:
    with db.transaction(database) as conn:
        conn.execute("insert into instances (id, definition, release, model) "
                     "values ('assistant-finance', 'assistant', 'test', 'fake') "
                     "on conflict do nothing")
    tasks = TaskService(database)
    task_id = tasks.create(TaskSpec(instance="assistant-finance", owner="ana", task=ASKED,
                                    deadline=datetime.now(UTC) + timedelta(hours=1)))
    tasks.run_next(task_id, lambda t, c: {
        "status": "done", "tokens": 10, "partial": ["Ana disputed INV-7 and INV-9"],
        "result": {"draft": "Dear Northwind, Ana Ortiz disputes..."}})
    return task_id


def test_an_export_of_someone_holds_the_tasks_they_asked_for(database):
    a_task(database)
    with db.transaction(database) as conn:
        found = export.gather(conn, "ana")
    assert ASKED in json.dumps(found, default=str), "the export says nothing of Ana's task"


def test_erasing_someone_erases_the_tasks_they_asked_for(database):
    task_id = a_task(database)
    with db.transaction(database) as conn:
        erasure.erase(conn, "ana", datetime.now(UTC), here=True)
        row = conn.execute("select owner, task, partial, result from tasks where id = %s",
                           (task_id,)).fetchone()
    assert row is None or ASKED not in row["task"], (
        "after Ana's erasure her task is still there, in her words, under her id", row["owner"])


def test_archiving_someone_who_left_moves_their_tasks_too(database):
    task_id = a_task(database)
    with db.transaction(database) as conn:
        departures.archive(conn, "ana", datetime.now(UTC))
        row = conn.execute("select owner from tasks where id = %s", (task_id,)).fetchone()
    # The id's next holder would be its owner: TaskService.list_for('ana') still lists it.
    assert row["owner"] != "ana", "archived, Ana's task still sits under her id"


def test_retention_lets_old_tasks_go(database):
    task_id = a_task(database)
    with db.transaction(database) as conn:
        conn.execute("update tasks set created_at = now() - interval '5 years', "
                     "updated_at = now() - interval '5 years' where id = %s", (task_id,))
        retention.sweep(conn, datetime.now(UTC), "sample")
        left = conn.execute("select 1 from tasks where id = %s", (task_id,)).fetchone()
    assert left is None, "a task finished five years ago is kept, with its text, forever"


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
