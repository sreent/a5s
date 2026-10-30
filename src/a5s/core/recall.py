"""Recall: an agent finds what was said before in its conversation with the person it acts
for, from the original turns, not from a summary, and corrects a summary at their word.

Records beat recollection: when someone asks about the past, or the agent needs to check
what was agreed, it searches the conversation and goes by what was said, and when. It reads
one person's own conversation with this agent and nobody else's, so only a run that acts
for them alone can search. When the person says a topic's summary is wrong
(services/summaries.py), the agent adds their correction to it, in their words, in answer to
their own message. These are among a5s's own tools (core/coretools.py).
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from a5s.core.coretools import Call, CoreTool, Refused
from a5s.core.obligations import day
from a5s.core.reminders import say

FOUND = 8  # turns, newest first
LONGEST = 1500  # characters of each
_WHO = {"person": "they", "agent": "you", "notice": "a5s, on your behalf"}


def search(call: Call) -> dict:
    person, query = call.reader, " ".join(str(call.args.get("query", "")).split())
    if not query:
        raise Refused("say what to look for, such as a record's key or a few words")
    like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = call.conn.execute(  # a5s's tasks for the agent aren't what anyone said
        "select role, content, at from turns where person = %s and agent = %s and role <> 'task' "
        "and (to_tsvector('simple', content) @@ websearch_to_tsquery('simple', %s) "
        "or content ilike %s) order by id desc limit %s",
        (person.id, call.run["definition"], query, like, FOUND)).fetchall()
    return {"found": [{"when": say(person, r["at"]), "who": _WHO[r["role"]],
                       "said": r["content"][:LONGEST]} for r in rows]}


def correct(call: Call) -> dict:
    """The person's correction to the summary of the topic the run is in, in their words."""
    person, text = call.person, " ".join(str(call.args.get("correction", "")).split())
    if not text:
        raise Refused("say what's wrong with the summary, and what's right, in a sentence")
    if len(text) > 500:
        raise Refused("keep the correction to a sentence or two")
    topic = call.run["trigger"].get("topic") or "general"
    row = call.conn.execute("select body from summaries where person = %s and agent = %s "
                            "and topic = %s for update", (person.id, call.run["definition"], topic)
                            ).fetchone()
    if row is None:
        raise Refused("there's no summary of this topic yet: what a5s keeps is the conversation")
    body = {**row["body"], "corrections": [*row["body"].get("corrections", []),
                                           {"said": text, "when": day(person, call.now)}]}
    call.conn.execute("update summaries set body = %s, updated_at = now() where person = %s "
                      "and agent = %s and topic = %s",
                      (Jsonb(body), person.id, call.run["definition"], topic))
    return {"corrected": True, "topic": topic, "correction": text}


TOOLS = {t.name: t for t in (
    CoreTool("search_conversation",
             "Search what you and the person you're working for said before, when they ask about "
             "the past or you need to check what was agreed. It finds the original messages, "
             "newest first, with when each was said.",
             {"type": "object", "required": ["query"], "properties": {
                 "query": {"type": "string", "description": "A record's key, or a few words"}}},
             search, sourced=lambda found: [  # when each was said, and what the agent didn't say
                 *(f["when"] for f in found["found"]),
                 *(f["said"] for f in found["found"] if f["who"] != _WHO["agent"])]),
    CoreTool("correct_summary",
             "When the person says the summary of this topic you were given is wrong, add their "
             "correction to it, in their words.",
             {"type": "object", "required": ["correction"], "properties": {
                 "correction": {"type": "string", "description": "What's right, in their words"}}},
             correct, text_fields=("correction",)),
)}
