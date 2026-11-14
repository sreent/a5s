"""The notebook: what an agent learns from records, kept for its instance's later runs (phase 3,
step 3).

An agent notes something it learned, such as which kind of question comes up on a kind of
record, with the typed tool note_learned, naming the records it comes from. Only a run that acts
for nobody can note, such as one on a schedule its release brings: its context holds its task
and what its tools return, and nobody's words, so what it notes comes from records alone, never
from what someone said, and a run that has read content from outside notes nothing. Code keeps
an entry only if every record it names is one the run read with its tools, in its instance's
parts, and every key, amount and date in it is in what the run read of those records, or in
them as they stand. The notebook keeps the newest 50.

A note is given only where everyone may see every record its run read with its tools, not just
those it names, since what it says may draw on any of them. A run for people is given the notes
about the record its case is about, beside the case's brief, as something to check, never every
note: a run for nobody, such as the schedule that keeps them, is given them all. Each day, apart
from any other sweep, code reads each note's records again, and a note whose records changed
goes. The agent's owner reads the entries on the core's page, and removes any, and the ledger
records each entry noted, lapsed or removed, by its hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import record_of
from a5s.core import ledger, parts, provenance, values
from a5s.core.coretools import Call, CoreTool, Refused

log = logging.getLogger(__name__)

NOTE = "note_learned"
LONGEST = 300  # characters of an entry
SOURCES = 10  # records an entry may name
MOST = 50  # entries an instance keeps: the newest [TBC]
CHECK_EVERY = timedelta(days=1)  # how often a note's records are read again
CHECKED = 200  # notes checked in one sweep, oldest checked first
SHOWN = 2000  # characters of entries a run is given


def fingerprint(record: Any) -> str | None:
    """A record's fields, as a digest: a note stands while its records' are unchanged."""
    if record is None:
        return None
    return hashlib.sha256(json.dumps(record.fields, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def _norm(scenario: Any, key: str) -> str:
    return next((v.norm for v in values.found(key, scenario.record_pattern) if v.kind == "key"),
                key)


def note(call: Call) -> dict:
    run = call.run
    if run["trigger"].get("kind") != "schedule" or run["acts_for"]:
        raise Refused("an agent notes what it learns only in a run that acts for nobody, such as "
                      "one on its schedule, which hears nobody's words: then it's from records "
                      "alone")
    if run["read_outside"]:
        raise Refused("this run has read content from outside, so it notes nothing")
    text = " ".join(str(call.args.get("note", "")).split())
    keys = list(dict.fromkeys(str(k).strip() for k in call.args.get("sources") or []
                              if str(k).strip()))
    if not text:
        raise Refused("say what you learned, in a sentence or two")
    if len(text) > LONGEST:
        raise Refused(f"keep it to {LONGEST} characters: it's a note")
    if not keys or len(keys) > SOURCES:
        raise Refused(f"name the records it comes from, one to {SOURCES}, by their keys")
    read = {_norm(call.scenario, k): (k, said) for k, said in
            provenance.records_read(call.conn, run["run"]).items()}
    if unread := [k for k in keys if _norm(call.scenario, k) not in read]:
        raise Refused(f"it comes only from records this run read with its tools, and it didn't "
                      f"read {', '.join(unread)}")
    if outside := [k for k in keys if not parts.workable(call.scenario, run, k)]:
        raise Refused(f"{', '.join(outside)} isn't in a part this agent works in")
    standing = {k: record_of(call.scenario, k) for k in keys}
    if gone := [k for k, r in standing.items() if r is None]:
        raise Refused(f"the records have no {', '.join(gone)}")
    held = [v for k in keys for v in read[_norm(call.scenario, k)][1]] + [
        v for k, r in standing.items() for v in values.found(
            json.dumps({k: r.fields}, ensure_ascii=False, default=str), call.scenario.record_pattern)]
    if wrong := values.unmatched(values.found(text, call.scenario.record_pattern), held):
        raise Refused(f"a note says only what the records it names hold, as this run read them, "
                      f"and they don't hold {', '.join(v.text for v in wrong)}")
    every = sorted(key for key, _ in read.values())  # whoever it reaches may see all it read
    kept = call.conn.execute(  # the newest MOST: a new note makes room, oldest first
        "select * from notebook where instance_id = %s and text <> %s order by written_at, id",
        (run["id"], text)).fetchall()
    for old in kept[:max(0, len(kept) - MOST + 1)]:
        call.conn.execute("delete from notebook where id = %s", (old["id"],))
        ledger.append(call.conn, entry(old, "lapse", f"the notebook keeps the newest {MOST}"))
    row = call.conn.execute(
        "insert into notebook (instance_id, agent, text, sources, written_run, written_at, "
        "renewed_at, read_records, fingerprints, checked_at, links) values (%(instance)s, "
        "%(agent)s, %(text)s, %(sources)s, %(run)s, %(now)s, %(now)s, %(read)s, %(prints)s, "
        "%(now)s, %(links)s) on conflict (instance_id, text) do update set sources = "
        "excluded.sources, renewed_at = excluded.renewed_at, read_records = "
        "excluded.read_records, fingerprints = excluded.fingerprints, checked_at = "
        "excluded.checked_at, links = excluded.links returning id",
        {"instance": run["id"], "agent": run["definition"], "text": text, "sources": keys,
         "run": run["run"], "now": call.now, "read": every,
         "prints": Jsonb({k: fingerprint(r) for k, r in standing.items()}),
         "links": Jsonb({k: r.link for k, r in standing.items() if r.link})}).fetchone()
    return {"noted": f"N-{row['id']}", "sources": keys}


TOOL = CoreTool(
    NOTE,
    "Note something you learned from the records, for your later runs, such as which kind of "
    "question comes up on a kind of record, in a sentence or two, naming the records it comes "
    "from by the keys your tools gave you. Only what those records hold, as you read them: "
    "nobody's words, and a run that has read content from outside, such as someone's message, "
    "notes nothing. Your later runs see it beside the records it names, and check them before "
    "relying on it. Each note reaches only people who may see every record this run read.",
    {"type": "object", "required": ["note", "sources"], "properties": {
        "note": {"type": "string", "description": "What you learned, in a sentence or two"},
        "sources": {"type": "array", "items": {"type": "string"},
                    "description": "The keys of the records it comes from, as your tools gave "
                                   "them"}}},
    note, text_fields=("note",),  # offered only to a run that acts for nobody, which may note
    offered=lambda run: not run["acts_for"] and run["trigger"].get("kind") == "schedule")


def given(conn: db.Connection, scenario: Any, run: dict) -> dict | None:
    """The entries a run is given: for people, those about the record its case is about, and
    for nobody, such as the schedule that keeps them, all of them. Only those whose every
    record its run read all the run's people may see, newest first, within a budget. How
    many goes on the run, for the measures (core/measures.py)."""
    people = list(run["acts_for"])
    topic = (run.get("trigger") or {}).get("topic") or "general"
    if people and topic == "general":
        return None
    rows = conn.execute("select * from notebook where instance_id = %s "
                        "and (%s::text is null or %s = any(sources)) "
                        "order by written_at desc, id desc",
                        (run["id"], topic if people else None, topic)).fetchall()
    shown, used = [], 0
    for row in rows:
        if not all(scenario.sees(p, k) for p in people  # one kept before round 7: its own
                   for k in row["read_records"] or row["sources"]):
            continue
        line = f"- {row['text']} (from {', '.join(row['sources'])})"
        if used + len(line) > SHOWN:
            break
        shown.append(line)
        used += len(line)
    if not shown:
        return None
    conn.execute("update runs set notes_given = %s where id = %s", (len(shown), run["run"]))
    return {"title": f"What you've learned from records, about {topic}" if people
            else "What you've learned from records",
            "text": "Notes from your own earlier runs, from records alone, each with the records "
                    "it comes from. Records change: check a record before you rely on a note "
                    "about it, and say what the record says.\n" + "\n".join(shown)}


def check(url: str, scenario: Any, now: datetime) -> dict[str, int]:
    """Read again the records of each note not checked for a day, oldest checked first, and
    let any note whose records changed, or went, go. Records are read outside any transaction,
    so a slow or failing records system holds up nobody else, and a note whose records can't be
    read now waits for the next sweep. Each note is settled in a transaction of its own."""
    with db.transaction(url) as conn:
        rows = conn.execute("select * from notebook where checked_at < %s "
                            "order by checked_at, id limit %s",
                            (now - CHECK_EVERY, CHECKED)).fetchall()
    unread = object()
    prints: dict[str, Any] = {}
    for key in sorted({k for r in rows for k in r["sources"]}):
        try:
            prints[key] = fingerprint(record_of(scenario, key))
        except Exception:  # noqa: BLE001 - the records system's own failure
            log.warning("couldn't read %s to check the notes on it", key)
            prints[key] = unread
    found = {"kept": 0, "lapsed": 0}
    for row in rows:
        if any(prints.get(k) is unread for k in row["sources"]):
            continue
        was = row["fingerprints"] or {}
        with db.transaction(url) as conn:
            if any(prints.get(k) != was.get(k) for k in row["sources"]):
                if gone := conn.execute("delete from notebook where id = %s returning *",
                                        (row["id"],)).fetchone():
                    ledger.append(conn, entry(gone, "lapse", "its records changed"))
                    found["lapsed"] += 1
            else:
                conn.execute("update notebook set checked_at = %s where id = %s",
                             (now, row["id"]))
                found["kept"] += 1
    return found


def entry(row: dict, action: str, why: str, by: str | None = None) -> dict:
    """The ledger's record of what became of an entry: by its hash, never its words."""
    return {"kind": "notebook", "action": action, "run": None, "instance": row["instance_id"],
            "acts_for": [], "decision": "record",
            "args": {"entry": f"N-{row['id']}", "sources": list(row["sources"]), "why": why,
                     "sha256": hashlib.sha256(row["text"].encode()).hexdigest(),
                     **({"by": by} if by else {})}}
