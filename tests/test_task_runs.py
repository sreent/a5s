"""Tasks as a5s runs them (core/tasking.py, docs/phase-4.md): someone asks the assistant for
work that takes more than one run, it starts once they say yes in a later message, and the
scheduler works on it a slice at a time, each slice one of the assistant's runs, held to what's
left of the task's budget. Its owner hears from it once it's done or needs them, and from a5s
itself when it stops without a word."""

from __future__ import annotations

from datetime import timedelta

from a5s import db
from a5s.core.tasks import TaskService, TaskSpec

ASKED = "Go through my open questions and say what each one waits on"
PLAN = [{"content": "Read Ana's open questions", "status": "completed"},
        {"content": "Say what each waits on", "status": "in_progress"}]
DONE = [{"content": "Read Ana's open questions", "status": "completed"},
        {"content": "Say what each waits on", "status": "completed"}]


def tasks_of(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from tasks order by number").fetchall()


def told(stack, person: str = "ana") -> list[str]:
    with db.transaction(stack.admin) as conn:
        return [r["text"] for r in conn.execute(
            "select text from outbox where person = %s and inbound_id is null order by id",
            (person,))]


def a_task(stack, budget: int = 400_000, days: int = 3) -> dict:
    """Ana's task with the assistant, said yes to."""
    tasks = TaskService(stack.admin)
    tasks.clock = stack.gateway.clock
    task_id = tasks.create(TaskSpec(instance="assistant-finance", owner="ana", task=ASKED,
                                    token_budget=budget,
                                    deadline=stack.gateway.clock() + timedelta(days=days)))
    return tasks.get(task_id)


def test_a_task_starts_only_once_its_owner_says_yes_in_a_later_message(stack):
    stack.model.reply(None, ("offer_task", {"task": ASKED}), ("confirm_task", {}))
    stack.model.reply("I can take that on as a task: shall I start it?")
    stack.say("Could you go through all my open questions and say what each waits on?")
    [offered] = tasks_of(stack)  # it may not start it in the message that asked for it
    assert (offered["status"], offered["owner"], offered["audience"]) == ("offered", "ana",
                                                                         ["ana"])
    assert offered["task"] == ASKED and offered["token_budget"] == 400_000
    assert stack.scheduler().work_due() == 0  # nothing runs while it waits for a yes
    stack.model.reply(None, ("confirm_task", {"task": f"T-{offered['number']}"}))
    stack.model.reply("I've started it, and I'll tell you when it's done.")
    stack.say("Yes, please do")
    [started] = tasks_of(stack)
    assert started["status"] == "queued"
    assert [e["action"] for e in stack.ledger() if e["kind"] == "task"] == ["offer", "start"]


def test_a_task_runs_slice_by_slice_and_writes_to_its_owner_once_its_done(stack):
    task = a_task(stack)
    stack.model.reply(None, ("search_records", {"query": "invoice"}),
                      ("checkpoint_task", {"step": 1, "progress": 0.5, "plan": PLAN,
                                           "partial": ["Q-1001 waits on the right address"]}))
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on in a later run.")  # still at work: it writes to nobody
    assert stack.scheduler().work_due() == 1
    [first] = tasks_of(stack)
    assert (first["status"], first["step"], first["partial"]) == (
        "waiting", 1, ["Q-1001 waits on the right address"])
    assert first["tokens"] == 3 * stack.model.tokens  # its run's own count, its three calls
    assert told(stack) == []
    stack.model.reply(None, ("finish_task", {"status": "done", "plan": DONE,
                                             "result": {"Q-1001": "the right address"}}))
    stack.model.reply("Ana, your task is done: Q-1001 waits on the right address.")
    assert stack.scheduler().work_due() == 1
    [done] = tasks_of(stack)
    assert (done["status"], done["result"], done["attempts"]) == (
        "done", {"Q-1001": "the right address"}, 2)
    assert done["tokens"] == 5 * stack.model.tokens
    [heard] = told(stack)  # from the assistant, once, and Q-1001 is what its earlier run read
    assert heard.startswith("Ana, your task is done") and "itself" not in heard
    brief = str(stack.model.requests[3]["body"]["messages"])
    assert ASKED in brief and "Q-1001 waits on the right address" in brief  # picked up
    assert stack.scheduler().work_due() == 0
    assert task["id"] == str(done["id"])


def test_a_tasks_run_is_held_to_what_the_task_has_left(stack):
    task = a_task(stack, budget=40)
    for _ in range(3):  # 15 tokens a call: the fourth call would pass the task's 40
        stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Done.")  # never asked for
    stack.scheduler().work_due()
    [after] = tasks_of(stack)
    assert after["tokens"] == 3 * stack.model.tokens and after["status"] == "waiting"
    denied = [e for e in stack.ledger() if e["kind"] == "model" and e["decision"] == "deny"]
    assert denied and "budgets" in denied[-1]["reasons"]
    stack.at((stack.gateway.clock() + timedelta(minutes=5)).isoformat())
    stack.scheduler().work_due()  # its next slice can't begin: it has spent its budget
    [stopped] = tasks_of(stack)
    assert (stopped["status"], stopped["last_error"]) == ("failed", "its token budget is spent")
    [heard] = told(stack)  # from a5s itself, in its own words
    assert heard == (f"T-{task['number']}, the task you asked the assistant for, has stopped: "
                     "its token budget is spent.")


def test_its_owner_hears_from_a5s_when_its_deadline_passes(stack):
    task = a_task(stack, days=1)
    stack.at((stack.gateway.clock() + timedelta(days=2)).isoformat())
    assert stack.scheduler().work_due() == 1  # its slice is due, and can't begin
    [stopped] = tasks_of(stack)
    assert (stopped["status"], stopped["last_error"]) == ("failed", "its deadline passed")
    assert told(stack) == [f"T-{task['number']}, the task you asked the assistant for, has "
                           "stopped: its deadline passed."]


def test_its_owner_sees_and_stops_their_task_through_the_assistant(stack):
    task = a_task(stack)
    name = f"T-{task['number']}"
    stack.model.reply(None, ("list_tasks", {}))
    stack.model.reply(None, ("cancel_task", {"task": name}))
    stack.model.reply(f"I've stopped {name}.")
    stack.say("What tasks do I have? Stop the one about my questions.")
    [cancelled] = tasks_of(stack)
    assert cancelled["status"] == "cancelled"
    listed = str(stack.model.requests[1]["body"]["messages"][-1]["content"])
    assert name in listed and ASKED in listed
    assert stack.scheduler().work_due() == 0


def test_someone_else_cant_see_or_stop_anyones_task(stack):
    task = a_task(stack)
    stack.model.reply(None, ("cancel_task", {"task": f"T-{task['number']}"}))
    stack.model.reply("I can't find that task.")
    stack.say("Cancel T-1", person="ben")
    assert tasks_of(stack)[0]["status"] == "queued"
    assert "isn't one of their tasks" in str(stack.model.requests[-1]["body"]["messages"][-1])
