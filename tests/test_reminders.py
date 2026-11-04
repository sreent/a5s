"""Reminders: what people ask the assistant to remind them of, and what it promises to follow
up. It offers one, and keeps it only once the person says yes, in a later message of their
own. Each is the person's alone, and a suspended agent never silences one."""

from a5s import db
from a5s.core import reminders
from a5s.definitions import REMINDER_TOOLS

FRIDAY = "2026-10-30T09:30:00+00:00"  # 09:30 in London: Ana's reminder is due, and nothing else
ABOUT = "check whether Northwind has answered about Q-1001"


def kept(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from reminders order by id").fetchall()


def last_tool_result(stack) -> str:
    """What the agent heard back from its last tool call."""
    return stack.model.requests[-1]["body"]["messages"][-1]["content"]


def asked_and_confirmed(stack) -> None:
    stack.model.reply(None, ("offer_reminder", {"about": ABOUT, "on": "2026-10-30", "record": "Q-1001"}))
    stack.model.reply("Shall I remind you on Friday at 09:00? Say yes, and I'll set it.")
    assert "Say yes" in stack.say("Remind me on Friday to check whether Northwind has answered.")
    [offered] = kept(stack)
    assert offered["confirmed_at"] is None  # not until she says so
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Done: I'll remind you on Friday at 09:00.")
    assert stack.say("Yes please") == "Done: I'll remind you on Friday at 09:00."


def test_a_reminder_is_kept_once_its_person_says_yes_and_given_on_the_day(stack):
    asked_and_confirmed(stack)
    [reminder] = kept(stack)
    assert reminder["confirmed_at"] is not None and reminder["person"] == "ana"
    assert reminder["due_at"].isoformat() == "2026-10-30T09:00:00+00:00"  # her working day's start
    assert '"set for": "Fri 30 Oct at 09:00"' in last_tool_result(stack)

    stack.at("2026-10-30T08:59:00+00:00")
    assert stack.scheduler().work_due() == 0
    stack.at(FRIDAY)
    stack.model.reply("Ana, you asked me to remind you: has Northwind answered about Q-1001?")
    assert stack.scheduler().work_due() == 1
    asked = last_tool_result(stack)
    assert f"agreed you'd remind them now: {ABOUT}." in asked and "check the record first" in asked
    assert [m["text"] for m in stack.inbox("ana")] == [
        "Ana, you asked me to remind you: has Northwind answered about Q-1001?"]
    opened = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"]
    assert (opened[-1]["acts_for"], opened[-1]["args"]["trigger"]) == (["ana"], "reminder")
    assert stack.scheduler().work_due() == 0  # once
    tools = [(e["action"], e["outcome"]["status"]) for e in stack.ledger()
             if e["kind"] == "tool" and e["decision"] == "record"]
    assert tools == [("offer_reminder", "ok"), ("confirm_reminder", "ok")]


def test_it_takes_a_later_message_of_theirs_to_confirm_one(stack):
    stack.model.reply(None, ("offer_reminder", {"about": ABOUT, "on": "2026-10-30"}),
                      ("confirm_reminder", {}))  # in the same breath: not her yes
    stack.model.reply("I've offered it. Say yes, and I'll set it.")
    stack.say("Remind me on Friday to check on Northwind.")
    [offered] = kept(stack)
    assert offered["confirmed_at"] is None
    denied = [e for e in stack.ledger() if e["action"] == "confirm_reminder" and e["decision"] == "record"]
    assert denied[0]["outcome"]["status"] == "refused"


def test_offering_the_same_reminder_again_waits_for_the_same_yes(stack):
    stack.model.reply(None, ("offer_reminder", {"about": ABOUT, "on": "2026-10-30"}))
    stack.model.reply("Shall I remind you on Friday?")
    stack.say("Remind me on Friday to check on Northwind.")
    stack.model.reply(None, ("offer_reminder", {"about": ABOUT, "on": "2026-10-30"}),
                      ("confirm_reminder", {}))  # as a model may, when she says yes
    stack.model.reply("Done.")
    stack.say("Yes")
    [reminder] = kept(stack)
    assert reminder["confirmed_at"] is not None


def test_offering_one_they_said_yes_to_makes_no_other(stack):
    asked_and_confirmed(stack)  # as when a model confirms it before offering it, in parallel
    stack.model.reply(None, ("offer_reminder", {"about": ABOUT, "on": "2026-10-30", "record": "Q-1001"}))
    stack.model.reply("It's set already.")
    stack.say("Remind me on Friday to check whether Northwind has answered.")
    assert "they've said yes to this already" in last_tool_result(stack)
    [reminder] = kept(stack)
    assert reminder["confirmed_at"] is not None


def test_only_a_run_answering_their_own_message_can_offer_one(stack):
    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's question has passed
    stack.scheduler().due()
    with db.transaction(stack.admin) as conn:
        number = conn.execute("select id from obligations where record = 'Q-1001'").fetchone()["id"]
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance",
                                       "trigger": {"kind": "obligation", "obligation": number}})
    with stack.client(opened.json()["token"]) as c:
        offered = c.post("/run/tools/offer_reminder", json={"args": {"about": "x", "on": "2026-11-20"}})
    assert offered.status_code == 403
    assert "only in answer to a message of theirs" in offered.json()["explanations"][0]


def test_a_run_that_read_outside_content_cant_set_one(stack):
    run, token = stack.open_run()
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set read_outside = true where id = %s", (run,))
    with stack.client(token) as c:
        offered = c.post("/run/tools/offer_reminder", json={"args": {"about": "x", "on": "2026-11-20"}})
    assert offered.status_code == 403 and "content from outside" in offered.json()["explanations"][0]
    assert kept(stack) == []


def test_a_suspended_assistant_never_silences_a_reminder(stack):
    asked_and_confirmed(stack)
    stack.suspend(by="ben")
    asked = len(stack.model.requests)
    stack.at(FRIDAY)
    assert stack.scheduler().work_due() == 0
    assert len(stack.model.requests) == asked  # the core reminds her itself, in code
    [told] = stack.inbox("ana")
    assert told["from"] == "a5s" and f"you asked the assistant to remind you now: {ABOUT}." in told["text"]
    assert "The assistant is suspended, so a5s is reminding you itself." in told["text"]
    assert kept(stack)[0]["reminded_at"] is not None


def test_people_list_and_cancel_their_reminders(stack):
    asked_and_confirmed(stack)
    stack.model.reply(None, ("list_reminders", {}))
    stack.model.reply("You have one, on Friday.")
    stack.say("What reminders do I have?")
    assert '"when": "Fri 30 Oct at 09:00"' in last_tool_result(stack)
    stack.model.reply(None, ("cancel_reminder", {"reminder": f"R-{kept(stack)[0]['id']}"}))
    stack.model.reply("Cancelled.")
    stack.say("Cancel it, thanks")
    stack.at(FRIDAY)
    assert stack.scheduler().work_due() == 0 and stack.inbox("ana") == []
    stack.model.reply(None, ("cancel_reminder", {"reminder": "R-999"}))
    stack.model.reply("I couldn't find that one.")
    stack.say("And cancel R-999", person="ben")
    assert "isn't one of their upcoming reminders" in last_tool_result(stack)


def test_waiting_on_something_pauses_reminders_until_then(stack):
    stack.scheduler().due()  # the obligations, which the scheduler brings in line every minute
    stack.model.reply(None, ("note_waiting", {"record": "Q-1002", "waiting_on": "finance",
                                              "until": "2026-11-05"}))
    stack.model.reply("Noted: I won't remind you about Q-1002 until Thursday.")
    stack.say("I'm waiting on finance for Q-1002 until the 5th", person="ben")
    stack.at("2026-11-02T09:30:00+00:00")  # half Ben's time has passed, but he's waiting
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    assert stack.scheduler().work_due() == 1  # Ana's reminder alone
    stack.at("2026-11-05T09:30:00+00:00")  # his wait is over
    stack.model.reply("Ben, Q-1002 is due tomorrow.")
    assert stack.scheduler().work_due() == 1
    assert stack.inbox("ben")[-1]["text"] == "Ben, Q-1002 is due tomorrow."

    stack.suspend(by="ben")
    stack.at("2026-11-09T09:00:00+00:00")  # overdue, so Ana hears, and hears why
    stack.scheduler().work_due()
    [escalated] = [m["text"] for m in stack.inbox("ana") if m["text"].startswith("Q-1002")]
    assert "they said they were waiting on finance until Thu 5 Nov." in escalated


def test_someone_can_only_note_waiting_on_their_own_open_records(stack):
    stack.model.reply(None, ("note_waiting", {"record": "Q-1003", "waiting_on": "the warehouse",
                                              "until": "2026-11-05"}))
    stack.model.reply("That isn't one of yours.")
    stack.say("Chen's Q-1003 is waiting on the warehouse until the 5th")
    assert "Q-1003 isn't one of their open records" in last_tool_result(stack)


def test_a_reminder_names_a_time_ahead_and_a_record_that_exists(stack):
    stack.model.reply(None, ("offer_reminder", {"about": "x", "on": "2026-10-01"}),
                      ("offer_reminder", {"about": "x", "on": "next friday"}),
                      ("offer_reminder", {"about": "x", "on": "2026-11-20", "record": "Q-9999"}))
    stack.model.reply("I couldn't set any of those.")
    stack.say("Remind me")
    results = [m["content"] for m in stack.model.requests[-1]["body"]["messages"] if m["role"] == "tool"]
    assert "has passed" in results[0] and "isn't a date" in results[1] and "no record Q-9999" in results[2]
    assert kept(stack) == []


def test_a5s_offers_its_reminder_tools_only_to_agents_that_keep_reminders(stack):
    assert set(reminders.TOOLS) == set(REMINDER_TOOLS)
    stack.model.reply("Hello.")
    stack.say("Hello")
    assert set(REMINDER_TOOLS) <= stack.model.tool_names(-1)
    stack.with_watcher()
    with db.transaction(stack.admin) as conn:
        grants = conn.execute("select grants from instances where id = 'watcher-finance'").fetchone()
    assert not set(REMINDER_TOOLS) & set(grants["grants"])
