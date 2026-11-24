"""Someone outside the directory, such as a customer who writes to a shared mailbox: what a5s
keeps that names them, by their address, for their request to see it, or to erase it, which the
data protection officer asks for as for anyone (core/officer.py; docs/data-protection.md).

a5s keeps little of them, and briefly: whom a message came from reaches a run as a handle, whose
value goes an hour after the run, with what a5s's reader read of their mail. But their address
can stay longer where a5s wrote it out for someone, such as in an answer to the team that named
them, where someone wrote it in a message, and in the words of a change an agent asked for.

An export says where a5s keeps their address, and how much: the texts themselves are other
people's conversations, which the officer reads as the organisation's records, if the request
needs them. An erasure puts a stand-in for their address in each of those texts, and lets go
of each handle and document of theirs. What's evidence of what agents did stays, as it does
for anyone a5s erases: the changes agents asked for that name them, and the samples of those,
until their time to keep ends (core/retention.py). It waits for nothing: while a run holds
their address, or a change that names them waits for a decision, it refuses, saying which.
The ledger records each, by a digest of their address, never the address.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, LiteralString

from a5s import db
from a5s.core import proposals

ADDRESS = re.compile(r"[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"'.]+")
STAND_IN = "[an address a5s erased]"  # in each text that held it
# Where a5s keeps words that may hold someone's address, each in the words of what it is, by
# its table, the column of its words, and when it was written
TEXTS: dict[str, tuple[LiteralString, LiteralString, LiteralString]] = {
    "messages a5s sent people": ("outbox", "text", "at"),
    "items waiting for someone's digest": ("digest_items", "text", "at"),
    "urgent messages held for someone": ("urgent_held", "text", "at"),
    "messages people sent agents": ("inbound", "text", "received_at"),
    "what people and agents said in conversations": ("turns", "content", "at"),
    "summaries of conversations": ("summaries", "body::text", "updated_at"),
    "what people said of agents' answers that were wrong": ("answer_feedback", "said", "at"),
    "tasks people asked for": ("tasks", "task", "created_at"),
}
# How each takes a stand-in for the address: in its words, or, for a summary, in its form
_PUT: dict[str, LiteralString] = {
    "summaries": "body = regexp_replace(body::text, %(pattern)s, %(stand_in)s, 'gi')::jsonb",
}


class Busy(Exception):
    """A run holds their address now: it might write it out once they're erased."""


class Waiting(Exception):
    """Changes that name them wait for a decision, or are being made, with their address."""

    def __init__(self, keys: list[str]):
        super().__init__(", ".join(keys))
        self.keys = keys


def is_address(person: str) -> bool:
    """Whether a request names someone by their address, rather than by the directory's id."""
    return ADDRESS.fullmatch(person.strip()) is not None


DIGESTED = "address:"  # how the ledger names someone by their address, then its digest


def subject(person: str) -> str:
    """Whom a request is about, as the ledger keeps it: an address by its digest alone."""
    if not is_address(person):
        return person
    return DIGESTED + hashlib.sha256(person.strip().lower().encode()).hexdigest()


def gather(conn: db.Connection, address: str) -> dict[str, Any]:
    """Where a5s keeps someone's address, and how much of it, for their request to see what
    a5s keeps about them: the runs that held it as a handle, and the documents a5s's reader
    read for them, each for an hour after its run; each kind of text that holds it, how many
    and from when to when; and the changes asked for that name them, with the samples of
    those, which stay as evidence."""
    given = {"address": address.strip().lower()}
    held = conn.execute(
        "select count(distinct h.run_id) as runs, min(r.opened_at) as first, max(r.opened_at) "
        "as last, (select count(*) from run_documents d where d.run_id in (select run_id from "
        "run_handles where lower(value) = %(address)s) or strpos(lower(d.text), %(address)s) > "
        "0) as documents from run_handles h join runs r on r.id = h.run_id where lower(h.value) "
        "= %(address)s", given).fetchone() or {}
    texts = {}
    for kind, (table, column, at) in TEXTS.items():
        found = conn.execute(
            f"select count(*) as n, min({at}) as first, max({at}) as last from {table} where "
            f"strpos(lower({column}), %(address)s) > 0", given).fetchone() or {}
        if found.get("n"):
            texts[kind] = {"n": found["n"], "first": _iso(found["first"]),
                           "last": _iso(found["last"])}
    changes = conn.execute(
        "select p.*, (select count(*) from samples s where s.proposal_id = p.id) as samples "
        "from proposals p where strpos(lower(p.said), %(address)s) > 0 or exists (select 1 from "
        "proposal_values v where v.proposal_id = p.id and lower(v.value) = %(address)s) "
        "order by p.id", given).fetchall()
    return {"address": address.strip(),
            "runs": {"n": held.get("runs") or 0, "first": _iso(held.get("first")),
                     "last": _iso(held.get("last"))},
            "documents": held.get("documents") or 0,
            "texts": texts,
            "changes": [{"key": proposals.key(p), "change": proposals.first(p),
                         "status": p["status"], "proposed_at": _iso(p["proposed_at"]),
                         "samples": p["samples"]} for p in changes]}


def holds(found: dict[str, Any]) -> bool:
    """Whether a5s keeps anything that names them."""
    return bool(found["runs"]["n"] or found["documents"] or found["texts"] or found["changes"])


def counts(found: dict[str, Any]) -> dict[str, int]:
    """What an export gave, in counts, for the ledger."""
    return {"runs": found["runs"]["n"], "documents": found["documents"],
            **{kind: t["n"] for kind, t in found["texts"].items()},
            "changes": len(found["changes"])}


def erase(conn: db.Connection, address: str) -> dict[str, Any]:
    """Erase someone's address from what a5s keeps, in the caller's transaction: a stand-in
    for it in each text, and each handle and document of theirs let go. How much of each went,
    and the changes that name them, which stay as evidence. Busy while a run holds their
    address; Waiting while a change that names them waits for a decision, or is being made."""
    given = {"address": address.strip().lower(), "stand_in": STAND_IN,
             "pattern": re.escape(address.strip())}
    if conn.execute("select 1 from run_handles h join runs r on r.id = h.run_id where "
                    "lower(h.value) = %(address)s and r.closed_at is null limit 1",
                    given).fetchone():
        raise Busy(address)
    waiting = [proposals.key(p) for p in conn.execute(
        "select p.id from proposals p where p.status in ('waiting', 'making') and "
        "(strpos(lower(p.said), %(address)s) > 0 or exists (select 1 from proposal_values v "
        "where v.proposal_id = p.id and lower(v.value) = %(address)s)) order by p.id",
        given).fetchall()]
    if waiting:
        raise Waiting(waiting)
    gone: dict[str, int] = {}
    if count := conn.execute(
            "delete from run_documents where run_id in (select run_id from run_handles where "
            "lower(value) = %(address)s) or strpos(lower(text), %(address)s) > 0",
            given).rowcount:
        gone["documents a5s's reader read for runs"] = count
    if count := conn.execute("delete from run_handles where lower(value) = %(address)s",
                             given).rowcount:
        gone["handles runs held it as"] = count
    for kind, (table, column, _) in TEXTS.items():
        put = _PUT.get(table) or f"{column} = regexp_replace({column}, %(pattern)s, " \
                                  "%(stand_in)s, 'gi')"
        if count := conn.execute(f"update {table} set {put} where strpos(lower({column}), "
                                 "%(address)s) > 0", given).rowcount:
            gone[kind] = count
    kept = [proposals.key(p) for p in conn.execute(
        "select id from proposals where strpos(lower(said), %(address)s) > 0 order by id",
        given).fetchall()]
    return {"gone": gone, "kept": kept}


def _iso(at: Any) -> str | None:
    return at.isoformat() if at is not None else None
