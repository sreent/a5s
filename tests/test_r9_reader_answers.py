"""Round 9 of the critique: a5s's reader's answer in its own words counts as the outside
document's only for the values the document holds, as its form's do: a value it made up is
the agent's own, and the person is told so (core/gateway.py; docs/critique.md, round 9)."""

import json

from a5s import db

FORM = {"asks_for": "a refund", "amount": "£860.00", "date": "2026-11-06", "question": "Q-1002"}


def read(stack, *texts: str) -> dict[str, str]:
    with db.transaction(stack.admin) as conn:
        return {r["text"]: r["source"] for r in conn.execute(
            "select text, source from run_reads where text = any(%s)", (list(texts),))}


def test_a_value_the_reader_made_up_is_the_agents_own(stack):
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM))  # the reader's form, checked against the email
    stack.model.reply(None, ("ask_about", {"document": "D-1", "question": "How much is owed?"}))
    stack.model.reply("They ask for a refund of £7,777.00 by 2027-03-15.")  # neither is in it
    stack.model.reply("Contoso asks for a refund of £7,777.00 by 2027-03-15.")
    said = stack.say("What does Contoso want?", person="ben")
    email = next(m["body"] for m in stack.gateway.scenario._messages if m["record"] == "Q-1002")
    assert "7,777" not in email and "2027-03-15" not in email
    assert read(stack, "£7,777.00", "2027-03-15") == {} and "itself" in said, said


def test_a_value_the_document_holds_is_its_own(stack):
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM))
    stack.model.reply(None, ("ask_about", {"document": "D-1", "question": "When was it paid?"}))
    stack.model.reply("They paid £860.00 twice on 2026-10-20.")  # as the email says
    stack.model.reply("Contoso paid £860.00 twice.")
    stack.say("What does Contoso say?", person="ben")
    assert read(stack, "2026-10-20") == {"2026-10-20": "outside D-1"}
