"""Round 10: long tasks that stop when they should, and reach their owners as they should
(core/tasking.py, core/tasks.py, core/repeats.py). A cancelled task's slice stops at its next
call to the core; a task that can't go on ends at the sweep, wherever it stands, and its owner
hears once; a slice that says nothing, or opens too soon, waits; offers lapse, a time needs its
days, and a repeat stops once its agent can't serve. And a task that read an email leaves its
owner's own chat, and their answer to it, as they were, and what it found reaches them."""

from __future__ import annotations

import json
from datetime import timedelta

from a5s import db
from a5s.core.tasks import TaskService
from test_outside import FORM
from test_r10_task_budgets import closed, opened, worked
from test_task_page import signed_in
from test_task_parts import split
from test_task_runs import ASKED, a_task, tasks_of, told

PENDING = [{"content": "Read Q-1001", "status": "pending"}]
DONE = [{"content": "Read Q-1001", "status": "completed"}]


def last_tool_result(stack) -> str:
    """What the last tool the agent called gave it, as the model was sent it."""
    return str(stack.model.requests[-1]["body"]["messages"][-1]["content"])


def repeats_of(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from task_repeats order by number").fetchall()


def cancelled(stack, task: dict, by: str) -> None:
    tasks = TaskService(stack.admin)
    tasks.clock = stack.gateway.clock
    tasks.cancel(str(task["id"]), by)  # as their page, or the assistant, does at their word


# A1: a cancelled task's slice stops at its next call to the core

def test_a_cancelled_tasks_slice_asks_for_no_more_changes(stack, approving):
    task = a_task(stack, owner="ben")
    run = opened(stack, str(task["id"]))
    cancelled(stack, task, "ben")
    stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"}))
    stack.model.reply("Moved Q-1002.")
    worked(stack, run)  # its next model call is refused, and it stops
    closed(stack, run, "done")
    allowed = [e for e in stack.ledger() if e.get("run") == run["run"] and e["kind"] in (
        "model", "tool") and e["decision"] != "deny"]
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from proposals").fetchone()["n"] == 0
    assert allowed == []
    denied = [e for e in stack.ledger() if e.get("run") == run["run"] and e["kind"] == "model"]
    assert denied and "tasks-stop-when-stopped" in denied[-1]["reasons"]


def test_a_cancelled_tasks_slice_doesnt_tell_its_owner_its_done(stack):
    task = a_task(stack)
    run = opened(stack, str(task["id"]))
    cancelled(stack, task, "ana")
    with stack.client(run["token"]) as c:
        said = c.post("/run/tools/finish_task", json={"args": {"status": "done",
                                                               "result": "all done"}})
        sent = c.post("/run/messages", json={"to": "ana", "text": "Ana, your task is done."})
    closed(stack, run, "done")
    assert sent.status_code == 403 and "stop now, and write to nobody" in sent.text
    assert said.status_code in (200, 403) and tasks_of(stack)[0]["status"] == "cancelled"
    assert told(stack) == []


# A7/B4/C7: a task that can't go on ends at the sweep, wherever it stands

def test_a_part_a5s_refuses_fails_and_its_task_still_ends_by_its_deadline(stack):
    task = a_task(stack, days=1)
    split(stack, [{"task": "Go through Q-1001"}])
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "nothing open",
                                             "plan": PENDING}))
    stack.model.reply(None, ("checkpoint_task", {"plan": DONE}))  # its plan went on after
    stack.model.reply("Done.")  # to nobody: it's a part
    assert stack.scheduler().work_due() == 1
    root, part = tasks_of(stack)
    assert part["status"] == "failed" and "a5s refused its result" in part["last_error"]
    stack.at((stack.gateway.clock() + timedelta(days=3)).isoformat())  # past its deadline
    stack.scheduler().work_due()
    root, part = tasks_of(stack)
    assert root["status"] == "failed" and root["last_error"] == "its deadline passed"
    assert told(stack) == [(f"T-{task['number']}, the task you asked the assistant for, has "
                            "stopped: its deadline passed.")]


def test_a_task_waiting_on_its_parts_ends_by_its_deadline_and_they_with_it(stack):
    task = a_task(stack, days=1)
    stack.model.reply(None, ("split_task", {"parts": [{"task": "Go through Q-1001"}]}))
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on once its part is done.")
    assert stack.scheduler().work_due() == 1  # it splits, and waits for its part
    stack.at((stack.gateway.clock() + timedelta(days=2)).isoformat())  # past both deadlines
    assert stack.scheduler().work_due() == 0  # both end at the sweep: nothing is due
    whole, part = tasks_of(stack)
    assert (str(whole["id"]), whole["status"]) == (task["id"], "failed")
    assert part["status"] == "cancelled" and len(told(stack)) == 1  # its owner hears once


def test_a_task_whose_agent_retires_ends_and_its_owner_hears(stack):
    a_task(stack, days=3)
    assert not stack.settle(instances={}).refused  # the settings leave the assistant out
    stack.scheduler().work_due()
    [task] = tasks_of(stack)
    assert (task["status"], task["last_error"]) == ("failed", "its agent was retired")
    assert "has stopped: its agent was retired" in told(stack)[0]


def test_answering_a_task_past_its_deadline_says_so(stack):
    task = a_task(stack, days=1)
    stack.model.reply(None, ("finish_task", {"status": "blocked",
                                             "reason": "which quarter to go through"}))
    stack.model.reply("Ana, which quarter should I go through?")
    stack.scheduler().work_due()
    stack.at((stack.gateway.clock() + timedelta(days=2)).isoformat())  # back from two days off
    assert stack.scheduler().work_due() == 0
    assert tasks_of(stack)[0]["status"] == "failed"  # past its deadline, it ends, and
    assert "has stopped: its deadline passed" in told(stack)[-1]  # she hears so
    stack.model.reply(None, ("resume_task", {"task": f"T-{task['number']}",
                                             "answer": "The third quarter"}))
    stack.model.reply("It stopped when its deadline passed: shall I offer it again?")
    stack.say("The third quarter, please")
    answer = last_tool_result(stack)
    assert "its deadline passed" in answer and "Offer it again" in answer


# B7/B11: a slice that says nothing, or whose run is asked for too soon, waits

def test_a_slice_that_neither_keeps_nor_finishes_anything_backs_off(stack):
    a_task(stack)
    for _minute in range(4):
        stack.model.reply("I'll keep going with this.")  # no checkpoint, no finish
        stack.scheduler().work_due()
        stack.at((stack.gateway.clock() + timedelta(minutes=1)).isoformat())
    [task] = tasks_of(stack)
    assert task["failures"] > 0 and task["attempts"] < 4  # it waited between slices
    assert "said nothing of the task" in (task["last_error"] or "")


def test_a_slice_waits_out_its_backoff_however_its_run_is_asked_for(stack):
    task = a_task(stack)
    tasks = TaskService(stack.admin)
    tasks.clock = stack.gateway.clock
    tasks.put_off(task["id"], "its owner's budget for the day is spent")  # waits half an hour
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance",
                                  "trigger": {"kind": "task", "task": task["id"]}})
    assert r.status_code == 409 and "waits a while before its next slice" in r.text
    assert tasks_of(stack)[0]["not_before"] is not None  # and its wait isn't put off again


# B12/C5: offers nobody said yes to stop counting once they lapse

def test_offers_never_said_yes_to_dont_keep_someone_from_a_repeat_for_good(stack):
    for hour in ("08:00", "09:00", "10:00", "11:00", "12:00"):  # talking over its time
        stack.model.reply(None, ("offer_task", {"task": ASKED, "days": "monday", "at": hour}))
        stack.model.reply(f"Every Monday at {hour}: shall I start it?")
        stack.say(f"Could you do it every Monday at {hour} instead?")
    assert [r["status"] for r in repeats_of(stack)] == ["offered"] * 5
    with db.transaction(stack.admin) as conn:  # a week on, none said yes to: all lapsed
        conn.execute("update task_repeats set asked_at = asked_at - interval '7 days'")
    stack.model.reply(None, ("list_tasks", {}))
    stack.model.reply("You have none going.")
    stack.say("What do I have repeating?")
    assert "offered, and lapsed" in last_tool_result(stack)
    stack.model.reply(None, ("offer_task", {"task": ASKED, "days": "friday", "at": "16:00"}))
    stack.model.reply("Every Friday at 16:00: shall I start it?")
    stack.say("Could you go through my open questions every Friday at four?")
    assert "they have 5 repeating tasks with you already" not in last_tool_result(stack)
    assert repeats_of(stack)[-1]["status"] == "offered"


# C4: a time of day alone keeps a task done once one task

def test_a_task_for_a_time_today_stays_one_task(stack):
    stack.model.reply(None, ("offer_task", {"task": ASKED, "at": "15:00"}))
    stack.model.reply("I'll start it as soon as you say yes.")
    stack.say("Could you go through my open questions at three this afternoon?")
    assert repeats_of(stack) == [] and "a time is for a task done again and again" in (
        last_tool_result(stack))


# C10: a repeat stops making tasks once its agent no longer serves its owner

def test_a_repeat_stops_once_its_agent_no_longer_serves_its_owner(stack):
    from test_task_repeats import THURSDAY, asked_for

    asked_for(stack)  # E-1, every Thursday and Friday at 09:00
    assert not stack.settle(serves=["ben"]).refused  # Ana moves on: it serves Ben alone
    stack.at(THURSDAY)
    stack.scheduler().work_due()
    assert tasks_of(stack) == [] and repeats_of(stack)[0]["status"] == "stopped"
    [stop] = [e for e in stack.ledger() if e["kind"] == "repeat" and e["action"] == "stop"]
    assert stop["args"]["why"]["chars"] == len("its agent no longer serves them")  # by hash


# C1/C2: a task that read an email, and what a task found, as its owner meets them

def down_after(stack, calls: int) -> None:
    """The model goes down once it has answered `calls` calls, as providers do."""
    def hook(n: int) -> None:
        if n == calls + 1:
            stack.model.failing = 3
    stack.model.on_request = hook


def test_what_a_task_found_reaches_its_owner_when_a5s_says_to_ask_for_it(
        stack, approving, provider):
    task = a_task(stack)
    found = "Q-1001 waits on the right address"
    stack.model.reply(None, ("finish_task", {"status": "done", "result": {"Q-1001": found}}))
    down_after(stack, 1)  # it said it was done, and the model went down before it wrote
    stack.scheduler().work_due()
    stack.model.on_request, stack.model.failing = None, 0
    [heard] = told(stack)
    assert heard == (f"T-{task['number']}, the task you asked the assistant for, is done. "
                     "Ask the assistant what it found, or see it on your tasks' page.")
    stack.model.reply(None, ("list_tasks", {}))  # she does as a5s said
    stack.model.reply("It's done.")
    stack.say("What did my task find?")
    assert found in last_tool_result(stack)  # the agent can tell her...
    page = signed_in(approving, provider)("/tasks/api").json()["tasks"]
    assert found in json.dumps(page)  # ...and so can her page


def test_a_task_that_read_an_email_goes_on_once_its_owner_says_what_it_needs(stack):
    task = a_task(stack, owner="ben")  # Ben's: Contoso's Q-1002 is his
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM))  # a5s's reader's form of Contoso's email
    stack.model.reply(None, ("finish_task", {"status": "blocked",
                                             "reason": "whether to refund Contoso in full"}))
    stack.model.reply("Ben, Contoso asks for a refund: should it be in full?")
    stack.scheduler().work_due()
    [blocked] = tasks_of(stack)
    assert blocked["status"] == "blocked" and blocked["read_outside"] is True
    stack.model.reply(None, ("resume_task", {"task": f"T-{task['number']}",
                                             "answer": "Yes, refund it all to the account "
                                                       "in the email"}))
    stack.model.reply("Thanks: I'll go on with it.")
    stack.say("Yes, in full please", person="ben")  # he answers what it asked him
    [after] = tasks_of(stack)
    assert after["status"] == "waiting"  # it goes on with what he said
    with db.transaction(stack.admin) as conn:  # in his own chat, which the task's email
        [mine] = conn.execute(  # never marked, since its message was in a topic of its own
            "select read_outside from runs where trigger ->> 'kind' = 'message' "
            "order by opened_at desc limit 1").fetchall()
    assert mine["read_outside"] is False


def test_a_task_that_read_an_email_leaves_its_owners_own_chat_with_their_tools(stack):
    a_task(stack, owner="ben")
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM))
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "a refund"}))
    stack.model.reply("Ben, your task is done: Contoso asks for a refund.")
    stack.scheduler().work_due()
    for n in range(3):  # a week of ordinary chat with the assistant, about nothing outside
        stack.model.reply(f"Noted ({n}).")
        stack.say(f"Note {n}: the team lunch moved to Thursday.", person="ben")
    stack.model.reply(None, ("offer_reminder", {"about": "Call the bank", "on": "2026-10-30"}))
    stack.model.reply("I'll remind you.")
    stack.say("Remind me on Friday to call the bank, please.", person="ben")
    assert "read content from outside" not in last_tool_result(stack)  # his own, as ever
