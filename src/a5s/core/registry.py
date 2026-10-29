"""The register: instances, their releases, grants, levels and status."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import INSTANCE_APPROVER, Person, Settings, Tool
from a5s.core import ledger, signing
from a5s.definitions import Definition

Directory = Callable[[str], Person | None]


def signers(settings: Settings, directory: Directory) -> tuple[list[str], list[str]]:
    """Who validly signed this version, and what's wrong with any other signature."""
    valid, problems = [], []
    for sig in settings.signatures:
        person = directory(sig.signer)
        if person is None:
            problems.append(f"{sig.signer} isn't in the directory")
        elif INSTANCE_APPROVER not in person.roles:
            problems.append(f"{sig.signer} doesn't hold the {INSTANCE_APPROVER} role")
        elif not person.public_key or not signing.verify(person.public_key, settings.raw, sig.value):
            problems.append(f"{sig.signer}'s signature isn't for this version")
        else:
            valid.append(sig.signer)
    return valid, problems


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
) -> Applied:
    """Bring instances in line with a signed version of the settings and the current releases.

    An unsigned version doesn't count, and neither does one older than the
    version in force. An instance's status is the core's own data, so applying
    settings never resumes a suspended instance.
    """
    valid, problems = signers(settings, directory)
    refused = [] if valid else [f"no {INSTANCE_APPROVER} signed this version", *problems]
    last = conn.execute(
        "select serial, version from settings_versions where scenario = %s "
        "order by serial desc limit 1",
        (scenario,),
    ).fetchone()
    if last and settings.serial < last["serial"]:
        refused.append(f"serial {settings.serial} is older than {last['serial']}, the version in force")
    if last and settings.serial == last["serial"] and settings.version != last["version"]:
        refused.append(f"serial {settings.serial} already belongs to another version")
    version = {"settings": settings.version, "serial": settings.serial}
    if refused:
        ledger.append(conn, {"kind": "admin", "action": "apply", "decision": "deny",
                             "reasons": refused, "args": version})
        return Applied(signers=valid, refused=refused)
    if not last or last["serial"] != settings.serial:
        conn.execute(
            "insert into settings_versions (scenario, serial, version, signers) "
            "values (%s, %s, %s, %s)",
            (scenario, settings.serial, settings.version, valid),
        )

    applied = Applied(signers=valid)
    for s in settings.instances:
        definition = definitions.get(s.definition)
        if definition is None:
            raise ValueError(f"instance {s.id}: no definition {s.definition}")
        wanted = definition.autonomy.start if s.level is None else s.level
        level = min(wanted, definition.autonomy.max)
        grants = [t for t in definition.tool_names if t in tools]
        conn.execute(
            """
            insert into instances
              (id, definition, release, level, grants, model, serves, owner, deputy,
               pins, settings_version)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
              definition = excluded.definition, release = excluded.release,
              level = excluded.level, grants = excluded.grants, model = excluded.model,
              serves = excluded.serves, owner = excluded.owner, deputy = excluded.deputy,
              pins = excluded.pins, settings_version = excluded.settings_version,
              updated_at = now()
            """,
            (
                s.id, definition.id, definition.release_id, level, grants, definition.model,
                list(s.serves), definition.owner, definition.deputy, Jsonb(definition.pins),
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
                    "grants": grants,
                    "model": definition.model,
                },
            },
        )
        applied.instances.append(s.id)
    return applied


def set_status(conn: psycopg.Connection, instance: str, *, by: str, suspend: bool) -> str:
    """Suspend or resume an instance, and return the reason if it can't be done."""
    row = conn.execute("select status, suspended_by from instances where id = %s for update",
                       (instance,)).fetchone()
    if row is None:
        return f"no instance {instance}"
    if suspend:
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
         "decision": "record", "args": {"by": by}},
    )
    return ""
