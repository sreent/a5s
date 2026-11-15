"""A made-up IT service management tool's MCP server, for the service desk scenario: its tickets,
and what requesters wrote on them, from the desk's synthetic data, offered over MCP's Streamable
HTTP as an organisation's ITSM offers its tools (docs/connectors.md#mcp-servers).

It answers each request in JSON, reads the data afresh for each call, and holds nothing real: what's
written to it, such as a reply on a ticket, it keeps in its memory, over the data, until it stops,
and it makes each once for a5s's key, as an organisation's ITSM makes a change once for each
request. The scenario's mcp.yaml points a5s at it on the gateway's own machine, so it runs beside
the gateway, sharing its network, as the stand-in model does beside the stack:

    python deploy/desk/itsm.py scenarios/service-desk/data.yaml      # on 127.0.0.1:9201

a5s offers its agents nothing of it but what mcp.yaml declares, and checks each tool is still as
declared before each call.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent))  # beside the desk's other made-up systems
from standin import KEY, Tools, once, serving

PORT = 9201
LINK = "https://itsm.desk.test/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}
REPLY = {"type": "object", "required": ["key", "body"],
         "properties": {"key": {"type": "string"}, "body": {"type": "string", "maxLength": 4000}}}


@dataclass
class Written:
    """What's been written to the ITSM since it started: each ticket's replies, and what each
    request a5s keyed made, so a request made again makes nothing more."""

    replies: dict[str, list[dict]] = field(default_factory=dict)
    made: dict[str, dict] = field(default_factory=dict)  # by a5s's key, or the reply itself

    def reset(self) -> None:
        self.replies.clear()
        self.made.clear()


def make(data: Path) -> FastAPI:
    """The server, on the scenario's data.yaml at `data`: what's written to it is in
    `app.state.written`."""
    written = Written()

    def read() -> dict:
        return yaml.safe_load(data.read_text()) or {}

    def search(args: dict, _: dict) -> dict:
        words = str(args.get("query") or "").casefold().split()
        return {"tickets": [{**t, "link": LINK + t["key"]} for t in read().get("tickets") or []
                            if any(w in t["title"].casefold() for w in words)]}

    def ticket(args: dict, _: dict) -> dict | None:
        found = next((t for t in read().get("tickets") or [] if t["key"] == args.get("key")), None)
        return {**found, "link": LINK + found["key"]} if found else None

    def comments(args: dict, _: dict) -> dict | None:
        key = args.get("key")
        if not any(t["key"] == key for t in read().get("tickets") or []):
            return None
        return {"key": key, "messages": [m for m in read().get("messages") or [] if m["record"] == key]}

    def reply(args: dict, meta: dict) -> dict | None:
        """A reply on a ticket, which its requester reads: once for a5s's key, and once for
        the same words on the same ticket, so asking again does nothing more."""
        key, body = str(args.get("key")), str(args.get("body") or "").strip()
        if not body or not any(t["key"] == key for t in read().get("tickets") or []):
            return None

        def post() -> dict:
            posted = {"key": key, "replied": body, "at": datetime.now(UTC).isoformat(timespec="seconds"),
                      "link": LINK + key}
            written.replies.setdefault(key, []).append({**posted, "a5s_key": meta.get("a5s/key")})
            return posted

        return once(written.made, meta, f"{key}\n{body}", post)

    tools: Tools = {
        "search_tickets": ("Search the tickets by words in their titles.", QUERY,
                           {"readOnlyHint": True}, search),
        "get_ticket": ("Get one ticket by its key.", KEY, {"readOnlyHint": True}, ticket),
        "ticket_comments": ("What requesters wrote on a ticket.", KEY,
                            {"readOnlyHint": True, "openWorldHint": True}, comments),
        "add_reply": ("Post a reply on a ticket, for its requester to read.", REPLY,
                      {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True,
                       "openWorldHint": False}, reply),
    }
    app = serving("desk-itsm", tools, "No such ticket, or nothing to post on it.")
    app.state.written = written
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=PORT, log_level="warning")
