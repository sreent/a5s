"""a5s's own words in answer to someone's message, such as that the agent they wrote to is
suspended, or that its model isn't answering. The scheduler asks the core to send each, as one
of these sentences with what changes in it, and the core says it in the language its reader
reads, or, in a group chat, the one everyone in it reads (core/words.py; round 15, A12). Words
that aren't among these, such as from a scheduler older than the core, go as they are.
"""

from __future__ import annotations

from a5s.core import dependencies, groups, words
from a5s.core.approvals import names_of

WENT_WRONG = ("Something went wrong on my side, so I couldn't answer that. Try again in a few "
              "minutes.")
NOT_STARTED = "a5s couldn't start on that. Try again, or ask {who}."
NOT_SENT = "I couldn't send you my reply, sorry."
MODEL_DOWN = ("The model I use isn't answering right now, so I couldn't finish that. Try again in "
              "a few minutes.")
SPENT = ("The {agent} has used its budget for you today, so it can't help with that until "
         "tomorrow. Ask {who} if it can't wait.")
TOO_MUCH = ("That took more work than one run may do, so I stopped. Try asking for less at once, "
            "or ask {who}.")
UNFINISHED = "I couldn't finish that. Try again, or ask {who}."
STOPPED = ("I couldn't finish your last message, so I stopped. Send it again if you still need "
           "it.")
NO_SUCH = "There's no {agent} for you."  # an agent there isn't, or that they may not know of
NOT_YET = "There's no {agent} for you yet. Ask for it on its page in the studio."
YOU_SUSPENDED = "The {agent} is suspended, because you suspended it. Resume it to carry on."
SUSPENDED = ("The {agent} is suspended at the moment, so it can't help. {by} suspended it and can "
             "resume it.")
NOT_AT_WORK = "The {agent} is {status}, so it can't help. Ask {who}."
CANT_HELP = "The {agent} can't help you at the moment. Ask {who}."
ANYONE = "whoever runs a5s"  # whom to ask about an instance nobody else runs
ADD = "Whoever approves the agents here can add them."  # in a group chat, of whom it doesn't serve

SAID = frozenset({WENT_WRONG, NOT_STARTED, NOT_SENT, MODEL_DOWN, SPENT, TOO_MUCH, UNFINISHED,
                  STOPPED, NO_SUCH, NOT_YET, YOU_SUSPENDED, SUSPENDED, NOT_AT_WORK, CANT_HELP,
                  groups.UNSERVED, groups.APART, groups.UNWRITTEN})
# What changes in them that a5s has words for too: whom to ask, and an instance's status, as the
# map of what depends on what says it (core/dependencies.py)
WORDS = frozenset({ANYONE, ADD, *dependencies.STATUS.values()})


def said(language: str, text: str, given: dict[str, str | list[str]] | None = None) -> str:
    """A notice in someone's language, with what changes in it put in: a list of names as one,
    in words (Ana Ortiz and Ben Okafor), and an instance's status, or whom to ask, in their
    language too. Words that aren't one of a5s's notices go as they are. ValueError if what's
    given doesn't fit the notice."""
    if text not in SAID:
        return text
    given = {**(given or {})}
    if isinstance(status := given.get("status"), str):
        given["status"] = dependencies.STATUS.get(status, status)
    put = {k: names_of(list(v), language) if isinstance(v, list) else
           words.say(language, v) if v in WORDS else v for k, v in given.items()}
    try:  # each notice is a5s's own, so only what's given goes in
        return words.say(language, text).format(**put)
    except (KeyError, IndexError) as exc:
        raise ValueError(f"the notice needs {exc} given") from None
