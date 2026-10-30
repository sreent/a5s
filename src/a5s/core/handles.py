"""Handles: sensitive values an agent passes on without seeing them.

A scenario's tool names the fields of what it returns that hold sensitive values, such as a
customer's contact. The gateway hands each such value to the agent as a handle for its run,
such as [h:7f3a9c2b], and keeps the value. The agent writes the handle wherever the value
should go. When it calls a system, the gateway puts the value back, and where it writes to
people, code puts the value in for them to read. The value's source is exact, the model never
needs to see it, and the ledger records handles, not values. A handle works only in the run
that was given it.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import psycopg

TOKEN = re.compile(r"\[h:([0-9a-f]{8})\]")


def issue(conn: psycopg.Connection, run: str, source: str, result: Any,
          fields: tuple[str, ...]) -> Any:
    """What a tool returned, with the values in the named fields handed over as handles."""
    if not fields:
        return result
    if isinstance(result, list):
        return [issue(conn, run, source, item, fields) for item in result]
    if not isinstance(result, dict):
        return result
    given = dict(result)
    for field in fields:
        if isinstance(given.get(field), str) and given[field]:
            given[field] = f"[h:{_handle(conn, run, source, field, given[field])}]"
    return given


def _handle(conn: psycopg.Connection, run: str, source: str, field: str, value: str) -> str:
    row = conn.execute("select handle from run_handles where run_id = %s and field = %s "
                       "and value = %s", (run, field, value)).fetchone()
    if row:
        return row["handle"]
    handle = secrets.token_hex(4)
    conn.execute("insert into run_handles (run_id, handle, field, value, source) "
                 "values (%s, %s, %s, %s, %s)", (run, handle, field, value, source))
    return handle


def resolved(conn: psycopg.Connection, run: str, text: str) -> str:
    """Text with the run's own handles replaced by their values. Any other is left as it is."""
    if not TOKEN.search(text):
        return text
    held = {r["handle"]: r["value"] for r in conn.execute(
        "select handle, value from run_handles where run_id = %s", (run,))}
    return TOKEN.sub(lambda m: held.get(m.group(1), m.group(0)), text)


def resolved_args(conn: psycopg.Connection, run: str, args: dict[str, Any]) -> dict[str, Any]:
    """A tool's arguments, with the run's handles replaced by their values, as a system gets them."""
    return {k: resolved(conn, run, v) if isinstance(v, str) else v for k, v in args.items()}
