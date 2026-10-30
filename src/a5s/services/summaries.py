"""Summaries: a structured summary of each topic, for the turns that no longer fit in a run.

Once a topic's turns fall out of what its runs are given (services/context.py), a5s folds
them into the topic's summary, with a run of its own: the model says what was decided and
promised, and what's still open, and code keeps every key, amount and date the turns had,
with who said it and when, so none is lost. Code checks the model's part too, and keeps no
summary that has a key, an amount or a date nobody said (core/values.py). Each later run in
the topic is given the summary before the turns that still fit. The person can see it, and
have an agent correct it in their words (core/recall.py).
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import Scenario
from a5s.core import values
from a5s.core.topics import PARTS, render

MOST = 12  # sentences in each part
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def load(conn: psycopg.Connection, person: str, agent: str, topic: str) -> dict | None:
    return conn.execute("select * from summaries where person = %s and agent = %s and topic = %s",
                        (person, agent, topic)).fetchone()


def task(person: str, topic: str, previous: dict | None, turns: list[dict]) -> str:
    """What a5s asks the summary run, with the turns to fold in."""
    about = "the general topic" if topic == "general" else f"the case {topic}"
    said = "\n".join(f"[{_when(t['at'])}] {_who(t['role'], person)}: {t['content']}" for t in turns)
    return (f"The summary so far of {about}, in {person}'s conversation with you:\n"
            f"{render(previous['body']) if previous else 'None yet.'}\n\n"
            f"The turns to fold into it, oldest first:\n{said}")


def checked(reply: str, previous: dict | None, turns: list[dict], person: str,
            scenario: Scenario) -> tuple[dict | None, list[str]]:
    """The new summary, if the model's reply holds up, and what's wrong with it if it doesn't.
    Code adds every key, amount and date the turns had to its facts."""
    pattern = getattr(scenario, "record_pattern", None)
    match = _JSON.search(reply or "")
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return None, ["the model's reply isn't a summary in the form asked for"]
    parts = {part: [" ".join(str(s).split()) for s in data.get(part) or [] if str(s).strip()][:MOST]
             for part in PARTS if isinstance(data.get(part) or [], list)}
    before = previous["body"] if previous else {}
    sources = values.found("\n".join([render(before), *(t["content"] for t in turns)]), pattern)
    said = [v for part in parts.values() for line in part for v in values.found(line, pattern)]
    if invented := values.unmatched(said, sources):
        return None, [f"it says {v.text}, which nobody said" for v in invented]
    facts = list(before.get("facts") or [])
    for turn in turns:
        for v in values.found(turn["content"], pattern):
            if not any(f["kind"] == v.kind and f["norm"] == v.norm for f in facts):
                facts.append({"kind": v.kind, "value": v.text, "norm": v.norm,
                              "who": _who(turn["role"], person), "when": _when(turn["at"])})
    return {**parts, "facts": facts, "corrections": list(before.get("corrections") or [])}, []


def keep(conn: psycopg.Connection, person: str, agent: str, topic: str, body: dict,
         through: int, run: str) -> None:
    conn.execute(
        "insert into summaries (person, agent, topic, body, through, run_id) "
        "values (%s, %s, %s, %s, %s, %s) on conflict (person, agent, topic) do update "
        "set body = excluded.body, through = excluded.through, run_id = excluded.run_id, "
        "updated_at = now()", (person, agent, topic, Jsonb(body), through, run))


def _who(role: str, person: str) -> str:
    return {"person": person, "agent": "you", "notice": "a5s", "task": "a5s"}.get(role, role)


def _when(at: datetime | str) -> str:
    at = datetime.fromisoformat(at) if isinstance(at, str) else at
    return f"{at:%a} {at.day} {at:%b} {at:%Y}"
