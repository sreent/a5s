"""Summaries: a structured summary of each topic, for the turns that no longer fit in a run.

Once a topic's turns fall out of what its runs are given (services/context.py), a5s folds
them into the topic's summary, with a run of its own: the model says what was decided and
promised, and what's still open, and code keeps every key, amount and date the turns had,
with who said it and when, so none is lost. Code checks the model's part too, and leaves out
any sentence with a key, an amount or a date nobody said (core/values.py). Each later run in
the topic is given the summary before the turns that still fit. The person can see it, and
have an agent correct it in their words (core/recall.py).

A group chat's conversation (core/groups.py) has summaries too, of the turns everyone in it
heard, each fact with who said it. A summary keeps who heard every turn it holds, and a run is
given it only if everyone it acts for heard all of it. Once someone has joined, the group's
next summary starts afresh, from what they heard.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import Scenario
from a5s.core import values
from a5s.core.topics import PARTS, render

MOST = 12  # sentences in each part
FACTS = 500  # the newest keys, amounts and dates a summary keeps
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def load(conn: db.Connection, person: str, agent: str, topic: str,
         members: list[str] | None = None) -> dict | None:
    """The topic's summary: in a group chat's conversation, only if all of `members` heard
    everything it holds."""
    found = conn.execute("select * from summaries where person = %s and agent = %s and topic = %s",
                         (person, agent, topic)).fetchone()
    return found if found is None or members is None or heard(found, members) else None


def heard(summary: dict, members: list[str]) -> bool:
    """Whether everyone in a group chat heard every turn its summary holds."""
    return set(members) <= set(summary["heard_by"] or ())


def heard_by(previous: dict | None, turns: list[dict]) -> list[str] | None:
    """Who heard everything a group's summary will hold, once these turns are folded into it:
    None for a person's own conversation."""
    if not turns or turns[0].get("heard_by") is None:
        return None
    every = set(previous["heard_by"] or ()) if previous else set(turns[0]["heard_by"])
    for turn in turns:
        every &= set(turn["heard_by"] or ())
    return sorted(every)


def task(person: str, topic: str, previous: dict | None, turns: list[dict],
         names: dict[str, str] | None = None) -> str:
    """What a5s asks the summary run, with the turns to fold in. In a group chat's
    conversation, `names` names whoever said each turn."""
    about = "the general topic" if topic == "general" else f"the case {topic}"
    whose = "a group chat's conversation" if names is not None else f"{person}'s conversation"
    said = "\n".join(f"[{_when(t['at'])}] {_who(t, person, names)}: {t['content']}" for t in turns)
    return (f"The summary so far of {about}, in {whose} with you:\n"
            f"{render(previous['body']) if previous else 'None yet.'}\n\n"
            f"The turns to fold into it, oldest first:\n{said}")


def checked(reply: str, previous: dict | None, turns: list[dict], person: str,
            scenario: Scenario, names: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """The new summary, and what code left out of the model's part. A sentence with a key, an
    amount or a date nobody said, nor a5s showed as when something was said, is left out, and
    a reply that isn't a summary leaves the summary so far as it was. Either way, code adds
    every key, amount and date the turns had to its facts, the newest few hundred, so nothing
    the turns held is lost, and the turns are folded once, not asked about again. In a group
    chat's conversation, each fact someone said keeps who they are, as `speaker`."""
    pattern = getattr(scenario, "record_pattern", None)
    before = previous["body"] if previous else {}
    match = _JSON.search(reply or "")
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    problems: list[str] = []
    if isinstance(data, dict):
        parts = {part: [" ".join(str(s).split()) for s in data.get(part) or []
                        if str(s).strip()][:MOST]
                 for part in PARTS if isinstance(data.get(part) or [], list)}
        sources = values.found("\n".join([render(before), *(t["content"] for t in turns),
                                          *(_when(t["at"]) for t in turns)]), pattern)
        for part, lines in parts.items():
            kept = []
            for line in lines:
                if invented := values.unmatched(values.found(line, pattern), sources):
                    problems += [f"it says {v.text}, which nobody said" for v in invented]
                else:
                    kept.append(line)
            parts[part] = kept
    else:
        problems.append("the model's reply isn't a summary in the form asked for")
        parts = {part: list(before.get(part) or []) for part in PARTS}
    facts = list(before.get("facts") or [])
    for turn in turns:
        for v in values.found(turn["content"], pattern):
            if not any(f["kind"] == v.kind and f["norm"] == v.norm for f in facts):
                facts.append({"kind": v.kind, "value": v.text, "norm": v.norm,
                              "who": _who(turn, person, names), "when": _when(turn["at"]),
                              **({"speaker": turn["speaker"]} if _said_by(turn) else {})})
    return {**parts, "facts": facts[-FACTS:],
            "corrections": list(before.get("corrections") or [])}, problems


def keep(conn: db.Connection, person: str, agent: str, topic: str, body: dict,
         through: int, run: str, heard: list[str] | None = None) -> None:
    """Keep the topic's summary, in place of the one before: in a group chat's conversation,
    with who heard everything it holds."""
    conn.execute(
        "insert into summaries (person, agent, topic, body, through, run_id, heard_by) "
        "values (%s, %s, %s, %s, %s, %s, %s) on conflict (person, agent, topic) do update "
        "set body = excluded.body, through = excluded.through, run_id = excluded.run_id, "
        "heard_by = excluded.heard_by, updated_at = now()",
        (person, agent, topic, Jsonb(body), through, run, heard))


def _said_by(turn: dict) -> bool:
    """Whether someone in a group chat said the turn."""
    return turn["role"] == "person" and bool(turn.get("speaker"))


def _who(turn: dict, person: str, names: dict[str, str] | None = None) -> str:
    if _said_by(turn):
        return (names or {}).get(turn["speaker"], turn["speaker"])
    return {"person": person, "agent": "you", "notice": "a5s", "task": "a5s"}.get(
        turn["role"], turn["role"])


def _when(at: datetime | str) -> str:
    at = datetime.fromisoformat(at) if isinstance(at, str) else at
    return f"{at:%a} {at.day} {at:%b} {at:%Y}"
