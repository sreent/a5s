"""Effect helpers for scenario connectors, called with the gateway's stable work key."""

from __future__ import annotations

from threading import Lock

from a5s.contract import ToolCall


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
