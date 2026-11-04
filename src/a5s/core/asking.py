"""Asking: an agent asks another for what it knows (phase 3, step 2).

An instance's settings name the instances it may ask (`asks`), which the owners of every part
either works in approve, as they approve any version. With the typed tool ask_agent, a run asks
one of them a question. The core opens a run of the instance asked at once, acting for the same
people as the run that asks, and the worker that asked runs it, as it runs its own, so a
question never waits on another worker and holds nothing of the core's while it's answered.
The run asked works within its own grant and level, and what those people may see, never the
asker's, and nobody it acts for decides what it holds. It sees no class of data the asking
run's model may not see either, since its answer goes there. It writes to nobody, and a run
asks three questions at most. Its answer goes back as the tool's result, with the mark of a run
that read content from outside, which then marks the run that asked, as the question carried
the asker's mark to it. A run that answers a question can't ask one, so questions never chain,
and the ledger links the two runs. Only the values the run asked had read, from its tools and
what a5s told it, count as read for the run that asked, never those it was asked about, and
what came from outside stays from outside. When the instance asked reports on records, such as
the watcher, it's given what changed in their records, as its reports would tell them.

A question and its answer can be given as an A2A task, in A2A 1.0's shapes for a message and a
task, so agents outside a5s can come later without a second way of asking.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import psycopg

from a5s.core import groups, handles, registry
from a5s.core.coretools import Call, CoreTool, Refused

ASK = "ask_agent"
KIND = "question"  # the trigger of the run that answers one
QUESTION = "the question it was asked"  # whence what the run asked read of the question
ASKS = 3  # questions a run may ask [TBC]
LONGEST = 1000  # characters of a question
KEPT_BACK = "[a value the {agent} can't pass on]"


def _never(call: Call) -> Any:
    raise Refused("a5s asks other agents itself, outside any transaction")  # see the gateway


TOOL = CoreTool(
    ASK,
    "Ask another agent a question, for the people you're working for, when it knows what you "
    "don't. Your context names the agents you may ask, and what each does. It sees only your "
    "question, so name the records it's about. Its answer comes back here and nobody else "
    "hears it: tell the people what it said, as its answer.",
    {"type": "object", "required": ["agent", "question"], "properties": {
        "agent": {"type": "string", "description": "The agent to ask, as your context names it"},
        "question": {"type": "string", "description": "The question, in a sentence or two"}}},
    _never, text_fields=("question",),  # never to a run that answers one: they don't chain
    offered=lambda run: run["trigger"].get("kind") != KIND and bool(run.get("asks")))


def message(role: str, text: str, message_id: str, task_id: str, context_id: str) -> dict:
    """An A2A 1.0 message, with one part of text."""
    return {"messageId": message_id, "contextId": context_id, "taskId": task_id,
            "role": role, "parts": [{"text": text}]}


def task(row: dict) -> dict:
    """A question, and any answer, as an A2A 1.0 task, from what a5s keeps of it: its context
    is the run that asked."""
    question, context = str(row["id"]), str(row["asked_by_run"])
    state, at = (("TASK_STATE_COMPLETED", row["answered_at"]) if row["answered_at"] else
                 ("TASK_STATE_FAILED", row["asked_at"]) if row["problem"] else
                 ("TASK_STATE_WORKING", row["asked_at"]) if row["run_id"] else
                 ("TASK_STATE_SUBMITTED", row["asked_at"]))
    found: dict[str, Any] = {
        "id": question, "contextId": context,
        "status": {"state": state, "timestamp": at.isoformat()},
        "history": [message("ROLE_USER", row["text"], f"{question}-q", question, context)]}
    if row["answer"] is not None:
        found["artifacts"] = [{"artifactId": f"{question}-a", "name": "answer",
                               "parts": [{"text": row["answer"]}]}]
    return found


def whom(conn: psycopg.Connection, scenario: Any, row: dict, agent: str) -> dict:
    """The instance of `agent` that the run's instance may ask, and that serves everyone the
    run acts for. Refused, in words the agent passes on, if there's none."""
    if row["trigger"].get("kind") == KIND:
        raise Refused("an agent that's asked a question can't ask another, so questions never "
                      "chain: answer from what you can find")
    if not row["acts_for"]:
        raise Refused("a question is asked for the people a run acts for, and this one acts for "
                      "nobody")
    found = conn.execute("select * from instances where id = any(%s) and definition = %s "
                         "and status = 'active' order by id",
                         (list(row.get("asks") or []), agent)).fetchall()
    for inst in found:
        if all(registry.serving(scenario, inst["serves"], p) for p in row["acts_for"]):
            return inst
    if found:
        raise Refused(f"the {agent} here doesn't work for everyone this run is for")
    raise Refused(f"you may not ask the {agent} here: the settings name the agents you may ask")


def ask(conn: psycopg.Connection, row: dict, inst: dict, text: str, now: datetime) -> str:
    """Keep a question a run asks, for the run that answers it, which the core opens at once.
    Its id. A run asks a few at most."""
    asked = conn.execute("select count(*) as n from questions where asked_by_run = %s",
                         (row["run"],)).fetchone()["n"]
    if asked >= ASKS:
        raise Refused(f"a run asks {ASKS} questions at most: answer from what you have")
    question = str(uuid.uuid4())
    conn.execute(
        "insert into questions (id, asked_by_run, asker, asked, acts_for, text, read_outside, "
        "asked_at) values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (question, row["run"], row["id"], inst["id"], list(row["acts_for"]), text,
         bool(row["read_outside"]), now))
    return question


def brief(scenario: Any, question: dict, asker: str, changed: list[str] | None = None) -> str:
    """The question, as a5s puts it to the agent asked: what it's asked, by which agent, and
    for whom, that its answer goes back to that agent, and, for an agent that reports on
    records, what changed in theirs, as its reports would tell them."""
    names = groups.names(scenario, list(question["acts_for"]))
    news = ("\n\nWhat changed in their records since you last told them, and what's open, "
            "worked out by code from the records:\n" + "\n".join(changed)) if changed else ""
    return (f"The {asker} asks you this, for {names}: {question['text']}{news}\n\n"
            f"Answer it from what you can find, for them. Your answer goes back to the {asker}, "
            "not to them, so write it for the agent, and don't ask anyone else. If you can't "
            "find something, say so plainly.")


def kept_back(text: str, agent: str) -> str:
    """An answer without the handles its run was given, which no other run can use."""
    return handles.TOKEN.sub(KEPT_BACK.format(agent=agent), text)
