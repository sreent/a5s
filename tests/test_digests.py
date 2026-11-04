"""Digests: each person gets one message a day from all the agents together, at a time they
choose. The agents' work for it is done when its time comes, so nothing in it is stale,
and what comes up after it waits for the next. Answers, escalations, and reminders for a
particular time go at once."""

from a5s import db

MONDAY = "2026-11-02T09:30:00+00:00"  # half the time for Ana's and Ben's questions has passed


def sent(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select person, due_at, items, channel from digests "
                            "order by due_at, person").fetchall()


def test_each_person_gets_one_message_from_all_their_agents(stack, monkeypatch):
    stack.with_watcher()
    records = stack.gateway.scenario._records
    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer"})
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")  # the assistant's, for Ana and Ben
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.model.reply("Ana, you have Q-1001, waiting on the customer.")  # the watcher's, first time
    stack.model.reply("Ben, you have Q-1002, waiting on finance.")
    assert stack.scheduler().work_due() == 4
    [ana] = stack.inbox("ana")
    assert (ana["from"], ana["text"]) == ("a5s", (
        "Your day from a5s, Mon 2 Nov.\n\n"
        "From the assistant:\nAna, Q-1001 is due on Wednesday.\n\n"
        "From the watcher:\nAna, you have Q-1001, waiting on the customer."))
    [ben] = stack.inbox("ben")
    assert ben["text"].startswith("Your day from a5s") and "From the watcher:" in ben["text"]
    assert [(d["person"], d["items"]) for d in sent(stack)] == [("ana", 2), ("ben", 2)]
    digested = [e for e in stack.ledger() if e["action"] == "digest"]
    assert [(e["acts_for"], e["args"]["items"]) for e in digested] == [(["ana"], 2), (["ben"], 2)]


def test_one_item_is_its_agents_own_message(stack):
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    [ana] = stack.inbox("ana")
    assert (ana["from"], ana["text"]) == ("assistant", "Ana, Q-1001 is due on Wednesday.")


def test_the_work_for_a_digest_waits_for_its_time_and_then_for_the_next(stack, monkeypatch):
    stack.at("2026-11-02T08:59:00+00:00")  # half the time has passed, but it isn't nine yet
    assert stack.scheduler().work_due() == 0 and stack.inbox("ana") == []
    stack.at("2026-11-02T09:00:00+00:00")
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    assert len(stack.inbox("ana")) == 1

    records = stack.gateway.scenario._records  # a question for Ana, half its time gone already
    monkeypatch.setitem(records, "Q-1006", {
        "key": "Q-1006", "title": "Missing purchase order", "status": "open", "customer": "Contoso",
        "owner": "ana", "opened": "2026-10-20", "due": "2026-11-04"})
    stack.at("2026-11-02T11:00:00+00:00")  # her digest has gone today
    assert stack.scheduler().work_due() == 0
    stack.at("2026-11-03T09:05:00+00:00")  # so it's in tomorrow's, fresh
    stack.model.reply("Ana, Q-1006 is due tomorrow.")
    assert stack.scheduler().work_due() == 1
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, Q-1006 is due tomorrow."]


def test_a_day_with_nothing_to_tell_sends_nothing(stack):
    stack.at("2026-10-29T09:30:00+00:00")  # nothing has fallen due yet
    assert stack.scheduler().work_due() == 0
    assert stack.inbox("ana") == [] and [(d["person"], d["items"]) for d in sent(stack)] == [
        ("ana", 0), ("ben", 0)]


def test_people_choose_their_digests_time(stack):
    stack.model.reply(None, ("set_digest_time", {"time": "10:30"}))
    stack.model.reply("Done: your digest comes at 10:30.")
    stack.say("Please send my digest at half past ten")
    stack.model.reply(None, ("set_digest_time", {"time": "19:00"}))
    stack.model.reply("That's after your working day.")
    stack.say("Or at seven in the evening", person="ben")
    assert "outside their working hours" in stack.model.requests[-1]["body"]["messages"][-1]["content"]

    stack.at(MONDAY)
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 1  # Ben's, at nine
    assert stack.inbox("ana") == []
    stack.at("2026-11-02T10:30:00+00:00")
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    assert stack.scheduler().work_due() == 1
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, Q-1001 is due on Wednesday."]


def test_a_reminder_for_a_particular_time_goes_at_once(stack):
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()  # their digests have gone today
    stack.inbox("ana")
    stack.model.reply(None, ("offer_reminder", {"about": "call Northwind", "on": "2026-11-02T14:00"}))
    stack.model.reply("Shall I remind you at two?")
    stack.say("Remind me to call Northwind at 2pm")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Done.")
    stack.say("Yes")
    stack.at("2026-11-02T14:00:00+00:00")
    stack.model.reply("Ana, it's time to call Northwind.")
    assert stack.scheduler().work_due() == 1
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, it's time to call Northwind."]


def test_answers_and_escalations_never_wait_for_a_digest(stack):
    stack.model.reply("Hello, Ana.")
    assert stack.say("Hello") == "Hello, Ana."  # at once
    stack.suspend(by="ben")
    stack.at("2026-11-09T09:00:00+00:00")  # Ben's Q-1002 is overdue, so Ana hears at once
    stack.scheduler().work_due()
    assert any(m["text"].startswith("Q-1002") for m in stack.inbox("ana"))
