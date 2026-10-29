"""a5s's sample scenario: a stand-in for a real one, with made-up data.

It has a directory of people, a records system of customer questions, each
owed by its owner until it's closed, and a store for drafts. It's the test bench
for building a5s, locally and in CI.
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
from a5s.contract import Obligation, Person, Settings, Signature, Tool, ToolCall, parse_settings

LINK = "https://sample.a5s.dev/"


class SampleScenario:
    name = "sample"
    record_links = (LINK,)

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        data = yaml.safe_load((folder / "data.yaml").read_text())
        self._people = {p["id"]: self._person(p) for p in data["people"]}
        self._records = {r["key"]: r for r in data["records"]}

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
            )
        """)
        conn.execute(sql.SQL(
            "grant usage on schema sample to {role}; "
            "grant select, insert on sample.drafts to {role}; "
            "grant usage on sequence sample.drafts_id_seq to {role}").format(
                role=sql.Identifier(tools_role)))

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    # Obligations, from the records

    def obligations(self) -> list[Obligation]:
        """Each open record, owed by its owner from the start of their working day when it
        opened to the end of their working day when it's due."""
        found = []
        for r in self._records.values():
            owner = self._people.get(r["owner"])
            if r["status"] == "closed" or owner is None:
                continue
            zone = ZoneInfo(owner.timezone)
            found.append(Obligation(
                source="records", record=r["key"], person=owner.id, title=r["title"],
                opened=_on(r["opened"], owner.hours[0], zone), due=_on(r["due"], owner.hours[1], zone),
                link=self._link("records", r["key"])))
        return found

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
                description="Search customer questions by words in their title or status.",
                schema={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Words to look for"}},
                    "required": ["query"],
                },
                run=self._search_records,
            ),
            Tool(
                name="get_record",
                description="Get one customer question by its key, such as Q-1001.",
                schema={
                    "type": "object",
                    "properties": {"key": {"type": "string", "description": "The record key"}},
                    "required": ["key"],
                },
                run=self._get_record,
            ),
            Tool(
                name="create_draft",
                description="Save a draft for the person to review and use. It sends nothing.",
                schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["title", "body"],
                },
                run=self._create_draft,
                writes=True,
                text_fields=("title", "body"),  # drafts keep only text and record links
            ),
        ]
        return {t.name: t for t in tools}

    def _link(self, kind: str, key: Any) -> str:
        return f"{LINK}{kind}/{key}"

    def _search_records(self, call: ToolCall) -> list[dict]:
        words = call.args["query"].lower().split()
        hits = [
            r
            for r in self._records.values()
            if any(w in f"{r['title']} {r['status']}".lower() for w in words)
        ]
        return [
            {"key": r["key"], "title": r["title"], "status": r["status"], "link": self._link("records", r["key"])}
            for r in hits
        ]

    def _get_record(self, call: ToolCall) -> dict:
        record = self._records.get(call.args["key"])
        if record is None:
            return {"error": f"no record {call.args['key']}"}
        return {**record, "link": self._link("records", record["key"])}

    def _create_draft(self, call: ToolCall) -> dict:
        with db.transaction(self.database_url) as conn:
            row = conn.execute(
                "insert into sample.drafts (title, body, created_for) values (%s, %s, %s) "
                "returning id",
                (call.args["title"], call.args["body"], ",".join(call.acts_for) or "nobody"),
            ).fetchone()
        return {"draft": row["id"], "link": self._link("drafts", row["id"])}


def _on(day: str | date, at: str, zone: ZoneInfo) -> datetime:
    return datetime.combine(date.fromisoformat(str(day)), time.fromisoformat(at), tzinfo=zone)
