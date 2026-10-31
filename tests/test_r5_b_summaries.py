"""Round 5, reviewer b: summaries when the model's summary doesn't hold up.

Once a topic's turns no longer fit in its runs, a run of a5s's own folds them into the
topic's summary, and code keeps every key, amount and date they had. But if the model's
part names one value nobody said, the whole summary is refused, code's facts with it: the
turns are out of every run's context, and nothing keeps what they said. Each later run in
the topic asks again, with every turn not yet folded, so the ask grows with the topic.
"""

from a5s import db
from a5s.core import topics

FILLER = "We went through the supplier's history line by line. " * 150  # about 8,000 characters
SAID = "The refund for Q-1002 is £1,240.50, and finance pays it on 2026-11-20."
INVENTED = ('{"decisions": ["Finance pays £999.99 on 2026-12-24."], "commitments": [], '
            '"open_questions": []}')


def a_long_conversation(stack, turns: int = 30) -> None:
    """Ana's conversation with the assistant, long past what one run is given."""
    with db.transaction(stack.admin) as conn:
        for i in range(turns):
            content = (SAID + " " if i == 0 else "") + FILLER
            conn.execute("insert into turns (person, agent, topic, role, content, at) values "
                         "('ana', 'assistant', 'general', %s, %s, now() - interval '1 day')",
                         ("person" if i % 2 == 0 else "agent", content))


def summary_asks(stack) -> list[int]:
    """How long each ask of a summary run was, in characters."""
    return [len(r["body"]["messages"][-1]["content"]) for r in stack.model.requests
            if r["body"]["messages"][0]["content"] == topics.SUMMARY]


def test_a_refused_summary_keeps_codes_facts_and_isnt_asked_again_on_every_run(stack):
    a_long_conversation(stack)
    for answer in ("Hello, Ana.", "Hello again.", "Still here."):
        stack.model.reply(answer)
        stack.model.reply(INVENTED)  # the summary run names an amount and a date nobody said
    for asked in ("Hello", "Hello again", "Are you there?"):
        stack.say(asked)
    asks = summary_asks(stack)
    with db.transaction(stack.admin) as conn:
        kept = conn.execute("select body from summaries").fetchall()
    given = [m["content"] for m in stack.model.requests[-2]["body"]["messages"]]  # the last answer
    assert any("£1,240.50" in text for text in given), (
        f"no summary was kept ({len(kept)}), and the turn with £1,240.50 is out of every run's "
        f"context, so the agent can't see it; a5s asked for a summary {len(asks)} times, "
        f"{asks} characters each")
    assert len(asks) <= 1, f"a5s asked again on every run: {asks} characters each"
