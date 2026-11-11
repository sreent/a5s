"""Round 9, reviewer A: this round counts the values in a5s's reader's free-text answer as the
outside document's own (gateway.asking_about), without checking the document holds them, as
the reader's form is checked. A value the reader made up then reaches people as the document's,
with no note that the agent wrote it itself."""

import json

from a5s import db

FORM = {"asks_for": "a refund", "amount": "£860.00", "date": "2026-11-06", "question": "Q-1002"}


def test_a_value_the_reader_made_up_passes_as_the_documents(stack):
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM))  # the reader's form, checked against the email
    stack.model.reply(None, ("ask_about", {"document": "D-1", "question": "How much is owed?"}))
    stack.model.reply("They ask for a refund of £7,777.00 by 2027-03-15.")  # neither is in it
    stack.model.reply("Contoso asks for a refund of £7,777.00 by 2027-03-15.")
    said = stack.say("What does Contoso want?", person="ben")
    email = next(m["body"] for m in stack.gateway.scenario._messages if m["record"] == "Q-1002")
    assert "7,777" not in email and "2027-03-15" not in email
    with db.transaction(stack.admin) as conn:
        sources = {r["text"]: r["source"] for r in conn.execute(
            "select text, source from run_reads where text in ('£7,777.00', '2027-03-15')")}
    # FAILS NOW: both count as read from the email, D-1, and the person isn't told the agent
    # wrote them itself
    assert not sources and "itself" in said, (sources, said)


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
