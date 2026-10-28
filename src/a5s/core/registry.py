"""The register: instances, their releases, grants, levels and status."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from a5s.contract import Settings, Tool
from a5s.core import ledger
from a5s.definitions import Definition


def apply(
    conn: psycopg.Connection,
    definitions: dict[str, Definition],
    settings: Settings,
    tools: dict[str, Tool],
) -> list[str]:
    """Bring instances in line with the settings and the current releases.

    An instance's status is the core's own data, so applying settings never
    resumes a suspended instance.
    """
    applied = []
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
                    "release": definition.release_id,
                    "level": level,
                    "grants": grants,
                    "model": definition.model,
                    "settings": settings.version,
                },
            },
        )
        applied.append(s.id)
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
