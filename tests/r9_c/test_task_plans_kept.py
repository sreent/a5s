"""Round 9, reviewer C: tasks and their plans (core/tasks.py, docs/phase-4.md) against
docs/data-protection.md, "the inventory, from the code".

A task keeps what its owner asked for, its plan's steps and its partial results, in their
words, by its owner's and audience's ids. The ledger keeps them by hash, as phase 4 says, but
the tasks table keeps the words, and no row of the inventory names it: retention never deletes
a task, an export doesn't give it, and an erasure leaves it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from a5s import db
from a5s.core import erasure, export, retention
from a5s.core.tasks import TaskService, TaskSpec

ASKED = "Find every record Ana's sick leave in October held up, and draft her manager a note"


def test_a_task_goes_with_its_owners_data(database):
    with db.transaction(database) as conn:
        conn.execute("insert into instances (id, definition, release, model) "
                     "values ('assistant-finance', 'assistant', 'test', 'fake') "
                     "on conflict do nothing")
    tasks = TaskService(database)
    task = tasks.create(TaskSpec(instance="assistant-finance", owner="ana", task=ASKED,
                                 token_budget=1000,
                                 deadline=datetime.now(UTC) + timedelta(hours=1)))
    tasks.run_next(task, lambda t, checkpoint: {"status": "done", "plan": [
        {"content": "List the records Ana's leave held up", "status": "completed"}]})
    now = datetime.now(UTC)
    with db.transaction(database) as conn:
        retention.sweep(conn, now + timedelta(days=800), "sample")  # over two years on
        exported = export.gather(conn, "ana")
        erasure.erase(conn, "ana", now, here=True)
        left = conn.execute("select task, plan from tasks where id = %s", (task,)).fetchone()
    print(sorted(exported))
    assert ASKED not in str(exported)  # her export doesn't give it
    # FAILS: retention and Ana's erasure both leave the task, in her words, with its plan.
    assert left is None, left


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
