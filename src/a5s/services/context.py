"""Context: each person's conversation with each agent, kept as a5s's own records.

Every run starts fresh and reads the conversation from here, so a conversation
never runs out of room and an upgrade never strands it. The conversation is in
topics, such as one for each case, and the core decides each run's topic
(core/topics.py). A run gets the topic's summary, the conversation's latest
turns, whatever their topic, and in a case, the case's older turns too, each
within its share of the budget the agent's release gives it. Turns that no
longer fit are folded into the summary (services/summaries.py).

A group chat's conversation is kept the same way, under the group's name (core/groups.py),
with who said each turn and who was there to hear it. A run in the group is given only the
turns everyone now in it heard, each with the name of whoever said it, and the topic's summary
only if everyone now in it heard all it holds.
"""

from __future__ import annotations

from a5s import db
from a5s.core.topics import render
from a5s.services import summaries

GENERAL = "general"
CHARS = 120_000  # a run's budget for its conversation, if it isn't given one: about 30,000 tokens
LATEST = 2 / 3  # in a case, the latest turns' share of the budget; the case's older turns get the rest
FOLD = 0.1  # turns that no longer fit are folded into the summary once they're this share of it


def add_turn(
    conn: db.Connection,
    *,
    person: str,
    agent: str,
    role: str,
    content: str,
    run: str | None = None,
    topic: str = GENERAL,
    speaker: str | None = None,
    heard_by: list[str] | None = None,
) -> None:
    """A turn of the conversation: in a group's, with who said it and who heard it."""
    conn.execute(
        "insert into turns (person, agent, topic, role, content, run_id, speaker, heard_by) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (person, agent, topic, role, content, run, speaker, heard_by),
    )


def history(
    conn: db.Connection, *, person: str, agent: str, topic: str = GENERAL,
    chars: int = CHARS, members: list[str] | None = None, names: dict[str, str] | None = None,
) -> list[dict]:
    """What a run is given of the conversation, oldest first, with when each was and its
    topic: the topic's summary, if it has one, then the conversation's latest turns that fit
    the rest of the budget, or in a case, their share of it, and the case's older turns that
    fit what's left. In a group, only what all of `members` heard, each turn people said with
    the name of whoever said it, from `names`."""
    summary = summaries.load(conn, person, agent, topic, members)
    told = _told(summary, chars)
    turns = [{"role": t["role"], "content": _said(t, names), "at": t["at"].isoformat(),
              "topic": t["topic"]} for _, t in sorted(_kept(conn, person, agent, topic,
                                                             chars - len(told), members).items())]
    return ([{"role": "summary", "content": told, "at": summary["updated_at"].isoformat(),
              "topic": topic, **({"group": True} if members is not None else {})}]
            if told else []) + turns


def dropped(conn: db.Connection, *, person: str, agent: str, topic: str,
            chars: int, members: list[str] | None = None) -> tuple[dict | None, list[dict]]:
    """The topic's summary, and its turns that no run is given any more and the summary
    doesn't hold yet, oldest first: what to fold into it. In a group, of what all of
    `members` heard: a summary someone in it didn't hear all of is started afresh."""
    summary = summaries.load(conn, person, agent, topic, members)
    told = _told(summary, chars)
    shown = [i for i, t in _kept(conn, person, agent, topic, chars - len(told), members).items()
             if t["topic"] == topic]
    first = min(shown) if shown else None
    heard = "" if members is None else " and heard_by @> %(members)s::text[]"
    return summary, conn.execute(
        "select id, role, content, at, topic, speaker, heard_by from turns where person = "
        f"%(person)s and agent = %(agent)s and topic = %(topic)s{heard} and id > %(through)s "
        "and (%(first)s::bigint is null or id < %(first)s) order by id",
        {"person": person, "agent": agent, "topic": topic, "members": members,
         "through": summary["through"] if summary else 0, "first": first}).fetchall()


def _told(summary: dict | None, chars: int) -> str:
    """A topic's summary as a run is given it: a third of the run's budget at most, keeping
    its newest facts, so it never crowds out the conversation's latest turns."""
    if summary is None:
        return ""
    body = summary["body"]
    told, facts = render(body), list(body.get("facts") or [])
    while facts and len(told) > chars // 3:
        facts = facts[max(1, len(facts) // 4):]  # the oldest quarter goes
        told = render({**body, "facts": facts})
    return told


def speakers(conn: db.Connection, group: str, agent: str) -> list[str]:
    """Whoever has said anything in a group chat's conversation with the agent."""
    return [r["speaker"] for r in conn.execute(
        "select distinct speaker from turns where person = %s and agent = %s "
        "and speaker is not null", (group, agent))]


def _said(turn: dict, names: dict[str, str] | None) -> str:
    """A turn's words, and in a group, who said them, each later line of theirs quoted, so
    none of it reads as someone else's turn, or a5s's."""
    if turn.get("speaker") and turn["role"] == "person":
        words = turn["content"].replace("\r", "").replace("\n", "\n> ")
        return f"{(names or {}).get(turn['speaker'], turn['speaker'])}: {words}"
    return turn["content"]


def _kept(conn: db.Connection, person: str, agent: str, topic: str, chars: int,
          members: list[str] | None = None) -> dict:
    """The turns that fit, by id: the conversation's latest, and in a case, its older ones.
    In a group, only the turns all of `members` heard."""
    heard = "" if members is None else " and heard_by @> %(members)s::text[]"
    given = {"person": person, "agent": agent, "members": members, "topic": topic}
    kept, used = _fit(conn.execute(  # never another task's own topic (core/tasking.py)
        "select id, role, content, at, topic, speaker from turns where person = %(person)s "
        f"and agent = %(agent)s{heard} and (topic = %(topic)s or topic not like 'task %%') "
        "order by id desc limit 500", given),
        chars if topic == GENERAL else int(chars * LATEST))
    if topic != GENERAL:
        before = min(kept) if kept else None
        older, _ = _fit(conn.execute(
            "select id, role, content, at, topic, speaker from turns where person = %(person)s "
            f"and agent = %(agent)s and topic = %(topic)s{heard} and (%(before)s::bigint is null "
            "or id < %(before)s) order by id desc limit 500", {**given, "before": before}),
            chars - used, keep_one=False)
        kept |= older
    return kept


def _fit(rows, chars: int, *, keep_one: bool = True) -> tuple[dict, int]:
    """The newest turns that fit, by id, and the characters they take. The newest is kept
    even if it doesn't fit, unless `keep_one` is off."""
    kept, used = {}, 0
    for row in rows:
        if used + len(row["content"]) > chars and (kept or not keep_one):
            break
        used += len(row["content"])
        kept[row["id"]] = row
    return kept, used
