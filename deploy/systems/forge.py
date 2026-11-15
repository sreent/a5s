"""A made-up forge's MCP server, with its CI, for the software delivery scenario: its issues and pull
requests, each pull request's checks as its CI ran them, and what customers wrote on an issue, from
the scenario's synthetic data, offered over MCP's Streamable HTTP as an organisation's forge offers
its tools (docs/connectors.md#mcp-servers); and asking someone to review a pull request, a change.

Like the desk's made-up systems, it reads the data afresh for each call, keeps what's done through
it in its memory, over the data, until it stops, makes each change once for a5s's key, and runs
beside the gateway, sharing its network:

    python deploy/systems/forge.py scenarios/software-delivery/data.yaml      # on 127.0.0.1:9203
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent))  # beside the other made-up systems
from standin import KEY, Tools, once, serving

PORT = 9203
LINK = "https://code.dev.test/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}
REVIEW = {"type": "object", "required": ["key", "reviewer"],
          "properties": {"key": {"type": "string"}, "reviewer": {"type": "string"}}}


@dataclass
class Written:
    """What's been done through the forge since it started, over the data: each record's fields
    as they've changed, such as a pull request's reviewers, and what each request a5s keyed
    made, so a request made again makes nothing more."""

    changed: dict[str, dict] = field(default_factory=dict)
    made: dict[str, dict] = field(default_factory=dict)

    def reset(self) -> None:
        self.changed.clear()
        self.made.clear()


def make(data: Path) -> FastAPI:
    """The server, on the scenario's data.yaml at `data`: what's done through it is in
    `app.state.written`."""
    written = Written()

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

        return once(written.made, meta, f"review {found['key']} {reviewer}", ask)

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
                host="127.0.0.1", port=PORT, log_level="warning")
