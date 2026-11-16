"""What the scenarios' made-up systems share: an MCP server, over Streamable HTTP, answering each
request in JSON, for the tools a system offers (docs/connectors.md#mcp-servers). Each system says,
for each tool, what it does, what it takes, its hints, and what it does with what it's given and
with a5s's key, which it makes a change once for; this answers MCP's handshake and requests with
them. And, for a system whose changes its scenario's own code reads, keeping what's been done
through it where that code reads it.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

SPOKEN = ("2025-03-26", "2025-06-18", "2025-11-25")  # MCP's versions it speaks, as a5s does
KEY = {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}

# The folder a made-up system keeps what's been done through it in, for its scenario's own code
STATE = "A5S_SYSTEMS_STATE"

# A tool: what it says it does, what it takes, its hints, and what it does with its arguments
# and the request's _meta, which holds a5s's key: None if it names nothing there is, or why it
# does nothing, in words
Does = Callable[[dict, dict], dict | str | None]
Tools = dict[str, tuple[str, dict, dict, Does]]


def serving(name: str, tools: Tools, nothing: str) -> FastAPI:
    """A made-up system's MCP server, called `name`, at /mcp: `nothing` is what it says when a
    tool is given something there's none of."""
    app = FastAPI(title=f"{name}, made up")

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
                "serverInfo": {"name": name, "version": "1.0.0"}}},
                headers={"Mcp-Session-Id": uuid.uuid4().hex})
        if method == "tools/list":
            return answer(ident, {"tools": [
                {"name": tool, "description": said, "inputSchema": takes, "annotations": hints}
                for tool, (said, takes, hints, _) in tools.items()]})
        if method == "tools/call":
            found = tools.get(params.get("name"))
            if found is None:
                return failed(ident, -32602, f"{params.get('name')!s:.40} isn't a tool of this server's")
            meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
            result = found[3](params.get("arguments") or {}, meta)
            if result is None or isinstance(result, str):
                return answer(ident, {"content": [{"type": "text", "text": result or nothing}],
                                      "isError": True})
            return answer(ident, {"content": [{"type": "text", "text": json.dumps(result)}],
                                  "structuredContent": result, "isError": False})
        return failed(ident, -32601, f"{method!s:.40} isn't a method this server has")

    return app


def once(made: dict[str, dict], meta: dict, same: str, do: Callable[[], dict]) -> dict:
    """What a change made, made once for a5s's key, or, without one, for `same`, what names the
    change itself: asked again, it makes nothing more, and says what it made."""
    key = str(meta.get("a5s/key") or same)
    if key not in made:
        made[key] = do()
    return made[key]


def kept(name: str, folder: str | Path | None = None) -> dict:
    """What the made-up system `name` kept of what's been done through it, as `keep` left it in
    its folder, so it carries on where it was when it stops and starts again: nothing, if there's
    no folder, or nothing kept there."""
    folder = folder or os.environ.get(STATE)
    if not folder:
        return {}
    try:
        found = json.loads((Path(folder) / f"{name}.json").read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def keep(name: str, state: dict, folder: str | Path | None = None) -> None:
    """What's been done through the made-up system `name`, kept as JSON in `folder`, or the one
    A5S_SYSTEMS_STATE names, if it names one, for its scenario's own code to read, as an
    organisation's code reads its own system as it stands, and for itself when it starts again:
    written whole, in one step, so whatever reads it never reads half of it."""
    folder = folder or os.environ.get(STATE)
    if not folder:
        return
    Path(folder).mkdir(parents=True, exist_ok=True)
    handle, path = tempfile.mkstemp(dir=folder, prefix=f".{name}.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump(state, out)
    os.chmod(path, 0o644)  # synthetic data, for the scenario's code in the gateway to read
    os.replace(path, Path(folder) / f"{name}.json")
