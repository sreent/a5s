"""The notebook: what an agent learns from records, kept for its instance's later runs (phase 3,
step 3).

An agent notes something it learned, such as which kind of question a customer usually raises,
with the typed tool note_learned, naming the records it comes from. Only a run that acts for
nobody can note, such as one on a schedule its release brings: its context holds its task and
what its tools return, and nobody's words, so what it notes comes from records alone, never from
what someone said, and a run that has read content from outside notes nothing. Code keeps an
entry only if every record it names is one the run read with its tools, in its instance's parts,
and every key, amount and date in it is in those records as they stand.

Each run of the instance is given the entries whose every record all its people may see, newest
first, within a budget. After 90 days an entry whose records still hold everything it says is
renewed, and any other goes. The agent's owner reads the entries on the core's page, and removes
any, and the ledger records each entry noted, renewed, lapsed or removed, by its hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

import psycopg

from a5s.contract import record_of
from a5s.core import ledger, parts, provenance, values
from a5s.core.coretools import Call, CoreTool, Refused

NOTE = "note_learned"
LONGEST = 300  # characters of an entry
SOURCES = 10  # records an entry may name
MOST = 50  # entries an instance keeps [TBC]
EXPIRES = timedelta(days=90)  # an entry is renewed once its records still hold it, or goes
SHOWN = 2000  # characters of entries a run is given


def _in_records(scenario: Any, keys: list[str]) -> tuple[list[values.Value], list[str]]:
    """The keys, amounts and dates the records hold now, and any record that's gone."""
    found, gone = [], []
    for key in keys:
        record = record_of(scenario, key)
        if record is None:
            gone.append(key)
            continue
        found += values.found(json.dumps({key: record.fields}, ensure_ascii=False, default=str),
                              scenario.record_pattern)
    return found, gone


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
        raise Refused(f"name the records it comes from, one to {SOURCES}, such as Q-1001")
    read = {r["norm"] for r in call.conn.execute(
        "select norm from run_reads where run_id = %s and kind = 'key' and source <> all(%s)",
        (run["run"], [provenance.THEY, provenance.A5S, provenance.OUTSIDE]))}
    named = {k: next((v.norm for v in values.found(k, call.scenario.record_pattern)
                      if v.kind == "key"), k) for k in keys}
    if unread := [k for k in keys if named[k] not in read]:
        raise Refused(f"it comes only from records this run read with its tools, and it didn't "
                      f"read {', '.join(unread)}")
    if outside := [k for k in keys if not parts.workable(call.scenario, run, k)]:
        raise Refused(f"{', '.join(outside)} isn't in a part this agent works in")
    held, gone = _in_records(call.scenario, keys)
    if gone:
        raise Refused(f"the records have no {', '.join(gone)}")
    if wrong := values.unmatched(values.found(text, call.scenario.record_pattern), held):
        raise Refused(f"a note says only what the records it names hold, and they don't hold "
                      f"{', '.join(v.text for v in wrong)}")
    kept = call.conn.execute("select count(*) as n from notebook where instance_id = %s",
                             (run["id"],)).fetchone()["n"]
    row = call.conn.execute(
        "insert into notebook (instance_id, agent, text, sources, written_run, written_at, "
        "renewed_at) select %(instance)s, %(agent)s, %(text)s, %(sources)s, %(run)s, %(now)s, "
        "%(now)s where %(kept)s < %(most)s or exists (select 1 from notebook where instance_id = "
        "%(instance)s and text = %(text)s) on conflict (instance_id, text) do update set "
        "sources = excluded.sources, renewed_at = excluded.renewed_at returning id",
        {"instance": run["id"], "agent": run["definition"], "text": text, "sources": keys,
         "run": run["run"], "now": call.now, "kept": kept, "most": MOST}).fetchone()
    if row is None:
        raise Refused(f"the notebook holds {MOST} entries already: its owner removes what's no "
                      "longer worth keeping")
    return {"noted": f"N-{row['id']}", "sources": keys}


TOOL = CoreTool(
    NOTE,
    "Note something you learned from the records, for your later runs, such as which kind of "
    "question a customer usually raises, in a sentence or two, naming the records it comes from. "
    "Only what those records hold: no one's words, and nothing from outside. Your later runs see "
    "it beside the records, which they check before relying on it.",
    {"type": "object", "required": ["note", "sources"], "properties": {
        "note": {"type": "string", "description": "What you learned, in a sentence or two"},
        "sources": {"type": "array", "items": {"type": "string"},
                    "description": "The keys of the records it comes from, such as Q-1001"}}},
    note, text_fields=("note",))


def given(conn: psycopg.Connection, scenario: Any, run: dict) -> dict | None:
    """The entries a run is given: its instance's, whose every record all its people may see,
    newest first, within a budget."""
    people = list(run["acts_for"])
    shown, used = [], 0
    for row in conn.execute("select * from notebook where instance_id = %s "
                            "order by renewed_at desc, id desc", (run["id"],)):
        if not all(scenario.sees(p, k) for p in people for k in row["sources"]):
            continue
        line = f"- {row['text']} (from {', '.join(row['sources'])})"
        if used + len(line) > SHOWN:
            break
        shown.append(line)
        used += len(line)
    if not shown:
        return None
    return {"title": "What you've learned from records",
            "text": "Notes from your own earlier runs, from records alone, each with the records "
                    "it comes from. Records change: check a record before you rely on a note "
                    "about it.\n" + "\n".join(shown)}


def renew(conn: psycopg.Connection, scenario: Any, now: datetime) -> dict[str, int]:
    """Renew each entry 90 days old whose records still hold everything it says, and let the
    rest go."""
    renewed = lapsed = 0
    for row in conn.execute("select * from notebook where renewed_at < %s for update skip locked",
                            (now - EXPIRES,)).fetchall():
        held, gone = _in_records(scenario, list(row["sources"]))
        if not gone and not values.unmatched(values.found(row["text"], scenario.record_pattern),
                                             held):
            conn.execute("update notebook set renewed_at = %s where id = %s", (now, row["id"]))
            renewed += 1
            continue
        conn.execute("delete from notebook where id = %s", (row["id"],))
        ledger.append(conn, entry(row, "lapse", "its records no longer hold it"))
        lapsed += 1
    return {"renewed": renewed, "lapsed": lapsed}


def entry(row: dict, action: str, why: str, by: str | None = None) -> dict:
    """The ledger's record of what became of an entry: by its hash, never its words."""
    return {"kind": "notebook", "action": action, "run": None, "instance": row["instance_id"],
            "acts_for": [], "decision": "record",
            "args": {"entry": f"N-{row['id']}", "sources": list(row["sources"]), "why": why,
                     "sha256": hashlib.sha256(row["text"].encode()).hexdigest(),
                     **({"by": by} if by else {})}}
