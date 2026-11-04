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
    """What a tool returned, with the values in the named fields handed over as handles, at
    any depth, and any value the run already holds a handle for hidden behind it wherever
    else it appears, such as in an error that repeats an argument."""

    def given(value: Any) -> Any:
        if isinstance(value, list):
            return [given(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {key: f"[h:{_handle(conn, run, source, key, found)}]"
                if key in fields and isinstance(found, str) and found else given(found)
                for key, found in value.items()}

    return masked(conn, run, given(result) if fields else result)


def masked(conn: psycopg.Connection, run: str, value: Any) -> Any:
    """A value with every value the run holds a handle for replaced by its handle, at any
    depth, so a handle's value never comes back to the model."""
    held = {r["value"]: r["handle"] for r in conn.execute(
        "select handle, value from run_handles where run_id = %s", (run,))}
    if not held:
        return value

    def hide(found: Any) -> Any:
        if isinstance(found, str):
            for secret in sorted(held, key=len, reverse=True):
                found = found.replace(secret, f"[h:{held[secret]}]")
            return found
        if isinstance(found, list):
            return [hide(item) for item in found]
        if isinstance(found, dict):
            return {k: hide(v) for k, v in found.items()}
        return found

    return hide(value)


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


def resolved_args(conn: psycopg.Connection, run: str, args: Any) -> Any:
    """A tool's arguments, with the run's handles replaced by their values at any depth, as a
    system gets them."""
    if isinstance(args, str):
        return resolved(conn, run, args)
    if isinstance(args, list):
        return [resolved_args(conn, run, item) for item in args]
    if isinstance(args, dict):
        return {k: resolved_args(conn, run, v) for k, v in args.items()}
    return args
