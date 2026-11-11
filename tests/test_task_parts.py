"""A task's run splits its work into parts (core/tasking.py): each part is a task of its own,
which a5s works on in runs of its own, sharing what the task has left. The task waits while
they're at work, and goes on once they've ended, told what each came to. A part writes to
nobody and can't wait on its owner: the task it's part of speaks for it."""

from a5s.core.tasks import TaskService
from test_task_runs import a_task, tasks_of, told

PARTS = [{"task": "Go through Q-1001"}, {"task": "Go through Q-1004"}]


def split(stack, parts: list[dict] = PARTS) -> None:
    stack.model.reply(None, ("split_task", {"parts": parts}))
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Split it into parts.")  # to nobody: it's still at work
    assert stack.scheduler().work_due() == 1


def test_a_task_splits_into_parts_and_goes_on_with_what_they_found(stack):
    a_task(stack)
    split(stack)
    root, first, second = tasks_of(stack)
    assert (root["status"], first["parent"], second["parent"]) == ("waiting", root["id"], root["id"])
    assert (first["task"], first["status"], first["audience"]) == ("Go through Q-1001", "queued",
                                                                   ["ana"])
    share = first["token_budget"]
    assert second["token_budget"] == share and 130_000 < share < 133_334  # one share kept
    assert first["deadline"] == root["deadline"]
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}),
                      ("finish_task", {"status": "done",
                                       "result": "Q-1001 waits on the right address"}))
    stack.model.reply("The first part is done.")  # a part's words, to nobody
    stack.model.reply(None, ("get_record", {"key": "Q-1004"}),
                      ("finish_task", {"status": "done",
                                       "result": "Q-1004 waits on a credit note"}))
    stack.model.reply("The second part is done.")
    assert stack.scheduler().work_due() == 2  # the parts, and not the task, while they work
    assert [t["status"] for t in tasks_of(stack)] == ["waiting", "done", "done"]
    assert told(stack) == []  # the parts wrote to nobody, and a5s said nothing of them
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "both found"}))
    stack.model.reply("Ana, your task is done: Q-1001 waits on the right address, and Q-1004 "
                      "on a credit note.")
    assert stack.scheduler().work_due() == 1  # the task, once its parts have ended
    brief = str(stack.model.requests[-2]["body"]["messages"])
    assert ("Its parts: T-2, to Go through Q-1001: done, and found Q-1001 waits on the right "
            "address; T-3, to Go through Q-1004: done") in brief
    [heard] = told(stack)  # once, from the task itself, with what its parts read
    assert heard.startswith("Ana, your task is done") and "itself" not in heard
    assert tasks_of(stack)[0]["status"] == "done"


def test_a_task_waits_while_its_parts_are_at_work(stack):
    a_task(stack)
    split(stack)
    root, *parts = tasks_of(stack)
    tasks = TaskService(stack.admin)
    assert set(tasks.due(stack.gateway.clock())) == {str(p["id"]) for p in parts}
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "nothing open"}))
    stack.model.reply("Done.")
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on.")
    stack.scheduler().work_due()
    assert str(root["id"]) not in tasks.due(stack.gateway.clock())  # one part is still at work


def test_a_part_writes_to_nobody_and_cant_wait_for_its_owner(stack):
    a_task(stack)
    split(stack, PARTS[:1])
    stack.model.reply(None, ("finish_task", {"status": "blocked", "reason": "which quarter"}))
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "nothing open"}))
    stack.model.reply("Ana, which quarter should I go through?")  # it may not ask her
    assert stack.scheduler().work_due() == 1
    refused = str(stack.model.requests[4]["body"]["messages"][-1]["content"])
    assert "a part of a task can't wait for its owner" in refused
    assert told(stack) == [] and tasks_of(stack)[1]["status"] == "done"
    held = [e for e in stack.ledger() if e["kind"] == "message" and e["decision"] == "deny"]
    assert held and "a-task-writes-once-it-ends" in held[-1]["reasons"]


def test_what_a_part_read_is_the_records_when_the_task_writes_it(stack):
    a_task(stack)
    split(stack, [{"task": "Look into the invoices"}])
    stack.model.reply(None, ("search_records", {"query": "invoice"}),
                      ("finish_task", {"status": "done", "result": "Q-1001 and Q-7777"}))
    stack.model.reply("The part is done.")
    stack.scheduler().work_due()
    stack.model.reply(None, ("finish_task", {"status": "done"}))
    stack.model.reply("Ana, your task is done: Q-1001 and Q-7777 are open.")
    stack.scheduler().work_due()
    [heard] = told(stack)  # Q-1001 is what its part read; Q-7777, nobody did
    assert "(a5s: Q-7777 came from the assistant itself" in heard and "Q-1001 came" not in heard


def test_a_task_splits_only_into_parts_its_budget_can_pay_for(stack):
    a_task(stack, budget=12_000)  # three ways, and one kept: under 5,000 each
    stack.model.reply(None, ("split_task", {"parts": [{"task": "a"}, {"task": "b"},
                                                      {"task": "c"}]}))
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on with it whole.")
    stack.scheduler().work_due()
    assert len(tasks_of(stack)) == 1
    assert "is too little to split 3 ways" in str(stack.model.requests[1]["body"]["messages"])
