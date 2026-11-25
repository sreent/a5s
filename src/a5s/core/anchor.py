"""Copies of the ledger in locked storage, and the check that the ledger still matches them.

The entries added since the last copy go to the store as a segment, with a head naming
its first and last entries and the hashes around them: what people decided, and what a5s
gave up, within a minute of it, and every other entry within 15 minutes (round 15, E8).
Nobody can change or delete either until its retention ends. So if anyone
rewrites the ledger, even recomputing every hash after the change, it no longer
matches its copies, and a5s refuses to copy any more of it. Only an entry not yet
copied can be rewritten unseen, by someone with the database's own powers: that
window is an accepted risk, and the auditors' page marks the entries still in it.
Each head the copier makes is marked with a secret the database alone keeps, and
only those count: anything else in the store, such as a head someone planted, even
one whose hashes chain on from the copies, as anyone's can, is reported and
otherwise ignored. It can't stop the copying, or hide a change (round 15, D1).

The copier looks every minute, by the database alone: it keeps the last copy it made,
and reads the copies afresh only when it starts, when another copier copied since, or
when the ledger no longer holds what it copied as it copied it, which stops it. Once a
day, and when it starts, it checks the whole ledger, its chain and every copy, and
records what it found, for the core's status and the auditors' page.

After the database is restored from a backup, its ledger lacks entries its copies
hold: the copier copies nothing until `a5s restore` puts them back
(core/restoring.py), since copying what the core writes next would fork the copies
for good.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta

from a5s import db
from a5s.core import ledger
from a5s.core.ledger import GENESIS, canonical
from a5s.core.stores import Exists, Store

log = logging.getLogger(__name__)
# How soon the copier copies (round 15, E8): the kinds of entry that record what people
# decided, approved, graded, read of the trail, or what a5s gave up, within a minute of being
# written, and the rest within COPY_WITHIN
WEIGHTY = ("admin", "audit", "cap", "proposal", "registry", "retention")
LOOK_EVERY = timedelta(minutes=1)
COPY_WITHIN = timedelta(minutes=15)
CHECK_EVERY = timedelta(days=1)  # how often it checks the whole ledger against its copies
MOST_PROBLEMS = 20  # a full check's problems the copier records, at most
SHIFTED = 5  # entries taken out or put in that a difference names as such, at most
SEGMENTS, HEADS = "segments/", "heads/"
_LOCK = 0x0A5_A2C0  # one copier at a time
_NUMBERED = re.compile(r"heads/(\d+)(\.\d+)?\.json")  # by the last entry each copies
RESTORED = ("the ledger's copies hold entries {first} to {last}, which the database lacks: it "
            "was restored from a backup, so a5s copies nothing, and a core that reads the copies "
            "won't start, until `a5s restore` puts them back "
            "(docs/runbooks.md#restoring-from-a-backup)")


class AnchorError(Exception):
    pass


def awaiting_restore(conn: db.Connection) -> str | None:
    """Why a5s opens no run now, if it doesn't: the copier stopped as the ledger's copies hold
    entries the database lacks, as after a restore from a backup, until `a5s restore` puts them
    back. Otherwise the scheduler would answer again messages answered since the backup, and
    make again changes made since (round 16, D9)."""
    row = conn.execute("select problem from copier where stopped").fetchone()
    found = str(row["problem"] or "") if row else ""
    return found if found.startswith(RESTORED.split("{", 1)[0]) else None


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


def _put_head(store: Store, secret: bytes, head: Head) -> str:
    """Write a head once, or take as its own the one another copier made of the same entries,
    marked as the copier marks each, rather than fork the copies (round 15, E8)."""
    base, body = f"{HEADS}{head.seq:012d}", canonical(asdict(head)).encode()
    for n in range(10):
        key = f"{base}{f'.{n}' if n else ''}.json"
        try:
            store.put(key, body)
            return key
        except Exists:
            try:
                there = Head(**json.loads(store.get(key)))
            except (ValueError, TypeError, KeyError):
                continue
            if _marked(secret, there) and (there.first, there.seq, there.hash, there.prev,
                                           there.segment_sha256) == (
                    head.first, head.seq, head.hash, head.prev, head.segment_sha256):
                return key
    raise AnchorError(f"{base}.json and the names after it are all taken")


class Copier:
    """The copier, as `a5s anchor` keeps it running: it remembers the last copy it made, or
    found, so it can look every minute by the database alone, and reads the copies only when
    it starts, when another copier copied since, or when the ledger no longer holds the last
    entry it copied as it copied it (round 15, E8)."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.known = False  # whether it knows the last copy, which may be none yet
        self.last: Head | None = None
        self.checked: datetime | None = None  # when it last checked the whole ledger

    def holds(self, conn: db.Connection) -> bool:
        """Whether what it knows still holds: the ledger has the last entry it copied, as it
        copied it, and no other copier has recorded copying past it."""
        if not self.known:
            return False
        row = conn.execute(
            "select (select hash from ledger where seq = %s) as hash, "
            "(select through from copier) as through", (self.last.seq if self.last else 0,)
        ).fetchone() or {}
        copied = self.last.seq if self.last else 0
        if (row.get("through") or 0) > copied:
            return False  # another copier copied since: read the copies afresh
        return self.last is None or (row.get("hash") is not None
                                     and bytes(row["hash"]).hex() == self.last.hash)

    def waiting(self, conn: db.Connection, within: timedelta = COPY_WITHIN,
                now: datetime | None = None) -> str:
        """What waits past the last copy, by the database alone: "nothing"; "now", where any
        of it is weighty, or the oldest has waited `within`; else "later"."""
        row = conn.execute(
            "select (select entry from ledger where seq = %(after)s + 1) as oldest, exists "
            "(select 1 from ledger where seq > %(after)s and kind = any(%(weighty)s)) as weighty",
            {"after": self.last.seq if self.last else 0, "weighty": list(WEIGHTY)}).fetchone()
        if row is None or row["oldest"] is None:
            return "nothing"
        at = datetime.fromisoformat(json.loads(row["oldest"])["at"])
        return "now" if row["weighty"] or (now or datetime.now(UTC)) - at >= within else "later"

    def tick(self, conn: db.Connection, within: timedelta = COPY_WITHIN,
             now: datetime | None = None) -> list[Head]:
        """What the copier does each time it looks: copy what's due, or everything, if it must
        read the copies afresh; else see that the ledger still holds what it copied, and
        record that it looked, where nothing waits."""
        if not self.holds(conn):
            return self.copy(conn)
        waiting = self.waiting(conn, within, now)
        if waiting == "now":
            return self.copy(conn)
        if waiting == "nothing":
            went(conn, self.last.seq if self.last else 0)
        return []

    def copy(self, conn: db.Connection, *, batch: int = 10_000) -> list[Head]:
        """Copy every entry not yet copied, in segments of up to `batch` entries."""
        locked = conn.execute("select pg_try_advisory_xact_lock(%s) as got", (_LOCK,)).fetchone()
        if not (locked and locked["got"]):
            return []  # another copier is at work
        if not self.holds(conn):  # read the copies afresh
            if lacking := behind(conn, self.store):  # never fork them: they'd stop for good
                raise AnchorError(RESTORED.format(first=lacking[0], last=lacking[1]))
            found = tip(conn, self.store)
            self.last, self.known = (found.head if found else None), True
        secret = _secret(conn)
        last = self.last
        through, prev = (last.seq, bytes.fromhex(last.hash)) if last else (0, GENESIS)
        made: list[Head] = []
        while rows := conn.execute(
                "select seq, entry, prev_hash, hash from ledger where seq > %s order by seq "
                "limit %s", (through, batch)).fetchall():
            before, lines = prev, []
            for row in rows:
                if (bytes(row["prev_hash"]) != prev or bytes(row["hash"])
                        != hashlib.sha256(prev + row["entry"].encode()).digest()):
                    raise AnchorError(f"entry {row['seq']} doesn't follow the one before it, "
                                      "so a5s won't copy it")
                lines.append(canonical({"seq": row["seq"], "entry": row["entry"],
                                        "prev_hash": prev.hex(), "hash": bytes(row["hash"]).hex()}))
                prev = bytes(row["hash"])
            body = ("\n".join(lines) + "\n").encode()
            first, through = rows[0]["seq"], rows[-1]["seq"]
            segment = _put(self.store, f"{SEGMENTS}{first:012d}-{through:012d}", ".jsonl", body)
            head = Head(first, through, prev.hex(), segment, hashlib.sha256(body).hexdigest(),
                        datetime.now(UTC).isoformat(), before.hex())
            head = replace(head, mark=_mark(secret, head))  # the copier's own (round 15, D1)
            _put_head(self.store, secret, head)
            self.last = head  # in the store for good, whatever becomes of this transaction
            made.append(head)
        went(conn, through)
        return made

    def checking(self, conn: db.Connection, within: timedelta = COPY_WITHIN,
                 now: datetime | None = None) -> tuple[str, ...] | None:
        """Check the whole ledger, its chain and every copy, when it starts and once a day
        after, by `now`, and record what it found, for the core's status and the auditors'
        page: the problems, or None where it isn't time yet."""
        at = now or datetime.now(UTC)
        if self.checked is not None and at - self.checked < CHECK_EVERY:
            return None
        found = audited(conn, self.store, every=within)
        checked(conn, found.copied_through, found.problems)
        self.checked = at
        return found.problems


def anchor(conn: db.Connection, store: Store, *, batch: int = 10_000) -> list[Head]:
    """Copy every entry not yet copied, in segments of up to `batch` entries, as a copier that
    starts afresh does."""
    return Copier(store).copy(conn, batch=batch)


def audited(conn: db.Connection, store: Store, *, every: timedelta = COPY_WITHIN,
            now: datetime | None = None) -> AnchorCheck:
    """The whole ledger checked: its chain, from its first entry, and against every copy."""
    chain = ledger.verify(conn)
    found = check(conn, store, every=every, now=now)
    broken = () if chain.ok else (f"the ledger's chain breaks at entry {chain.broken_at}",)
    return replace(found, ok=found.ok and chain.ok, problems=broken + found.problems)


# How the copier is doing, for the core's status and the operators' figures, which read no
# copies themselves (round 15, D8)

def went(conn: db.Connection, through: int) -> None:
    """Record that the copier copied the ledger through an entry, or found nothing new past
    it, in the caller's transaction, which copied them."""
    conn.execute(
        "insert into copier (only_one, through, copied_at, problem, problem_at, stopped) "
        "values (true, %s, now(), null, null, false) on conflict (only_one) do update set "
        "through = excluded.through, copied_at = excluded.copied_at, problem = null, "
        "problem_at = null, stopped = false", (through,))


def stuck(url: str, problem: str, stopped: bool) -> None:
    """Record why the copier couldn't copy, and whether it stopped until someone acts, such as
    `a5s restore` after a restore from a backup. Logged alone where even that can't be
    recorded, as while the database is away."""
    try:
        with db.transaction(url) as conn:
            conn.execute(
                "insert into copier (only_one, problem, problem_at, stopped) values "
                "(true, %s, now(), %s) on conflict (only_one) do update set problem = "
                "excluded.problem, problem_at = excluded.problem_at, stopped = excluded.stopped",
                (problem[:500], stopped))
    except Exception:  # what the copier says of it is in its log regardless
        log.exception("couldn't record why the copier couldn't copy")


def checked(conn: db.Connection, through: int, problems: Iterable[str]) -> None:
    """Record what the copier's check of the whole ledger found, in the caller's transaction:
    how far its copies matched it, and the problems, if any (round 15, E8)."""
    conn.execute(
        "insert into copier (only_one, checked_at, checked_through, check_problems) values "
        "(true, now(), %s, %s) on conflict (only_one) do update set checked_at = "
        "excluded.checked_at, checked_through = excluded.checked_through, check_problems = "
        "excluded.check_problems", (through, list(problems)[:MOST_PROBLEMS]))


def state(conn: db.Connection) -> dict | None:
    """How the copier is doing, as it last recorded it, and how far the ledger has gone on
    past its copies since: None if no copier has run. With what its last check of the whole
    ledger found, if it has checked it (round 15, E8)."""
    found = conn.execute(
        "select through, problem, stopped, extract(epoch from now() - copied_at) as age, "
        "checked_through, check_problems, extract(epoch from now() - checked_at) as checked, "
        "(select coalesce(max(seq), 0) from ledger) as top from copier").fetchone()
    if found is None:
        return None
    return {"through": found["through"], "behind": max(0, found["top"] - (found["through"] or 0)),
            "copied_seconds_ago": float(found["age"]) if found["age"] is not None else None,
            "problem": found["problem"], "stopped": bool(found["stopped"]),
            "checked": None if found["checked"] is None else {
                "seconds_ago": float(found["checked"]), "through": found["checked_through"],
                "problems": list(found["check_problems"] or [])}}


def trail(conn: db.Connection) -> dict | None:
    """Whether the trail checks out, as auditors are told (round 15, E8): by what the copier
    last recorded, which reads the copies for them, None where no copier has run. It checks
    out once the copier has checked the whole ledger and found nothing wrong, while it isn't
    stopped, and while its last check isn't long overdue. Entries past `copied_through` aren't
    in the locked copies yet, so until they are, someone with the database's own powers could
    rewrite them unseen."""
    found = state(conn)
    if found is None:
        return None
    full = found["checked"]
    problems = [*(full["problems"] if full else [])]
    if found["stopped"] and found["problem"] not in problems:
        problems.insert(0, found["problem"])
    copied = found["copied_seconds_ago"]
    # a check or a copy long overdue, as when the copier stopped running: it can't vouch now
    stale = bool(full) and full["seconds_ago"] > 2 * CHECK_EVERY.total_seconds()
    late = found["behind"] > 0 and (copied or 0) > 2 * COPY_WITHIN.total_seconds()
    return {"checks_out": bool(full) and not problems and not stale, "problems": problems,
            "copied_through": found["through"], "uncopied": found["behind"],
            "copied_minutes_ago": None if copied is None else int(copied // 60),
            "checked_minutes_ago": None if not full else int(full["seconds_ago"] // 60),
            "failing": bool(found["problem"]) and not found["stopped"], "stale": stale,
            "late": late}


def _difference(conn: db.Connection, rows: list[dict]) -> str | None:
    """The first way the ledger differs from a copy of some of its entries, if it does: an
    entry missing, changed, or taken out or put in, with those after it renumbered."""
    if not rows:
        return None
    stored = {r["seq"]: r for r in conn.execute(
        "select seq, entry, hash from ledger where seq between %s and %s",
        (rows[0]["seq"], rows[-1]["seq"] + SHIFTED))}
    for n, row in enumerate(rows):
        mine = stored.get(row["seq"])
        if mine is None:
            return f"entry {row['seq']} is missing from the ledger, though it was copied"
        if mine["entry"] != row["entry"] or bytes(mine["hash"]).hex() != row["hash"]:
            return _shifted(row["seq"], mine["entry"], rows[n:], stored) or (
                f"entry {row['seq']} was changed after it was copied")
    return None


def _shifted(seq: int, mine: str, copied: list[dict], stored: dict[int, dict]) -> str | None:
    """Whether entries were taken out of the ledger at `seq` after they were copied, or put in
    there, and those after renumbered: the ledger's entry there is a later one of the copy's,
    or the copy's a later one of the ledger's, but for its number (round 15, E8)."""
    def unnumbered(entry: str) -> dict:
        return {k: v for k, v in json.loads(entry).items() if k != "seq"}

    here = unnumbered(mine)
    for gap, later in enumerate(copied[1:SHIFTED + 1], start=1):
        if unnumbered(later["entry"]) == here:
            return (f"entry {seq} was taken out after it was copied, and those after it "
                    "renumbered" if gap == 1 else f"entries {seq} to {seq + gap - 1} were taken "
                    "out after they were copied, and those after them renumbered")
    theirs = unnumbered(copied[0]["entry"])
    for gap in range(1, SHIFTED + 1):
        if (later := stored.get(seq + gap)) and unnumbered(later["entry"]) == theirs:
            return (f"{'an entry was' if gap == 1 else f'{gap} entries were'} put in at entry "
                    f"{seq} after it was copied, and those after renumbered")
    return None


def check(conn: db.Connection, store: Store, *, every: timedelta = COPY_WITHIN,
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
