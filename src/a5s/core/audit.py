"""The audit trail: the ledger as an auditor reads it (docs/administration.md).

Entries are found by period, kind, action, decision, instance and person, a page at a time.
A period is exported as the ledger holds it: each entry with its hash and the one before, a
line each, as the locked copies hold them, so anyone can check the chain, and, with the copies,
that it's the ledger's own. A report says who holds each role, and who approved, decided,
released, suspended, exported or erased what. Each search, export and report is itself in
the ledger, so reading the trail leaves a trace too.

The ledger keeps what anyone said only by hash, so nothing here holds it. Only someone with the
auditor's role, or assurance's, reads the trail.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import psycopg

from a5s.contract import (
    ASSURANCE,
    DATA_PROTECTION,
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    RELEASE_APPROVER,
)
from a5s.core import ledger
from a5s.core.ledger import GENESIS

AUDITOR = "auditor"
READERS = (AUDITOR, ASSURANCE)  # who reads the trail
MOST = 500  # entries a page holds at most
MOST_EXPORTED = 10_000  # entries an export's page holds at most
_PLAIN = ("by", "since", "until", "kind", "action", "decision", "instance")


def reads(person: Any) -> bool:
    """Whether someone may read the trail: an auditor, or assurance."""
    return person is not None and any(role in person.roles for role in READERS)


def _head(conn: psycopg.Connection) -> int:
    return conn.execute("select coalesce(max(seq), 0) as n from ledger").fetchone()["n"]


def _first_at(conn: psycopg.Connection, at: datetime, head: int) -> int:
    """The first entry made at or after `at`, or head + 1 if none was, found by halving: the
    ledger's entries are in the order they were made."""
    low, high = 1, head + 1
    while low < high:
        middle = (low + high) // 2
        made = conn.execute("select entry::jsonb->>'at' as at from ledger where seq = %s",
                            (middle,)).fetchone()["at"]
        if datetime.fromisoformat(made) < at:
            low = middle + 1
        else:
            high = middle
    return low


def _span(conn: psycopg.Connection, since: datetime | None, until: datetime | None,
          after: int) -> tuple[int, int]:
    """The first and last entries of a period, from `since` up to but not including `until`,
    after the entry `after`."""
    head = _head(conn)
    first = max(after + 1, _first_at(conn, _utc(since), head) if since else 1)
    last = _first_at(conn, _utc(until), head) - 1 if until else head
    return first, last


def _utc(at: datetime) -> datetime:
    """A time someone gave without a zone is UTC's, as the ledger's are."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def search(conn: psycopg.Connection, *, since: datetime | None = None,
           until: datetime | None = None, kind: str | None = None, action: str | None = None,
           decision: str | None = None, instance: str | None = None, person: str | None = None,
           after: int = 0, limit: int = MOST) -> dict[str, Any]:
    """A page of a period's entries, oldest first, as asked: of a kind, such as admin; an
    action, such as approve; a decision, such as deny; an instance; and acting for someone, or
    by them. `next` is where the next page starts, after, if there's more."""
    first, last = _span(conn, since, until, after)
    limit = max(1, min(limit, MOST))
    rows = conn.execute(
        "select seq, entry from ledger where seq between %(first)s and %(last)s "
        "and (%(kind)s::text is null or kind = %(kind)s) "
        "and (%(action)s::text is null or action = %(action)s) "
        "and (%(decision)s::text is null or decision = %(decision)s) "
        "and (%(instance)s::text is null or instance_id = %(instance)s) "
        "and (%(person)s::text is null or (entry::jsonb->'acts_for') ? %(person)s "
        "     or entry::jsonb->'args'->>'by' = %(person)s) "
        "order by seq limit %(limit)s",
        {"first": first, "last": last, "kind": kind, "action": action, "decision": decision,
         "instance": instance, "person": person, "limit": limit}).fetchall()
    return {"entries": [json.loads(r["entry"]) for r in rows],
            "next": rows[-1]["seq"] if len(rows) == limit else None}


def export(conn: psycopg.Connection, *, since: datetime | None = None,
           until: datetime | None = None, after: int = 0,
           limit: int = MOST_EXPORTED) -> dict[str, Any]:
    """A page of a period's entries exactly as the ledger holds them, oldest first: each with
    its hash and the one before, as the locked copies hold them. `next` is where the next page
    starts, after, if there's more; `head` is the ledger's last entry as it was exported."""
    first, last = _span(conn, since, until, after)
    rows = conn.execute(
        "select seq, entry, prev_hash, hash from ledger where seq between %s and %s "
        "order by seq limit %s", (first, last, max(1, min(limit, MOST_EXPORTED)))).fetchall()
    head = conn.execute("select seq, hash from ledger order by seq desc limit 1").fetchone()
    return {"entries": [{"seq": r["seq"], "entry": r["entry"],
                         "prev_hash": bytes(r["prev_hash"]).hex(), "hash": bytes(r["hash"]).hex()}
                        for r in rows],
            "next": rows[-1]["seq"] if rows and rows[-1]["seq"] < last else None,
            "head": {"seq": head["seq"], "hash": bytes(head["hash"]).hex()} if head else None}


def checks(lines: Iterable[dict[str, Any]]) -> str | None:
    """Why an export doesn't hold together, if it doesn't: each entry's hash must be its
    own, its number one more than the last, and its hash before the last one's. None if it
    holds together, which shows nothing was changed, left out or put in after export."""
    prev: str | None = None
    number: int | None = None
    for line in lines:
        seq, entry = line.get("seq"), line.get("entry")
        if not isinstance(seq, int) or not isinstance(entry, str):
            return "a line isn't one of the ledger's entries"
        if number is not None and seq != number + 1:
            return f"entry {seq} doesn't follow entry {number}"
        if prev is not None and line.get("prev_hash") != prev:
            return f"entry {seq} doesn't continue from entry {number}"
        try:
            before = bytes.fromhex(line.get("prev_hash", ""))
        except ValueError:
            return f"entry {seq}'s hash before isn't one"
        if seq == 1 and before != GENESIS:
            return "the ledger's first entry continues from nothing"
        if hashlib.sha256(before + entry.encode()).hexdigest() != line.get("hash") \
                or json.loads(entry).get("seq") != seq:
            return f"entry {seq} isn't as the ledger made it"
        prev, number = line["hash"], seq
    return None


def copied(lines: list[dict[str, Any]], store: Any) -> str | None:
    """Why an export doesn't match the ledger's locked copies, if it doesn't: each of its
    entries must be in a copied segment, with the same hash. None if each is."""
    from a5s.core import anchor

    want = {line["seq"]: line["hash"] for line in lines}
    found, _ = anchor._heads(store)
    seq, prev = 0, GENESIS
    while want and (candidates := [c for c in found.pop(seq + 1, [])
                                   if c.head.prev in ("", prev.hex())]):
        for copy in candidates:
            if (rows := anchor._rows(store, copy.head, prev)) is not None:
                break
        else:
            break
        for row in rows:
            if row["seq"] in want and want.pop(row["seq"]) != row["hash"]:
                return f"entry {row['seq']} differs from the ledger's locked copy {copy.key}"
        seq, prev = copy.head.seq, bytes.fromhex(copy.head.hash)
    if want:
        return (f"entries from {min(want)} on aren't in the locked copies, which a5s makes "
                "every hour: check again later")
    return None


ADMIN = {"approve": "approved settings", "propose": "proposed settings",
         "apply": "applied settings", "approve-release": "approved a release",
         "decide": "decided held changes", "grade": "graded samples",
         "suspend": "suspended or resumed an instance", "retire": "retired an instance",
         "restore": "restored an instance", "end-change": "ended a held change",
         "export": "exported someone's data", "erase": "erased someone's data",
         "archive": "archived a leaver", "request": "asked as the data protection officer",
         "ask": "asked for approval", "refuse-sign-in": "a sign-in refused"}


def roles_of(scenario: Any, parts: Iterable[str], agents: Iterable[str]) -> list[dict]:
    """Who holds each of a5s's roles now, as the directory says."""
    names = [INSTANCE_APPROVER, RELEASE_APPROVER, ASSURANCE, DATA_PROTECTION, AUDITOR, "grader",
             *(f"{PART_OWNER}:{p}" for p in sorted(set(parts))),
             *(f"{PART_DELEGATE}:{p}" for p in sorted(set(parts))),
             *(f"agent-owner:{a}" for a in sorted(set(agents)))]
    return [{"role": name, "held_by": sorted(p.id for p in scenario.holders(name))}
            for name in names]


def report(conn: psycopg.Connection, scenario: Any, agents: Iterable[str], *,
           since: datetime | None = None, until: datetime | None = None) -> dict[str, Any]:
    """Who holds each role now, and each administrative act of a period: who did it, when,
    and to what, as the ledger records it."""
    parts = [r["part"] for r in conn.execute(
        "select distinct jsonb_object_keys(parts) as part from instances")]
    acts, after = [], 0
    while True:
        page = search(conn, since=since, until=until, kind="admin", after=after)
        for entry in page["entries"]:
            args = entry.get("args") or {}
            acts.append({"seq": entry["seq"], "at": entry.get("at"), "action": entry["action"],
                         "what": ADMIN.get(entry["action"], entry["action"]),
                         "by": args.get("by") or args.get("signed_by"),
                         "instance": entry.get("instance"),
                         "about": {k: v for k, v in args.items()
                                   if k not in ("by", "signed_by", "identity")}})
        if not page["next"]:
            return {"roles": roles_of(scenario, parts, agents), "acts": acts}
        after = page["next"]


def noted(conn: psycopg.Connection, by: str, read: str, **what: Any) -> int:
    """Put a read of the trail, a search, an export or a report, in the ledger: who read it,
    and what they asked for, with whom they asked about by hash alone."""
    return ledger.append(conn, {"kind": "audit", "action": read, "run": None, "instance": None,
                                "acts_for": [], "decision": "record",
                                "args": ledger.mask({k: v for k, v in {"by": by, **what}.items()
                                                     if v is not None}, plain=_PLAIN)})
