"""Round 15, A12: a5s's own words in a chat, such as that the agent is suspended or its model
isn't answering, are notices the core puts together from a5s's sentences, with what changes in
them, or as the scheduler wrote them where it can't. The conversation keeps them as they were
said."""

from __future__ import annotations

import pytest

from a5s.core import groups, notices


def test_a_notice_puts_in_what_changes():
    assert notices.said("en", groups.UNSERVED, {"who": ["Ana Ortiz", "Ben Okafor"],
                                                "add": notices.ADD}) == (
        "I don't work for Ana Ortiz and Ben Okafor yet, so I can't help in this chat. Whoever "
        "approves the agents here can add them. Or ask me in a chat without them, or one to one.")
    assert notices.said("en", notices.NOT_AT_WORK, {"agent": "assistant", "status": "proposed",
                                                    "who": notices.ANYONE}) == (
        "The assistant is waiting for approval, so it can't help. Ask whoever runs a5s.")
    old = "The assistant {is} as an older scheduler wrote it."  # none of a5s's: as it is
    assert notices.said("en", old, {"is": "x"}) == old
    with pytest.raises(ValueError, match="who"):
        notices.said("en", notices.UNFINISHED, {})


def test_the_core_says_a_notice_whole_or_as_the_scheduler_wrote_it(stack):
    """A notice comes with the scheduler's own words too, so a core missing what it needs, or
    an older one, still says it."""
    english = "I couldn't finish that. Try again, or ask Ana Ortiz."
    with stack.client() as c:
        missing = c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                           "text": english, "notice": notices.UNFINISHED})
        whole = c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                         "text": english, "notice": notices.UNFINISHED,
                                         "given": {"who": "Ana Ortiz"}})
        unknown = c.post("/notices", json={"inbound": stack.send("Hello", "ben"),
                                           "text": "Words of a newer scheduler.",
                                           "notice": "Words of a {newer} scheduler."})
    assert missing.json() == whole.json() == {"sent": True, "text": english}
    assert unknown.json() == {"sent": True, "text": "Words of a newer scheduler."}
