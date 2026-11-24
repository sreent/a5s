"""Reply verification (docs/model-execution.md): what a run writes is checked in code
before it reaches a person. A record key it names must be one its run read; a key it made
up is answered once more, with the correction, and what remains is the agent's own, said
so in a note apart from its words."""
from __future__ import annotations

from collections.abc import Iterable

from a5s import db
from a5s.core import values


def unknown_keys(conn: db.Connection, run: str, text: str, pattern: str | None,
                 heard: Iterable[str] = ()) -> list[str]:
    """The record keys `text` names that the run never read, so the agent may have made
    them up: what a5s asks it to write again, once, with the correction. `heard` are the keys,
    as a5s writes them alike, that the run was told by the person it answers, in their message
    or their conversation, such as one they asked about that a5s couldn't find: saying it back
    makes nothing up (round 16, A10)."""
    found = [v for v in values.found(text, pattern) if v.kind == "key"]
    if not found:
        return []
    known = {row["norm"] for row in conn.execute(
        "select norm from run_reads where run_id = %s and kind = 'key'", (run,))} | set(heard)
    return sorted({v.text for v in found if v.norm not in known})