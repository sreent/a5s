"""A person's message, through the scheduler, a Deep Agents run and the gateway."""

from a5s import db
from a5s.services import context


def test_a_message_runs_through_deep_agents_and_the_gateway(stack):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open: the invoice went to the wrong address.")

    reply = stack.scheduler().handle_message(person="ana", agent="assistant",
                                             text="Is the invoice question still open?")

    assert reply == "Q-1001 is open: the invoice went to the wrong address."
    offered = stack.model.tool_names()
    assert {"search_records", "get_record", "create_draft"} <= offered
    assert "execute" not in offered  # workers have no shell

    run = next(e["run"] for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open")
    trail = [(e["kind"], e["action"], e["decision"]) for e in stack.ledger(run)]
    assert trail == [
        ("run", "open", "allow"),
        ("model", "fake", "allow"), ("model", "fake", "record"),
        ("tool", "search_records", "allow"), ("tool", "search_records", "record"),
        ("model", "fake", "allow"), ("model", "fake", "record"),
        ("message", "send", "allow"),
        ("run", "close", "record"),
    ]
    assert stack.verify().ok


def test_the_next_run_reads_the_conversation(stack):
    scheduler = stack.scheduler()
    stack.model.reply("Noted: the invoice question is Q-1001.")
    scheduler.handle_message(person="ana", agent="assistant", text="Remember Q-1001 for me.")
    stack.model.reply("You asked me to remember Q-1001.")
    scheduler.handle_message(person="ana", agent="assistant", text="What did I ask you?")

    second = stack.model.requests[-1]["body"]["messages"]
    said = " ".join(str(m.get("content")) for m in second)
    assert "Remember Q-1001 for me." in said and "Noted: the invoice question is Q-1001." in said
    with db.transaction(stack.cfg.database_url) as conn:
        turns = context.recent(conn, person="ana", agent="assistant")
    assert [t["role"] for t in turns] == ["person", "agent", "person", "agent"]


def test_conversations_stay_apart(stack):
    scheduler = stack.scheduler()
    stack.model.reply("Done.")
    scheduler.handle_message(person="ana", agent="assistant", text="Ana's private note")
    stack.model.reply("Hello Ben.")
    scheduler.handle_message(person="ben", agent="assistant", text="Hello")
    assert "Ana's private note" not in str(stack.model.requests[-1]["body"]["messages"])


def test_suspending_mid_run_stops_the_next_call(stack):
    def suspend_on_first_call(n: int) -> None:
        if n == 1:
            stack.suspend()

    stack.model.on_request = suspend_on_first_call
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    reply = stack.scheduler().handle_message(person="ana", agent="assistant", text="Find it")

    assert reply.startswith("I couldn't finish that.")
    assert len(stack.model.requests) == 1  # the model is never called again
    denied = [e for e in stack.ledger() if e["decision"] == "deny"]
    assert denied and denied[0]["kind"] == "tool"
    assert "only-active-instances-act" in denied[0]["reasons"]


def test_a_suspended_agent_answers_from_code_not_the_model(stack):
    stack.suspend()
    reply = stack.scheduler().handle_message(person="ana", agent="assistant", text="Hello?")
    assert reply == "The assistant is suspended at the moment, so it can't help. Ask Ana Ortiz."
    assert not stack.model.requests


def test_people_outside_the_directory_or_the_instance_get_no_agent(stack):
    scheduler = stack.scheduler()
    assert "doesn't know who you are" in scheduler.handle_message(
        person="mallory", agent="assistant", text="hi")
    assert scheduler.handle_message(person="chen", agent="assistant", text="hi") == (
        "There's no assistant for you yet.")
    assert not stack.model.requests
