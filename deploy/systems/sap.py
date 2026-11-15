"""A made-up SAP MDG's MCP server, for the master data governance scenario: its change requests and
master records, from the scenario's synthetic data, what suppliers sent with a request, and an
update to what a change request proposes, a change, offered over MCP's Streamable HTTP as an
organisation's SAP offers its tools (docs/connectors.md#mcp-servers).

Bank details are SAP's to hold: a5s passes them on to its agents only as handles, and what
suppliers sent only through its reader. SAP checks an update by the critical-field rules a5s's
own checks use, which here are SAP's configuration too, and a request that needed information,
and has it now, goes back to its steward, as SAP MDG's workflow sends it.

Like the other made-up systems, it reads the data afresh for each call, keeps what's done through
it over the data, makes each change once for a5s's key, and runs beside the gateway, sharing its
network. With A5S_SYSTEMS_STATE set, it keeps what's done through it in a file in that folder,
which the scenario's own code reads, so what a5s shows people of a request, and checks of it, is
what SAP holds:

    python deploy/systems/sap.py scenarios/master-data/data.yaml      # on 127.0.0.1:9204
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
from standin import KEY, Tools, keep, once, serving

from a5s.master_data import CORRECTABLE, FIELDS, TYPES, UNITS, failures

NAME = "sap"  # as the scenario's mcp.yaml names it, and the file it keeps its changes in
PORT = 9204
LINK = "https://mdg.sap.test/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}
UPDATE = {"type": "object", "required": ["key"], "additionalProperties": False, "properties": {
    "key": {"type": "string"}, "description": {"type": "string", "minLength": 1},
    "base_unit": {"type": "string", "enum": list(UNITS)},
    "material_type": {"type": "string", "enum": list(TYPES)}}}
SEARCHED = ("title", "status", "name", "description", "kind")  # what a search's words are found in


@dataclass
class Written:
    """What's been done through SAP since it started, over the data: each change request's values
    and status as they've changed, and what each update a5s keyed made, so one asked for again
    makes nothing more. Kept in A5S_SYSTEMS_STATE's folder too, if it names one."""

    data: Path
    changed: dict[str, dict] = field(default_factory=dict)
    made: dict[str, dict] = field(default_factory=dict)

    def read(self) -> dict:
        return yaml.safe_load(self.data.read_text()) or {}

    def request(self, key: object) -> dict | None:
        """A change request as SAP holds it now."""
        found = next((r for r in self.read().get("requests") or [] if r["key"] == key), None)
        return None if found is None else {**found, **self.changed.get(found["key"], {})}

    def amend(self, key: str, values: dict, status: str | None = None) -> None:
        """A change request changed in SAP itself, outside a5s, as its requester or steward
        changes it there."""
        found = self.request(key)
        assert found is not None, key
        self.changed[key] = {"values": {**found["values"], **values},
                             "status": status or found["status"]}
        self.save()

    def save(self) -> None:
        keep(NAME, {"changed": self.changed})

    def reset(self) -> None:
        self.changed.clear()
        self.made.clear()
        self.save()


def make(data: Path) -> FastAPI:
    """The server, on the scenario's data.yaml at `data`: what's done through it is in
    `app.state.written`."""
    written = Written(data)

    def shown(found: dict) -> dict:
        return {**found, "link": LINK + found["key"]}

    def everything() -> list[dict]:
        found = written.read()
        return [*(written.request(r["key"]) or r for r in found.get("requests") or []),
                *(found.get("records") or [])]

    def search(args: dict, _: dict) -> dict:
        words = str(args.get("query") or "").casefold().split()
        return {"found": [shown(r) for r in everything() if any(
            w in " ".join(str(v) for k, v in r.items() if k in SEARCHED).casefold() for w in words)]}

    def read_one(args: dict, _: dict) -> dict | None:
        found = next((r for r in everything() if r["key"] == args.get("key")), None)
        return shown(found) if found else None

    def attachments(args: dict, _: dict) -> dict | None:
        key = args.get("key")
        if written.request(key) is None:
            return None
        return {"key": key, "letters": [m for m in written.read().get("letters") or []
                                        if m["record"] == key]}

    def update(args: dict, meta: dict) -> dict | str | None:
        """An update to what a change request proposes, as its data object's owner decided."""
        found = written.request(args.get("key"))
        if found is None:
            return None
        given = {k: str(v) for k, v in args.items() if k in CORRECTABLE}
        objects = written.read().get("objects") or {}
        if found["status"] in ("approved", "rejected"):
            return f"{found['key']} is {found['status']}: nothing in it changes now"
        if not given:
            return f"Name what to change: {', '.join(CORRECTABLE)}"
        if wrong := [k for k in given if k not in FIELDS[found["object"]]]:
            return (f"{', '.join(wrong)} isn't a field of "
                    f"{objects[found['object']]['name'].lower()}")

        def change() -> dict:
            now = written.request(found["key"]) or found  # as it is when it's made
            values = {**now["values"], **given}
            record = next((r for r in written.read().get("records") or []
                           if r["key"] == now.get("record")), {})
            status = now["status"]
            if status == "needs info" and not failures(now["object"], {**record, **values}):
                status = "in review"  # what it needed is there: back to its steward
            written.changed[now["key"]] = {"values": values, "status": status}
            written.save()
            return {"key": now["key"], "values": given, "status": status,
                    "at": datetime.now(UTC).isoformat(timespec="seconds"), "link": LINK + now["key"]}

        return once(written.made, meta, f"update {found['key']} {sorted(given.items())}", change)

    tools: Tools = {
        "search_master_data": ("Search change requests and master records by words.", QUERY,
                               {"readOnlyHint": True}, search),
        "read_master_data": ("Read one change request, or one master record, by its key.", KEY,
                             {"readOnlyHint": True}, read_one),
        "change_request_attachments": ("What suppliers and customers sent with a change request.",
                                       KEY, {"readOnlyHint": True, "openWorldHint": True},
                                       attachments),
        "update_change_request": ("Update what a change request proposes.", UPDATE,
                                  {"readOnlyHint": False, "destructiveHint": False,
                                   "idempotentHint": True, "openWorldHint": False}, update),
    }
    app = serving("mdg-sap", tools, "No such change request or master record.")
    app.state.written = written
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=PORT, log_level="warning")
