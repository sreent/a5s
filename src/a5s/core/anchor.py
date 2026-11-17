"""Copies of the ledger in locked storage, and the check that the ledger still matches them.

Every hour, the entries added since the last copy go to the store as a segment,
with a head naming its first and last entries and the hashes around them.
Nobody can change or delete either until its retention ends. So if anyone
rewrites the ledger, even recomputing every hash after the change, it no longer
matches its copies, and a5s refuses to copy any more of it. Each head the copier
makes is marked with a secret the database alone keeps, and only those count:
anything else in the store, such as a head someone planted, even one whose hashes
chain on from the copies, as anyone's can, is reported and otherwise ignored. It
can't stop the copying, or hide a change (round 15, D1).

After the database is restored from a backup, its ledger lacks entries its copies
hold: the copier copies nothing until `a5s restore` puts them back
(core/restoring.py), since copying what the core writes next would fork the copies
for good.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta

from a5s import db
from a5s.core.ledger import GENESIS, canonical
from a5s.core.stores import Exists, Store

SEGMENTS, HEADS = "segments/", "heads/"
_LOCK = 0x0A5_A2C0  # one copier at a time
_NUMBERED = re.compile(r"heads/(\d+)(\.\d+)?\.json")  # by the last entry each copies
RESTORED = ("the ledger's copies hold entries {first} to {last}, which the database lacks: it "
            "was restored from a backup, so a5s copies nothing, and a core that reads the copies "
            "won't start, until `a5s restore` puts them back "
            "(docs/runbooks.md#restoring-from-a-backup)")


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
    prev: str = ""  # the hash of the entry before `first`; copies made before it was kept lack it
    mark: str = ""  # the copier's, by the database's secret; copies made before it lack it


@dataclass(frozen=True)
class Copy:
    key: str
    head: Head


@dataclass(frozen=True)
class AnchorCheck:
    ok: bool
    copied_through: int
    copied_at: str | None
    locked: bool
    problems: tuple[str, ...] = ()


def _heads(store: Store,
           secret: bytes | None = None) -> tuple[dict[int, list[Copy]], list[str]]:
    """Every head in the store, by the entry it starts at, and the keys that aren't heads:
    given the database's secret, the heads the copier marked alone, and the keys of the rest
    with those that aren't heads. Without it, as an auditor without the database reads them,
    every head."""
    found: dict[int, list[Copy]] = defaultdict(list)
    junk = []
    for key in sorted(store.keys(HEADS)):
        try:
            head = Head(**json.loads(store.get(key)))
        except (ValueError, TypeError, KeyError):
            junk.append(key)
            continue
        if secret is not None and not _marked(secret, head):
            junk.append(key)  # planted, as the copier marks each it makes (round 15, D1)
            continue
        found[head.first].append(Copy(key, head))
    return found, junk


def _rows(store: Store, head: Head, prev: bytes) -> list[dict] | None:
    """The segment a head names, if it's the one named and continues from `prev`."""
    try:
        body = store.get(head.segment)
        rows = [json.loads(line) for line in body.decode().splitlines()]
    except (KeyError, ValueError):
        return None
    if hashlib.sha256(body).hexdigest() != head.segment_sha256 or not rows:
        return None
    for number, row in enumerate(rows, start=head.first):
        expected = hashlib.sha256(prev + row["entry"].encode()).digest()
        if row["seq"] != number or row["prev_hash"] != prev.hex() or row["hash"] != expected.hex():
            return None
        prev = expected
    return rows if rows[-1]["seq"] == head.seq and prev.hex() == head.hash else None


def _secret(conn: db.Connection) -> bytes:
    """The secret the database keeps to mark the ledger's copies with."""
    row = conn.execute("select secret from copy_secret").fetchone()
    if row is None:
        raise AnchorError("the database keeps no secret to mark the ledger's copies with")
    return row["secret"].encode()


def _mark(secret: bytes, head: Head) -> str:
    body = canonical({k: v for k, v in asdict(head).items() if k != "mark"})
    return hmac.new(secret, b"a5s ledger copy\n" + body.encode(), hashlib.sha256).hexdigest()


def _marked(secret: bytes, head: Head) -> bool:
    """Whether the copier made this head: by its mark, which nobody without the database's
    secret can make, though anyone can chain hashes."""
    return bool(head.mark) and hmac.compare_digest(head.mark, _mark(secret, head))


def _top(conn: db.Connection) -> int:
    row = conn.execute("select coalesce(max(seq), 0) as top from ledger").fetchone()
    return row["top"] if row else 0


def behind(conn: db.Connection, store: Store) -> tuple[int, int] | None:
    """The first and last of the entries the ledger's copies hold that the database lacks, as
    after it's restored from a backup, or None. By the heads named past the ledger's last
    entry alone, so it reads little, and by those the copier marked alone, so none planted in
    the store counts (round 15, D1)."""
    top, secret, last = _top(conn), _secret(conn), 0
    for key in store.keys(HEADS):
        named = _NUMBERED.fullmatch(key)
        if named is None or int(named.group(1)) <= top:
            continue
        try:
            head = Head(**json.loads(store.get(key)))
        except (ValueError, TypeError, KeyError):
            continue
        if head.seq > top and _marked(secret, head):
            last = max(last, head.seq)
    return (top + 1, last) if last else None


def beyond(conn: db.Connection, store: Store) -> list[dict]:
    """The entries the ledger's copies hold beyond the ledger, continuing it, each as its
    copy has it, from the copies the copier marked alone: none, unless the database was
    restored from a backup since they were copied (round 15, D1). Where such a copy holds
    an entry the ledger has too, they must be the same."""
    found, _ = _heads(store, _secret(conn))
    last, top = tip(conn, store, found), _top(conn)
    seq, prev = (last.head.seq, bytes.fromhex(last.head.hash)) if last else (0, GENESIS)
    held: list[dict] = []
    while candidates := [c for c in found.pop(seq + 1, []) if c.head.prev == prev.hex()]:
        whole = next(((c, rows) for c in candidates
                      if (rows := _rows(store, c.head, prev)) is not None), None)
        if whole is None:
            break
        copy, rows = whole
        if problem := _difference(conn, [r for r in rows if r["seq"] <= top]):
            raise AnchorError(f"{problem}: the ledger no longer matches its copy {copy.key}")
        held += [r for r in rows if r["seq"] > top]
        seq, prev = copy.head.seq, bytes.fromhex(copy.head.hash)
    return held


def _hashes(conn: db.Connection, seqs: set[int]) -> dict[int, str]:
    rows = conn.execute("select seq, hash from ledger where seq = any(%s)", (list(seqs),))
    return {r["seq"]: bytes(r["hash"]).hex() for r in rows}


def tip(conn: db.Connection, store: Store,
        heads: dict[int, list[Copy]] | None = None) -> Copy | None:
    """The last copy that continues the ones before it and matches the ledger, of `heads`,
    if given, else of the heads the copier marked.

    Heads that continue nothing, or that the ledger never had, are passed over. But
    if a real continuation, whose segment checks out, differs from the ledger, the
    ledger was rewritten: AnchorError.
    """
    found = dict(heads) if heads is not None else _heads(store, _secret(conn))[0]
    last, seq, prev = None, 0, GENESIS
    while candidates := [c for c in found.pop(seq + 1, []) if c.head.prev in ("", prev.hex())]:
        hashes = _hashes(conn, {c.head.seq for c in candidates})
        matching = [c for c in candidates if hashes.get(c.head.seq) == c.head.hash]
        if not matching:
            for c in candidates:
                if c.head.seq in hashes and _rows(store, c.head, prev) is not None:
                    raise AnchorError(f"the ledger no longer matches its copy {c.key}, "
                                      "so a5s won't copy any more of it")
            break
        last = matching[0]
        seq, prev = last.head.seq, bytes.fromhex(last.head.hash)
    return last


def _put(store: Store, base: str, ext: str, body: bytes) -> str:
    """Write once under a key, or under another if something else already has it."""
    for n in range(10):
        key = f"{base}{f'.{n}' if n else ''}{ext}"
        try:
            store.put(key, body)
            return key
        except Exists:
            if store.get(key) == body:  # a copy that stopped half way left it
                return key
    raise AnchorError(f"{base}{ext} and the names after it are all taken")


def anchor(conn: db.Connection, store: Store, *, batch: int = 10_000) -> list[Head]:
    """Copy every entry not yet copied, in segments of up to `batch` entries."""
    if not conn.execute("select pg_try_advisory_xact_lock(%s) as got", (_LOCK,)).fetchone()["got"]:
        return []  # another copier is at work
    if lacking := behind(conn, store):  # never fork them: they'd stop for good (round 15, D1)
        raise AnchorError(RESTORED.format(first=lacking[0], last=lacking[1]))
    secret = _secret(conn)
    last = tip(conn, store)
    through, prev = (last.head.seq, bytes.fromhex(last.head.hash)) if last else (0, GENESIS)
    made: list[Head] = []
    while rows := conn.execute(
            "select seq, entry, prev_hash, hash from ledger where seq > %s order by seq limit %s",
            (through, batch)).fetchall():
        before, lines = prev, []
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
        segment = _put(store, f"{SEGMENTS}{first:012d}-{through:012d}", ".jsonl", body)
        head = Head(first, through, prev.hex(), segment, hashlib.sha256(body).hexdigest(),
                    datetime.now(UTC).isoformat(), before.hex())
        head = replace(head, mark=_mark(secret, head))  # the copier's own (round 15, D1)
        _put(store, f"{HEADS}{through:012d}", ".json", canonical(asdict(head)).encode())
        made.append(head)
    return made


def _difference(conn: db.Connection, rows: list[dict]) -> str | None:
    """The first way the ledger differs from a copy of some of its entries, if it does."""
    if not rows:
        return None
    stored = {r["seq"]: r for r in conn.execute(
        "select seq, entry, hash from ledger where seq between %s and %s",
        (rows[0]["seq"], rows[-1]["seq"]))}
    for row in rows:
        mine = stored.get(row["seq"])
        if mine is None:
            return f"entry {row['seq']} is missing from the ledger, though it was copied"
        if mine["entry"] != row["entry"] or bytes(mine["hash"]).hex() != row["hash"]:
            return f"entry {row['seq']} was changed after it was copied"
    return None


def check(conn: db.Connection, store: Store, *, every: timedelta = timedelta(hours=1),
          now: datetime | None = None) -> AnchorCheck:
    """Whether the ledger matches its copies, the copies are whole, and they're up to date."""
    problems = [f"someone tried to replace or delete {key}"
                for prefix in (HEADS, SEGMENTS)
                for key, disturbed in sorted(store.keys(prefix).items()) if disturbed]
    found, junk = _heads(store, _secret(conn))  # the copier's own, and the rest
    problems += [f"{key} isn't a copy a5s made" for key in junk]
    last, seq, prev = None, 0, GENESIS
    while candidates := found.pop(seq + 1, []):
        real = [(c, rows) for c in candidates if (rows := _rows(store, c.head, prev)) is not None]
        problems += [f"{c.key} doesn't continue the copies before it"
                     for c in candidates if all(c is not r for r, _ in real)]
        if not real:
            break
        if len(real) > 1:
            problems.append(f"the copies fork after entry {seq}: "
                            f"{', '.join(c.key for c, _ in real)}")
        differences = [(c, _difference(conn, rows)) for c, rows in real]
        last, difference = next(((c, d) for c, d in differences if d is None), differences[0])
        if difference:
            problems.append(difference)
            break
        seq, prev = last.head.seq, bytes.fromhex(last.head.hash)
    problems += [f"{c.key} isn't part of the ledger's copies"
                 for group in found.values() for c in group]
    through = last.head.seq if last else 0
    waiting = conn.execute("select entry from ledger where seq > %s order by seq limit 1",
                           (through,)).fetchone()
    if waiting:
        since = datetime.fromisoformat(json.loads(waiting["entry"])["at"])
        if (now or datetime.now(UTC)) - since > 2 * every:
            problems.append(f"nothing written since {since.isoformat()} has been copied, "
                            "so copying has stopped")
    return AnchorCheck(not problems, through, last.head.at if last else None, store.locked,
                       tuple(problems))
