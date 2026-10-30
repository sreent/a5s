"""Summaries: once a topic's turns no longer fit in its runs, a run of a5s's own folds them
into the topic's summary. Code keeps every key, amount and date they had, keeps no summary
that has one nobody said, and gives it to the topic's later runs. People see their summaries,
and have them corrected."""

import json

import httpx

from a5s import db
from a5s.core import topics
from a5s.services import context

OLD = "Contoso's refund for Q-1002 is £1,240.50, due by 2026-11-06."


def summaries(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from summaries order by topic").fetchall()


def a_long_conversation(stack) -> None:
    """Ana's earlier turns, more than a run with a small budget is given."""
    with db.transaction(stack.admin) as conn:
        context.add_turn(conn, person="ana", agent="assistant", role="person", content=OLD)
        context.add_turn(conn, person="ana", agent="assistant", role="agent", content="Noted.")
        for n in range(5):
            context.add_turn(conn, person="ana", agent="assistant", role="person",
                             content=f"Note {n}: " + "the weekly sync went through invoices. " * 25)
    stack.gateway.definitions["assistant"].context.budget_tokens = 1000  # 4,000 characters


def folded(decisions: list[str]) -> str:
    return json.dumps({"decisions": decisions, "commitments": [], "open_questions": []})


def answering(stack) -> list[dict]:
    """What the agent's own runs were sent, not a5s's summary runs."""
    return [r["body"]["messages"] for r in stack.model.requests
            if r["body"]["messages"][0]["content"] != topics.SUMMARY]


def test_turns_that_no_longer_fit_are_folded_into_the_topics_summary(stack):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))
    assert stack.say("Hello") == "Hello, Ana."
    asked = stack.model.requests[-1]["body"]["messages"]
    assert asked[0] == {"role": "system", "content": topics.SUMMARY}
    assert "The turns to fold into it, oldest first:" in asked[1]["content"] and OLD in asked[1]["content"]
    assert "tools" not in stack.model.requests[-1]["body"]  # a5s's own run has none

    [summary] = summaries(stack)
    assert (summary["topic"], summary["body"]["decisions"]) == (
        "general", ["Contoso's refund for Q-1002 is £1,240.50."])
    assert [(f["value"], f["who"]) for f in summary["body"]["facts"]] == [
        ("Q-1002", "Ana Ortiz"), ("£1,240.50", "Ana Ortiz"), ("2026-11-06", "Ana Ortiz")]

    stack.model.reply("It's due on 2026-11-06.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))  # another turn drops
    stack.say("When is the refund due?")
    given = answering(stack)[-1][1]["content"]
    assert given.startswith("[from a5s, not the person] A summary of this topic")
    assert "Decided: Contoso's refund for Q-1002 is £1,240.50." in given
    assert "Keys, amounts and dates, exactly as said: Q-1002 (Ana Ortiz, " in given
    opened = [e["args"]["trigger"] for e in stack.ledger() if e["action"] == "open"]
    assert opened == ["message", "summary", "message", "summary"]
    assert summaries(stack)[0]["through"] > summary["through"]


def test_code_keeps_every_key_amount_and_date_the_model_leaves_out(stack):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply(folded([]))  # it says nothing at all
    stack.say("Hello")
    [summary] = summaries(stack)
    assert [f["norm"] for f in summary["body"]["facts"]] == ["Q-1002", "GBP 1240.50", "2026-11-06"]


def test_a_summary_that_says_a_value_nobody_said_isnt_kept(stack):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,999.00."]))
    stack.say("Hello")
    assert summaries(stack) == []
    closed = [e for e in stack.ledger() if e["action"] == "close"]
    assert closed[-1]["outcome"] == "summary refused: it says £1,999.00, which nobody said"


def test_a_reply_that_isnt_a_summary_isnt_kept(stack):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply("Here's a summary: they talked about refunds.")
    stack.say("Hello")
    assert summaries(stack) == []


def test_nothing_is_folded_while_the_conversation_fits(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    assert len(stack.model.requests) == 1 and summaries(stack) == []


def test_a_summary_run_calls_no_tools_and_writes_to_nobody(stack):
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "summary", "person": "ana", "topic": "general"}}).json()
    with stack.client(opened["token"]) as c:
        info = c.get("/run").json()
        tool = c.post("/run/tools/get_record", json={"args": {"key": "Q-1001"}})
        message = c.post("/run/messages", json={"to": "ana", "text": "Hello"})
    assert (info["plain"], info["tools"], info["context"], info["instructions"]) == (
        True, [], [], topics.SUMMARY)
    assert tool.status_code == message.status_code == 403
    assert "call no tools" in tool.json()["explanations"][0]
    assert "write to nobody" in message.json()["explanations"][0]


def test_people_see_their_summaries_and_have_them_corrected(stack):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))
    stack.say("Hello")
    seen = httpx.get(f"{stack.channels_url}/channels/local/summaries",
                     params={"person": "ana", "agent": "assistant"}).json()["summaries"]
    assert [s["topic"] for s in seen] == ["general"]
    assert seen[0]["text"].startswith("Decided: Contoso's refund for Q-1002 is £1,240.50.")
    assert httpx.get(f"{stack.channels_url}/channels/local/summaries",
                     params={"person": "ben", "agent": "assistant"}).json()["summaries"] == []

    stack.gateway.definitions["assistant"].context.budget_tokens = 30000  # it all fits again
    stack.model.reply(None, ("correct_summary", {"correction": "The refund goes to Fabrikam."}))
    stack.model.reply("Corrected.")
    stack.say("The summary's wrong: the refund goes to Fabrikam, not Contoso.")
    [summary] = summaries(stack)
    assert summary["body"]["corrections"][0]["said"] == "The refund goes to Fabrikam."
    stack.model.reply("Fabrikam.")
    stack.say("Who gets the refund?")
    assert "Corrections, in their words: The refund goes to Fabrikam." in answering(stack)[-1][1]["content"]
