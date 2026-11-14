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

from a5s import db

GENESIS = bytes(32)
_LOCK = 0x0A5_1ED6E7  # serialises appends, so the chain has no forks
_LONG_TEXT = 120


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def mask(args: dict[str, Any], plain: tuple[str, ...] = ()) -> dict[str, Any]:
    """Arguments as the ledger keeps them: numbers, yes or no, and the `plain` ones, such as
    the key of the record a call is about, as they are, and anything people or agents wrote
    by hash and length only, however short, so the ledger keeps nothing anyone said."""
    masked: dict[str, Any] = {}
    for key, value in args.items():
        if value is None or isinstance(value, bool | int | float) or (
                key in plain and isinstance(value, str) and len(value) <= _LONG_TEXT):
            masked[key] = value
        else:
            text = value if isinstance(value, str) else canonical(value)
            masked[key] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)}
    return masked


def append(conn: db.Connection, entry: dict[str, Any]) -> int:
    """Append an entry in the caller's transaction, and return its sequence number. It waits
    for the ledger's lock a while at most, so one stalled writer fails others rather than
    holding them all, and the work fails, and is tried again, as a database error would. Its
    time is the database's clock, which every one of a5s's parts writes through, so none whose
    own clock is behind puts an entry before the one it follows; and never before the last
    entry's, if the database's clock went back, as after a failover. So a period's entries
    are those between two times, in the chain's order."""
    conn.execute("set local lock_timeout = '30s'")
    conn.execute("select pg_advisory_xact_lock(%s)", (_LOCK,))
    head = conn.execute(
        "select clock_timestamp() as now, h.seq, h.hash, h.entry::jsonb ->> 'at' as at "
        "from (select 1) one left join (select seq, hash, entry from ledger "
        "order by seq desc limit 1) h on true").fetchone()
    seq, prev = (head["seq"] + 1, bytes(head["hash"])) if head["seq"] else (1, GENESIS)
    at = head["now"].astimezone(UTC)
    if head["at"] and (last := datetime.fromisoformat(head["at"])) > at:
        at = last
    text = canonical({**entry, "seq": seq, "at": at.isoformat()})
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


def verify(conn: db.Connection) -> Verification:
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


def entries(conn: db.Connection, *, run: str | None = None, limit: int = 100) -> list[dict]:
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
