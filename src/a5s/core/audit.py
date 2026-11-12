"""The audit trail: the ledger as an auditor reads it (docs/administration.md).

Entries are found by period, kind, action, decision, instance and person, a page at a time.
A period is exported as the ledger holds it: each entry with its hash and the one before, a
line each, as the locked copies hold them, so anyone can check the chain, and, with the copies,
that it's the ledger's own. A report says who holds each role, and who approved, decided,
released, suspended, exported or erased what. Each search, export and report is itself in
the ledger, so reading the trail leaves a trace too.

The ledger keeps what anyone said only by hash, so nothing here holds it. Only someone with the
auditor's role, or assurance's, reads the trail: through the core's API, for the team that runs
a5s, and on their own page in the channels app. There, whoever acted in one of a5s's roles shows
as themselves, and everyone else an entry names, such as whom agents acted for, shows as a
stand-in, the same one each time, until the data protection officer agrees to names.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
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
STAND_IN = "person-"  # how a stand-in for someone starts
_STAND_IN = re.compile(r"person-[0-9a-f]{12}")
ACTORS = ("admin", "audit", "proposal")  # entries whose `by` acted in one of a5s's roles
ACTING = ("by", "signed_by")  # where those entries name who acted
# The kinds of entry a5s writes, for the auditors' page to offer
KINDS = ("admin", "audit", "breaker", "budget", "cap", "inbound", "message", "model", "notice",
         "proposal", "repeat", "retention", "run", "task", "tool")


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
           acted_for: str | None = None, by: str | None = None, after: int = 0,
           limit: int = MOST) -> dict[str, Any]:
    """A page of a period's entries, oldest first, as asked: of a kind, such as admin; an
    action, such as approve; a decision, such as deny; an instance; acting for someone, or by
    them (`person`); acting for someone alone (`acted_for`); or where someone acted in one of
    a5s's roles, such as approving (`by`). `next` is where the next page starts, after, if
    there's more."""
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
        "and (%(acted_for)s::text is null or (entry::jsonb->'acts_for') ? %(acted_for)s) "
        "and (%(by)s::text is null or (kind = any(%(actors)s) and ("
        "     entry::jsonb->'args'->'by' ? %(by)s or entry::jsonb->'args'->'signed_by' ? %(by)s))) "
        "order by seq limit %(limit)s",
        {"first": first, "last": last, "kind": kind, "action": action, "decision": decision,
         "instance": instance, "person": person, "acted_for": acted_for, "by": by,
         "actors": list(ACTORS), "limit": limit}).fetchall()
    return {"entries": [json.loads(r["entry"]) for r in rows],
            "next": rows[-1]["seq"] if len(rows) == limit else None}


def _line(row: dict) -> dict[str, Any]:
    return {"seq": row["seq"], "entry": row["entry"], "prev_hash": bytes(row["prev_hash"]).hex(),
            "hash": bytes(row["hash"]).hex()}


def export(conn: psycopg.Connection, *, since: datetime | None = None,
           until: datetime | None = None, after: int = 0,
           limit: int = MOST_EXPORTED) -> dict[str, Any]:
    """A page of a period's entries exactly as the ledger holds them, oldest first: each with
    its hash and the one before, as the locked copies hold them. `next` is where the next page
    starts, after, if there's more; `head` is the ledger's last entry as it was exported; and
    `bounds` is the period, its first and last entries, and the entries either side of it, the
    last made before it and the first made after, so a check of the export, against the
    locked copies, shows it holds the whole period, from its start to its end (`bounded`)."""
    start, last = _span(conn, since, until, 0)  # the period's, as the page is read
    first = max(after + 1, start)
    rows = conn.execute(
        "select seq, entry, prev_hash, hash from ledger where seq between %s and %s "
        "order by seq limit %s", (first, last, max(1, min(limit, MOST_EXPORTED)))).fetchall()
    head = conn.execute("select seq, hash from ledger order by seq desc limit 1").fetchone()
    end = last
    either = {r["seq"]: _line(r) for r in conn.execute(
        "select seq, entry, prev_hash, hash from ledger where seq = any(%s)",
        ([start - 1, end + 1],))}
    return {"entries": [_line(r) for r in rows],
            "next": rows[-1]["seq"] if rows and rows[-1]["seq"] < last else None,
            "head": {"seq": head["seq"], "hash": bytes(head["hash"]).hex()} if head else None,
            "bounds": {"since": _utc(since).isoformat() if since else None,
                       "until": _utc(until).isoformat() if until else None,
                       "first": start, "last": end, "before": either.get(start - 1),
                       "after": either.get(end + 1)}}


def _made(line: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(line["entry"])["at"])
    except (KeyError, TypeError, ValueError):
        return None


def bounded(bounds: dict[str, Any], lines: list[dict[str, Any]]) -> str | None:
    """Why an export doesn't hold the period it says it does, from its start to its end, if
    it doesn't: its first and last entries must be the period's, the entry before it, made
    before the period began, must end where its first begins, and the entry after it, made
    once the period was over, must begin where its last ends. Call `checks` first. Alone it
    shows only that the export agrees with itself: against the locked copies (`copied` of the
    entries either side too, then `ended`), that it's the ledger's own, whole."""
    first, last = bounds.get("first"), bounds.get("last")
    if not isinstance(first, int) or not isinstance(last, int):
        return "it doesn't say which of the ledger's entries the period holds"
    held = (lines[0]["seq"], lines[-1]["seq"]) if lines else None
    if held != ((first, last) if first <= last else None):
        return (f"the period's entries are {first} to {last}, but it holds "
                + (f"{held[0]} to {held[1]}" if held else "none"))
    since = datetime.fromisoformat(bounds["since"]) if bounds.get("since") else None
    until = datetime.fromisoformat(bounds["until"]) if bounds.get("until") else None
    before, after = bounds.get("before"), bounds.get("after")
    if first > 1:
        if not before or before.get("seq") != first - 1 or checks([before]):
            return "it doesn't give the entry before the period as the ledger made it"
        if lines and before["hash"] != lines[0]["prev_hash"]:
            return "its first entry doesn't follow the entry before the period"
        if since and ((made := _made(before)) is None or made >= since):
            return f"the entry before the period, {first - 1}, was made in it"
    if after:
        if after.get("seq") != last + 1 or checks([after]):
            return "it doesn't give the entry after the period as the ledger made it"
        if lines and after["prev_hash"] != lines[-1]["hash"]:
            return "the entry after the period doesn't follow its last entry"
        if until and ((made := _made(after)) is None or made < until):
            return f"the entry after the period, {last + 1}, was made in it"
    return None


def either_side(bounds: dict[str, Any]) -> list[dict[str, Any]]:
    """The entries either side of an export's period, which the locked copies hold too."""
    return [line for line in (bounds.get("before"), bounds.get("after")) if line]


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


def _stored(store: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Each entry the ledger's locked copies hold, in order, with the copy that holds it, as
    far as the copies go on from one another."""
    from a5s.core import anchor

    found, _ = anchor._heads(store)
    seq, prev = 0, GENESIS
    while candidates := [c for c in found.pop(seq + 1, []) if c.head.prev in ("", prev.hex())]:
        for copy in candidates:
            if (rows := anchor._rows(store, copy.head, prev)) is not None:
                break
        else:
            return
        for row in rows:
            yield copy.key, row
        seq, prev = copy.head.seq, bytes.fromhex(copy.head.hash)


def copied(lines: list[dict[str, Any]], store: Any) -> str | None:
    """Why an export doesn't match the ledger's locked copies, if it doesn't: each of its
    entries must be in a copied segment, with the same hash. None if each is."""
    want = {line["seq"]: line["hash"] for line in lines}
    for key, row in _stored(store):
        if not want:
            break
        if row["seq"] in want and want.pop(row["seq"]) != row["hash"]:
            return f"entry {row['seq']} differs from the ledger's locked copy {key}"
    if want:
        return (f"entries from {min(want)} on aren't in the locked copies, which a5s makes "
                "every hour: check again later")
    return None


def ended(bounds: dict[str, Any], store: Any) -> str | None:
    """Why the locked copies show that an export's period went on past where it says it
    ended, if they do: an export that gives no entry after its period, to a time it was
    asked for, whose copies hold the next entry, made before that time. None otherwise."""
    if bounds.get("after") or not bounds.get("until") or not isinstance(bounds.get("last"), int):
        return None
    until, nxt = datetime.fromisoformat(bounds["until"]), bounds["last"] + 1
    for key, row in _stored(store):
        if row["seq"] == nxt:
            made = _made(row)
            if made is not None and made < until:
                return (f"the locked copy {key} holds entry {nxt}, made in the period, which "
                        "the export leaves out")
            return None
    return None


def key(conn: psycopg.Connection) -> bytes:
    """The deployment's own key for stand-ins: made once, at random, and kept only in the
    database, so nobody who reads the trail can work a stand-in back to whom it's for."""
    conn.execute("insert into audit_key (key) values (%s) on conflict do nothing",
                 (secrets.token_bytes(32),))
    return bytes(conn.execute("select key from audit_key").fetchone()["key"])


def stand_in(secret: bytes, person: str) -> str:
    """Someone's stand-in, the same each time in a deployment, and no other's."""
    return STAND_IN + hmac.new(secret, person.encode(), hashlib.sha256).hexdigest()[:12]


@dataclass
class Shown:
    """How the auditors' page shows the trail. Whoever acted in one of a5s's roles, approving,
    deciding, signing or reading the trail, shows as themselves, since that's what an audit
    checks. Until the data protection officer agrees to names (`names`), everyone else an
    entry names, whom agents acted for, told or asked about, shows as a stand-in. Text that
    names someone in passing, such as a reason, and what the ledger keeps by hash, show as
    the ledger keeps them."""

    scenario: Any
    secret: bytes
    names: bool = False
    _seen: dict[str, str] = field(default_factory=dict)

    def person(self, value: Any) -> Any:
        """Someone's id as the page shows it: themselves once names are agreed, else their
        stand-in; and anything that isn't someone the directory knows, as it is."""
        if self.names or not isinstance(value, str):
            return value
        if value not in self._seen:
            known = self.scenario.person(value) is not None
            self._seen[value] = stand_in(self.secret, value) if known else value
        return self._seen[value]

    def _named(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._named(v) for v in value]
        if isinstance(value, dict):
            return {k: self._named(v) for k, v in value.items()}
        return self.person(value)

    def entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """An entry as the page shows it: whom it acted for, and everyone its arguments name,
        as stand-ins, but for whoever acted in one of a5s's roles."""
        if self.names:
            return entry
        args = entry.get("args") if isinstance(entry.get("args"), dict) else None
        shown = dict(entry)
        if "acts_for" in entry:
            shown["acts_for"] = self._named(entry["acts_for"])
        if args is not None:
            acting = entry.get("kind") in ACTORS
            shown["args"] = {k: v if acting and k in ACTING else self._named(v)
                             for k, v in args.items()}
        return shown

    def report(self, found: dict[str, Any]) -> dict[str, Any]:
        """The report as the page shows it: each role's holders, and who did each act, as
        themselves; and whom an act was about, such as an export's subject, as a stand-in."""
        if self.names:
            return found
        return {**found, "acts": [{**act, "about": self._named(act["about"])}
                                  for act in found["acts"]]}

    def whom(self, conn: psycopg.Connection, given: str, since: datetime | None = None,
             until: datetime | None = None) -> str | None:
        """Whom a stand-in stands for, among those the period's entries acted for; or, once
        names are agreed, the id given. None for an id before then, so the page never says
        whether agents acted for someone it names."""
        if self.names:
            return given
        if not given.startswith(STAND_IN):
            return None
        first, last = _span(conn, since, until, 0)
        for row in conn.execute(
                "select distinct acted from ledger, "
                "jsonb_array_elements_text(entry::jsonb->'acts_for') acted "
                "where seq between %s and %s", (first, last)):
            if hmac.compare_digest(stand_in(self.secret, row["acted"]), given):
                return row["acted"]
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


WHOM = ("person", "acted_for", "acted_by")  # whom a read asked about, kept as a stand-in


def noted(conn: psycopg.Connection, by: str, read: str, through: str | None = None,
          **what: Any) -> int:
    """Put a read of the trail, a search, an export or a report, in the ledger: who read it,
    and through what, their own sign-in or the core's service token naming them, and what they
    asked for, with whom they asked about as a stand-in, under the deployment's own key, so
    nobody reading the ledger can work it back to them, as a hash of their id would let them."""
    secret = key(conn)
    for whom in WHOM:
        if isinstance(asked := what.get(whom), str) and not _STAND_IN.fullmatch(asked):
            what[whom] = stand_in(secret, asked)
    return ledger.append(conn, {"kind": "audit", "action": read, "run": None, "instance": None,
                                "acts_for": [], "decision": "record",
                                "args": ledger.mask({k: v for k, v in {
                                    "by": by, "through": through, **what}.items()
                                    if v is not None}, plain=_PLAIN + ("through",) + WHOM)})
