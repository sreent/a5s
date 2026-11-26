"""The administrators' page (docs/administration.md, step 3): who holds each of a5s's roles,
and by what, the directory or a group of the identity provider's; what waits for whom, such as
versions of the settings, the release and held changes; and the latest administrative acts,
from the audit trail, with whom an act was about as a stand-in until the data protection
officer agrees to names. It only shows: the settings app and the command line change.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
from a5s.core import approvals, audit, languages, memberships, proposals, registry, studio, words
from a5s.core.releases import agent_owner

LATEST = 20  # administrative acts the page shows, newest first
DAYS = 30  # over how many days
_ADMINISTERS = (INSTANCE_APPROVER, RELEASE_APPROVER, ASSURANCE, DATA_PROTECTION, audit.AUDITOR)


# Each role's name, as people say it; {scope} is its part or agent, and a role with neither is
# named by its words, such as "Data protection officer" for data-protection-officer
SCOPED = {PART_OWNER: "Owner of {scope}", PART_DELEGATE: "Delegate in {scope}",
          "agent-owner": "Owner of the {scope}", "agent-author": "Author of the {scope}",
          "agent-viewer": "Viewer of the {scope}"}


def named(role: str, language: str = "en") -> str:
    """A role's name, in words, in the language someone reads: its id stays beside it where
    groups are given it."""
    kind, _, scope = role.partition(":")
    if scope and kind in SCOPED:
        return words.say(language, SCOPED[kind], scope=scope)
    return words.say(language, role.replace("-", " ").capitalize())


# Whom the administrators' page is for, as its refusal says it (round 17, C6): not graders,
# authors or viewers alone, though they hold a role (docs/administration.md)
AUDIENCE = ("those who own, approve, decide or oversee in a5s, and the team that runs it: part "
            "owners and their delegates, agents' owners, instance and release approvers, "
            "assurance, auditors and the data protection officer")


def administers(person: Person | None, team: str) -> bool:
    """Whether someone may see the page: they're of its `AUDIENCE`."""
    return person is not None and (person.team == team or any(
        r in _ADMINISTERS or r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:", "agent-owner:"))
        for r in person.roles))


def held(scenario: Any, conn: db.Connection, roles: list[str],
         language: str = languages.ENGLISH) -> list[dict[str, Any]]:
    """Who holds each role, and by what: the directory, or a group, as their latest sign-in
    showed it and the settings in force map it, in the language someone reads."""
    own = memberships.rooted(scenario)
    state = getattr(scenario, "_a5s_roles", None)
    if state is not None:
        scenario.fresh(conn)
    mapping = state.mapping if state is not None else {}
    kept = memberships.stored(conn) if mapping else {}
    found = []
    for role in roles:
        holders = {p.id: {"id": p.id, "name": p.name, "by": [words.say(language, "the directory")]}
                   for p in own.holders(role)}
        for pid, groups in sorted(kept.items()):
            for group in groups:
                if role in mapping.get(group, ()) and (p := own.person(pid)) is not None:
                    holders.setdefault(pid, {"id": pid, "name": p.name, "by": []})["by"].append(
                        words.say(language, "group {group}", group=group))
        found.append({"role": role, "held_by": sorted(holders.values(), key=lambda h: h["id"])})
    return found


def mapped(scenario: Any) -> list[dict[str, Any]]:
    """The groups the settings in force give roles, and how many people's latest sign-ins
    showed each."""
    state = getattr(scenario, "_a5s_roles", None)
    if state is None:
        return []
    return [{"group": group, "roles": list(roles),
             "people": sum(group in groups for groups in state.groups.values())}
            for group, roles in sorted(state.mapping.items())]


def waiting(conn: db.Connection, gw: Any) -> dict[str, Any]:
    """What waits for whom: versions of the settings, for their approvers; the release, for
    the people its changes need; and held changes, for each part's deciders, by how many."""
    last = approvals.latest(conn, gw.scenario.name)
    before = parse_settings(bytes(last["raw"])) if last else None
    versions = []
    for row in conn.execute("select serial, digest, raw from settings_proposals where scenario = %s "
                            "and outcome is null and serial > %s order by serial",
                            (gw.scenario.name, last["serial"] if last else -1)):
        settings = parse_settings(bytes(row["raw"]))
        approved = approvals.recorded(conn, gw.scenario.name, row["digest"])
        valid, _ = registry.signers(settings, gw.scenario.person, approved)
        versions.append({"serial": row["serial"], "approved_by": valid,
                         "needs": registry.missing(settings, gw.scenario.person, valid, before,
                                                   memberships.rooted(gw.scenario).person)})
    by_part: dict[str, dict[str, Any]] = {}  # who may decide each now, as the directory stands
    for held_change in conn.execute("select parts, records, acts_for, steered_by from "
                                    "proposals where status = 'waiting'"):
        who = {p.id for p in proposals.everyone(proposals.deciders(
            gw.scenario, list(held_change["records"]), proposals.not_deciding(held_change)))}
        for part in held_change["parts"]:
            found = by_part.setdefault(part, {"n": 0, "deciders": set()})
            found["n"] += 1
            found["deciders"] |= who
    changes = [{"part": part, "waiting": found["n"], "deciders": sorted(found["deciders"])}
               for part, found in sorted(by_part.items())]
    return {"settings": versions, "release": gw.release_problems(conn), "held_changes": changes}


def ownerless(conn: db.Connection, gw: Any) -> dict[str, list[dict[str, Any]]]:
    """What nobody answers for any more, so the work its owner does waits, with what to do about
    each: every agent of the release nobody the directory names owns; every instance not retired
    that names nobody to run it, or someone the directory no longer knows; and every part an
    instance works in that nobody owns, so nobody approves its instances' settings."""
    scenario = gw.scenario
    names = sorted(gw.definitions)
    agents = [{"agent": name, "what": "nobody the directory names owns it, so nobody signs its "
                                      "releases as its owner, gives a group its roles, or "
                                      "answers the asks for it",
               "do": "name its owner in the directory, in a release, or retire it"}
              for name, row in zip(names, held(scenario, conn, [agent_owner(n) for n in names]),
                                   strict=True) if not row["held_by"]]
    insts = conn.execute("select id, definition, owner, deputy, parts from instances "
                         "where status <> 'retired' order by id").fetchall()
    instances = []
    for inst in insts:
        gone = [who for who in (inst["owner"], inst["deputy"])
                if who and scenario.person(who) is None]
        if inst["owner"] is None or gone:
            instances.append({
                "instance": inst["id"], "agent": inst["definition"],
                "what": (f"the directory no longer knows {', '.join(gone)}, who "
                         f"{'run' if len(gone) > 1 else 'runs'} it") if gone
                        else "it names nobody to run it",
                "do": "a version of the settings naming whoever runs it now"})
    used = sorted({part for i in insts for part in (i["parts"] or {})})
    parts = [{"part": part, "what": "nobody the directory names owns it, so nobody approves its "
                                    "instances' settings, and its held changes wait for its "
                                    "delegates alone",
              "do": "name its owner in the directory, in a release"}
             for part, row in zip(used, held(scenario, conn, [f"{PART_OWNER}:{p}" for p in used]),
                                  strict=True) if not row["held_by"]]
    return {"agents": agents, "instances": instances, "parts": parts}


def _seen(act: dict, conn: db.Connection, known: set[str], viewer: Person | None) -> dict | None:
    """An act as the viewer may see it: none of an agent they may not know of, an act on an
    instance by its agent as much as one naming it; and what it did to an instance, such as a
    grade, the settings applied or who suspended it, only for those who may watch it (round 13,
    B1). Without a viewer, the whole of it."""
    about, instance = act["about"] or {}, act.get("instance")
    inst = conn.execute("select id, definition, owner, deputy, parts from instances where id = %s",
                        (instance,)).fetchone() if instance else None
    agent = about.get("agent") or (inst["definition"] if inst else None)
    if agent is not None and agent not in known:
        return None
    if instance and viewer is not None and (inst is None or not studio.watches(inst, viewer)):
        return {**act, "about": {}}  # that it happened, not what it did
    return act


def page(conn: db.Connection, gw: Any, now: datetime, days: int = DAYS,
         viewer: Person | None = None) -> dict[str, Any]:
    """All the page shows: to a viewer, only of the agents they may know of (core/studio.py's
    layers), so an unlisted agent's role, a new agent's draft and who asked for which agent stay
    with those who may know of them."""
    known = set(gw.definitions)
    if viewer is not None:
        every = studio.instances(conn)
        known = {name for name, d in gw.definitions.items()
                 if studio.layers(name, d, every, viewer, gw.scenario)}
    parts = [r["part"] for r in conn.execute(
        "select distinct jsonb_object_keys(parts) as part from instances")]
    roles = [row["role"] for row in audit.roles_of(gw.scenario, parts, sorted(known))]
    report = audit.report(conn, gw.scenario, sorted(known), since=now - timedelta(days=days))
    acts = [a for a in (_seen(a, conn, known, viewer) for a in report["acts"]) if a is not None]
    shown = audit.Shown(gw.scenario, audit.key(conn), names=gw.data_protection(conn).audit_names,
                        left=audit.left(conn))
    gone = ownerless(conn, gw)
    gone = {**gone, "agents": [a for a in gone["agents"] if a["agent"] in known],
            "instances": [i for i in gone["instances"] if i["agent"] in known]}
    return {"roles": [{**row, "name": named(row["role"])} for row in held(gw.scenario, conn, roles)],
            "groups": mapped(gw.scenario),
            "claim": gw.identity.cfg.groups_claim if gw.identity else None,
            "waiting": waiting(conn, gw), "ownerless": gone, "days": days,
            "latest": shown.report({"acts": acts[-LATEST:][::-1]})["acts"]}
