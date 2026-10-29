"""a5s's sample scenario: a stand-in for a real one, with made-up data.

It has a directory of people, a records system of customer questions, and a
store for drafts. It's the test bench for building a5s, locally and in CI.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from a5s import db
from a5s.contract import InstanceSettings, Person, Settings, Signature, Tool, ToolCall

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
            **{**entry, "roles": tuple(entry.get("roles", ()))},
            public_key=key.read_text().strip() if key.exists() else None,
        )

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    # Settings

    def settings(self) -> Settings:
        raw = (self.folder / "settings.yaml").read_bytes()
        data = yaml.safe_load(raw)
        sig_file = self.folder / "settings.sig"
        signed = yaml.safe_load(sig_file.read_text()) if sig_file.exists() else None
        return Settings(
            version=hashlib.sha256(raw).hexdigest()[:16],
            serial=int(data.get("serial", 0)),
            raw=raw,
            signatures=tuple(Signature(s["signer"], s["value"])
                             for s in (signed or {}).get("signatures", [])),
            instances=tuple(
                InstanceSettings(
                    id=iid,
                    definition=i["definition"],
                    serves=tuple(i["serves"]),
                    level=i.get("level"),
                )
                for iid, i in data["instances"].items()
            ),
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
