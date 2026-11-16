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
from a5s.core import (
    administration,
    approvals,
    asks,
    audit,
    memberships,
    notebook,
    proposals,
    registry,
    releases,
    samples,
    studio,
)
from a5s.core.tasks import OFFERED

MOST = 20  # samples counted to grade, beyond which the home says "20 or more"

# What each role lets someone do, by its kind; {scope} is its part or agent
MAY = {
    PART_OWNER: "approve the instances that work in {scope}, and how far each may act there; "
                "decide the changes agents ask for there; watch those instances' runs",
    PART_DELEGATE: "decide the changes agents ask for in {scope}, beside its owner",
    "agent-owner": "own the {scope}: its definition and releases, drafts of it, and its "
                   "instances' runs; start new agents; suspend it; and give a group its "
                   "authors' or viewers' role",
    "agent-author": "draft changes to the {scope}, try them in the sandbox, and publish them for "
                    "its owners to sign",
    "agent-viewer": "see how the {scope} is built, read only: its instructions and skills",
    releases.ENGINEER: "start new agents, and draft them",
    INSTANCE_APPROVER: "approve the instances that work in no part, and set their levels",
    RELEASE_APPROVER: "approve releases, from outside the team that runs a5s",
    samples.GRADER: "grade agents' work, never your own team's",
    audit.AUDITOR: "read the ledger: find what was done and decided, and export it",
    ASSURANCE: "hold the ledger's locked copies, test releases, and read the ledger; where the "
               "directory names you, give a group the auditor's role",
    DATA_PROTECTION: "export or erase what a5s keeps about one person, one request at a time; "
                     "where the directory names you, approve the settings' choices for people's "
                     "data: how long a5s keeps it, and whom it names; and give a group "
                     "your role",
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
    found = [{"role": h["role"], "name": administration.named(h["role"]), "by": by, "may": may(h["role"])}
             for h in administration.held(gw.scenario, conn, list(person.roles))
             for by in [next((x["by"] for x in h["held_by"] if x["id"] == person.id), None)]
             if by]
    if person.team == gw.cfg.team:
        found.insert(0, {"role": TEAM, "name": "The team that runs a5s", "by": ["the directory"],
                         "may": TEAM_MAY})
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
                          "go": f"/studio/approve?settings={row['digest']}"})  # its own page
    held = sum(1 for p in conn.execute("select records, acts_for from proposals "
                                       "where status = 'waiting'")
               if proposals.may_decide(scenario, p, person.id))  # as the directory stands now
    if held:
        found.append({"kind": "decide", "what": f"{held} {'change' if held == 1 else 'changes'} "
                      f"an agent asked for {'waits' if held == 1 else 'wait'} for your decision",
                      "why": [], "go": "/studio/decide"})
    if samples.GRADER in person.roles and (
            graded := len(samples.gradeable(conn, scenario, person, MOST + 1))):
        count = f"{MOST} or more" if graded > MOST else str(graded)
        found.append({"kind": "grade", "what": f"{count} {'sample' if graded == 1 else 'samples'} "
                      f"of agents' work {'waits' if graded == 1 else 'wait'} for your grade",
                      "why": [], "go": "/studio/grade"})
    running = (gw.releases.current if gw.releases is not None and not gw.cfg.development
               else None)
    for need in releases.awaiting(conn, running, scenario, gw.cfg.team, person):
        found.append({"kind": "release", "what": f"Release {running.version} of a5s waits for "
                      f"your signature, as {releases.who(need.role)}", "why": [need.why],
                      "go": None, "how": "a5s release sign"})
    for ask in asks.waiting(conn, scenario, studio.instances(conn), person):
        found.append({"kind": "ask", "what": f"{ask['person']} asks for the {ask['agent']}",
                      "why": ask["why"], "go": f"/studio/agents/{ask['agent']}"})
    tasks = conn.execute("select count(*) as n from tasks where owner = %s and parent is null "
                         "and status in ('blocked', %s)", (person.id, OFFERED)).fetchone()["n"]
    if tasks:
        found.append({"kind": "tasks", "what": f"{tasks} of your tasks "
                      f"{'waits' if tasks == 1 else 'wait'} for you, blocked or asked for",
                      "why": [], "go": "/studio/tasks"})
    return found


def _changes(n: int) -> str:
    return f"{n} {'change' if n == 1 else 'changes'} it asked for {'waits' if n == 1 else 'wait'}"


def of_instance(conn: db.Connection, gw: Any, person: Person, inst: dict) -> list[dict]:
    """What of one instance waits, for someone who may watch it, each where it's done, as the
    home says: the changes it asked for that wait for their decision, and for others'; its
    samples that wait for their grade, and for others'; and its notebook, if they keep it.
    Counts alone, and the oldest's time: what each is, they see where they may act on it."""
    found: list[dict] = []
    scenario = gw.scenario
    held = conn.execute("select records, acts_for, proposed_at from proposals where status = "
                        "'waiting' and instance_id = %s order by proposed_at, id",
                        (inst["id"],)).fetchall()
    mine = [p for p in held if proposals.may_decide(scenario, p, person.id)]  # the directory now
    others = [p for p in held if p not in mine]
    if mine:
        found.append({"kind": "decide", "what": f"{_changes(len(mine))} for your decision",
                      "why": [], "go": "/studio/decide", "since": mine[0]["proposed_at"]})
    if others:
        found.append({"kind": "held", "what": f"{_changes(len(others))} for someone else's "
                      "decision, as its parts' owners and delegates decide them", "why": [],
                      "go": None, "since": others[0]["proposed_at"]})
    graded = samples.gradeable(conn, scenario, person, MOST + 1, inst["id"]) \
        if samples.GRADER in person.roles else []
    if graded:
        count = f"{MOST} or more" if len(graded) > MOST else str(len(graded))
        found.append({"kind": "grade", "what": f"{count} {'sample' if len(graded) == 1 else 'samples'} "
                      f"of its work {'waits' if len(graded) == 1 else 'wait'} for your grade",
                      "why": [], "go": "/studio/grade", "since": graded[0]["drawn_at"]})
    theirs = {g["id"] for g in graded}
    rest = [r for r in conn.execute("select id, drawn_at from samples where scenario = %s and "
                                    "instance_id = %s and grade is null and lapsed_at is null "
                                    "order by id", (scenario.name, inst["id"]))
            if r["id"] not in theirs]
    if rest and len(graded) <= MOST:  # other graders, outside the team that built it, grade them
        found.append({"kind": "graded", "what": f"{len(rest)} {'sample' if len(rest) == 1 else 'samples'} "
                      f"of its work {'waits' if len(rest) == 1 else 'wait'} for a grade, from "
                      "graders outside the team that built it", "why": [], "go": None,
                      "since": min(r["drawn_at"] for r in rest)})
    if notebook.keeps(person, inst):
        notes = [r for r in conn.execute("select read_records, sources from notebook where "
                                         "instance_id = %s", (inst["id"],))
                 if notebook.readable(scenario, person.id, r)]
        if notes:
            found.append({"kind": "notebook", "what": f"{len(notes)} "
                          f"{'note' if len(notes) == 1 else 'notes'} it keeps from what it "
                          "learned, which you may read and remove", "why": [], "go": "/studio/notebook"})
    return found
