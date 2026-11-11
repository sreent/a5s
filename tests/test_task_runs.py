"""Tasks as a5s runs them (core/tasking.py, docs/phase-4.md): someone asks the assistant for
work that takes more than one run, it starts once they say yes in a later message, and the
scheduler works on it a slice at a time, each slice one of the assistant's runs, held to what's
left of the task's budget. Its owner hears from it once it's done or needs them, and from a5s
itself when it stops without a word. Each of its runs is given what its earlier runs read,
with where each value came from, and their mark if any read content from outside; and when
it needs its owner, it goes on with what they say."""

from __future__ import annotations

import json
from datetime import timedelta

from a5s import db
from a5s.core import budgets
from a5s.core.tasks import TaskService, TaskSpec
from a5s.worker import run_agent
from test_outside import FORM, marked

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


def spend_their_day(stack, person: str = "ana") -> None:
    """Their budget with the assistant for the day it is now, spent."""
    day = budgets.day_of(stack.gateway.scenario, person, stack.gateway.clock())
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into spend (instance_id, person, day, tokens) values (%s, %s, %s, %s) "
                     "on conflict (instance_id, person, day) do update set tokens = excluded.tokens",
                     ("assistant-finance", person, day, 1_000_000))


def a_task(stack, budget: int = 400_000, days: int = 3, owner: str = "ana") -> dict:
    """Someone's task with the assistant, Ana's unless it says, said yes to."""
    tasks = TaskService(stack.admin)
    tasks.clock = stack.gateway.clock
    task_id = tasks.create(TaskSpec(instance="assistant-finance", owner=owner, task=ASKED,
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
    assert told(stack) == [(f"T-{task['number']}, the task you asked the assistant for, has "
                            "stopped: its deadline passed.")]


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


def test_a_task_whose_run_cant_open_waits_rather_than_being_asked_for_at_every_sweep(stack):
    a_task(stack)
    spend_their_day(stack)  # nothing ran, so it's no failed slice: it waits half an hour
    assert stack.scheduler().work_due() == 1
    [put_off] = tasks_of(stack)
    assert (put_off["status"], put_off["failures"], put_off["attempts"]) == ("queued", 0, 0)
    assert "used its budget for ana today" in put_off["last_error"]
    assert stack.scheduler().work_due() == 0  # not asked for again at once
    stack.at((stack.gateway.clock() + timedelta(minutes=31)).isoformat())
    assert stack.scheduler().work_due() == 1
    opened = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"]
    assert [e["decision"] for e in opened] == ["deny", "deny"] and told(stack) == []


def test_a_task_put_off_past_its_deadline_fails_and_its_owner_hears_once(stack):
    task = a_task(stack, days=1)
    stack.at((stack.gateway.clock() + timedelta(days=2)).isoformat())
    spend_their_day(stack)  # so its run can't open, and its slice never begins
    assert stack.scheduler().work_due() == 1
    [stopped] = tasks_of(stack)
    assert (stopped["status"], stopped["last_error"]) == ("failed", "its deadline passed")
    assert told(stack) == [(f"T-{task['number']}, the task you asked the assistant for, has "
                            "stopped: its deadline passed.")]
    assert stack.scheduler().work_due() == 0 and len(told(stack)) == 1


def test_a_tasks_owner_hears_once_when_its_run_stops_after_writing_to_them(stack):
    a_task(stack)
    stack.model.reply(None, ("finish_task", {"status": "done", "result": {"Q-1001": "an address"}}))
    stack.model.reply("Ana, your task is done: Q-1001 waits on the right address.")
    stopping = stack.scheduler()
    stopping._close = lambda run, outcome: None  # it stops once it has written, before closing
    assert stopping.work_due() == 1
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set expires_at = now() - interval '1 second'")
    stack.scheduler().sweep()  # its run is closed as abandoned, with what it said
    [done] = tasks_of(stack)
    assert (done["status"], done["result"]) == ("done", {"Q-1001": "an address"})
    [heard] = told(stack)  # the assistant's own message, and no word of a5s's besides
    assert heard.startswith("Ana, your task is done")


def test_a_value_an_earlier_run_read_is_the_records_and_one_it_made_up_is_its_own(stack):
    a_task(stack)
    stack.model.reply(None, ("search_records", {"query": "invoice"}),
                      ("checkpoint_task", {"step": 1, "partial": [
                          "Q-1001 waits on the right address", "Q-7777 waits too"]}))
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on in a later run.")
    stack.scheduler().work_due()
    stack.model.reply(None, ("finish_task", {"status": "done"}))
    stack.model.reply("Ana, your task is done: Q-1001 and Q-7777 wait on the right address.")
    stack.scheduler().work_due()  # a later run, which read neither itself
    [heard] = told(stack)
    assert "(a5s: Q-7777 came from the assistant itself" in heard and "Q-1001 came" not in heard


def test_what_the_agent_wrote_of_a_task_never_counts_as_read(stack):
    stack.model.reply(None, ("offer_task", {"task": "Chase Q-7777 with Northwind"}))
    stack.model.reply("I can chase Q-7777 for you as a task: shall I start it?")
    said = stack.say("Could you chase Northwind for me?")
    assert "(a5s: Q-7777 came from the assistant itself" in said


def test_a_task_whose_run_read_a_customers_email_stays_marked_in_its_later_runs(stack):
    a_task(stack, owner="ben")
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM))  # a5s's reader's form of Contoso's email
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on in a later run.")
    stack.scheduler().work_due()
    stack.model.reply(None, ("finish_task", {"status": "done"}))
    stack.model.reply("Ben, your task is done: Contoso asks for a refund.")
    stack.scheduler().work_due()
    assert marked(stack) == [True, True]  # its later run read nothing from outside itself
    assert tasks_of(stack)[0]["read_outside"] is True


def test_a_task_that_needs_its_owner_goes_on_with_what_they_said(stack):
    task = a_task(stack)
    name = f"T-{task['number']}"
    stack.model.reply(None, ("finish_task", {"status": "blocked",
                                             "reason": "which quarter to go through"}))
    stack.model.reply("Ana, which quarter should I go through?")
    stack.scheduler().work_due()
    [blocked] = tasks_of(stack)
    assert (blocked["status"], blocked["last_error"]) == ("blocked", "which quarter to go through")
    assert told(stack) == ["Ana, which quarter should I go through?"]  # the agent's, alone
    assert stack.scheduler().work_due() == 0  # it waits for her
    stack.model.reply(None, ("resume_task", {"task": name, "answer": "The third quarter"}))
    stack.model.reply("Thanks: I'll go on with it.")
    stack.say("The third quarter, please")
    [resumed] = tasks_of(stack)
    assert (resumed["status"], resumed["answered"]) == (
        "waiting", {"needed": "which quarter to go through", "said": "The third quarter"})
    stack.model.reply(None, ("finish_task", {"status": "done", "result": {"quarter": 3}}))
    stack.model.reply("Ana, your task is done.")
    assert stack.scheduler().work_due() == 1
    brief = str(stack.model.requests[-2]["body"]["messages"])
    assert "It needed Ana Ortiz: which quarter to go through. They said: The third quarter" in brief
    assert tasks_of(stack)[0]["status"] == "done"


def test_an_offer_made_twice_is_one_and_lapses_unless_its_said_yes_to(stack):
    stack.model.reply(None, ("offer_task", {"task": ASKED}), ("offer_task", {"task": ASKED}))
    stack.model.reply("I can take that on as a task: shall I start it?")
    stack.say("Could you go through all my open questions and say what each waits on?")
    [offered] = tasks_of(stack)
    assert offered["status"] == "offered"
    with db.transaction(stack.admin) as conn:  # offered two days before her next message
        conn.execute("update tasks set asked_at = asked_at - interval '2 days'")
    stack.model.reply(None, ("list_tasks", {}))
    stack.model.reply("The one I offered lapsed: shall I offer it again?")
    stack.say("What tasks do I have?")
    listed = str(stack.model.requests[-1]["body"]["messages"][-1]["content"])
    assert "offered, and lapsed" in listed


def test_only_a_task_that_needs_its_owner_goes_on_with_what_they_say(stack):
    task = a_task(stack)
    stack.model.reply(None, ("resume_task", {"task": f"T-{task['number']}", "answer": "Go on"}))
    stack.model.reply("It's queued already.")
    stack.say("Go on with my task")
    assert tasks_of(stack)[0]["status"] == "queued"
    assert "only a task that needs them" in str(stack.model.requests[-1]["body"]["messages"][-1])


def test_a_task_survives_a_scheduler_that_stops_mid_slice_and_goes_on_from_its_checkpoint(
        stack):
    a_task(stack)
    stack.model.reply(None, ("checkpoint_task", {"step": 1, "progress": 0.5, "plan": PLAN,
                                                 "partial": ["Q-1001 waits on the right address"]}))
    stack.model.reply("Going on.")
    stopping = stack.scheduler(worker=lambda url, token, history: (run_agent(
        url, token, history), (_ for _ in ()).throw(SystemExit))[0])  # it stops part way
    stopping._close = lambda run, outcome: None  # and never closes its run
    try:
        stopping.work_due()
    except SystemExit:
        pass
    with db.transaction(stack.admin) as conn:  # its run outlives its time
        conn.execute("update runs set expires_at = now() - interval '1 second'")
    stack.scheduler().sweep()  # the core closes it, as abandoned, and the slice with it
    [stopped] = tasks_of(stack)
    assert (stopped["status"], stopped["failures"], stopped["step"]) == ("waiting", 1, 1)
    stack.at((stack.gateway.clock() + timedelta(minutes=1)).isoformat())  # past its backoff
    stack.model.reply(None, ("finish_task", {"status": "done", "plan": DONE,
                                             "result": {"Q-1001": "the right address"}}))
    stack.model.reply("Ana, your task is done: Q-1001 waits on the right address.")
    assert stack.scheduler().work_due() == 1  # a fresh run, from what the task kept
    brief = str(stack.model.requests[-2]["body"]["messages"])
    assert "Q-1001 waits on the right address" in brief and "(in progress)" in brief
    [done] = tasks_of(stack)
    assert (done["status"], done["attempts"], done["failures"]) == ("done", 2, 0)
    [heard] = told(stack)  # once, as the task's own message
    assert heard.startswith("Ana, your task is done: Q-1001 waits on the right address.")
