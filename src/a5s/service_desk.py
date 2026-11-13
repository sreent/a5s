"""A read-only IT service-desk scenario with a synthetic ITSM and knowledge base."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import yaml

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
from a5s.effects import draft_once
from a5s.knowledge import MarkdownKnowledge

LINK = "https://itsm.desk.test/"


class ServiceDeskScenario:
    name = "service-desk"
    record_links = (LINK,)
    record_pattern = r"\b(?:INC|REQ)\d{7}\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        data = yaml.safe_load((folder / "data.yaml").read_text())
        self._people = {p["id"]: self._person(folder, p) for p in data["people"]}
        self._tickets = {t["key"]: t for t in data["tickets"]}
        self._messages = data.get("messages") or []
        self.drafts = []
        self._draft_lock = threading.Lock()
        self.reads = 0

    @staticmethod
    def _person(folder: Path, entry: dict) -> Person:
        key = folder / "keys" / f"{entry['id']}.pub"
        return Person(**{k: tuple(v) if isinstance(v, list) else v for k, v in entry.items()},
                      public_key=key.read_text().strip() if key.exists() else None)

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._people.values() if p.team == name]

    def part_of(self, record: str) -> str | None:
        return (self._tickets.get(record) or {}).get("part")

    def sees(self, person: str, record: str) -> bool:
        ticket, who = self._tickets.get(record), self._people.get(person)
        if ticket is None or who is None:
            return False
        return person in (ticket["requester"], ticket["assignee"]) or who.team == f"{ticket['part']}-team"

    def _knowledge_part(self, person: str, part: str) -> bool:
        who = self._people.get(person)
        return bool(who and who.team == f"{part}-team")

    def setup(self, conn, tools_role: str) -> None:
        pass

    def obligations(self) -> list[Obligation]:
        return [Obligation("records", t["key"], t["assignee"], t["title"],
                           datetime.fromisoformat(f"{t['opened']}T09:00:00+00:00"),
                           datetime.fromisoformat(f"{t['due']}T17:00:00+00:00"), LINK + t["key"])
                for t in self._tickets.values() if t.get("status") != "closed"]

    def watched(self) -> list[Record]:
        self.reads += 1
        return [self._record(t) for t in self._tickets.values()]

    def record(self, key: str) -> Record | None:
        found = self._tickets.get(key)
        return self._record(found) if found else None

    @staticmethod
    def _record(ticket: dict) -> Record:
        return Record("records", ticket["key"], ticket["assignee"], ticket["title"],
                      {"status": ticket.get("status")}, LINK + ticket["key"])

    def settings(self) -> Settings:
        sig = self.folder / "settings.sig"
        signed = (yaml.safe_load(sig.read_text()) or {}).get("signatures", []) if sig.exists() else []
        return parse_settings((self.folder / "settings.yaml").read_bytes(),
                              tuple(Signature(s["signer"], s["value"]) for s in signed))

    def policy_pack(self) -> None:
        return None

    def tools(self) -> dict[str, Tool]:
        def search(call: ToolCall) -> dict:
            words = str(call.args.get("query") or "").casefold().split()
            return {"tickets": [{**t, "link": LINK + t["key"]} for t in self._tickets.values()
                                if any(w in t["title"].casefold() for w in words)]}

        def get(call: ToolCall) -> dict:
            found = self._tickets.get(call.args["key"])
            return {**found, "link": LINK + found["key"]} if found else {"error": "no such ticket"}

        def draft(call: ToolCall) -> dict:
            return draft_once(call, self.drafts, LINK, self._draft_lock)

        def comments(call: ToolCall) -> dict:
            return {"key": call.args["key"], "messages": [
                m for m in self._messages if m["record"] == call.args["key"]]}

        query = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        key = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
        body = {"type": "object", "required": ["title", "body"], "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "record": {"type": "string"}}}
        tools = {t.name: t for t in (
            Tool("search_records", "Search ITSM tickets by words in their title.", query, search,
                 handles=("contact",), record_field="key"),
            Tool("get_record", "Get one ITSM ticket by its key, such as INC0000001.", key, get,
                 handles=("contact",), record_arg="key", record_field="key"),
            Tool("create_draft", "Save a draft ticket reply for a person to review and use.", body,
                 draft, writes=True, text_fields=("title", "body"), record_arg="record",
                 idempotent=True),
            Tool("get_messages", "Get what requesters wrote on a ticket through a5s's reader.", key,
                 comments, handles=("from",), record_arg="key", record_field="key",
                 outside=("body",),
                 extract={"asks_for": "choice:a reset|access|equipment|something else"}),
        )}
        tools.update(MarkdownKnowledge(self.folder / "knowledge",
                                       sees_part=self._knowledge_part, person=self.person).tools())
        return tools
