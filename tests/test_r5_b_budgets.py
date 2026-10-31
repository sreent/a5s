"""Round 5, reviewer b: budgets against the context each run is given.

Each model call in a run carries the whole context: the release's instructions, Deep Agents'
own prompt and tools, and up to `context.budget_tokens` of the conversation. The assistant's
release gives 50,000 tokens to the conversation and 200,000 tokens to a run, so once a
conversation has grown to fill its share, a run has room for about four model calls, and a
person about four answers a day. The scripted model here counts tokens as a provider would,
about four characters each.
"""

import json

from a5s import db

FILLER = "We went through the supplier's history line by line. " * 150  # about 8,000 characters


def counted_like_a_provider(stack) -> list[int]:
    """Have the fake provider report about one token for every four characters it's sent."""
    seen: list[int] = []

    def count(_n: int) -> None:
        stack.model.tokens = len(json.dumps(stack.model.requests[-1]["body"])) // 4
        seen.append(stack.model.tokens)

    stack.model.on_request = count
    return seen


def a_months_old_conversation(stack, chars: int = 200_000) -> None:
    with db.transaction(stack.admin) as conn:
        for i in range(chars // len(FILLER) + 1):
            conn.execute("insert into turns (person, agent, topic, role, content, at) values "
                         "('ana', 'assistant', 'general', %s, %s, now() - interval '1 day')",
                         ("person" if i % 2 == 0 else "agent", FILLER))


def test_an_ordinary_request_fits_a_run_once_the_conversation_has_grown(stack):
    a_months_old_conversation(stack)
    seen = counted_like_a_provider(stack)
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply(None, ("search_records", {"query": "Northwind"}))
    stack.model.reply(None, ("create_draft", {"title": "Reply to Northwind",
                                              "body": "Thanks for your note.", "record": "Q-1001"}))
    stack.model.reply(None, ("offer_reminder", {"about": "check Northwind answered",
                                                "on": "2026-11-06", "record": "Q-1001"}))
    stack.model.reply("I've drafted the reply. Shall I remind you on Friday?")
    told = stack.say("Draft a reply to Northwind, and remind me on Friday.")  # no case: general
    assert told == "I've drafted the reply. Shall I remind you on Friday?", (
        f"five model calls didn't fit one run: the calls took {seen} tokens; a5s said: {told}")


def test_a_person_gets_more_than_a_handful_of_answers_a_day(stack):
    a_months_old_conversation(stack)
    seen = counted_like_a_provider(stack)
    answered = 0
    for i in range(10):
        stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
        stack.model.reply(f"Q-1001 is open, answer {i}.")
        if stack.say(f"Where are things now? ({i})") == f"Q-1001 is open, answer {i}.":
            answered += 1
    stack.model.script.clear()
    assert answered == 10, (
        f"Ana got {answered} answers of two model calls each before the assistant's budget for "
        f"her day ran out; each call took about {max(seen):,} tokens")
