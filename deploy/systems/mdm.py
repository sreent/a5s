"""A made-up device management system's MCP server, for the service desk scenario: each person's
devices, from the desk's synthetic data, by their asset tag, LT- for a laptop and PH- for a phone,
with whether each meets the organisation's rules for devices, and why not, offered over MCP's
Streamable HTTP as an organisation's device management offers its tools
(docs/connectors.md#mcp-servers); and locking a device remotely, a change, which its holder undoes
by signing in to it again, as they do once it's found.

Like the other made-up systems, it reads the data afresh for each call, keeps what's done through
it over the data, makes each change once for a5s's key, and runs beside the gateway, sharing its
network. With A5S_SYSTEMS_STATE set, it keeps what's done through it in a file in that folder,
which the scenario's own code reads, so what a5s shows of a device, and what its decider sees, is
what the system holds, and it carries on from there when it starts again. A5S_SYSTEM_PORT moves
it, as the sandbox's own copy runs:

    python deploy/systems/mdm.py scenarios/service-desk/data.yaml      # on 127.0.0.1:9205
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

NAME = "mdm"  # as the scenario's mcp.yaml names it, and the file it keeps its changes in
PORT = 9205
LINK = "https://mdm.desk.test/devices/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}


@dataclass
class Written:
    """What's been done through the system, over the data: each device's fields as they've
    changed, such as whether it's locked, and what each request a5s keyed made, so a request
    made again makes nothing more. Kept in `state`, or A5S_SYSTEMS_STATE's folder, if it names
    one, and read back when the system starts."""

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

    def devices() -> list[dict]:
        found = yaml.safe_load(data.read_text()) or {}
        return [{"locked": False, "reasons": [], **d, **written.changed.get(d["key"], {}),
                 "link": LINK + d["key"]} for d in found.get("devices") or []]

    def one(key: object) -> dict | None:
        return next((d for d in devices() if d["key"] == key), None)

    def search(args: dict, _: dict) -> dict:
        words = str(args.get("query") or "").casefold().split()
        return {"devices": [d for d in devices() if any(
            w in f"{d['key']} {d['kind']} {d['holder']} {d['model']} {d['os']}".casefold() for w in words)]}

    def get(args: dict, _: dict) -> dict | None:
        return one(args.get("key"))

    def lock(args: dict, meta: dict) -> dict | None:
        """Lock a device, so nobody can use it until its holder signs in to it again."""
        found = one(args.get("key"))
        if found is None:
            return None

        def locking() -> dict:
            written.changed.setdefault(found["key"], {})["locked"] = True
            return {"key": found["key"], "locked": True, "link": found["link"],
                    "at": datetime.now(UTC).isoformat(timespec="seconds")}

        made = once(written.made, meta, f"lock {found['key']}", locking)
        written.save()
        return made

    tools: Tools = {
        "search_devices": ("Search devices by words in their tag, kind, holder, model or system.", QUERY,
                           {"readOnlyHint": True}, search),
        "get_device": (("Get a device by its tag: its holder, whether it meets the rules and why not, "
                        "and whether it's locked."), KEY, {"readOnlyHint": True}, get),
        "lock_device": ("Lock a device remotely, until its holder signs in to it again.", KEY,
                        {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True,
                         "openWorldHint": False}, lock),
    }
    app = serving("desk-mdm", tools, "No such device.")
    app.state.written = written
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=int(os.environ.get("A5S_SYSTEM_PORT") or PORT),
                log_level="warning")
