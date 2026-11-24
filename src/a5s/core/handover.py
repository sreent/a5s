"""Handing a conversation over to people (docs/agent-model.md#handing-a-conversation-over). An
instance's settings name the directory's teams it may hand a conversation to (`hands_to`), such
as the service desk, which the owners of its parts approve, as they approve whom it may ask. Its
agent, where its release lets it (`context.handover`), hands one over with hand_over, in answer
to the person's own message, in their own chat, with a short brief of what they need.

- The core keeps the brief and what the person said lately, their own words alone, never the
  agent's, which the records behind them may not be the team's to see: the channels app reads
  no conversation. The person is told, in their chat, who takes it from there and what they see.
- While it's handed over, the agent answers nothing in that chat: what the person writes waits
  for the team, who find it on their home and on the studio's page of conversations handed to
  them. One of them takes it, and answers in the studio; the core puts each answer in the
  person's chat, as the agent's bot, with their name, and keeps it, and what the person said,
  in the conversation, so the agent knows it all once the conversation is handed back.
- Whoever took it hands it back, or anyone of the team does, and the agent answers again. One
  nobody has answered or handed back in three days lapses, and is handed back.
- What anyone of the team reads names only the records they may see: a record's key they may
  not see reads as such.

The ledger records each handover and its end, and each answer's delivery, never the words.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import Person, Scenario
from a5s.core import languages, studio
from a5s.core.coretools import Call, CoreTool, Refused, one_to_one
from a5s.core.words import say

HAND = "hand_over"
LATELY = 10  # of the person's own messages the team reads, the latest [starting value]
QUIET = timedelta(days=1)  # a gap this long ends what the team reads of them, as a new talk [starting value]
BRIEF = 600  # characters of an agent's brief, at most
REPLY = 4000  # characters of an answer from the team, at most
LAPSE = timedelta(days=3)  # a handover nobody answers or hands back is handed back [starting value]
HIDDEN = "[a record you may not see]"
# A brief the agent wrote from records someone of the team may not see, in its place: a brief may
# say what a record holds without naming it, so it's theirs to read only if the run is
WITHHELD = ("[the agent's brief, which draws on records you may not see: read what they've said "
            "instead]")


def team_of(scenario: Scenario, person: Person, team: str) -> bool:
    """Whether someone is in a team, as the directory says now."""
    return any(p.id == person.id for p in scenario.team(team))


def _hand(call: Call) -> dict:
    person = call.person  # a message of theirs, in their own chat, from a run that read nothing
    # from outside: whom the conversation goes to is theirs to have asked for
    team = str(call.args.get("team") or "").strip()
    teams = list(call.run.get("hands_to") or [])
    if team not in teams:
        raise Refused(f"this agent hands conversations to {', '.join(teams)} alone" if teams
                      else "this agent hands conversations to nobody here")
    if not call.scenario.team(team):
        raise Refused(f"nobody in the directory is in the {team} team now")
    agent = call.run["definition"]
    if call.conn.execute("select 1 from handovers where person = %s and agent = %s and "
                         "ended_at is null", (person.id, agent)).fetchone():
        raise Refused("this conversation is handed over already: its people answer it until they "
                      "hand it back")
    brief = " ".join(str(call.args.get("brief") or "").split())[:BRIEF]
    if not brief:
        raise Refused("say in a brief what they need, for whoever takes it")
    said, after = [], call.asked_at  # this talk's, back to the last quiet day: never older
    for r in call.conn.execute(  # words of theirs, whatever they were about
            "select content, at from turns where person = %s and agent = %s and role = 'person' "
            "and speaker is null order by id desc limit %s", (person.id, agent, LATELY)):
        if after - r["at"] > QUIET:
            break
        said.append({"at": r["at"].isoformat(), "text": r["content"]})
        after = r["at"]
    said.reverse()
    asked = call.said  # the message it answers, if it isn't a turn yet
    if asked and (not said or said[-1]["text"] != asked):
        said = [*said, {"at": call.asked_at.isoformat(), "text": asked}][-LATELY:]
    row = call.conn.execute(
        "insert into handovers (person, agent, instance_id, run_id, team, brief, said) values "
        "(%s, %s, %s, %s, %s, %s, %s) returning id",
        (person.id, agent, call.run["id"], call.run["run"], team, brief, Jsonb(said))).fetchone()
    return {"handed_over": True, "team": team, "handover": row["id"] if row else None,
            "say": (f"Tell them the {team} team takes it from here, in this chat: they read your "
                    "brief and what they've said to you since they last left it a day or more, "
                    "and you answer again once they hand it back.")}


TOOL = CoreTool(
    name=HAND,
    description=("Hand this conversation to the people of a team your settings name, such as "
                 "the service desk, with a short brief of what the person needs: they answer "
                 "the person here, in this chat, until they hand it back to you. Use it when "
                 "the person asks for a person, or needs what only people there can do, and say "
                 "so to them first."),
    schema={"type": "object", "required": ["team", "brief"], "properties": {
        "team": {"type": "string", "description": "the team, as your settings name it"},
        "brief": {"type": "string", "maxLength": BRIEF,
                  "description": "what they need, in a few sentences, for whoever takes it"}}},
    run=_hand, text_fields=("brief",), plain=("team",),
    offered=lambda run: one_to_one(run) and bool(run.get("hands_to")))
TOOLS = {HAND: TOOL}


def masked(scenario: Scenario, viewer: str, text: str,
           language: str = languages.ENGLISH) -> str:
    """Text as someone of the team reads it: each record's key they may not see, as such, in
    the language they read."""
    pattern = getattr(scenario, "record_pattern", None)
    if not pattern:
        return text
    hidden = say(language, HIDDEN)
    return re.sub(pattern, lambda m: m.group(0) if scenario.sees(viewer, m.group(0)) else hidden,
                  text)


# The studio's page of conversations handed to someone's teams, in the channels app

def waiting(conn: db.Connection, scenario: Scenario, person: Person) -> list[dict]:
    """The conversations handed over to the teams someone is in, still open, oldest first."""
    rows = [r for r in conn.execute("select * from handovers where ended_at is null order by "
                                    "started_at").fetchall()
            if r["person"] != person.id and team_of(scenario, person, r["team"])]
    briefed = _briefed(conn, scenario, person, rows)
    return [_line(conn, scenario, person, r, briefed) for r in rows]


def _briefed(conn: db.Connection, scenario: Scenario, viewer: Person, rows: list[dict]) -> set[str]:
    """The runs that handed these over whose briefs someone may read: those whose every record
    they may see, as the studio shows a run (core/studio.py)."""
    return studio.seeable(conn, scenario, viewer, [str(r["run_id"]) for r in rows if r["run_id"]])


def _name(scenario: Scenario, who: str | None) -> str | None:
    found = scenario.person(who) if who else None
    return found.name if found else who


def _since(conn: db.Connection, row: dict) -> list[dict]:
    """What the person has written in their own chat with the agent since it was handed over."""
    return conn.execute("select id::text as id, text, received_at, answered_at from inbound "
                        "where person = %s and agent = %s and conversation is null and "
                        "received_at > %s order by received_at",
                        (row["person"], row["agent"], row["started_at"])).fetchall()


def _line(conn: db.Connection, scenario: Scenario, viewer: Person, row: dict,
          briefed: set[str]) -> dict:
    waiting_ = [m for m in _since(conn, row) if m["answered_at"] is None]
    language = languages.of(viewer)  # the words a5s puts in, in theirs
    return {"id": row["id"], "person": _name(scenario, row["person"]) or row["person"],
            "agent": row["agent"], "team": row["team"],
            "brief": masked(scenario, viewer.id, row["brief"], language)
            if row["run_id"] and str(row["run_id"]) in briefed else say(language, WITHHELD),
            "started_at": row["started_at"].isoformat(),
            "taken_by": _name(scenario, row["taken_by"]), "mine": row["taken_by"] == viewer.id,
            "unanswered": len(waiting_)}


def one(conn: db.Connection, scenario: Scenario, viewer: Person, handover: int) -> dict | None:
    """A conversation handed over, as someone of its team reads it: the brief, what the person
    said before and since, and the team's answers, each record they may not see as such. None
    for anyone else."""
    row = conn.execute("select * from handovers where id = %s", (handover,)).fetchone()
    if row is None or row["person"] == viewer.id or not team_of(scenario, viewer, row["team"]):
        return None
    replies = conn.execute("select by_person, text, at, sent_at from handover_replies where "
                           "handover_id = %s order by id", (handover,)).fetchall()
    language = languages.of(viewer)
    return {**_line(conn, scenario, viewer, row, _briefed(conn, scenario, viewer, [row])),
            "said": [{"at": s["at"], "text": masked(scenario, viewer.id, s["text"], language)}
                     for s in row["said"]],
            "since": [{"at": m["received_at"].isoformat(),
                       "text": masked(scenario, viewer.id, m["text"], language),
                       "answered": m["answered_at"] is not None} for m in _since(conn, row)],
            "answers": [{"by": _name(scenario, r["by_person"]) or r["by_person"],
                         "text": masked(scenario, viewer.id, r["text"], language),
                         "at": r["at"].isoformat(),
                         "sent": r["sent_at"] is not None} for r in replies],
            "ended": row["ended_at"] is not None}


def _open(conn: db.Connection, scenario: Scenario, viewer: Person, handover: int) -> dict:
    row = conn.execute("select * from handovers where id = %s for update", (handover,)).fetchone()
    if row is None or row["person"] == viewer.id or not team_of(scenario, viewer, row["team"]):
        raise LookupError(handover)
    if row["ended_at"] is not None:
        raise Refused("it's been handed back to the agent")
    return row


def take(conn: db.Connection, scenario: Scenario, viewer: Person, handover: int) -> None:
    """Take a conversation handed to one's team, to answer it: one of the team at a time."""
    row = _open(conn, scenario, viewer, handover)
    if row["taken_by"] not in (None, viewer.id):
        raise Refused(f"{_name(scenario, row['taken_by'])} has taken it")
    conn.execute("update handovers set taken_by = %s, taken_at = now() where id = %s",
                 (viewer.id, handover))


def answer(conn: db.Connection, scenario: Scenario, viewer: Person, handover: int,
           text: str) -> None:
    """Answer the person, as whoever took it, for the core to put in their chat."""
    row = _open(conn, scenario, viewer, handover)
    if row["taken_by"] != viewer.id:
        raise Refused("take it first, so the person hears from one of you at a time")
    said = text.strip()[:REPLY]
    if not said:
        raise Refused("say something to them")
    conn.execute("insert into handover_replies (handover_id, by_person, text) values (%s, %s, %s)",
                 (handover, viewer.id, said))


def back(conn: db.Connection, scenario: Scenario, viewer: Person, handover: int) -> None:
    """Hand it back to the agent, as anyone of the team may, which answers the person again."""
    _open(conn, scenario, viewer, handover)
    conn.execute("update handovers set ended_at = now(), ended_by = %s where id = %s",
                 (viewer.id, handover))


def teams_handed_to(conn: db.Connection) -> set[str]:
    """The teams any instance at work may hand a conversation to."""
    return {r["team"] for r in conn.execute(
        "select distinct unnest(hands_to) as team from instances where status <> 'retired'")}


def answers_any(conn: db.Connection, scenario: Scenario, person: Person) -> bool:
    """Whether someone is in a team an instance may hand conversations to: the page is theirs."""
    return any(team_of(scenario, person, t) for t in teams_handed_to(conn))


def steered(conn: db.Connection, person: str, agent: str) -> list[str]:
    """Who of a team answered someone, while their conversation with an agent was handed over,
    among the turns a run of it is given: whose words may have asked for what it asks for, so
    they decide none of it, as nobody decides what their own words in a group chat asked for."""
    return sorted({r["speaker"] for r in conn.execute(
        "select speaker from (select speaker, role from turns where person = %s and agent = %s "
        "order by id desc limit 500) t where role = 'person' and speaker is not null",
        (person, agent))})


def open_for(conn: db.Connection, person: str, agent: str) -> dict | None:
    return conn.execute("select * from handovers where person = %s and agent = %s and "
                        "ended_at is null", (person, agent)).fetchone()


def lapsing(conn: db.Connection) -> list[dict]:
    """In the core: open handovers nobody has answered or handed back for LAPSE, ended."""
    return conn.execute(
        "update handovers h set ended_at = now() where ended_at is null and greatest(started_at, "
        "coalesce((select max(at) from handover_replies r where r.handover_id = h.id), started_at)) "
        "< now() - %s returning *", (LAPSE,)).fetchall()


TO = ("The {agent} has handed this conversation to the {team} team, at your word: someone there "
      "answers you here. They read its brief, and what you've said to it since you last left it "
      "a day or more, but not its answers nor anything older. The {agent} answers again once "
      "they hand it back.")
BACK = ("The {team} team has handed this conversation back to the {agent}, which answers you "
        "again from here.")


def words(row: dict, scenario: Any, language: str = languages.ENGLISH) -> dict[str, str]:
    """What the person is told when it's handed over, and back, in the language they read."""
    return {"to": say(language, TO, agent=row["agent"], team=row["team"]),
            "back": say(language, BACK, agent=row["agent"], team=row["team"])}
