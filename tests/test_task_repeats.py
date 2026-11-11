"""Tasks people ask an agent to do again and again, such as every Monday at 09:00
(core/repeats.py): offered, and said yes to in a later message, as a task is. At each of its
times, in its owner's time zone, the core makes a task of it, once the last one it made has
ended, and its owner stops it at their word, through the agent or on their own page."""

from a5s import db
from a5s.core import erasure, export
from test_task_page import signed_in
from test_task_runs import ASKED, tasks_of, told

THURSDAY = "2026-10-29T09:05:00+00:00"  # 09:05 in London, where Ana is, in the quiet week
FRIDAY = "2026-10-30T09:05:00+00:00"  # the sample's tests keep: nothing else falls due
DAYS = ["thursday", "friday"]


def repeats_of(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from task_repeats order by number").fetchall()


def asked_for(stack, days: object = None, at: str = "09:00") -> None:
    """Ana asks the assistant for her task again and again, and says yes."""
    stack.model.reply(None, ("offer_task", {"task": ASKED, "days": days or DAYS, "at": at}))
    stack.model.reply("I can do that again and again: shall I start?")
    stack.say("Could you go through my open questions every Monday morning?")
    stack.model.reply(None, ("confirm_task", {}))
    stack.model.reply("Started.")
    stack.say("Yes please")


def test_a_repeat_starts_once_its_owner_says_yes_and_makes_a_task_at_each_time(stack):
    stack.model.reply(None, ("offer_task", {"task": ASKED, "days": DAYS, "at": "09:00"}))
    stack.model.reply("I can do that every Thursday and Friday at 09:00: shall I start?")
    stack.say("Could you go through my open questions every Monday morning?")
    [offered] = repeats_of(stack)
    assert (offered["status"], offered["days"], offered["at"]) == ("offered", ["thu", "fri"],
                                                                   ["09:00"])
    assert stack.scheduler().work_due() == 0 and tasks_of(stack) == []
    stack.model.reply(None, ("confirm_task", {}))
    stack.model.reply("Started: every Thursday and Friday at 09:00.")
    stack.say("Yes please")
    assert repeats_of(stack)[0]["status"] == "active"
    assert stack.scheduler().work_due() == 0  # nothing until its next time
    stack.at(THURSDAY)
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "nothing open"}))
    stack.model.reply("Ana, this week's look at your open questions is done: nothing waits.")
    assert stack.scheduler().work_due() == 1  # its task, made, and worked on
    [task] = tasks_of(stack)
    assert (task["task"], task["status"], task["repeat"]) == (ASKED, "done", offered["id"])
    brief = str(stack.model.requests[-2]["body"]["messages"])
    assert ("It's one of the times they asked for it, every Thursday and Friday at 09:00 "
            "(E-1)") in brief
    assert told(stack) == ["Ana, this week's look at your open questions is done: nothing waits."]
    assert stack.scheduler().work_due() == 0  # once for each time it comes round
    stack.at(FRIDAY)
    stack.model.reply(None, ("finish_task", {"status": "done", "result": "nothing open"}))
    stack.model.reply("Ana, done again.")
    assert stack.scheduler().work_due() == 1
    assert [t["status"] for t in tasks_of(stack)] == ["done", "done"]


def test_a_time_that_comes_round_while_its_last_task_is_at_work_is_let_go(stack):
    asked_for(stack, days="every day")
    stack.at("2026-10-29T09:05:00+00:00")
    stack.model.reply(None, ("finish_task", {"status": "waiting"}))
    stack.model.reply("Going on with it later.")
    stack.scheduler().work_due()
    with db.transaction(stack.admin) as conn:  # it waits a while before its next slice
        conn.execute("update tasks set not_before = '2026-10-31T00:00:00+00:00'")
    stack.at("2026-10-30T09:05:00+00:00")
    stack.scheduler().work_due()
    assert len(tasks_of(stack)) == 1  # no second task while the first is at work
    skipped = [e for e in stack.ledger() if e["kind"] == "repeat" and e["action"] == "skip"]
    assert len(skipped) == 1


def test_its_owner_lists_and_stops_it_through_the_assistant(stack):
    asked_for(stack)
    stack.model.reply(None, ("list_tasks", {}))
    stack.model.reply(None, ("cancel_task", {"task": "E-1"}))
    stack.model.reply("I've stopped it.")
    stack.say("What do I have repeating? Stop it.")
    listed = str(stack.model.requests[-2]["body"]["messages"][-1]["content"])
    assert "E-1" in listed and "every Thursday and Friday at 09:00" in listed
    assert repeats_of(stack)[0]["status"] == "stopped"
    stack.at(THURSDAY)
    assert stack.scheduler().work_due() == 0 and tasks_of(stack) == []


def test_someone_has_at_most_five_with_an_agent(stack):
    for n in range(5):
        stack.model.reply(None, ("offer_task", {"task": f"Look at queue {n}", "days": "monday",
                                                "at": "09:00"}))
        stack.model.reply("Shall I?")
        stack.say(f"Every Monday, look at queue {n}")
    stack.model.reply(None, ("offer_task", {"task": "One more", "days": "friday", "at": "16:00"}))
    stack.model.reply("You have five already.")
    stack.say("And every Friday?")
    assert len(repeats_of(stack)) == 5
    assert "they have 5 repeating tasks with you already" in str(
        stack.model.requests[-1]["body"]["messages"][-1])


def test_when_it_comes_round_must_be_a_time_and_days(stack):
    stack.model.reply(None, ("offer_task", {"task": ASKED, "days": "someday", "at": "9am"}))
    stack.model.reply("When should it come round?")
    stack.say("Every so often, please")
    assert repeats_of(stack) == []
    assert "say when it comes round" in str(stack.model.requests[-1]["body"]["messages"][-1])


def test_their_page_shows_their_repeats_and_stops_one(stack, approving, provider):
    asked_for(stack)
    api = signed_in(approving, provider)
    [shown] = api("/tasks/api").json()["repeats"]
    assert (shown["repeat"], shown["when"], shown["status"], shown["agent"]) == (
        "E-1", "every Thursday and Friday at 09:00", "active", "assistant")
    assert api("/tasks/api/E-1/cancel", "ben", "POST").status_code == 404  # not his
    assert api("/tasks/api/E-1/cancel", method="POST").json() == {"stopped": "E-1"}
    assert repeats_of(stack)[0]["status"] == "stopped"
    assert api("/tasks/api/E-1/cancel", method="POST").status_code == 409  # stopped already


def test_an_export_holds_them_and_an_erasure_takes_them(stack):
    asked_for(stack)
    with db.transaction(stack.admin) as conn:
        [found] = export.gather(conn, "ana")["repeats"]
        assert (found["task"], found["status"]) == (ASKED, "active")
        assert export.gather(conn, "ben")["repeats"] == []
        gone, _ = erasure.erase(conn, "ana", stack.gateway.clock())
    assert gone["repeats"] == 1 and repeats_of(stack) == []


def test_someone_stops_a_repeat_on_their_page_in_the_browser(stack, approving, provider,
                                                            browser):
    asked_for(stack)
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}/tasks/")
    page.wait_for_selector("#repeats >> text=every Thursday and Friday at 09:00", timeout=30000)
    assert "E-1, with the assistant" in page.inner_text("#repeats")
    page.click("#repeats button:has-text('Stop')")
    page.wait_for_selector("#status >> text=Stopped E-1", timeout=30000)
    assert "stopped" in page.inner_text("#repeats") and page.locator("#repeats button").count() == 0
    assert repeats_of(stack)[0]["status"] == "stopped"
