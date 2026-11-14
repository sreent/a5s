"""Groups: an agent in a group chat, such as a Teams group chat or a Matrix room.

People bring an agent into a group chat of up to 20 people, each of whom the directory knows,
and it answers whoever mentions it there. The core reads who's in the chat from the chat itself
at each message, so a run acts for everyone in it then: it finds, sees and says only what all of
them may see, and its changes count for each of them. Its daily budget is the asker's.

A group's conversation is the chat's own, apart from each person's, and keyed by its own name,
group:<hex>. Each turn records who said it, and who was in the chat, and a run is given only the
turns said while everyone now in it was there, so nobody added later gets what was said before.

What's one person's stays one to one: notes on how they like to work, their digest, what they
wait on and the list of their reminders, and agents writing first. A reminder asked for in a
group is the asker's alone: only they can say yes to it, there, and it reaches them alone.
"""

from __future__ import annotations

import hashlib
from typing import Any

from a5s import db

LIMIT = 20  # people in a group chat an agent works in [TBC]
PREFIX = "group:"  # what a group's name starts with: never a person in the directory

# What a5s says in a group chat it won't work in, and why: who or what's in the way, and what
# to do now
TOO_MANY = (f"I work in group chats of up to {LIMIT} people, so I can't help here. Ask me in a "
            "smaller chat, or one to one.")
STRANGERS = ("I can help in a chat only if everyone in it is in the organisation's directory, and "
             "{who} isn't, so I can't help here. Ask me one to one.")
HISTORY = ("I work only in rooms where people added later can't read what was said before they "
           "joined. Ask whoever administers this room to set who can read its history to members "
           "only, since they joined, then ask me again.")
ENCRYPTED = ("I can't read encrypted rooms yet, so I can't help in this one. Ask me in a room "
             "made with encryption off, or one to one.")
CHANNELS = "I work in group chats, not in a team's channels. Ask me in a group chat, or one to one."
UNREAD = ("I couldn't tell who's in this chat just now, so I can't answer here. Ask me again in a "
          "minute.")
UNSERVED = ("I don't work for {who} yet, so I can't help in this chat. {add} Or ask me in a chat "
            "without them, or one to one.")
APART = ("I can't work for everyone here at once, so I can't help in this chat. Ask me in a "
         "smaller chat, or one to one.")
UNWRITTEN = ("I may not write to {who}, so I can't help in this chat. Ask me in a chat without "
             "them, or one to one.")
JOINED = ("Someone joined the chat while I was answering, so I've kept that answer back for whoever "
          "asked: {where}. Ask me again here, and I'll answer for everyone here now.")


def key(channel: str, place: str) -> str:
    """A group chat's name in a5s: the same for the chat whenever its messages arrive."""
    return PREFIX + hashlib.sha256(f"{channel}\n{place}".encode()).hexdigest()[:16]


def record(conn: db.Connection, channel: str, place: str) -> str:
    """The group's name, noting the chat the first time a5s hears from it."""
    name = key(channel, place)
    conn.execute("insert into groups (id, channel, place) values (%s, %s, %s) "
                 "on conflict do nothing", (name, channel, place))
    return name


def of(name: str | None) -> bool:
    """Whether a conversation is a group's."""
    return bool(name) and name.startswith(PREFIX)


def asker(run: dict[str, Any]) -> str | None:
    """Who a run answers: the one person it acts for, or in a group, whoever asked."""
    trigger = run.get("trigger") or {}
    if of(trigger.get("conversation")):
        return trigger.get("sender")
    acts_for = list(run.get("acts_for") or [])
    return acts_for[0] if len(acts_for) == 1 else None


def listed(names: list[str], most: int = 3) -> str:
    """Names in words, the first few of them: A, B and C, or A, B, C and 4 others."""
    if len(names) > most:
        return f"{', '.join(names[:most])} and {len(names) - most} others"
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def names(scenario: Any, people: list[str]) -> str:
    """People by their names, in words: Ana Ortiz and Ben Okafor."""
    named = [p.name if (p := scenario.person(who)) else who for who in people]
    if not named:
        return "nobody"
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"


def section(scenario: Any, members: list[str], sender: str | None) -> dict:
    """Who a run in a group works for, as it's given it."""
    named = [(p.name if (p := scenario.person(m)) else m) + (" (who asked)" if m == sender else "")
             for m in members]
    return {"title": "Who you're working for: everyone in this group chat",
            "text": "You're answering in a group chat, and everyone in it reads your answer: "
                    + ", ".join(named) + ". Say only what all of them may see. Each message in "
                    "the conversation says who wrote it. You hear only messages that mention "
                    "you: if someone refers to something said without a mention, ask them to "
                    "say it again with one, and when you ask someone something, ask them to "
                    "answer with a mention of you. Anything that's one person's own, such as "
                    "their notes, their digest or their list of reminders, they ask for one to "
                    "one, and a reminder you offer here is for the person who asked, alone."}


def requesters(run: dict[str, Any]) -> list[str]:
    """Whom a run's changes are asked for: the one person it acts for, or in a group chat,
    whoever asked there and whoever spoke in what the run was given, whose words may have asked
    for them. They're who decides nothing of it, and whose limits it counts against. A run in a
    group sees only what everyone in it may see, whoever asked."""
    trigger = run.get("trigger") or {}
    if of(trigger.get("conversation")) and trigger.get("asked_by"):
        return sorted(trigger["asked_by"])
    return list(run.get("acts_for") or [])
