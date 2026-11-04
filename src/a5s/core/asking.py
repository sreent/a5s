"""Asking: an agent asks another for what it knows (phase 3, step 2).

An instance's settings name the instances it may ask (`asks`), which the owners of every part
either works in approve, as they approve any version. With the typed tool ask_agent, a run asks
one of them a question. The core opens a run of the instance asked, acting for the same people
as the run that asks: it works within its own grant and level, and what those people may see,
never the asker's, and nobody it acts for decides what it holds. It writes to nobody. Its
answer goes back as the tool's result, with the mark of a run that read content from outside,
which then marks the run that asked, as the question carried the asker's mark to it. A run that
answers a question can't ask one, so questions never chain, and the ledger links the two runs.
Only the values the run asked had read count as read for the run that asked: any it wrote
itself, the asker's run doesn't take as found.

The question and its answer are kept as an A2A task, in A2A 1.0's shapes for a message and a
task, so agents outside a5s can come later without a second way of asking.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s.core import groups, handles, registry
from a5s.core.coretools import Call, CoreTool, Refused

ASK = "ask_agent"
KIND = "question"  # the trigger of the run that answers one
WAIT = 120.0  # seconds a run waits for an answer [TBC]
LONGEST = 1000  # characters of a question
KEPT_BACK = "[a value the {agent} can't pass on]"


def _never(call: Call) -> Any:
    raise Refused("a5s asks other agents itself, outside any transaction")  # see the gateway


TOOL = CoreTool(
    ASK,
    "Ask another agent a question, for the people you're working for, when it knows what you "
    "don't, such as the watcher about what changed on someone's records. Your context names the "
    "agents you may ask. Its answer comes back here and nobody else hears it: tell the people "
    "what it said, as its answer.",
    {"type": "object", "required": ["agent", "question"], "properties": {
        "agent": {"type": "string", "description": "The agent to ask, such as watcher"},
        "question": {"type": "string", "description": "The question, in a sentence or two"}}},
    _never, text_fields=("question",))


def message(role: str, text: str, message_id: str, task_id: str, context_id: str) -> dict:
    """An A2A 1.0 message, with one part of text."""
    return {"messageId": message_id, "contextId": context_id, "taskId": task_id,
            "role": role, "parts": [{"text": text}]}


def task(question: str, context: str, text: str, state: str, at: datetime,
         answer: str | None = None) -> dict:
    """A question, and any answer, as an A2A 1.0 task: its context is the run that asks."""
    found: dict[str, Any] = {
        "id": question, "contextId": context,
        "status": {"state": state, "timestamp": at.isoformat()},
        "history": [message("ROLE_USER", text, f"{question}-q", question, context)]}
    if answer is not None:
        found["artifacts"] = [{"artifactId": f"{question}-a", "name": "answer",
                               "parts": [{"text": answer}]}]
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
    """Keep a question for the scheduler to have answered, and wake it. Its id."""
    question = str(uuid.uuid4())
    conn.execute(
        "insert into questions (id, asked_by_run, asker, asked, acts_for, text, read_outside, "
        "asked_at, task) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (question, row["run"], row["id"], inst["id"], list(row["acts_for"]), text,
         bool(row["read_outside"]), now,
         Jsonb(task(question, row["run"], text, "TASK_STATE_SUBMITTED", now))))
    conn.execute("notify a5s_inbound")
    return question


def brief(scenario: Any, question: dict, asker: str) -> str:
    """The question, as a5s puts it to the agent asked: what it's asked, by which agent, and
    for whom, and that its answer goes back to that agent."""
    names = groups.names(scenario, list(question["acts_for"]))
    return (f"The {asker} asks you this, for {names}: {question['text']}\n\n"
            f"Answer it from what you can find, for them. Your answer goes back to the {asker}, "
            "not to them, so write it for the agent, and don't ask anyone else.")


def kept_back(text: str, agent: str) -> str:
    """An answer without the handles its run was given, which no other run can use."""
    return handles.TOKEN.sub(KEPT_BACK.format(agent=agent), text)
