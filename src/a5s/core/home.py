"""The studio's home (docs/studio.md#people-roles-and-spaces): what waits for whoever signed
in, and each role they hold, what gave it them, the directory or a group of the identity
provider's, and what it lets them do. Anyone the directory knows sees their own, whether or
not they hold a role. It shows; it changes nothing: each thing waiting is done where it always
is, on its own page, or at the command line.
"""

from __future__ import annotations

from typing import Any

from a5s import db
from a5s.contract import (
    ASSURANCE,
    DATA_PROTECTION,
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    RELEASE_APPROVER,
    Person,
    parse_settings,
)
from a5s.core import administration, approvals, audit, memberships, registry, releases, samples
from a5s.core.tasks import OFFERED

MOST = 20  # samples counted to grade, beyond which the home says "20 or more"

# What each role lets someone do, by its kind; {scope} is its part or agent
MAY = {
    PART_OWNER: "approve the instances that work in {scope}, and how far each may act there; "
                "decide the changes agents ask for there; watch those instances' runs",
    PART_DELEGATE: "decide the changes agents ask for in {scope}, beside its owner",
    "agent-owner": "own the {scope}: its definition and releases, drafts of it, and its "
                   "instances' runs; start new agents; suspend it",
    "agent-author": "draft changes to the {scope}, try them in the sandbox, and publish them for "
                    "its owners to sign",
    releases.ENGINEER: "start new agents, and draft them",
    INSTANCE_APPROVER: "approve the instances that work in no part, and set their levels",
    RELEASE_APPROVER: "approve releases, from outside the team that runs a5s",
    samples.GRADER: "grade agents' work, never your own team's",
    audit.AUDITOR: "read the ledger: find what was done and decided, and export it",
    ASSURANCE: "hold the ledger's locked copies, test releases, and read the ledger",
    DATA_PROTECTION: "export or erase what a5s keeps about one person, one request at a time",
}
TEAM = "the team that runs a5s"
TEAM_MAY = ("run it, and make it safer alone: suspend an instance, lower a cap or withdraw a "
            "release, never loosen it; sign its releases as an engineer")


def may(role: str) -> str:
    """What a role lets someone do, in words."""
    kind, _, scope = role.partition(":")
    words = MAY.get(kind) or MAY.get(role)
    return words.format(scope=scope) if words else "what the scenario gives it"


def roles(conn: db.Connection, gw: Any, person: Person) -> list[dict]:
    """Each role someone holds, what gave it them, and what it lets them do: the team that
    runs a5s first, if they're in it."""
    found = [{"role": h["role"], "by": by, "may": may(h["role"])}
             for h in administration.held(gw.scenario, conn, list(person.roles))
             for by in [next((x["by"] for x in h["held_by"] if x["id"] == person.id), None)]
             if by]
    if person.team == gw.cfg.team:
        found.insert(0, {"role": TEAM, "by": ["the directory"], "may": TEAM_MAY})
    return found


def waiting(conn: db.Connection, gw: Any, person: Person) -> list[dict]:
    """What waits for someone: each with what it is, why it's theirs, and where they do it, a
    page of a5s's, or the command line."""
    found: list[dict] = []
    scenario = gw.scenario
    rooted = memberships.rooted(scenario)
    own = rooted.person(person.id)
    last = approvals.latest(conn, scenario.name)
    before = parse_settings(bytes(last["raw"])) if last else None
    for row in conn.execute("select serial, digest, raw from settings_proposals where scenario = %s "
                            "and outcome is null and serial > %s order by serial",
                            (scenario.name, last["serial"] if last else -1)):
        settings = parse_settings(bytes(row["raw"]))
        valid, _ = registry.signers(settings, scenario.person,
                                    approvals.recorded(conn, scenario.name, row["digest"]))
        if person.id in valid:
            continue
        why = [w for role, w, directory_alone in registry.needed(
                   settings, scenario.person, valid, before, rooted.person)
               if role in (own.roles if directory_alone and own else
                           () if directory_alone else person.roles)]
        if why:
            found.append({"kind": "settings", "what": f"Version {row['serial']} of the settings "
                          "waits for your approval", "why": list(dict.fromkeys(why)),
                          "go": "/settings/"})
    held = conn.execute("select count(*) as n from proposals where status = 'waiting' "
                        "and %s = any(deciders)", (person.id,)).fetchone()["n"]
    if held:
        found.append({"kind": "decide", "what": f"{held} {'change' if held == 1 else 'changes'} "
                      f"an agent asked for {'waits' if held == 1 else 'wait'} for your decision",
                      "why": [], "go": "/decide/"})
    if samples.GRADER in person.roles and (
            graded := len(samples.gradeable(conn, scenario, person, MOST + 1))):
        count = f"{MOST} or more" if graded > MOST else str(graded)
        found.append({"kind": "grade", "what": f"{count} {'sample' if graded == 1 else 'samples'} "
                      f"of agents' work {'waits' if graded == 1 else 'wait'} for your grade",
                      "why": [], "go": "/grade/"})
    running = (gw.releases.current if gw.releases is not None and not gw.cfg.development
               else None)
    for need in releases.awaiting(conn, running, scenario, gw.cfg.team, person):
        found.append({"kind": "release", "what": f"Release {running.version} of a5s waits for "
                      f"your signature, as {releases.who(need.role)}", "why": [need.why],
                      "go": None, "how": "a5s release sign"})
    tasks = conn.execute("select count(*) as n from tasks where owner = %s and parent is null "
                         "and status in ('blocked', %s)", (person.id, OFFERED)).fetchone()["n"]
    if tasks:
        found.append({"kind": "tasks", "what": f"{tasks} of your tasks "
                      f"{'waits' if tasks == 1 else 'wait'} for you, blocked or asked for",
                      "why": [], "go": "/tasks/"})
    return found
