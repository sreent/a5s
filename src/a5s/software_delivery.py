"""A read-only software delivery scenario: a synthetic issue tracker and code review.

An engineering team's issues and pull requests, with their reviewers, checks and due dates, and
an engineering handbook. People ask a dev assistant what's happening with an issue or a pull
request, how the team releases, or to draft a description or a reply, and it chases the reviews
and fixes people owe. It never merges, approves, changes an issue, or runs code: the issue
tracker and code review keep their own controls. Issues labelled security are for the security
team and their assignee alone, and what customers wrote reaches the agent only through a5s's
reader.
"""

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

LINK = "https://code.dev.test/"


def _at(day: str, hour: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour}+00:00")


class SoftwareDeliveryScenario:
    name = "software-delivery"
    record_links = (LINK,)
    record_pattern = r"\b(?:DEV-\d{3,5}|PR-\d{1,5})\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        data = yaml.safe_load((folder / "data.yaml").read_text())
        self._people = {p["id"]: self._person(folder, p) for p in data["people"]}
        self._issues = {i["key"]: i for i in data["issues"]}
        self._pulls = {p["key"]: p for p in data["pulls"]}
        self._comments = data.get("comments") or []
        self.drafts: list[dict] = []
        self._draft_lock = threading.Lock()

    @staticmethod
    def _person(folder: Path, entry: dict) -> Person:
        key = folder / "keys" / f"{entry['id']}.pub"
        return Person(**{k: tuple(v) if isinstance(v, list) else v for k, v in entry.items()},
                      public_key=key.read_text().strip() if key.exists() else None)

    # The directory

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._people.values() if p.team == name]

    # Records, and who may see each

    def _found(self, key: str) -> dict | None:
        return self._issues.get(key) or self._pulls.get(key)

    def part_of(self, record: str) -> str | None:
        return (self._found(record) or {}).get("part")

    def sees(self, person: str, record: str) -> bool:
        found, who = self._found(record), self._people.get(person)
        if found is None or who is None:
            return False
        if "security" in (found.get("labels") or ()):  # need-to-know: the security team's
            return who.team == "security-team" or person == found.get("assignee")
        involved = {found.get("assignee"), found.get("reporter"), found.get("author"),
                    *(found.get("reviewers") or ())}
        return person in involved or who.team == f"{found['part']}-team"

    def _knowledge_part(self, person: str, part: str) -> bool:
        who = self._people.get(person)
        return bool(who and who.team == f"{part}-team")

    def setup(self, conn, tools_role: str) -> None:
        pass

    def obligations(self) -> list[Obligation]:
        """The fixes people owe, by when their issues are due, and the reviews they were asked
        for, by when the pull request asked for them."""
        owed = [Obligation("records", i["key"], i["assignee"], i["title"],
                           _at(i["opened"], "09:00:00"), _at(i["due"], "17:00:00"),
                           LINK + i["key"])
                for i in self._issues.values() if i["status"] != "closed"]
        owed += [Obligation("records", p["key"], reviewer, f"Review: {p['title']}",
                            _at(p["opened"], "09:00:00"), _at(p["review_due"], "17:00:00"),
                            LINK + p["key"])
                 for p in self._pulls.values() if p["status"] == "open"
                 for reviewer in p["reviewers"]]
        return owed

    def watched(self) -> list[Record]:
        return [self._record(r) for r in (*self._issues.values(), *self._pulls.values())]

    def record(self, key: str) -> Record | None:
        found = self._found(key)
        return self._record(found) if found else None

    @staticmethod
    def _record(found: dict) -> Record:
        fields = {"status": found["status"]}
        if "checks" in found:
            fields["checks"] = found["checks"]
        return Record("records", found["key"], found.get("assignee") or found["author"],
                      found["title"], fields, LINK + found["key"])

    def settings(self) -> Settings:
        sig = self.folder / "settings.sig"
        signed = (yaml.safe_load(sig.read_text()) or {}).get("signatures", []) if sig.exists() else []
        return parse_settings((self.folder / "settings.yaml").read_bytes(),
                              tuple(Signature(s["signer"], s["value"]) for s in signed))

    def policy_pack(self) -> None:
        return None

    # Tools, read only but for drafts

    def tools(self) -> dict[str, Tool]:
        def shown(found: dict) -> dict:
            return {**found, "link": LINK + found["key"]}

        def search(call: ToolCall) -> dict:
            words = str(call.args.get("query") or "").casefold().split()
            return {"records": [shown(r) for r in (*self._issues.values(), *self._pulls.values())
                                if any(w in f"{r['title']} {r['status']}".casefold()
                                       for w in words)]}

        def get(call: ToolCall) -> dict:
            found = self._found(str(call.args.get("key", "")))
            return shown(found) if found else {"error": "no such issue or pull request"}

        def comments(call: ToolCall) -> dict:
            return {"key": call.args["key"], "comments": [
                c for c in self._comments if c["record"] == call.args["key"]]}

        def draft(call: ToolCall) -> dict:
            return draft_once(call, self.drafts, LINK, self._draft_lock)

        query = {"type": "object", "properties": {"query": {"type": "string"}},
                 "required": ["query"]}
        key = {"type": "object", "required": ["key"], "properties": {"key": {
            "type": "string", "description": "An issue, such as DEV-101, or a pull request, "
                                             "such as PR-17"}}}
        body = {"type": "object", "required": ["title", "body"], "properties": {
            "title": {"type": "string"}, "body": {"type": "string"},
            "record": {"type": "string", "description": "The issue or pull request it's for"}}}
        tools = {t.name: t for t in (
            Tool("search_records", "Search issues and pull requests by words in their title or "
                 "status.", query, search, record_field="key"),
            Tool("get_record", "Get one issue or pull request by its key: its status, assignee "
                 "or author, reviewers, checks, and the issue a pull request fixes.", key, get,
                 record_arg="key", record_field="key"),
            Tool("get_comments", "Get what customers wrote on an issue, through a5s's reader: "
                 "what it asks for, and the dates and keys it names, never its words.", key,
                 comments, handles=("from",), record_arg="key", record_field="key",
                 outside=("body",),
                 extract={"asks_for": "choice:a fix|a workaround|a release date|"
                                      "something else",
                          "date": "date", "issue": "key"}),
            Tool("create_draft", "Save a draft, such as a pull request's description, a review "
                 "comment or a release note, for a person to read, change and post.", body,
                 draft, writes=True, text_fields=("title", "body"), record_arg="record",
                 idempotent=True),
        )}
        tools.update(MarkdownKnowledge(self.folder / "knowledge",
                                       sees_part=self._knowledge_part, person=self.person).tools())
        return tools
