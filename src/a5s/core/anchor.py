"""Copies of the ledger in locked storage, and the check that the ledger still matches them.

Every hour, the entries added since the last copy go to the store as a segment,
with a head naming the last entry and its hash. Nobody can change or delete
either until its retention ends. So if anyone rewrites the ledger, even
recomputing every hash after the change, it no longer matches its copies, and
a5s refuses to copy a history that doesn't match.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from a5s.core.ledger import GENESIS, canonical
from a5s.core.stores import Exists, Store

SEGMENTS, HEADS = "segments/", "heads/"
_LOCK = 0x0A5_A2C0  # one copier at a time


class AnchorError(Exception):
    pass


@dataclass(frozen=True)
class Head:
    first: int  # the first entry in the segment
    seq: int  # the last
    hash: str
    segment: str
    segment_sha256: str
    at: str


@dataclass(frozen=True)
class AnchorCheck:
    ok: bool
    copied_through: int
    copied_at: str | None
    locked: bool
    problems: tuple[str, ...] = ()


def heads(store: Store) -> list[Head]:
    return [Head(**json.loads(store.get(key))) for key in sorted(store.keys(HEADS))]


def latest(store: Store) -> Head | None:
    keys = store.keys(HEADS)  # named by the last entry, zero-padded, so they sort
    return Head(**json.loads(store.get(max(keys)))) if keys else None


def _put(store: Store, key: str, body: bytes, same: bool) -> None:
    try:
        store.put(key, body)
    except Exists:  # a copy that stopped half way left it; it must say the same
        if not same:
            raise AnchorError(f"{key} was already copied, by another copier") from None
        if store.get(key) != body:
            raise AnchorError(f"{key} was already copied, with different contents") from None


def anchor(conn: psycopg.Connection, store: Store, *, batch: int = 10_000) -> list[Head]:
    """Copy every entry not yet copied, in segments of up to `batch` entries."""
    if not conn.execute("select pg_try_advisory_xact_lock(%s) as got", (_LOCK,)).fetchone()["got"]:
        return []  # another copier is at work
    last = latest(store)
    through, prev = (last.seq, bytes.fromhex(last.hash)) if last else (0, GENESIS)
    if last:
        row = conn.execute("select hash from ledger where seq = %s", (through,)).fetchone()
        if row is None or bytes(row["hash"]) != prev:
            raise AnchorError(f"the ledger no longer matches its copy at entry {through}, "
                              "so a5s won't copy any more of it")
    made: list[Head] = []
    while rows := conn.execute(
            "select seq, entry, prev_hash, hash from ledger where seq > %s order by seq limit %s",
            (through, batch)).fetchall():
        lines = []
        for row in rows:
            if (bytes(row["prev_hash"]) != prev
                    or bytes(row["hash"]) != hashlib.sha256(prev + row["entry"].encode()).digest()):
                raise AnchorError(f"entry {row['seq']} doesn't follow the one before it, "
                                  "so a5s won't copy it")
            lines.append(canonical({"seq": row["seq"], "entry": row["entry"],
                                    "prev_hash": prev.hex(), "hash": bytes(row["hash"]).hex()}))
            prev = bytes(row["hash"])
        body = ("\n".join(lines) + "\n").encode()
        first, through = rows[0]["seq"], rows[-1]["seq"]
        segment = f"{SEGMENTS}{first:012d}-{through:012d}.jsonl"
        _put(store, segment, body, same=True)
        head = Head(first, through, prev.hex(), segment, hashlib.sha256(body).hexdigest(),
                    datetime.now(UTC).isoformat())
        _put(store, f"{HEADS}{through:012d}.json", canonical(asdict(head)).encode(), same=False)
        made.append(head)
    return made


def _check_copies(conn: psycopg.Connection, store: Store, done: list[Head]) -> list[str]:
    """Walk the copies in order: each must follow the last, and match the ledger."""
    seq, prev = 0, GENESIS
    for head in done:
        try:
            body = store.get(head.segment)
        except KeyError:
            return [f"the copy {head.segment} is missing"]
        if hashlib.sha256(body).hexdigest() != head.segment_sha256:
            return [f"the copy {head.segment} isn't the one its head names"]
        rows = [json.loads(line) for line in body.decode().splitlines()]
        if head.first != seq + 1 or rows[0]["seq"] != seq + 1:
            return [f"the copies jump from entry {seq} to entry {rows[0]['seq']}"]
        for row in rows:
            expected = hashlib.sha256(prev + row["entry"].encode()).digest()
            if row["prev_hash"] != prev.hex() or row["hash"] != expected.hex():
                return [f"the copy of entry {row['seq']} doesn't follow the one before it"]
            prev = expected
        if rows[-1]["seq"] != head.seq or prev.hex() != head.hash:
            return [f"the copy {head.segment} doesn't end where its head says"]
        stored = {r["seq"]: r for r in conn.execute(
            "select seq, entry, hash from ledger where seq between %s and %s",
            (head.first, head.seq))}
        for row in rows:
            mine = stored.get(row["seq"])
            if mine is None:
                return [f"entry {row['seq']} is missing from the ledger, though it was copied"]
            if mine["entry"] != row["entry"] or bytes(mine["hash"]).hex() != row["hash"]:
                return [f"entry {row['seq']} was changed after it was copied"]
        seq = head.seq
    return []


def check(conn: psycopg.Connection, store: Store, *, every: timedelta = timedelta(hours=1),
          now: datetime | None = None) -> AnchorCheck:
    """Whether the ledger matches its copies, and the copies are up to date."""
    problems = [f"someone tried to replace or delete {key}"
                for prefix in (HEADS, SEGMENTS)
                for key, disturbed in sorted(store.keys(prefix).items()) if disturbed]
    done = heads(store)
    problems += _check_copies(conn, store, done)
    through = done[-1].seq if done else 0
    waiting = conn.execute("select entry from ledger where seq > %s order by seq limit 1",
                           (through,)).fetchone()
    if waiting:
        since = datetime.fromisoformat(json.loads(waiting["entry"])["at"])
        if (now or datetime.now(UTC)) - since > 2 * every:
            problems.append(f"nothing written since {since.isoformat()} has been copied, "
                            "so copying has stopped")
    return AnchorCheck(not problems, through, done[-1].at if done else None, store.locked,
                       tuple(problems))
