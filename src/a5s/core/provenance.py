"""Provenance: whose a value is, answered in code, never by asking the model.

The keys, amounts and dates an agent writes are matched exactly against what its run has
read (core/values.py): the records, through its tools and the brief a5s gave it, a5s's own
tasks, and what the person said, in their messages and in the facts its summaries keep for
them. A match carries its source. Anything else is the agent's own, and code says so apart
from the agent's words, in a note on what it wrote. Free text is always the agent's own.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from a5s.contract import Scenario
from a5s.core import groups, values
from a5s.core.values import Value

THEY = "they said it"
A5S = "a5s"
OUTSIDE = "outside"  # a document from outside the organisation, as a5s's reader read it


def read(conn: psycopg.Connection, run: str, source: str, said: Any, pattern: str | None) -> None:
    """Note the values a run read, and where from."""
    text = said if isinstance(said, str) else json.dumps(said, ensure_ascii=False, default=str)
    noted(conn, run, source, values.found(text, pattern))


def noted(conn: psycopg.Connection, run: str, source: str, found: list[Value]) -> None:
    """Note values a run read, as found, and where from."""
    for v in found:
        conn.execute("insert into run_reads (run_id, source, kind, norm, text) "
                     "values (%s, %s, %s, %s, %s) on conflict do nothing",
                     (run, source, v.kind, v.norm, v.text))


ABOUT = " about "  # in what a run read of each record a tool's result held: "<tool> about <key>"


def read_records(conn: psycopg.Connection, run: str, tool: str, field: str | None, result: Any,
                 pattern: str | None) -> None:
    """Note what a tool's result said of each record in it, by its key, apart: each item that
    names a record by `field`, without the records within it, which are items of their own. So
    a note can be checked against what the run read of the records it names (core/notebook.py)."""
    if not field:
        return

    def named(value: Any) -> str | None:
        key = value.get(field) if isinstance(value, dict) else None
        return key if isinstance(key, str) and key else None

    def alone(value: Any) -> Any:  # the item, with the records in it as their keys
        if isinstance(value, dict):
            return {k: named(v) or alone(v) for k, v in value.items()}
        if isinstance(value, list):
            return [named(v) or alone(v) for v in value]
        return value

    def walk(value: Any) -> None:
        if (key := named(value)) is not None:
            read(conn, run, f"{tool}{ABOUT}{key}", alone(value), pattern)
        for v in value.values() if isinstance(value, dict) else value if isinstance(
                value, list) else ():
            walk(v)

    walk(result)


def records_read(conn: psycopg.Connection, run: str) -> dict[str, list[Value]]:
    """The records a run read with its tools, by key, each with what it read of it."""
    found: dict[str, list[Value]] = {}
    for r in conn.execute("select source, kind, norm, text from run_reads where run_id = %s "
                          "and source like %s", (run, f"%{ABOUT}%")):
        key = r["source"].rsplit(ABOUT, 1)[1]
        found.setdefault(key, []).append(Value(r["kind"], r["text"], r["norm"]))
    return found


def sources(conn: psycopg.Connection, scenario: Scenario, run: dict) -> list[tuple[Value, str]]:
    """What the run has read, and from where: its tools, a5s's briefs and tasks, and, when it
    acts for one person, what they said."""
    pattern = getattr(scenario, "record_pattern", None)
    found = [(Value(r["kind"], r["text"], r["norm"]), r["source"]) for r in conn.execute(
        "select * from run_reads where run_id = %s", (run["run"],))]
    group = run["trigger"].get("conversation")  # in a group chat, what anyone in it said that
    group = group if groups.of(group) else None  # everyone now in it heard
    if len(run["acts_for"]) != 1 and not group:
        return found
    who = group or run["acts_for"][0]
    person = None if group else scenario.person(who)
    if inbound := run["trigger"].get("inbound"):
        row = conn.execute("select text from inbound where id = %s", (inbound,)).fetchone()
        found += [(v, THEY) for v in values.found(row["text"] if row else "", pattern)]
    heard = " and heard_by @> %(members)s::text[]" if group else ""
    for row in conn.execute(  # not the agent's words, nor a5s's notes on them, which name
            "select role, content from turns where person = %(who)s and agent = %(agent)s "
            "and role <> 'agent' and not (role = 'notice' and content like '(a5s:%%')"
            f"{heard} order by id desc limit 500",  # its own values
            {"who": who, "agent": run["definition"], "members": list(run["acts_for"])}):
        found += [(v, THEY if row["role"] == "person" else A5S)
                  for v in values.found(row["content"], pattern)]
    for row in conn.execute(  # in a group, the summaries everyone it acts for heard all of
            "select body, heard_by from summaries where person = %s and agent = %s",
            (who, run["definition"])):
        if group and not set(run["acts_for"]) <= set(row["heard_by"] or ()):
            continue
        found += [(Value(f["kind"], f["value"], f["norm"]), THEY) for f in row["body"].get("facts", [])
                  if (f.get("speaker") if group else person is not None and f["who"] == person.name)]
    return found


def traced(conn: psycopg.Connection, scenario: Scenario, run: dict, text: str) -> list[dict]:
    """Each key, amount and date in what an agent wrote, with where it came from, or None
    where it's the agent's own."""
    known = sources(conn, scenario, run)  # where else a value came from, before outside

    def source(v: Value) -> str | None:
        return next((s for k, s in known if v.matches(k) and not s.startswith(OUTSIDE)),
                    next((s for k, s in known if v.matches(k)), None))

    return [{"value": v.text, "kind": v.kind, "from": source(v)}
            for v in values.found(text, getattr(scenario, "record_pattern", None))]


def note(agent: str, own: list[str]) -> str:
    """a5s's words on what the agent wrote itself, for people to see apart from its own."""
    which = own[0] if len(own) == 1 else f"{', '.join(own[:-1])} and {own[-1]}"
    them = "it" if len(own) == 1 else "them"
    return (f"(a5s: {which} came from the {agent} itself, not from the records or from you, "
            f"so check {them} before you rely on {them}.)")
