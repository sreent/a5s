"""Answers people said were wrong: a "that's wrong" on an agent's answer, in any chat, which
the agent's owners grade, right, wrong or critical (docs/studio.md). Changes are graded from
samples; answers, until now, never were.

Someone says it the way their chat has: a 👎 reaction in Slack or Matrix, Teams' own buttons
on the answer, or the web chat's. Only an agent's answer takes it, never a5s's own words, and
only from whom it answered, or someone in the group chat it was said in, once each. Whatever
they write with it is for its owners, and the web chat says so as they write it.

An owner of the agent sees what was said to be wrong, the answer itself, and the run behind
it, only as the studio shows runs: for a run whose every record they may see, and every record
the answer and their words name, and until the data protection officer agrees to names in the
studio, only of an instance that serves as many people as the officer chose, with the names of
whom it answered, whoever said it was wrong and everyone a5s serves masked by code, as emails,
links and long numbers are (core/masking.py), and who said it only once the officer agrees. They
grade it; a grade
changes no level, as a sample's does, but says how the agent's answers stand. It's kept as the
conversation it's in is, 12 months, archived when someone leaves, erased when they ask, and in
their export.
"""

from __future__ import annotations

import hashlib
from typing import Any

from a5s import db
from a5s.contract import DataProtection, Person, Scenario
from a5s.core import languages, ledger, masking, registry, studio, words
from a5s.core.releases import agent_owner

KIND = "feedback"  # in the ledger
SAID_MOST = 1000  # characters of their words a5s keeps
GRADES = ("right", "wrong", "critical")
WRONG = {"slack": frozenset({"-1", "thumbsdown", "x"}),  # Slack's names for 👎 and ❌
         "matrix": frozenset({"👎", "👎️", "❌"})}
NOTED = ("Noted: its owners will see that answer, the run behind it and what you said of it, "
         "to check it, and who you are only if the data protection officer lets them.")
MOST_SHOWN = 100  # of an agent's, those waiting for a grade first, then the newest


def noted(conn: db.Connection, person: Person | None) -> str:
    """What someone's told once a5s has kept what they said, in the language they read."""
    return words.say(languages.of(conn, person), NOTED) if person is not None else NOTED


class Refused(Exception):
    """Why a5s won't take that someone said an answer was wrong."""


def answer(row: dict[str, Any]) -> bool:
    """Whether a message a5s keeps in its outbox is an agent's answer, which people may say is
    wrong: one an agent's run wrote, not a5s's own words, nor a card."""
    return bool(row.get("agent") and row.get("run_id") and not row.get("card"))


def wrong(channel: str, reaction: str) -> bool:
    """Whether a reaction in a chat says an answer was wrong."""
    return reaction.strip().split("::")[0] in WRONG.get(channel, frozenset())


def sent(conn: db.Connection, channel: str, sent_as: str) -> dict | None:
    """What a5s sent, by the chat's own id for it."""
    return conn.execute("select id from outbox where channel = %s and sent_as = %s",
                        (channel, sent_as)).fetchone()


def record(conn: db.Connection, outbox: int, person: str, said: str | None,
           channel: str) -> dict | None:
    """Keep that someone said an agent's answer was wrong, in the caller's transaction, with
    their words, if any, and the ledger's word on it, by their words' hash alone: the row kept,
    or None if they'd said so already. Refused if it isn't an agent's answer to them, nor in a
    chat they were in."""
    row = conn.execute("select o.*, i.members from outbox o left join inbound i "
                       "on i.id = o.inbound_id where o.id = %s", (outbox,)).fetchone()
    if row is None or not answer(row):
        raise Refused("that isn't an agent's answer")
    if person != row["person"] and person not in (row["members"] or []):
        raise Refused("only whom it answered, or someone in the chat it was said in, says so")
    words = " ".join((said or "").split())[:SAID_MOST] or None
    made = conn.execute(
        "insert into answer_feedback (outbox_id, run_id, instance_id, agent, person, said, "
        "channel) values (%s, %s, %s, %s, %s, %s, %s) on conflict (outbox_id, person) do "
        "nothing returning *",
        (outbox, row["run_id"], row["instance_id"], row["agent"], person, words,
         channel)).fetchone()
    if made is None:
        return None
    ledger.append(conn, {
        "kind": KIND, "action": "wrong", "run": str(row["run_id"]),
        "instance": row["instance_id"], "acts_for": [person], "decision": "record",
        "args": {"feedback": made["id"], "outbox": outbox, "channel": channel,
                 **({"chars": len(words), "sha256": hashlib.sha256(words.encode()).hexdigest()}
                    if words else {})}})
    return made


def owns(viewer: Person, agent: str) -> bool:
    """Whether someone grades what people say of an agent's answers: they own it."""
    return agent_owner(agent) in viewer.roles


def _checkable(conn: db.Connection, scenario: Scenario, viewer: Person, rows: list[dict],
               names: bool, fewest: int) -> set[int]:
    """Of these answers people said were wrong, those an owner of their agent may check, as the
    studio shows runs: each whose run's every record they may see, and every record the answer
    and their words name; and until the officer agrees to names, only of an instance serving at
    least `fewest` people, whose runs the studio shows one by one."""
    seen = studio.seeable(conn, scenario, viewer, [str(r["run_id"]) for r in rows if r["run_id"]])
    many: set[str] = set()
    if not names and rows:
        many = {i["id"] for i in conn.execute(
            "select id, serves from instances where id = any(%s)",
            (sorted({r["instance_id"] for r in rows if r["instance_id"]}),)).fetchall()
                if len(registry.served(scenario, i["serves"] or [])) >= fewest}
    return {r["id"] for r in rows if r["run_id"] and str(r["run_id"]) in seen
            and (names or r["instance_id"] in many)
            and all(scenario.sees(viewer.id, k) for k in studio.named(
                scenario, f"{r.get('answer') or ''}\n{r.get('said') or ''}"))}


ROWS = ("select f.*, o.text as answer, r.acts_for from answer_feedback f "
        "join outbox o on o.id = f.outbox_id left join runs r on r.id = f.run_id ")


def shown(conn: db.Connection, scenario: Scenario, viewer: Person, agent: str,
          names: bool = False, fewest: int = DataProtection.fewest_people) -> dict:
    """What people said of an agent's answers that an owner of it may check, those that wait for
    a grade first, then the newest, so none waiting is ever out of sight (round 14):
    each answer they may check (_checkable), with the answer, their words, how it was graded,
    and who said it only if `names`, else with whoever it names masked; how many others; and
    the counts."""
    if not owns(viewer, agent):
        return {"agent": agent, "answers": [], "hidden": 0, "waiting": 0, "graded": {}}
    rows = conn.execute(ROWS + "where f.agent = %s order by (f.grade is null) desc, f.at desc "
                        "limit %s",
                        (agent, MOST_SHOWN)).fetchall()
    checkable = _checkable(conn, scenario, viewer, rows, names, fewest)
    mine = [r for r in rows if r["id"] in checkable]
    everyone = masking.known(conn, scenario) if mine and not names else set()

    def said(r: dict, text: str | None) -> str | None:
        if text is None or names:
            return text
        return masking.mask(text, scenario, [*(r["acts_for"] or []), r["person"], *everyone])[0]

    graded: dict[str, int] = {}
    for r in mine:
        if r["grade"]:
            graded[r["grade"]] = graded.get(r["grade"], 0) + 1
    return {"agent": agent, "hidden": len(rows) - len(mine),
            "waiting": sum(1 for r in mine if r["grade"] is None), "graded": graded,
            "answers": [{
                "id": r["id"], "at": r["at"].isoformat(), "instance": r["instance_id"],
                "run": str(r["run_id"]), "channel": r["channel"], "answer": said(r, r["answer"]),
                "said": said(r, r["said"]), "grade": r["grade"],
                "graded_at": r["graded_at"].isoformat() if r["graded_at"] else None,
                "graded_by": studio.name_of(scenario, r["graded_by"]),
                "by": studio.name_of(scenario, r["person"]) if names else None} for r in mine]}


def grade(conn: db.Connection, scenario: Scenario, viewer: Person, feedback: int,
          given: str, names: bool = False, fewest: int = DataProtection.fewest_people) -> dict:
    """An owner's grade of an answer someone said was wrong, in the caller's transaction, and
    the ledger's word on it; a grade given before is changed. Refused for an answer they may
    not check."""
    if given not in GRADES:
        raise Refused("a grade is right, wrong or critical")
    row = conn.execute(ROWS + "where f.id = %s", (feedback,)).fetchone()
    if row is None or not owns(viewer, row["agent"]) or feedback not in _checkable(
            conn, scenario, viewer, [row], names, fewest):
        raise Refused("there's no such answer for you to check")
    conn.execute("update answer_feedback set grade = %s, graded_by = %s, graded_at = now() "
                 "where id = %s", (given, viewer.id, feedback))
    ledger.append(conn, {"kind": KIND, "action": "grade", "run": str(row["run_id"]),
                         "instance": row["instance_id"], "acts_for": [], "decision": "record",
                         "args": {"feedback": feedback, "grade": given, "by": viewer.id,
                                  **({"before": row["grade"]} if row["grade"] else {})}})
    return {"id": feedback, "grade": given}


def waiting(conn: db.Connection, scenario: Scenario, viewer: Person, agents: list[str],
            names: bool = False, fewest: int = DataProtection.fewest_people) -> dict[str, int]:
    """For each agent someone owns, how many answers people said were wrong wait for them to
    check, of those they may check."""
    found = {}
    for agent in (a for a in agents if owns(viewer, a)):
        rows = conn.execute(ROWS + "where f.agent = %s and f.grade is null and f.run_id is not "
                            "null limit %s", (agent, MOST_SHOWN)).fetchall()
        if n := len(_checkable(conn, scenario, viewer, rows, names, fewest)):
            found[agent] = n
    return found
