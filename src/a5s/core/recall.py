"""Recall: an agent finds what was said before in its conversation with the person it acts
for, from the original turns, not from a summary.

Records beat recollection: when someone asks about the past, or the agent needs to check
what was agreed, it searches the conversation and goes by what was said, and when. It reads
one person's own conversation with this agent and nobody else's, so only a run that acts
for them alone can search. It's one of a5s's own tools (core/coretools.py).
"""

from __future__ import annotations

from a5s.core.coretools import Call, CoreTool, Refused
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


TOOLS = {t.name: t for t in (
    CoreTool("search_conversation",
             "Search what you and the person you're working for said before, when they ask about "
             "the past or you need to check what was agreed. It finds the original messages, "
             "newest first, with when each was said.",
             {"type": "object", "required": ["query"], "properties": {
                 "query": {"type": "string", "description": "A record's key, or a few words"}}},
             search),
)}
