"""Asking for an agent (docs/studio.md#people-roles-and-spaces): someone who knows of an agent,
from the studio's catalogue, and isn't served by it, asks to be.

Only those who approve versions of the settings propose one, so an ask isn't a version: it's a
request to the people who can answer it, who see it waiting on their studio's home. They're the
agent's owners, who know which of its instances fits, and those who approve its instances: the
owners of the parts they work in, and, for one in no part, or none yet, the instance approvers.
One of them answers it with a version of the settings that serves the asker through one of the
agent's instances, which goes to its approvers as any version does (core/settings_app.py), or
declines it. An ask ends once a version in force serves its asker through one of the agent's
instances, or when they withdraw it, one of those it waits on declines it, or nobody has answered
it in LAPSE. The ledger records each ask and how it ended. An ask holds nothing anyone wrote:
who asked, for which agent, when, and how it ended.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from a5s import db
from a5s.contract import INSTANCE_APPROVER, PART_OWNER, Person, Scenario
from a5s.core import ledger, registry
from a5s.core.releases import agent_owner

LAPSE = timedelta(days=30)  # an ask nobody answers [starting value]
SERVING = ("active", "suspended")
COLUMNS = "id, person, agent, asked_at, ended_at, outcome, ended_by"


class Refused(ValueError):
    """Why someone can't ask for an agent, in words."""


def serving(scenario: Scenario, insts: list[dict], agent: str, person: str) -> list[str]:
    """The instances of an agent that serve someone."""
    return [i["id"] for i in insts if i["definition"] == agent and i["status"] in SERVING
            and registry.serving(scenario, i["serves"], person)]


def waits_on(insts: list[dict], agent: str, person: Person) -> list[str]:
    """Why an ask for an agent waits on someone: they own it, own a part one of its instances
    works in, or approve instances, where one is in no part or it has none yet. None if it
    doesn't wait on them."""
    roles, why = set(person.roles), []
    if agent_owner(agent) in roles:
        why.append(f"you own the {agent}")
    mine = [i for i in insts if i["definition"] == agent and i["status"] != "retired"]
    for inst in mine:
        why += [f"you own {part}, where {inst['id']} works" for part in sorted(inst["parts"] or {})
                if f"{PART_OWNER}:{part}" in roles]
    if INSTANCE_APPROVER in roles and (not mine or any(not i["parts"] for i in mine)):
        why.append("you approve instances")
    return list(dict.fromkeys(why))


def theirs(conn: db.Connection, scenario: str, person: str, agent: str) -> dict | None:
    """Someone's open ask for an agent, if they have one."""
    return conn.execute(f"select {COLUMNS} from agent_asks where scenario = %s and person = %s "
                        "and agent = %s and ended_at is null",
                        (scenario, person, agent)).fetchone()


def ask(conn: db.Connection, scenario: Scenario, insts: list[dict], person: Person,
        agent: str) -> dict:
    """Ask for an agent, in the caller's transaction: their open ask, if they have one already.
    Refused if it serves them already."""
    if through := serving(scenario, insts, agent, person.id):
        raise Refused(f"the {agent} serves you already, through {', '.join(through)}")
    if found := theirs(conn, scenario.name, person.id, agent):
        return found
    made = conn.execute(f"insert into agent_asks (id, scenario, person, agent) values "
                        f"(%s, %s, %s, %s) on conflict do nothing returning {COLUMNS}",
                        (uuid.uuid4(), scenario.name, person.id, agent)).fetchone()
    if made is None:  # asked twice at once: the other's stands
        if found := theirs(conn, scenario.name, person.id, agent):
            return found
        raise Refused("you asked for it from elsewhere at the same moment: try again")
    ledger.append(conn, {"kind": "admin", "action": "ask for agent", "run": None,
                         "instance": None, "acts_for": [], "decision": "record",
                         "args": {"agent": agent, "ask": str(made["id"]), "asker": person.id}})
    return made


def end(conn: db.Connection, scenario: str, ask_id: str, outcome: str,
        by: str | None) -> dict | None:
    """End an open ask, in the caller's transaction: how, and by whom, if anyone."""
    try:
        uuid.UUID(ask_id)
    except ValueError:
        return None
    ended = conn.execute(f"update agent_asks set ended_at = now(), outcome = %s, ended_by = %s "
                         f"where id = %s::uuid and scenario = %s and ended_at is null "
                         f"returning {COLUMNS}", (outcome, by, ask_id, scenario)).fetchone()
    if ended:  # whoever answered it acted in a role; the asker, withdrawing it, didn't
        acted = ({"asker": by} if by == ended["person"] else {"by": by}) if by else {}
        ledger.append(conn, {"kind": "admin", "action": f"ask for agent {outcome}", "run": None,
                             "instance": None, "acts_for": [], "decision": "record",
                             "args": {"agent": ended["agent"], "ask": ask_id, **acted}})
    return ended


def settle(conn: db.Connection, scenario: Scenario, insts: list[dict]) -> None:
    """End the asks now served, by the settings in force, and those nobody answered in LAPSE."""
    for row in conn.execute(f"select {COLUMNS}, asked_at < now() - %s::interval as lapsed "
                            "from agent_asks where scenario = %s and ended_at is null "
                            "for update skip locked", (LAPSE, scenario.name)).fetchall():
        if serving(scenario, insts, row["agent"], row["person"]):
            end(conn, scenario.name, str(row["id"]), "served", None)
        elif row["lapsed"]:
            end(conn, scenario.name, str(row["id"]), "lapsed", None)


def waiting(conn: db.Connection, scenario: Scenario, insts: list[dict],
            person: Person) -> list[dict]:
    """The open asks that wait on someone, each with whose it is and why it's theirs."""
    found = []
    for row in conn.execute(f"select {COLUMNS} from agent_asks where scenario = %s and ended_at "
                            "is null order by asked_at", (scenario.name,)):
        if row["person"] != person.id and (why := waits_on(insts, row["agent"], person)):
            asker = scenario.person(row["person"])
            found.append({"id": str(row["id"]), "agent": row["agent"], "asker": row["person"],
                          "person": asker.name if asker else row["person"],
                          "asked_at": row["asked_at"].isoformat(), "why": why})
    return found


def shown(row: dict[str, Any]) -> dict:
    """An ask as its asker sees it: never who declined it."""
    return {"id": str(row["id"]), "agent": row["agent"], "asked_at": row["asked_at"].isoformat(),
            "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
            "outcome": row["outcome"]}
