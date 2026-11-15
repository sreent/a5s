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

import json
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

PORT = 9201
SPOKEN = ("2025-03-26", "2025-06-18", "2025-11-25")  # MCP's versions it speaks, as a5s does
LINK = "https://itsm.desk.test/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}
KEY = {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}
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
    app = FastAPI(title="the desk's ITSM, made up")
    written = app.state.written = Written()

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
        key, body = args.get("key"), str(args.get("body") or "").strip()
        if not body or not any(t["key"] == key for t in read().get("tickets") or []):
            return None
        once = str(meta.get("a5s/key") or f"{key}\n{body}")
        if once in written.made:
            return written.made[once]
        posted = {"key": key, "replied": body, "at": datetime.now(UTC).isoformat(timespec="seconds"),
                  "link": LINK + str(key)}
        written.replies.setdefault(str(key), []).append({**posted, "a5s_key": meta.get("a5s/key")})
        written.made[once] = posted
        return posted

    # Each tool: what it says it does, what it takes, its hints, and what it does
    tools: dict[str, tuple[str, dict, dict, Callable[[dict, dict], dict | None]]] = {
        "search_tickets": ("Search the tickets by words in their titles.", QUERY,
                           {"readOnlyHint": True}, search),
        "get_ticket": ("Get one ticket by its key.", KEY, {"readOnlyHint": True}, ticket),
        "ticket_comments": ("What requesters wrote on a ticket.", KEY,
                            {"readOnlyHint": True, "openWorldHint": True}, comments),
        "add_reply": ("Post a reply on a ticket, for its requester to read.", REPLY,
                      {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True,
                       "openWorldHint": False}, reply),
    }

    def answer(ident: Any, result: dict) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": ident, "result": result})

    def failed(ident: Any, code: int, words: str) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": words}})

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        message = await request.json()
        method, ident = message.get("method"), message.get("id")
        params = message.get("params") or {}
        if ident is None:  # a notification, such as that a5s has initialized
            return Response(status_code=202)
        if method == "initialize":
            asked = params.get("protocolVersion")
            return JSONResponse({"jsonrpc": "2.0", "id": ident, "result": {
                "protocolVersion": asked if asked in SPOKEN else SPOKEN[-1],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "desk-itsm", "version": "1.0.0"}}},
                headers={"Mcp-Session-Id": uuid.uuid4().hex})
        if method == "tools/list":
            return answer(ident, {"tools": [
                {"name": name, "description": said, "inputSchema": takes, "annotations": hints}
                for name, (said, takes, hints, _) in tools.items()]})
        if method == "tools/call":
            found = tools.get(params.get("name"))
            if found is None:
                return failed(ident, -32602, f"{params.get('name')!s:.40} isn't a tool of this server's")
            meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
            result = found[3](params.get("arguments") or {}, meta)
            if result is None:
                return answer(ident, {"content": [{"type": "text", "text": "No such ticket, or "
                                                   "nothing to post on it."}], "isError": True})
            return answer(ident, {"content": [{"type": "text", "text": json.dumps(result)}],
                                  "structuredContent": result, "isError": False})
        return failed(ident, -32601, f"{method!s:.40} isn't a method this server has")

    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=PORT, log_level="warning")
