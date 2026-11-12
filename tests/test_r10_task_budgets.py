"""Round 10: what a task may spend, and change (core/tasking.py's split, core/counts.py,
core/budgets.py). A slice that splits its task is held to the share it kept; a task's slices
and parts are one piece of work for the scenario's limits and for a change asked again; and a
person's tasks leave a fifth of their day for what they ask themselves."""

from __future__ import annotations

from datetime import UTC, datetime

from a5s import db
from a5s.core import budgets
from a5s.worker import BudgetSpent, TaskStopped, run_agent
from test_levels import due_of, levelled
from test_proposals import held
from test_task_runs import a_task, tasks_of

BUDGET = 70_000
CALL = 10_000  # what each model call takes, as the provider counts it


def opened(stack, task_id: str) -> dict:
    """A slice of the task, opened as the scheduler opens it: its run, token and brief."""
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance",
                                  "trigger": {"kind": "task", "task": task_id}})
    assert r.status_code == 200, r.text
    return r.json()


def worked(stack, run: dict) -> None:
    """The run's agent, on its brief, until it stops or the core stops its model calls."""
    try:
        run_agent(stack.url, run["token"], [{"role": "task", "content": run["task"],
                                             "at": datetime.now(UTC).isoformat()}])
    except (BudgetSpent, TaskStopped):  # as the core stops its model calls
        pass


def closed(stack, run: dict, outcome: str = "budget spent") -> None:
    with stack.client() as c:
        assert c.post(f"/runs/{run['run']}/close", json={"outcome": outcome}).status_code == 200


def cap_of(stack, run: dict) -> int:
    """What the run's model calls are held to now."""
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select trigger, task_cap from runs where id = %s",
                           (run["run"],)).fetchone()
    return min(row["trigger"]["cap"], row["task_cap"] if row["task_cap"] is not None
               else row["trigger"]["cap"])


def tool(stack, run: dict, name: str, **args) -> dict:
    with stack.client(run["token"]) as c:
        r = c.post(f"/run/tools/{name}", json={"args": args})
    assert r.status_code == 200, r.text
    return r.json()["result"]


# A3: a slice that splits its task is held to what it kept for itself

def test_a_slice_that_splits_is_held_to_the_share_it_kept(stack):
    task = a_task(stack, budget=BUDGET)
    stack.model.tokens = CALL
    root = opened(stack, str(task["id"]))
    assert cap_of(stack, root) == BUDGET
    stack.model.reply(None, ("split_task", {"parts": [{"task": "Go through Q-1001"},
                                                      {"task": "Go through Q-1004"}]}))
    for n in range(5):  # and it goes on, rather than say it's waiting, as a model may
        stack.model.reply(None, ("checkpoint_task", {"progress": (n + 1) / 10}))
    worked(stack, root)
    _, *parts = tasks_of(stack)
    share = (BUDGET - CALL) // 3  # what was left as it split, for two parts and itself
    assert [p["token_budget"] for p in parts] == [share, share]
    assert cap_of(stack, root) == CALL + share  # what it spent, and the share it kept
    runs = [opened(stack, str(p["id"])) for p in parts]  # at work beside it
    for r in runs:
        for n in range(3):
            stack.model.reply(None, ("checkpoint_task", {"progress": (n + 5) / 10}))
        worked(stack, r)
        closed(stack, r)
    closed(stack, root)
    spent = {str(t["id"]): t["tokens"] for t in tasks_of(stack)}
    assert spent[str(task["id"])] == CALL + share  # it stopped at its share
    assert sum(spent.values()) <= BUDGET  # the tree, root and parts, within the root's


# A5/B2: a task's slices and parts are one piece of work for the scenario's limits

def test_a_task_cant_spread_a_change_past_its_limit_over_its_slices(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_run": 1}})  # one a piece of work
    task = a_task(stack, owner="ben")  # Ben's task changes Q-1002, which Ana decides
    first = opened(stack, str(task["id"]))
    assert "held" not in tool(stack, first, "change_due_date", key="Q-1002", due="2026-11-13")
    tool(stack, first, "finish_task", status="waiting")
    closed(stack, first, "done")
    second = opened(stack, str(task["id"]))
    again = tool(stack, second, "change_due_date", key="Q-1002", due="2026-11-20")
    closed(stack, second, "done")
    assert "held" in again and due_of(stack) == "2026-11-13"  # it waits for Ana
    [waiting] = held(stack)  # and its decider is told why
    assert any("this task, in its runs and its parts', asked for 1 already" in f
               for f in waiting["flags"])


def test_a_tasks_slices_share_the_limit_a_piece_of_work_has(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_run": 1}})
    a_task(stack, owner="ben")
    stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"}),
                      ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on in a later run.")
    assert stack.scheduler().work_due() == 1
    stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
                      ("finish_task", {"status": "done", "result": "moved"}))
    stack.model.reply("Ben, your task is done.")
    assert stack.scheduler().work_due() == 1
    assert [t["status"] for t in tasks_of(stack)] == ["done"]
    assert due_of(stack) == "2026-11-13"  # its second change waits for billing's owner


def test_a_change_a_part_asks_for_again_is_the_change_its_task_made(stack, approving):
    levelled(stack)  # changes to due dates in billing are made at level 2
    a_task(stack, owner="ben")
    move = ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"})
    stack.model.reply(None, move)
    stack.model.reply(None, ("split_task", {"parts": [{"task": "Check Q-1002's due date"}]}))
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on once its part is done.")
    assert stack.scheduler().work_due() == 1
    stack.model.reply(None, move)  # the part, doing what it's told the task is for
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "it's moved"}))
    stack.model.reply("Done.")
    assert stack.scheduler().work_due() == 1
    with db.transaction(stack.admin) as conn:
        made = conn.execute("select count(*) as n from sample.changes where key = 'Q-1002'"
                            ).fetchone()["n"]
    assert made == 1  # made once, by the task, and the part told so


# C6: a person's tasks leave a fifth of their day for what they ask themselves

def spend(stack, tokens: int, person: str = "ana") -> None:
    day = budgets.day_of(stack.gateway.scenario, person, stack.gateway.clock())
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into spend (instance_id, person, day, tokens) values (%s, %s, %s, %s) "
                     "on conflict (instance_id, person, day) do update set tokens = excluded.tokens",
                     ("assistant-finance", person, day, tokens))


def test_someone_whose_tasks_spent_their_share_of_the_day_can_still_talk_to_their_agent(stack):
    day = stack.gateway.definitions["assistant"].budget.per_person_per_day
    a_task(stack)
    spend(stack, day * 3 // 5)  # what her tasks may spend of her day
    assert stack.scheduler().work_due() == 1  # its slice can't begin, and waits
    [put_off] = tasks_of(stack)
    assert put_off["status"] == "queued" and put_off["attempts"] == 0
    assert "for tasks: the rest is kept for what they ask themselves" in put_off["last_error"]
    stack.model.reply("Hello, Ana.")
    assert stack.say("Hello") == "Hello, Ana."  # her own chat goes on
    spend(stack, day * 4 // 5)  # and once that's spent too, only chases and reminders go on
    stack.model.reply("Hello again, Ana.")
    assert stack.say("Hello") != "Hello again, Ana."


def test_a_tasks_questions_to_other_agents_are_paid_as_its_task_is(stack):
    budget = stack.gateway.definitions["assistant"].budget
    spend(stack, budget.per_person_per_day * 3 // 5)
    now = stack.gateway.clock()
    with db.transaction(stack.admin) as conn:
        def refused(trigger: dict) -> str | None:
            return budgets.refused(conn, stack.gateway.scenario, budget, "assistant-finance",
                                   ["ana"], "question", 0, now, trigger)
        assert refused({"payer": "ana"}) is None  # a question her own message asked
        assert "for tasks" in (refused({"payer": "ana", "for_task": True}) or "")
