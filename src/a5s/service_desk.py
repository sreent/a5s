"""An IT service-desk scenario with a synthetic ITSM, identity provider and knowledge base.

Its ITSM's tools come through the ITSM's MCP server, which the scenario's mcp.yaml declares
(deploy/systems/itsm.py, in this made-up desk): searching tickets, reading one, what requesters
wrote on one, and posting a reply on one, a change a5s holds for the ticket's service area's
decider. Self-service comes through the identity provider's (deploy/systems/idp.py): an account,
the provider's own password reset, which its holder finishes there, and removing an account's
authenticators. What stays here is the desk's own: the directory, who may see each ticket and
account, the obligations its tickets make, a draft reply for a person to send, its knowledge
base, and its policy pack, pack.cedar in its folder, which lets a reset run alone only for the
person asking, and never an authenticator change."""

from __future__ import annotations

import re
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
IDP = "https://idp.desk.test/accounts/"
ACCOUNT = re.compile(r"ACC-([a-z][a-z0-9-]*)")  # a person's account: ACC- and their id
ACCESS = "access"  # the service area accounts are in


class ServiceDeskScenario:
    name = "service-desk"
    record_links = (LINK, IDP)
    record_pattern = r"\b(?:INC|REQ)\d{7}\b|\bACC-[a-z][a-z0-9-]*\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        data = yaml.safe_load((folder / "data.yaml").read_text())
        self._people = {p["id"]: Person.listed(p, folder) for p in data["people"]}
        self._tickets = {t["key"]: t for t in data["tickets"]}
        self._accounts = {a["key"]: a for a in data.get("accounts") or []}
        self.drafts = []
        self._draft_lock = threading.Lock()
        self.reads = 0

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._people.values() if p.team == name]

    def _holder(self, record: str) -> Person | None:
        """Whose account a record is, if it's one."""
        found = ACCOUNT.fullmatch(record)
        return self._people.get(found[1]) if found else None

    def part_of(self, record: str) -> str | None:
        if self._holder(record) is not None:
            return ACCESS
        return (self._tickets.get(record) or {}).get("part")

    def sees(self, person: str, record: str) -> bool:
        who = self._people.get(person)
        if who is None:
            return False
        if (holder := self._holder(record)) is not None:  # its holder, and access's resolvers
            return person == holder.id or who.team == f"{ACCESS}-team"
        ticket = self._tickets.get(record)
        if ticket is None:
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
        if (holder := self._holder(key)) is not None:  # whose next step it is: its holder's
            state = (self._accounts.get(key) or {}).get("state", "active")
            return Record("accounts", key, holder.id, f"{holder.name}'s account", {"state": state},
                          IDP + key)
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

    def policy_pack(self) -> str | None:
        pack = self.folder / "pack.cedar"
        return pack.read_text() if pack.exists() else None

    def tools(self) -> dict[str, Tool]:
        def draft(call: ToolCall) -> dict:
            return draft_once(call, self.drafts, LINK, self._draft_lock)

        body = {"type": "object", "required": ["title", "body"], "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "record": {"type": "string"}}}
        tools = {"create_draft": Tool(
            "create_draft", "Save a draft ticket reply for a person to review and use.", body, draft,
            writes=True, text_fields=("title", "body"), record_arg="record", idempotent=True)}
        tools.update(MarkdownKnowledge(self.folder / "knowledge",
                                       sees_part=self._knowledge_part, person=self.person).tools())
        return tools
