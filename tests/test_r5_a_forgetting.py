"""Round 5, reviewer a: what people say reaches the ledger in the arguments of a5s's own tools.

The ledger keeps a message by its hash. But it keeps a tool's arguments as they are, unless
they're longer than 120 characters, and a5s's own tools carry people's words: the note on how
they like to work, what to remind them of, what they're waiting on, their corrections. The
ledger can't be changed or deleted, and its copies are locked, so these outlast forgetting and
retention. architecture.md: "a note someone asks to forget goes at once"; the ledger "keeps
nothing that was said".
"""

from test_profiles import offered_and_confirmed

NOTE = "Keep answers to two sentences, with the record's link."  # as test_profiles offers it
REMINDER = "ring the clinic about my scan results"


def test_a_note_someone_asks_to_forget_isnt_kept_in_the_ledger(stack):
    offered_and_confirmed(stack)
    stack.model.reply(None, ("forget_note", {}))
    stack.model.reply("I've forgotten it.")
    assert stack.say("Please forget my note") == "I've forgotten it."
    assert NOTE not in str(stack.ledger())  # today: in the offer_note entry, for good


def test_what_someone_asks_to_be_reminded_of_isnt_kept_in_the_ledger(stack):
    stack.model.reply(None, ("offer_reminder", {"about": REMINDER, "on": "2026-11-20"}))
    stack.model.reply("Shall I remind you on Friday the 20th?")
    stack.say("Remind me to ring the clinic about my scan results on the 20th")
    assert REMINDER not in str(stack.ledger())
