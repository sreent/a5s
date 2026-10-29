"""A person's message, through the scheduler, a Deep Agents run and the gateway."""

from a5s import db
from a5s.services import context


def test_a_message_runs_through_deep_agents_and_the_gateway(stack):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open: the invoice went to the wrong address.")

    reply = stack.say("Is the invoice question still open?")

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
    stack.model.reply("Noted: the invoice question is Q-1001.")
    stack.say("Remember Q-1001 for me.")
    stack.model.reply("You asked me to remember Q-1001.")
    stack.say("What did I ask you?")

    second = stack.model.requests[-1]["body"]["messages"]
    said = " ".join(str(m.get("content")) for m in second)
    assert "Remember Q-1001 for me." in said and "Noted: the invoice question is Q-1001." in said
    with db.transaction(stack.admin) as conn:
        turns = context.recent(conn, person="ana", agent="assistant")
    assert [t["role"] for t in turns] == ["person", "agent", "person", "agent"]


def test_conversations_stay_apart(stack):
    stack.model.reply("Done.")
    stack.say("Ana's private note")
    stack.model.reply("Hello Ben.")
    stack.say("Hello", person="ben")
    assert "Ana's private note" not in str(stack.model.requests[-1]["body"]["messages"])


def test_suspending_mid_run_stops_the_next_call(stack):
    def suspend_on_first_call(n: int) -> None:
        if n == 1:
            stack.suspend()

    stack.model.on_request = suspend_on_first_call
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    reply = stack.say("Find it")

    assert reply.startswith("I couldn't finish that.")
    assert len(stack.model.requests) == 1  # the model is never called again
    denied = [(e["kind"], e["action"], e["reasons"]) for e in stack.ledger() if e["decision"] == "deny"]
    assert denied == [
        ("explain", "search_records", ["only-active-instances-act"]),  # so the tool never ran
        ("model", "fake", ["only-active-instances-act"]),
    ]


def test_a_suspended_agent_answers_from_code_not_the_model(stack):
    stack.suspend()
    reply = stack.say("Hello?")
    assert reply == "The assistant is suspended at the moment, so it can't help. Ask Ana Ortiz."
    assert not stack.model.requests


def test_people_outside_the_directory_or_the_instance_get_no_agent(stack):
    assert "doesn't know who you are" in stack.say("hi", person="mallory")
    assert stack.say("hi", person="chen") == "There's no assistant for you yet."
    assert not stack.model.requests


def tool_calls(stack, name: str) -> list[dict]:
    return [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == name]


def test_a_call_policy_would_deny_never_runs_and_the_agent_hears_why(stack):
    stack.settle(level=0)  # signed by Ana, an instance approver
    stack.model.reply(None, ("create_draft", {"title": "Re: Q-1001", "body": "Sorry about that."}))
    stack.model.reply("I can't save drafts at the moment.")

    reply = stack.say("Draft a reply")

    assert reply == "I can't save drafts at the moment."
    assert tool_calls(stack, "create_draft") == []  # the gateway never ran it
    explained = [e for e in stack.ledger() if e["kind"] == "explain"]
    assert [e["reasons"] for e in explained] == [["level-0-only-observes"]]
    told = str(stack.model.requests[1]["body"]["messages"])
    assert "at level 0 the agent only observes" in told


def test_subagents_ask_first_too(stack):
    stack.settle(level=0)  # signed by Ana, an instance approver
    stack.model.reply(None, ("task", {"description": "Save a draft reply about Q-1001.",
                                      "subagent_type": "general-purpose"}))
    stack.model.reply(None, ("create_draft", {"title": "Re: Q-1001", "body": "Sorry."}))
    stack.model.reply("I wasn't allowed to save the draft.")
    stack.model.reply("The draft couldn't be saved.")

    reply = stack.say("Draft it")

    assert reply == "The draft couldn't be saved."
    offered_to_subagent = stack.model.tool_names(1)
    assert "create_draft" in offered_to_subagent and "execute" not in offered_to_subagent
    assert tool_calls(stack, "create_draft") == []
    assert [e["action"] for e in stack.ledger() if e["kind"] == "explain"] == ["create_draft"]
