"""Reply verification (docs/model-execution.md): what a run writes is checked in code
before it reaches a person. A record key it names must be one its run read; a key it made
up is answered once more, with the correction, and what remains is the agent's own, said
so in a note apart from its words."""
from __future__ import annotations

from a5s import db
from a5s.core import values


def unknown_keys(conn: db.Connection, run: str, text: str, pattern: str | None) -> list[str]:
    """The record keys `text` names that the run never read, so the agent may have made
    them up: what a5s asks it to write again, once, with the correction."""
    found = [v for v in values.found(text, pattern) if v.kind == "key"]
    if not found:
        return []
    known = {row["norm"] for row in conn.execute(
        "select norm from run_reads where run_id = %s and kind = 'key'", (run,))}
    return sorted({v.text for v in found if v.norm not in known})