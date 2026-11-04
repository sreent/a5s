"""a5s's sample scenario: a stand-in for a real one, with made-up data.

It has a directory of people, a records system of customer questions, each in a part of
the business and owed by its owner until it's closed, and a store for drafts. A question's
due date can be changed, and a question closed: the records system keeps each change apart
from the questions as data.yaml has them. It's the test bench for building a5s, locally and
in CI.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
import yaml
from psycopg import sql

from a5s import db
from a5s.contract import (
    Obligation,
    Person,
    Record,
    Settings,
    Signature,
    Tool,
    ToolCall,
    parse_settings,
)

LINK = "https://sample.a5s.dev/"


class SampleScenario:
    name = "sample"
    record_links = (LINK,)
    record_pattern = r"\bQ-\d{4}\b"  # customer questions' keys, such as Q-1001

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        data = yaml.safe_load((folder / "data.yaml").read_text())
        self._people = {p["id"]: self._person(p) for p in data["people"]}
        self._parts = data.get("parts") or {}
        self._records = {r["key"]: r for r in data["records"]}
        self._messages = data.get("messages") or []

    # Directory

    def _person(self, entry: dict) -> Person:
        key = self.folder / "keys" / f"{entry['id']}.pub"
        return Person(
            **{k: tuple(v) if isinstance(v, list) else v for k, v in entry.items()},
            public_key=key.read_text().strip() if key.exists() else None,
        )

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    # Its own system, kept apart from a5s's tables

    def setup(self, conn: psycopg.Connection, tools_role: str) -> None:
        conn.execute("""
            create schema if not exists sample;
            create table if not exists sample.drafts (
              id bigserial primary key,
              title text not null,
              body text not null,
              created_for text not null,
              at timestamptz not null default now()
            );
            alter table sample.drafts add column if not exists record text;
            create table if not exists sample.changes (
              id bigserial primary key,
              key text not null,
              field text not null,
              value text not null,
              made_for text not null,
              at timestamptz not null default now()
            );
            create index if not exists sample_changes_by_key on sample.changes (key, id)
        """)
        conn.execute(sql.SQL(
            "grant usage on schema sample to {role}; "
            "grant select, insert on sample.drafts, sample.changes to {role}; "
            "grant usage on sequence sample.drafts_id_seq, sample.changes_id_seq to {role}").format(
                role=sql.Identifier(tools_role)))

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._people.values() if p.team == name]

    def part_of(self, record: str) -> str | None:
        found = self._records.get(record)
        return found.get("part") if found else None

    def sees(self, person: str, record: str) -> bool:
        """The team whose part it's in may see a record, and so may any team the part names as
        seeing its records, its owner and whoever is above them."""
        found, who = self._records.get(record), self._people.get(person)
        if found is None or who is None:
            return False
        part = self._parts.get(found.get("part")) or {}
        if who.team == part.get("team") or who.team in (part.get("seen_by") or ()):
            return True
        above, seen = self._people.get(found["owner"]), set()
        while above is not None and above.id not in seen:
            if above.id == person:
                return True
            seen.add(above.id)
            above = self._people.get(above.manager) if above.manager else None
        return False

    # Obligations, from the records

    def obligations(self) -> list[Obligation]:
        """Each open record, owed by its owner from the start of their working day when it
        opened to the end of their working day when it's due."""
        found = []
        for r in self._standing().values():
            owner = self._people.get(r["owner"])
            if r["status"] == "closed" or owner is None:
                continue
            zone = ZoneInfo(owner.timezone)
            found.append(Obligation(
                source="records", record=r["key"], person=owner.id, title=r["title"],
                opened=_on(r["opened"], owner.hours[0], zone), due=_on(r["due"], owner.hours[1], zone),
                link=self._link("records", r["key"])))
        return found

    def watched(self) -> list[Record]:
        """Each record, as its owner stands to it."""
        return [self._record(r) for r in self._standing().values() if r["owner"] in self._people]

    def record(self, key: str) -> Record | None:
        """One record, as watched() stands to it, read on its own."""
        found = self._standing(key).get(key)
        return self._record(found) if found and found["owner"] in self._people else None

    def _standing(self, key: str | None = None) -> dict[str, dict]:
        """The records as they stand: as data.yaml has them, with the changes made since."""
        found = {k: dict(v) for k, v in self._records.items() if key is None or k == key}
        with db.transaction(self.database_url) as conn:
            for row in conn.execute("select key, field, value from sample.changes "
                                    "where %s::text is null or key = %s order by id", (key, key)):
                if row["key"] in found:
                    found[row["key"]][row["field"]] = row["value"]
        return found

    def _record(self, r: dict) -> Record:
        return Record(source="records", key=r["key"], person=r["owner"], title=r["title"],
                      fields={"status": r["status"], "due date": r["due"], "customer": r["customer"]},
                      link=self._link("records", r["key"]))

    # Settings

    def settings(self) -> Settings:
        sig_file = self.folder / "settings.sig"
        signed = yaml.safe_load(sig_file.read_text()) if sig_file.exists() else None
        return parse_settings(
            (self.folder / "settings.yaml").read_bytes(),
            tuple(Signature(s["signer"], s["value"]) for s in (signed or {}).get("signatures", [])),
        )

    def policy_pack(self) -> str | None:
        pack = self.folder / "pack.cedar"
        return pack.read_text() if pack.exists() else None

    # Tools

    def tools(self) -> dict[str, Tool]:
        tools = [
            Tool(
                name="search_records",
                description="Search customer questions by words in their title or status, "
                            "such as \"invoice\" or \"open\". With no words, it lists them all.",
                schema={
                    "type": "object",
                    "properties": {"query": {"type": "string",
                                             "description": "Words to look for, or none for all"}},
                },
                run=self._search_records,
                record_field="key",
            ),
            Tool(
                name="get_record",
                description="Get one customer question by its key, such as Q-1001. Its "
                            "customer's contact comes as a handle, such as [h:7f3a9c2b].",
                schema={
                    "type": "object",
                    "properties": {"key": {"type": "string", "description": "The record key"}},
                    "required": ["key"],
                },
                run=self._get_record,
                handles=("contact",),  # agents pass it on without seeing it
                record_arg="key",
                record_field="key",
            ),
            Tool(
                name="create_draft",
                description="Save a draft for the person to review and use. It sends nothing.",
                schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "record": {"type": "string",
                                   "description": "The record it's about, such as Q-1001, if any"},
                    },
                    "required": ["title", "body"],
                },
                run=self._create_draft,
                writes=True,
                text_fields=("title", "body"),  # drafts keep only text and record links
                record_arg="record",  # in that record's part
            ),
            Tool(
                name="get_messages",
                description="Get the emails a customer sent about one of their questions, by "
                            "its key, such as Q-1001. a5s's reader reads each for you: you get "
                            "what it asks for, and the amounts, dates and keys it names, never "
                            "its words. Ask a5s's reader about an email with ask_about, by its "
                            "number, such as D-1.",
                schema={
                    "type": "object",
                    "properties": {"key": {"type": "string", "description": "The question's key"}},
                    "required": ["key"],
                },
                run=self._get_messages,
                handles=("from",),
                record_arg="key",
                record_field="key",
                outside=("body",),  # the customer's own words, which no agent sees
                extract={"asks_for": "choice:a refund|a copy of an invoice|a new due date|"
                                     "a change of address|something else",
                         "amount": "amount", "date": "date", "question": "key"},
            ),
            Tool(
                name="change_due_date",
                description="Change a customer question's due date.",
                schema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "The question, such as Q-1001"},
                        "due": {"type": "string", "description": "The new due date, as YYYY-MM-DD"},
                    },
                    "required": ["key", "due"],
                },
                run=self._change_due_date,
                record_arg="key",
                action="change-due-date",  # it changes the records: below level 2, a person decides
            ),
            Tool(
                name="close_question",
                description="Close a customer question that's been answered.",
                schema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "The question, such as Q-1001"},
                    },
                    "required": ["key"],
                },
                run=self._close_question,
                record_arg="key",
                action="close-question",
            ),
        ]
        return {t.name: t for t in tools}

    def _link(self, kind: str, key: Any) -> str:
        return f"{LINK}{kind}/{key}"

    def _search_records(self, call: ToolCall) -> list[dict]:
        words = str(call.args.get("query") or "").lower().split()
        hits = [
            r
            for r in self._standing().values()
            if not words or any(w in f"{r['title']} {r['status']}".lower() for w in words)
        ]  # the gateway keeps only those the people the run acts for may see
        return [
            {"key": r["key"], "title": r["title"], "status": r["status"], "link": self._link("records", r["key"])}
            for r in hits
        ]

    def _get_record(self, call: ToolCall) -> dict:
        record = self._standing(call.args["key"]).get(call.args["key"])
        if record is None:
            return {"error": f"no record {call.args['key']}"}
        return {**record, "link": self._link("records", record["key"])}

    def _get_messages(self, call: ToolCall) -> dict:
        key = call.args["key"]
        if key not in self._records:
            return {"error": f"no record {key}"}
        return {"key": key, "link": self._link("records", key),
                "messages": [{"from": m["from"], "at": str(m["at"]), "body": m["body"]}
                             for m in self._messages if m["record"] == key]}

    def _change(self, call: ToolCall, field: str, value: str) -> dict:
        key = call.args["key"]
        if key not in self._records:
            return {"error": f"no record {key}"}
        with db.transaction(self.database_url) as conn:
            conn.execute("insert into sample.changes (key, field, value, made_for) "
                         "values (%s, %s, %s, %s)",
                         (key, field, value, ",".join(call.acts_for) or "nobody"))
        return {"key": key, field: value, "link": self._link("records", key)}

    def _change_due_date(self, call: ToolCall) -> dict:
        try:
            due = date.fromisoformat(str(call.args["due"]))
        except ValueError:
            return {"error": "a due date is written as YYYY-MM-DD"}
        return self._change(call, "due", due.isoformat())

    def _close_question(self, call: ToolCall) -> dict:
        return self._change(call, "status", "closed")

    def _create_draft(self, call: ToolCall) -> dict:
        with db.transaction(self.database_url) as conn:
            row = conn.execute(
                "insert into sample.drafts (title, body, created_for, record) "
                "values (%s, %s, %s, %s) returning id",
                (call.args["title"], call.args["body"], ",".join(call.acts_for) or "nobody",
                 call.args.get("record")),
            ).fetchone()
        return {"draft": row["id"], "link": self._link("drafts", row["id"])}


def _on(day: str | date, at: str, zone: ZoneInfo) -> datetime:
    return datetime.combine(date.fromisoformat(str(day)), time.fromisoformat(at), tzinfo=zone)
