"""Topics and case briefs. A message that names a record goes in its case, and one that names
none stays in the conversation's current topic. A run in a case is given a brief of it, built
by code from the records, and the case's older turns beside the conversation's latest."""

from a5s import db
from a5s.services import context

MONDAY = "2026-11-02T09:30:00+00:00"  # half the time for Ana's and Ben's questions has passed
RECORD = ("Q-1001, Invoice sent to the wrong address: status open, due date 2026-11-04, customer "
          "Northwind. Ana Ortiz owns it. https://sample.a5s.dev/records/Q-1001")


def system_prompt(stack, request: int = -1) -> str:
    return stack.model.requests[request]["body"]["messages"][0]["content"]


def said(stack, request: int = -1) -> list[str]:
    return [m["content"] for m in stack.model.requests[request]["body"]["messages"][1:]]


def topics_of(stack, person: str = "ana") -> list[tuple[str, str]]:
    with db.transaction(stack.admin) as conn:
        return [(r["role"], r["topic"]) for r in conn.execute(
            "select role, topic from turns where person = %s order by id", (person,))]


def test_a_message_that_names_a_record_goes_in_its_case_with_a_brief(stack):
    stack.scheduler().due()  # the core works out what the records owe
    stack.model.reply("Q-1001 is open, and due on Wednesday.")
    stack.say("What's happening with Q-1001?")
    told = system_prompt(stack)
    assert f"## The case: Q-1001, from the records\n\n{RECORD}\n" in told
    assert "Ana Ortiz owes it, by the end of their working day on Wed 4 Nov." in told
    assert topics_of(stack) == [("person", "Q-1001"), ("agent", "Q-1001")]
    opened = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"]
    assert opened[-1]["args"]["trigger"] == "message"


def test_a_follow_up_stays_in_the_conversations_topic_until_it_goes_quiet(stack):
    stack.model.reply("Q-1001 is open.")
    stack.say("What's Q-1001?")
    stack.model.reply("Northwind.")
    stack.say("And who's the customer?")
    assert "## The case: Q-1001" in system_prompt(stack)
    with db.transaction(stack.admin) as conn:  # five hours pass without a word
        conn.execute("update turns set at = at - interval '5 hours'")
    stack.model.reply("Hello again.")
    stack.say("Hello again")
    assert "## The case:" not in system_prompt(stack)
    assert [t for _, t in topics_of(stack)] == ["Q-1001"] * 4 + ["general"] * 2


def test_a_message_that_names_several_records_stays_where_it_was(stack):
    stack.model.reply("Both are open.")
    stack.say("Compare Q-1001 and Q-1002")
    assert "## The case:" not in system_prompt(stack)
    assert {t for _, t in topics_of(stack)} == {"general"}


def test_a_chase_goes_in_its_records_case_with_what_a5s_keeps_for_its_person(stack):
    stack.model.reply(None, ("offer_reminder", {"about": "chase Northwind", "on": "2026-11-03",
                                                "record": "Q-1001"}))
    stack.model.reply("Shall I?")
    stack.say("Remind me tomorrow to chase Northwind about Q-1001")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Set.")
    stack.say("Yes")
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    ana = next(r for r in stack.model.requests[-2:] if "Ana Ortiz owes it" in
               r["body"]["messages"][0]["content"])
    told = ana["body"]["messages"][0]["content"]
    assert ("Ana Ortiz owes it, by the end of their working day on Wed 4 Nov. a5s reminded "
            "them on Mon 2 Nov.") in told
    assert "Their reminder about it: on Tue 3 Nov at 09:00, chase Northwind." in told
    assert topics_of(stack)[-2:] == [("task", "Q-1001"), ("agent", "Q-1001")]


def test_a_brief_says_nothing_of_what_a5s_keeps_for_anyone_else(stack):
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()  # Ana has been chased about Q-1001
    stack.model.reply("It's Ana's.")
    stack.say("Whose is Q-1001?", person="ben")
    told = system_prompt(stack)
    assert RECORD in told
    assert "owes it" not in told and "reminded" not in told


def test_a_run_in_a_case_gets_its_older_turns_beside_the_latest(stack):
    with db.transaction(stack.admin) as conn:
        context.add_turn(conn, person="ana", agent="assistant", role="person",
                         content="For Q-1001, Northwind wants the invoice sent to Leeds.",
                         topic="Q-1001")
        for n in range(5):
            context.add_turn(conn, person="ana", agent="assistant", role="person",
                             content=f"Chat {n}: " + "x" * 1000)
    stack.gateway.definitions["assistant"].context.budget_tokens = 1000  # 4,000 characters
    stack.model.reply("To Leeds.")
    stack.say("Where should the Q-1001 invoice go?")
    told = said(stack)
    assert told[0].endswith("For Q-1001, Northwind wants the invoice sent to Leeds.")
    assert sum("Chat " in t for t in told) == 2  # only the latest that fit two thirds
    assert told[-1].endswith("Where should the Q-1001 invoice go?")


def test_a_run_goes_on_when_the_records_cant_be_read(stack, monkeypatch):
    def down():
        raise ConnectionError("the records system is down")

    monkeypatch.setattr(stack.gateway.scenario, "watched", down)
    stack.model.reply("I can't see the records right now.")
    assert stack.say("What about Q-1001?") == "I can't see the records right now."
    assert "The records can't be read right now, so a5s has nothing on Q-1001." in system_prompt(stack)
