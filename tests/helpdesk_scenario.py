"""A help desk written against the contract alone (src/a5s/contract.py), as round 9's reviewer
C wrote it: its tickets are numbered in plain digits, so its key pattern is \\b\\d{6}\\b."""

from __future__ import annotations

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

LINK = "https://help.desk.test/"


class HelpdeskScenario:
    name = "helpdesk"
    record_links = (LINK,)
    record_pattern = r"\b\d{6}\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        data = yaml.safe_load((folder / "data.yaml").read_text())
        self._people = {}
        for p in data["people"]:
            key = folder / "keys" / f"{p['id']}.pub"
            self._people[p["id"]] = Person(
                **{k: tuple(v) if isinstance(v, list) else v for k, v in p.items()},
                public_key=key.read_text().strip() if key.exists() else None)
        self._tickets = {str(t["key"]): t for t in data["tickets"]}

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
        return bool(ticket and who and (person == ticket["requester"]
                                        or who.team == f"{ticket['part']}-team"))

    def setup(self, conn, tools_role: str) -> None:
        pass

    def obligations(self) -> list[Obligation]:
        return []

    def watched(self) -> list[Record]:
        return [self.record(k) for k in self._tickets]

    def record(self, key: str) -> Record | None:
        t = self._tickets.get(key)
        return Record("records", key, t["requester"], t["title"], {"status": t["status"]},
                      LINK + key) if t else None

    def settings(self) -> Settings:
        sig = self.folder / "settings.sig"
        signed = (yaml.safe_load(sig.read_text()) or {}).get("signatures", []) if sig.exists() else []
        return parse_settings((self.folder / "settings.yaml").read_bytes(),
                              tuple(Signature(s["signer"], s["value"]) for s in signed))

    def policy_pack(self) -> None:
        return None

    def tools(self) -> dict[str, Tool]:
        def get(call: ToolCall) -> dict:
            t = self._tickets.get(str(call.args.get("key", "")))
            return {**t, "key": str(t["key"]), "link": LINK + str(t["key"])} if t else {
                "error": "no such ticket"}

        key = {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}
        return {"get_record": Tool("get_record", "Get one ticket by its number, such as 104233.",
                                   key, get, record_arg="key", record_field="key")}
