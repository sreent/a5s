"""The administrators' page (docs/administration.md, step 3): who holds each of a5s's roles,
and by what, the directory or a group of the identity provider's; what waits for whom, such as
versions of the settings, the release and held changes; and the latest administrative acts,
from the audit trail, with whom an act was about as a stand-in until the data protection
officer agrees to names. It only shows: the settings app and the command line change.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import psycopg

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
from a5s.core import approvals, audit, memberships, registry

LATEST = 20  # administrative acts the page shows, newest first
DAYS = 30  # over how many days
_ADMINISTERS = (INSTANCE_APPROVER, RELEASE_APPROVER, ASSURANCE, DATA_PROTECTION, audit.AUDITOR)


def administers(person: Person | None, team: str) -> bool:
    """Whether someone may see the page: they hold one of a5s's roles, or run a5s."""
    return person is not None and (person.team == team or any(
        r in _ADMINISTERS or r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:", "agent-owner:"))
        for r in person.roles))


def held(scenario: Any, conn: psycopg.Connection, roles: list[str]) -> list[dict[str, Any]]:
    """Who holds each role, and by what: the directory, or a group, as their latest sign-in
    showed it and the settings in force map it."""
    own = memberships.rooted(scenario)
    state = getattr(scenario, "_a5s_roles", None)
    if state is not None:
        scenario.fresh(conn)
    mapping = state.mapping if state is not None else {}
    kept = memberships.stored(conn) if mapping else {}
    found = []
    for role in roles:
        holders = {p.id: {"id": p.id, "name": p.name, "by": ["the directory"]}
                   for p in own.holders(role)}
        for pid, groups in sorted(kept.items()):
            for group in groups:
                if role in mapping.get(group, ()) and (p := own.person(pid)) is not None:
                    holders.setdefault(pid, {"id": pid, "name": p.name, "by": []})["by"].append(
                        f"group {group}")
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


def waiting(conn: psycopg.Connection, gw: Any) -> dict[str, Any]:
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
    changes = [{"part": r["part"], "waiting": r["n"], "deciders": sorted(r["deciders"])}
               for r in conn.execute(
                   "select part, count(*) as n, array(select distinct d from proposals q, "
                   "unnest(q.deciders) d where q.status = 'waiting' and part = any(q.parts)) "
                   "as deciders from proposals p, unnest(p.parts) part "
                   "where p.status = 'waiting' group by part order by part")]
    return {"settings": versions, "release": gw.release_problems(conn), "held_changes": changes}


def page(conn: psycopg.Connection, gw: Any, now: datetime, days: int = DAYS) -> dict[str, Any]:
    """All the page shows."""
    parts = [r["part"] for r in conn.execute(
        "select distinct jsonb_object_keys(parts) as part from instances")]
    roles = [row["role"] for row in audit.roles_of(gw.scenario, parts, gw.definitions.keys())]
    report = audit.report(conn, gw.scenario, gw.definitions.keys(),
                          since=now - timedelta(days=days))
    shown = audit.Shown(gw.scenario, audit.key(conn), names=gw.cfg.audit_names)
    return {"roles": held(gw.scenario, conn, roles), "groups": mapped(gw.scenario),
            "claim": gw.identity.cfg.groups_claim if gw.identity else None,
            "waiting": waiting(conn, gw), "days": days,
            "latest": shown.report({"acts": report["acts"][-LATEST:][::-1]})["acts"]}
