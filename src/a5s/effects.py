"""Effect helpers for scenario connectors, called with the gateway's stable work key, and what's
been changed through the made-up systems of the scenarios a5s ships, as their code reads it."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from a5s.contract import ToolCall

SYSTEMS_STATE = "A5S_SYSTEMS_STATE"  # where the made-up systems keep what's done through them
_READ: dict[Path, tuple[tuple[int, int, int], dict]] = {}  # each file, as it was last read


def draft_once(call: ToolCall, rows: list[dict], link: str, lock: Lock) -> dict:
    """Create a draft once, returning its original number and link when the effect repeats."""
    if call.key is None:
        raise ValueError("an idempotent draft needs the gateway's effect key")
    with lock:
        for number, row in enumerate(rows, start=1):
            if row.get("_effect_key") == call.key:
                return {"draft": number, "link": f"{link}drafts/{number}", "replayed": True}
        rows.append({**call.args, "_effect_key": call.key})
        return {"draft": len(rows), "link": f"{link}drafts/{len(rows)}"}


def changed_through(system: str) -> dict[str, dict]:
    """What's been changed through the made-up `system` a scenario's mcp.yaml names, record by
    record, as the system keeps it in the folder A5S_SYSTEMS_STATE names: nothing, if it names
    none or the system has changed nothing. The scenario's own code lays it over its data, as an
    organisation's code reads its system as it stands, so what a5s shows of a record, and its
    deciders, is what the system holds. Read again only once the system has written it again."""
    folder = os.environ.get(SYSTEMS_STATE)
    if not folder:
        return {}
    path = Path(folder) / f"{system}.json"
    try:
        seen = path.stat()
    except FileNotFoundError:
        return {}
    stamp = (seen.st_ino, seen.st_mtime_ns, seen.st_size)  # each write replaces it whole
    if (cached := _READ.get(path)) is not None and cached[0] == stamp:
        return cached[1]
    found = (json.loads(path.read_text(encoding="utf-8")) or {}).get("changed") or {}
    _READ[path] = (stamp, found)
    return found
