"""Recall: an agent finds what was said before in its conversation with the person it acts
for, from the original turns, not from a summary, and corrects a summary at their word.

Records beat recollection: when someone asks about the past, or the agent needs to check
what was agreed, it searches the conversation and goes by what was said, and when. It reads
one person's own conversation with this agent and nobody else's, so only a run that acts
for them alone can search, or in a group chat, the group's own conversation, and only what
everyone now in it heard (core/groups.py). When the person says a topic's summary is wrong
(services/summaries.py), the agent adds their correction to it, in their words, in answer to
their own message. These are among a5s's own tools (core/coretools.py).
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from a5s.core import groups, values
from a5s.core.coretools import Call, CoreTool, Refused
from a5s.core.obligations import day
from a5s.core.reminders import say

FOUND = 8  # turns, newest first
LONGEST = 1500  # characters of each
_WHO = {"person": "they", "agent": "you", "notice": "a5s, on your behalf"}


def search(call: Call) -> dict:
    group = call.conversation  # whose time zone it says when things were: the asker's, in one
    person = call.scenario.person(groups.asker(call.run) or "") if group else call.reader
    if person is None:
        raise Refused("the directory doesn't know them")
    query = " ".join(str(call.args.get("query", "")).split())
    if not query:
        raise Refused("say what to look for, such as a record's key or a few words")
    like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    heard = " and heard_by @> %(members)s::text[]" if group else ""
    rows = call.conn.execute(  # a5s's tasks for the agent aren't what anyone said
        "select role, content, at, speaker from turns where person = %(whose)s "
        f"and agent = %(agent)s and role <> 'task'{heard} and (to_tsvector('simple', content) "
        "@@ websearch_to_tsquery('simple', %(query)s) or content ilike %(like)s) "
        "order by id desc limit %(found)s",
        {"whose": group or person.id, "agent": call.run["definition"], "query": query,
         "like": like, "members": list(call.run["acts_for"]), "found": FOUND}).fetchall()
    return {"found": [{"when": say(person, r["at"]), "who": _who(call, r),
                       "said": r["content"][:LONGEST]} for r in rows]}


def _who(call: Call, row: dict) -> str:
    """Who said a turn: in a group chat, by name."""
    if row["role"] == "person" and row["speaker"]:
        return (p.name if (p := call.scenario.person(row["speaker"])) else row["speaker"])
    return _WHO[row["role"]]


def correct(call: Call) -> dict:
    """A correction to the summary of the topic the run is in, in the words of whoever said
    it: to their own summary, or in a group chat, to the group's, which everyone now in it
    heard all of, with their name on it."""
    group = call.conversation
    person = call.asker if group else call.person
    text = " ".join(str(call.args.get("correction", "")).split())
    if not text:
        raise Refused("say what's wrong with the summary, and what's right, in a sentence")
    if len(text) > 500:
        raise Refused("keep the correction to a sentence or two")
    said = call.conn.execute("select text from inbound where id = %s",
                             (call.run["trigger"].get("inbound"),)).fetchone()
    pattern = call.scenario.record_pattern
    if wrong := values.unmatched(values.found(text, pattern),
                                 values.found(said["text"] if said else "", pattern)):
        raise Refused(f"a correction keeps only what they said, and they didn't say "
                      f"{', '.join(v.text for v in wrong)}: put it in their words")
    topic = call.run["trigger"].get("topic") or "general"
    whose, members = group or person.id, list(call.run["acts_for"])
    row = call.conn.execute("select body, heard_by from summaries where person = %s and agent = %s "
                            "and topic = %s for update", (whose, call.run["definition"], topic)
                            ).fetchone()
    if row is None or (group and not set(members) <= set(row["heard_by"] or ())):
        raise Refused("there's no summary of this topic yet: what a5s keeps is the conversation")
    said_by = {"by": person.name, "speaker": person.id} if group else {}  # in a group, whose
    # words they are: by name, for the summary, and by id, for their export and erasure
    body = {**row["body"], "corrections": [*row["body"].get("corrections", []),
                                           {"said": text, "when": day(person, call.now),
                                            **said_by}]}
    call.conn.execute("update summaries set body = %s, updated_at = now(), heard_by = %s "
                      "where person = %s and agent = %s and topic = %s",  # those who heard it all
                      (Jsonb(body), sorted(members) if group else row["heard_by"], whose,
                       call.run["definition"], topic))
    return {"corrected": True, "topic": topic, "correction": text}


TOOLS = {t.name: t for t in (
    CoreTool("search_conversation",
             "Search what you and the person you're working for said before, when they ask about "
             "the past or you need to check what was agreed. It finds the original messages, "
             "newest first, with when each was said.",
             {"type": "object", "required": ["query"], "properties": {
                 "query": {"type": "string", "description": "A record's key, or a few words"}}},
             search, sourced=lambda found: [  # when each was said, and what people said:
                 *(f["when"] for f in found["found"]),  # not the agent's words, nor a5s's notes
                 *(f["said"] for f in found["found"]
                   if f["who"] not in (_WHO["agent"], _WHO["notice"]))]),
    CoreTool("correct_summary",
             "When someone you're working for says the summary of this topic you were given is "
             "wrong, add their correction to it, in their words.",
             {"type": "object", "required": ["correction"], "properties": {
                 "correction": {"type": "string", "description": "What's right, in their words"}}},
             correct, text_fields=("correction",)),
)}
