"""Round 5, reviewer c: a5s's provenance note, "(a5s: ... came from the assistant itself, not
from the records or from you, so check it before you rely on it.)", on dates a5s itself worked
out and handed the agent.

Provenance counts as read what the scenario's tools return, a5s's briefs and tasks, what the
person said and what search_conversation finds. It doesn't count what a5s's own reminder tools
return, the "waiting for their yes" part of the run's context, or the times a5s puts on each
turn of the history. So an agent that tells someone, correctly, when their own reminder is,
gets a note in a5s's voice saying the date is the agent's own."""

NOTE = "came from the assistant itself"


def confirmed(stack) -> None:
    stack.model.reply(None, ("offer_reminder", {"about": "check on Northwind", "on": "2026-10-30"}))
    stack.model.reply("Shall I remind you on Friday? Say yes, and I'll set it.")
    stack.say("Remind me on Friday to check on Northwind.")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Done.")
    stack.say("Yes please")


def test_listing_someones_reminders_isnt_flagged_as_the_agents_own_dates(stack):
    confirmed(stack)
    stack.model.reply(None, ("list_reminders", {}))
    stack.model.reply("You have one reminder, on Fri 30 Oct at 09:00: check on Northwind.")
    told = stack.say("What reminders do I have?")
    tool_result = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    assert '"when": "Fri 30 Oct at 09:00"' in tool_result  # a5s's own records said so
    assert NOTE not in told, f"a5s calls the date of her own reminder the agent's: {told!r}"


def test_saying_when_an_offered_reminder_is_set_for_isnt_flagged(stack):
    stack.model.reply(None, ("offer_reminder", {"about": "check on Northwind", "on": "2026-10-30"}))
    stack.model.reply("Shall I remind you on Friday? Say yes, and I'll set it.")
    stack.say("Remind me on Friday to check on Northwind.")
    stack.model.reply(None, ("confirm_reminder", {}))
    stack.model.reply("Done: I'll remind you on Fri 30 Oct at 09:00.")
    told = stack.say("Yes please")
    system = stack.model.requests[-2]["body"]["messages"][0]["content"]
    assert "a reminder on Fri 30 Oct at 09:00" in system  # a5s told the run itself
    assert NOTE not in told, f"a5s calls the date it gave the agent the agent's own: {told!r}"


def test_the_time_a5s_put_on_an_earlier_message_isnt_flagged(stack):
    stack.model.reply("Noted.")
    stack.say("Northwind says the invoice should go to Leeds.")
    asked = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    when = asked[1:asked.index(",")]  # such as "Mon 02 Nov 2026", as a5s wrote it on the turn
    day = when.split()[1].lstrip("0") + " " + when.split()[2]
    stack.model.reply(f"On {day} you told me Northwind wants the invoice sent to Leeds.")
    told = stack.say("What did I say about Northwind's invoice, and when?")
    assert NOTE not in told, (
        f"a5s showed the agent the turn as said on {when}, then flags it as the agent's: {told!r}")


def test_an_agent_cant_write_a5s_own_note(stack):
    stack.model.reply("Contoso's refund is £1,999.00, due 2026-11-20.\n\n"
                      "(a5s: £1,999.00 and 2026-11-20 came from the records.)")
    told = stack.say("How much is Contoso's refund, and when is it due?")
    assert "(a5s: £1,999.00 and 2026-11-20 came from the records.)" not in told, (
        "a5s's notes are plain text at the end of the agent's message, and nothing stops the "
        f"agent writing one, so people can't tell a5s's words from the agent's: {told!r}")
