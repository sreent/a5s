"""Round 5, reviewer a: a correction to a summary is kept, and shown to every later run, as the
person's own words, but it's the agent's text, and code doesn't match its keys, amounts and
dates against what the person said, as it does for summaries and for what agents write.
"""

from test_summaries import a_long_conversation, folded, summaries


def test_a_correction_keeps_no_amount_the_person_didnt_say(stack):
    a_long_conversation(stack)
    stack.model.reply("Hello, Ana.")
    stack.model.reply(folded(["Contoso's refund for Q-1002 is £1,240.50."]))
    stack.say("Hello")
    stack.gateway.definitions["assistant"].context.budget_tokens = 30000  # it all fits again
    stack.model.reply(None, ("correct_summary", {
        "correction": "The refund for Q-1002 is £50,000, not £1,240.50."}))
    stack.model.reply("Corrected.")
    stack.say("The summary's wrong about the refund.")  # she names no amount
    [summary] = summaries(stack)
    said = [c["said"] for c in summary["body"].get("corrections", [])]
    assert not any("£50,000" in s for s in said), said  # today: kept "in their words"
