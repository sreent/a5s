"""The ledger: an append-only record of every decision and outcome.

Each entry is canonical JSON, hashed together with the hash of the entry before
it, so rewriting any entry breaks every hash after it. Entries are written in
the same transaction as the decision they record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

GENESIS = bytes(32)
_LOCK = 0x0A5_1ED6E7  # serialises appends, so the chain has no forks
_LONG_TEXT = 120


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def mask(args: dict[str, Any]) -> dict[str, Any]:
    """Keep short values, and record long text by hash and length only."""
    masked = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > _LONG_TEXT:
            masked[key] = {"sha256": hashlib.sha256(value.encode()).hexdigest(), "chars": len(value)}
        else:
            masked[key] = value
    return masked


def append(conn: psycopg.Connection, entry: dict[str, Any]) -> int:
    """Append an entry in the caller's transaction, and return its sequence number."""
    conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK,))
    head = conn.execute("select seq, hash from ledger order by seq desc limit 1").fetchone()
    seq, prev = (head["seq"] + 1, bytes(head["hash"])) if head else (1, GENESIS)
    text = canonical({**entry, "seq": seq, "at": datetime.now(UTC).isoformat()})
    hashed = hashlib.sha256(prev + text.encode()).digest()
    conn.execute(
        "insert into ledger (seq, entry, prev_hash, hash) values (%s, %s, %s, %s)",
        (seq, text, prev, hashed),
    )
    return seq


@dataclass(frozen=True)
class Verification:
    ok: bool
    entries: int
    head: str
    broken_at: int | None = None


def verify(conn: psycopg.Connection) -> Verification:
    """Recompute the chain from the start, and say where it breaks, if it does."""
    prev, count = GENESIS, 0
    for row in conn.execute("select seq, entry, prev_hash, hash from ledger order by seq"):
        expected = hashlib.sha256(prev + row["entry"].encode()).digest()
        intact = (
            row["seq"] == count + 1
            and json.loads(row["entry"]).get("seq") == row["seq"]
            and bytes(row["prev_hash"]) == prev
            and bytes(row["hash"]) == expected
        )
        if not intact:
            return Verification(False, count, prev.hex(), broken_at=row["seq"])
        prev, count = bytes(row["hash"]), count + 1
    return Verification(True, count, prev.hex())


def entries(conn: psycopg.Connection, *, run: str | None = None, limit: int = 100) -> list[dict]:
    if run:
        rows = conn.execute(
            "select entry from ledger where run_id = %s order by seq", (run,)
        ).fetchall()
    else:
        rows = conn.execute(
            "select entry from (select seq, entry from ledger order by seq desc limit %s) t "
            "order by seq",
            (limit,),
        ).fetchall()
    return [json.loads(r["entry"]) for r in rows]
