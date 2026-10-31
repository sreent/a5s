"""The register: instances, their releases, grants, levels and status."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import (
    INSTANCE_APPROVER,
    PART_OWNER,
    InstanceSettings,
    Person,
    Settings,
    Tool,
    parse_settings,
)
from a5s.core import ledger, signing
from a5s.definitions import Definition

Directory = Callable[[str], Person | None]
Holders = Callable[[str], list[Person]]


def serving(scenario: Any, serves: Iterable[str], person: str) -> bool:
    """Whether an instance's `serves` takes someone in: by name, or as one of a team or of a
    role's holders, as the directory says now, so a joiner is served without new settings."""
    serves = list(serves)
    if person in serves:
        return True
    who = scenario.person(person)
    return who is not None and any(
        (entry.startswith("team:") and who.team == entry[5:])
        or (entry.startswith("role:") and entry[5:] in who.roles) for entry in serves)


def served(scenario: Any, serves: Iterable[str]) -> list[str]:
    """Everyone an instance serves, by name, as the directory says now."""
    found: set[str] = set()
    for entry in serves:
        if entry.startswith("team:"):
            found |= {p.id for p in scenario.team(entry[5:])}
        elif entry.startswith("role:"):
            found |= {p.id for p in scenario.holders(entry[5:])}
        else:
            found.add(entry)
    return sorted(found)


def approves(person: Person) -> bool:
    """Whether someone approves instances: the owner of a part, or an instance approver."""
    return INSTANCE_APPROVER in person.roles or any(r.startswith(f"{PART_OWNER}:")
                                                    for r in person.roles)


def signers(settings: Settings, directory: Directory,
            approved: Iterable[str] = ()) -> tuple[list[str], list[str]]:
    """Who validly signed this version, with their keys or through the identity provider,
    and what's wrong with any other signature. `approved` are the people whose approvals
    through the identity provider the core sealed (core/approvals.py)."""
    valid, problems = [], []
    for sig in settings.signatures:
        person = directory(sig.signer)
        if person is None:
            problems.append(f"{sig.signer} isn't in the directory")
        elif not approves(person):
            problems.append(f"{sig.signer} approves no instances: they own no part, and don't "
                            f"hold the {INSTANCE_APPROVER} role")
        elif not person.public_key or not signing.verify(person.public_key, settings.raw, sig.value):
            problems.append(f"{sig.signer}'s signature isn't for this version")
        else:
            valid.append(sig.signer)
    for who in approved:
        person = directory(who)
        if person is None:
            problems.append(f"{who}, who approved it, isn't in the directory")
        elif not approves(person):
            problems.append(f"{who}, who approved it, approves no instances")
        elif who not in valid:
            valid.append(who)
    return valid, problems


def _covered(settings: Settings, before: Settings | None) -> list[InstanceSettings]:
    """The instances a version decides on: those it names, and those in force it retires."""
    named = {i.id for i in settings.instances}
    return [*settings.instances, *(i for i in (before.instances if before else ()) if i.id not in named)]


def _classes_change(settings: Settings, before: Settings | None) -> bool:
    """Whether a version sets the scenario's classes of data afresh, which decide which models
    may see what: the first version does, and so does one that changes them."""
    return before is None or ((settings.data_class, settings.classified)
                              != (before.data_class, before.classified))


def missing(settings: Settings, directory: Directory, valid: Iterable[str],
            before: Settings | None = None) -> list[str]:
    """Whose approval a version still needs, given who validly approved it: for each part an
    instance works in, its owner's, and an instance approver's for any instance in no part,
    and for the scenario's classes of data, if it sets them afresh. `before` is the version
    before it, whose instances a version that leaves them out retires, so their approvers
    decide that too."""
    held = {role for who in valid if (p := directory(who)) for role in p.roles}
    if not held:
        return ["nobody who approves instances has approved it"]
    covered = _covered(settings, before)
    needs = [f"the owner of {part} hasn't approved it"
             for part in sorted({p for i in covered for p in i.parts})
             if f"{PART_OWNER}:{part}" not in held]
    if INSTANCE_APPROVER not in held:
        if any(not i.parts for i in covered):
            needs.append(f"no {INSTANCE_APPROVER} has approved it, for the instances in no part")
        if _classes_change(settings, before):
            needs.append(f"no {INSTANCE_APPROVER} has approved its classes of data")
    return needs


def approvers(settings: Settings, holders: Holders, before: Settings | None = None) -> list[Person]:
    """The people whose approval a version needs: each part's owners, and the instance
    approvers, if any instance it decides on is in no part, or it sets the classes of data
    afresh."""
    covered = _covered(settings, before)
    roles = [f"{PART_OWNER}:{p}" for p in sorted({p for i in covered for p in i.parts})]
    if any(not i.parts for i in covered) or _classes_change(settings, before):
        roles.append(INSTANCE_APPROVER)
    found: dict[str, Person] = {}
    for role in roles:
        found.update({p.id: p for p in holders(role) if p.id not in found})
    return list(found.values())


def levels(instance: InstanceSettings, release: Definition) -> tuple[int, dict[str, int]]:
    """How far an instance may act: its level, and its level in each of its parts, each
    within its release's maximum. With parts, its level is the lowest of theirs."""
    start, most = release.autonomy.start, release.autonomy.max
    parts = {p: instance.level_in(p, start, most) for p in sorted(instance.parts)}
    level = min(start if instance.level is None else instance.level, most)
    return (min(parts.values()) if parts else level), parts


@dataclass
class Applied:
    instances: list[str] = field(default_factory=list)
    signers: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)  # why this version doesn't count


def apply(
    conn: psycopg.Connection,
    definitions: dict[str, Definition],
    settings: Settings,
    tools: dict[str, Tool],
    directory: Directory,
    scenario: str,
    approved: Iterable[str] = (),
) -> Applied:
    """Bring instances in line with a signed version of the settings and the current releases.

    An unsigned version doesn't count, and neither does one older than the
    version in force. An instance the version leaves out is retired, and one it
    brings back is restored. Otherwise an instance's status is the core's own
    data, so applying settings never resumes a suspended instance. `approved` are
    the people whose approvals of it through the identity provider the core sealed.
    """
    last = conn.execute(
        "select serial, version, raw from settings_versions where scenario = %s "
        "order by serial desc limit 1",
        (scenario,),
    ).fetchone()
    before = parse_settings(bytes(last["raw"])) if last and last["raw"] else None
    valid, problems = signers(settings, directory, approved)
    needs = missing(settings, directory, valid, before)
    refused = [*needs, *problems] if needs else []
    for s in settings.instances:
        definition = definitions.get(s.definition)
        absent = [t for t in definition.tool_names if t not in tools] if definition else []
        if absent:
            refused.append(f"{s.definition} names tools the scenario doesn't have: "
                           f"{', '.join(absent)}")
    if last and settings.serial < last["serial"]:
        refused.append(f"serial {settings.serial} is older than {last['serial']}, the version in force")
    if last and settings.serial == last["serial"] and settings.version != last["version"]:
        refused.append(f"serial {settings.serial} already belongs to another version")
    version = {"settings": settings.version, "serial": settings.serial}
    if refused:
        ledger.append(conn, {"kind": "admin", "action": "apply", "decision": "deny",
                             "reasons": refused, "args": version})
        return Applied(signers=valid, refused=refused)
    signatures = Jsonb([{"signer": s.signer, "value": s.value} for s in settings.signatures])
    conn.execute(  # exactly what was signed, so the core can check it again at every run
        "insert into settings_versions (scenario, serial, version, signers, raw, signatures) "
        "values (%s, %s, %s, %s, %s, %s) on conflict (scenario, serial) do update "
        "set raw = excluded.raw, signatures = excluded.signatures",
        (scenario, settings.serial, settings.version, valid, settings.raw, signatures),
    )

    applied = Applied(signers=valid)
    for s in settings.instances:
        definition = definitions.get(s.definition)
        if definition is None:
            raise ValueError(f"instance {s.id}: no definition {s.definition}")
        level, parts = levels(s, definition)
        grants = definition.grants
        was = conn.execute("select status, suspended_by from instances where id = %s",
                           (s.id,)).fetchone()
        if was and was["status"] == "retired":  # a suspension outlasts retiring, and restoring
            back = "suspended" if was["suspended_by"] else "active"
            ledger.append(conn, {"kind": "admin", "action": "restore", "instance": s.id,
                                 "decision": "record", "args": {**version, "status": back}})
        conn.execute(
            """
            insert into instances
              (id, definition, release, level, parts, grants, model, serves, owner, deputy,
               pins, settings_version)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
              definition = excluded.definition, release = excluded.release,
              level = excluded.level, parts = excluded.parts, grants = excluded.grants,
              model = excluded.model,
              serves = excluded.serves, owner = excluded.owner, deputy = excluded.deputy,
              pins = excluded.pins, settings_version = excluded.settings_version,
              status = case when instances.status <> 'retired' then instances.status
                            when instances.suspended_by is not null then 'suspended'
                            else 'active' end,
              updated_at = now()
            """,
            (
                s.id, definition.id, definition.release_id, level, Jsonb(parts), grants,
                definition.model,
                list(s.serves), s.owner or definition.owner, s.deputy or definition.deputy,
                Jsonb(definition.pins),
                settings.version,
            ),
        )
        ledger.append(
            conn,
            {
                "kind": "admin",
                "action": "apply",
                "instance": s.id,
                "decision": "record",
                "args": {
                    **version,
                    "signed_by": valid,
                    "ignored_signatures": problems,
                    "release": definition.release_id,
                    "level": level,
                    **({"parts": parts} if parts else {}),
                    "grants": grants,
                    "model": definition.model,
                },
            },
        )
        applied.instances.append(s.id)

    withdrawn = conn.execute(  # this scenario's instances that the version leaves out
        """
        update instances set status = 'retired', updated_at = now()
        where status <> 'retired' and not (id = any(%s))
          and settings_version in (select version from settings_versions where scenario = %s)
        returning id
        """,
        ([s.id for s in settings.instances], scenario),
    ).fetchall()
    for row in withdrawn:
        ledger.append(conn, {"kind": "admin", "action": "retire", "instance": row["id"],
                             "decision": "record", "args": version})
    return applied


def set_status(conn: psycopg.Connection, instance: str, *, by: str, suspend: bool,
               identity: str = "unverified (development)") -> str:
    """Suspend or resume an instance, and return the reason if it can't be done."""
    row = conn.execute("select status, suspended_by from instances where id = %s for update",
                       (instance,)).fetchone()
    if row is None:
        return f"no instance {instance}"
    if row["status"] == "retired":
        return f"{instance} is retired"
    if suspend and row["status"] == "suspended":
        pass  # it stays suspended by whoever suspended it first, who alone can resume it
    elif suspend:
        conn.execute(
            "update instances set status = 'suspended', suspended_by = %s, updated_at = now() "
            "where id = %s",
            (by, instance),
        )
    else:
        if row["status"] != "suspended":
            return f"{instance} isn't suspended"
        if row["suspended_by"] != by:
            return (f"only {row['suspended_by']} can resume {instance}. Resuming someone else's "
                    "suspension needs the release approver, which phase 1 doesn't have yet.")
        conn.execute(
            "update instances set status = 'active', suspended_by = null, updated_at = now() "
            "where id = %s",
            (instance,),
        )
    ledger.append(
        conn,
        {"kind": "admin", "action": "suspend" if suspend else "resume", "instance": instance,
         "decision": "record", "args": {"by": by, "identity": identity,
                                        "suspended_by": row["suspended_by"] or by if suspend
                                        else None}},
    )
    return ""
