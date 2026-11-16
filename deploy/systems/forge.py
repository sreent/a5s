"""A made-up forge's MCP server, with its CI, for the software delivery scenario: its issues and pull
requests, each pull request's checks as its CI ran them, and what customers wrote on an issue, from
the scenario's synthetic data, offered over MCP's Streamable HTTP as an organisation's forge offers
its tools (docs/connectors.md#mcp-servers); and asking someone to review a pull request, a change.

Like the other made-up systems, it reads the data afresh for each call, keeps what's done through
it over the data, makes each change once for a5s's key, and runs beside the gateway, sharing its
network. With A5S_SYSTEMS_STATE set, it keeps what's done through it in a file in that folder,
which the scenario's own code reads, so whom a5s lets see a pull request, and whose review it
chases, is whom the forge has asked, and it carries on from there when it starts again.
A5S_SYSTEM_PORT moves it, as the sandbox's own copy runs:

    python deploy/systems/forge.py scenarios/software-delivery/data.yaml      # on 127.0.0.1:9203
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent))  # beside the other made-up systems
from standin import KEY, Tools, keep, kept, once, serving

NAME = "forge"  # as the scenario's mcp.yaml names it, and the file it keeps its changes in
PORT = 9203
LINK = "https://code.dev.test/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}
REVIEW = {"type": "object", "required": ["key", "reviewer"],
          "properties": {"key": {"type": "string"}, "reviewer": {"type": "string"}}}


@dataclass
class Written:
    """What's been done through the forge, over the data: each record's fields as they've
    changed, such as a pull request's reviewers, and what each request a5s keyed made, so a
    request made again makes nothing more. Kept in `state`, or A5S_SYSTEMS_STATE's folder, if it
    names one, and read back when the forge starts (round 12, A8)."""

    changed: dict[str, dict] = field(default_factory=dict)
    made: dict[str, dict] = field(default_factory=dict)
    state: Path | None = None

    def __post_init__(self) -> None:
        found = kept(NAME, self.state)
        self.changed.update(found.get("changed") or {})
        self.made.update(found.get("made") or {})

    def save(self) -> None:
        keep(NAME, {"changed": self.changed, "made": self.made}, self.state)

    def reset(self) -> None:
        self.changed.clear()
        self.made.clear()
        self.save()


def make(data: Path, state: Path | None = None) -> FastAPI:
    """The server, on the scenario's data.yaml at `data`, keeping what's done through it in
    `state`, or A5S_SYSTEMS_STATE's folder: what's done through it is in `app.state.written`."""
    written = Written(state=state)

    def read() -> dict:
        return yaml.safe_load(data.read_text()) or {}

    def records() -> list[dict]:
        found = read()
        return [{**r, **written.changed.get(r["key"], {}), "link": LINK + r["key"]}
                for r in (*(found.get("issues") or []), *(found.get("pulls") or []))]

    def one(key: object) -> dict | None:
        return next((r for r in records() if r["key"] == key), None)

    def search(args: dict, _: dict) -> dict:
        words = str(args.get("query") or "").casefold().split()
        return {"records": [r for r in records()
                            if any(w in f"{r['title']} {r['status']}".casefold() for w in words)]}

    def get(args: dict, _: dict) -> dict | None:
        return one(args.get("key"))

    def comments(args: dict, _: dict) -> dict | None:
        key = args.get("key")
        if one(key) is None:
            return None
        return {"key": key, "comments": [c for c in read().get("comments") or [] if c["record"] == key]}

    def request_review(args: dict, meta: dict) -> dict | None:
        """Ask someone to review an open pull request, as its repository's owners decided."""
        found, reviewer = one(args.get("key")), str(args.get("reviewer") or "").strip()
        people = {p["id"] for p in read().get("people") or []}
        if found is None or "reviewers" not in found or found["status"] != "open" or reviewer not in people:
            return None

        def ask() -> dict:
            reviewers = sorted({*found["reviewers"], reviewer})
            written.changed.setdefault(found["key"], {})["reviewers"] = reviewers
            return {"key": found["key"], "reviewers": reviewers, "link": found["link"],
                    "at": datetime.now(UTC).isoformat(timespec="seconds")}

        made = once(written.made, meta, f"review {found['key']} {reviewer}", ask)
        written.save()
        return made

    tools: Tools = {
        "search_items": ("Search issues and pull requests by words in their titles or status.", QUERY,
                         {"readOnlyHint": True}, search),
        "get_item": ("Get one issue or pull request by its key, a pull request with its CI checks.",
                     KEY, {"readOnlyHint": True}, get),
        "item_comments": ("What customers wrote on an issue.", KEY,
                          {"readOnlyHint": True, "openWorldHint": True}, comments),
        "request_review": ("Ask someone to review an open pull request.", REVIEW,
                           {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True,
                            "openWorldHint": False}, request_review),
    }
    app = serving("delivery-forge", tools, "No such issue or pull request, or nothing to do with it.")
    app.state.written = written
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=int(os.environ.get("A5S_SYSTEM_PORT") or PORT),
                log_level="warning")
