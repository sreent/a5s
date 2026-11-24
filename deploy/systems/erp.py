"""A made-up ERP's procurement module behind its MCP server, for the procure-to-pay scenario: its
suppliers, purchase orders, goods receipts and suppliers' invoices, from the scenario's synthetic
data, and what suppliers sent with each invoice, offered over MCP's Streamable HTTP as an
organisation's ERP offers its tools (docs/connectors.md#mcp-servers).

Three changes go through it, each one a5s holds for the deciders of its part, or makes on its own
where the settings and graded samples let it: approving an invoice for payment, correcting the
order an invoice names, and moving a purchase order's delivery date. Each is made once for
a5s's key, as an organisation's ERP makes a change once for each request. What's done through it,
and what the warehouse books in, it keeps over the data, in A5S_SYSTEMS_STATE's folder, for the
scenario's own code to read, and for itself when it starts again:

    python deploy/systems/erp.py scenarios/procure-to-pay/data.yaml      # on 127.0.0.1:9206

a5s offers its agents nothing of it but what mcp.yaml declares, and checks each tool is still as
declared before each call.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent))  # beside the other made-up systems
from standin import KEY, Tools, keep, kept, once, serving

NAME = "erp"  # as the scenario's mcp.yaml names it, and the file it keeps its changes in
PORT = 9206
LINK = "https://erp.harbour.test/"
QUERY = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}
ORDER = re.compile(r"PO-\d{4}")
APPROVE = {"type": "object", "required": ["key"], "additionalProperties": False,
           "properties": {"key": {"type": "string", "pattern": r"^INV-\d{4}$"}}}
CORRECT = {"type": "object", "required": ["key", "order"], "additionalProperties": False,
           "properties": {"key": {"type": "string", "pattern": r"^INV-\d{4}$"},
                          "order": {"type": "string", "pattern": r"^PO-\d{4}$"}}}
DELIVERY = {"type": "object", "required": ["key", "delivery"], "additionalProperties": False,
            "properties": {"key": {"type": "string", "pattern": r"^PO-\d{4}$"},
                           "delivery": {"type": "string", "format": "date"}}}
KINDS = {"SUP-": "suppliers", "PO-": "orders", "GR-": "receipts", "INV-": "invoices"}
SEARCHED = ("key", "name", "item", "status", "supplier", "order", "note")


@dataclass
class Written:
    """What's been done through the ERP, over the data: each record's fields as they've changed,
    receipts the warehouse booked in since, and what each change a5s keyed made, so one asked for
    again makes nothing more. Kept in `state`, or A5S_SYSTEMS_STATE's folder, if it names one, and
    read back from it when the ERP starts, so it forgets nothing it did when it stops."""

    data: Path
    changed: dict[str, dict] = field(default_factory=dict)
    made: dict[str, dict] = field(default_factory=dict)
    state: Path | None = None

    def __post_init__(self) -> None:
        found = kept(NAME, self.state)
        self.changed.update(found.get("changed") or {})
        self.made.update(found.get("made") or {})

    def read(self) -> dict:
        return yaml.safe_load(self.data.read_text()) or {}

    def records(self) -> list[dict]:
        """Every record as the ERP holds it now: the data's, each with what's changed laid over
        it, and the receipts booked in since."""
        found = self.read()
        listed = [r for kind in KINDS.values() for r in found.get(kind) or []]
        known = {r["key"] for r in listed}
        return ([{**r, **self.changed.get(r["key"], {})} for r in listed]
                + [dict(r) for k, r in self.changed.items() if k not in known and r.get("added")])

    def record(self, key: object) -> dict | None:
        return next((r for r in self.records() if r["key"] == key), None)

    def book_in(self, key: str, order: str, received: int, at: str, clerk: str) -> None:
        """A goods receipt the warehouse books in itself, outside a5s, as it books one in there."""
        self.changed[key] = {"key": key, "order": order, "received": received, "at": at,
                             "clerk": clerk, "added": True}
        self.save()

    def amend(self, key: str, **fields: object) -> None:
        """A record changed in the ERP itself, outside a5s, as its people change it there."""
        assert self.record(key) is not None, key
        self.changed[key] = {**self.changed.get(key, {}), **fields}
        self.save()

    def save(self) -> None:
        keep(NAME, {"changed": self.changed, "made": self.made}, self.state)

    def reset(self) -> None:
        self.changed.clear()
        self.made.clear()
        self.save()


def make(data: Path, state: Path | None = None) -> FastAPI:
    """The server, on the scenario's data.yaml at `data`, keeping what's done through it in
    `state`, or A5S_SYSTEMS_STATE's folder: what's done through it is in `app.state.written`."""
    written = Written(data, state=state)

    def shown(found: dict) -> dict:
        kind = next((k for p, k in KINDS.items() if found["key"].startswith(p)), "records")
        return {**{k: v for k, v in found.items() if k != "added"}, "kind": kind,
                "link": LINK + found["key"]}

    def search(args: dict, _: dict) -> dict:
        words = str(args.get("query") or "").casefold().split()
        return {"found": [shown(r) for r in written.records() if any(
            w in " ".join(str(r.get(k, "")) for k in SEARCHED).casefold() for w in words)]}

    def read_one(args: dict, _: dict) -> dict | None:
        found = written.record(args.get("key"))
        return shown(found) if found else None

    def documents(args: dict, _: dict) -> dict | None:
        key = args.get("key")
        if not str(key).startswith("INV-") or written.record(key) is None:
            return None
        return {"key": key, "documents": [d for d in written.read().get("documents") or []
                                          if d["record"] == key]}

    def approve(args: dict, meta: dict) -> dict | str | None:
        """An invoice approved for payment, as its deciders decided: once for a5s's key."""
        found = written.record(args.get("key"))
        if found is None:
            return None
        if found["status"] != "received":
            return f"{found['key']} is {found['status']}: it can't be approved for payment now"

        def change() -> dict:
            written.changed[found["key"]] = {**written.changed.get(found["key"], {}),
                                             "status": "approved for payment"}
            written.save()
            return {"key": found["key"], "status": "approved for payment",
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "link": LINK + found["key"]}

        made = once(written.made, meta, f"approve {found['key']}", change)
        written.save()  # and that it made it, for its key, should it start again
        return made

    def correct(args: dict, meta: dict) -> dict | str | None:
        """The order an invoice names, corrected: only to an order of the same supplier's."""
        found = written.record(args.get("key"))
        if found is None or not str(found["key"]).startswith("INV-"):
            return None
        order = written.record(args.get("order"))
        if order is None or not ORDER.fullmatch(str(order["key"])):
            return f"There's no purchase order {args.get('order')}"
        if order["supplier"] != found["supplier"]:
            return f"{order['key']} is another supplier's order: an invoice names its own supplier's"
        if found["status"] != "received":
            return f"{found['key']} is {found['status']}: nothing in it changes now"

        def change() -> dict:
            written.changed[found["key"]] = {**written.changed.get(found["key"], {}),
                                             "order": order["key"]}
            written.save()
            return {"key": found["key"], "order": order["key"],
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "link": LINK + found["key"]}

        made = once(written.made, meta, f"correct {found['key']} {order['key']}", change)
        written.save()
        return made

    def delivery(args: dict, meta: dict) -> dict | str | None:
        """A purchase order's delivery date, moved as its owner decided."""
        found = written.record(args.get("key"))
        if found is None or not str(found["key"]).startswith("PO-"):
            return None
        try:
            when = date.fromisoformat(str(args.get("delivery")))
        except ValueError:
            return "A delivery date is a date, such as 2026-12-04"
        if found["status"] == "received":
            return f"{found['key']} has been received: its delivery date doesn't move now"

        def change() -> dict:
            written.changed[found["key"]] = {**written.changed.get(found["key"], {}),
                                             "delivery": when.isoformat()}
            written.save()
            return {"key": found["key"], "delivery": when.isoformat(),
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "link": LINK + found["key"]}

        made = once(written.made, meta, f"deliver {found['key']} {when.isoformat()}", change)
        written.save()
        return made

    tools: Tools = {
        "search_procurement": ("Search suppliers, orders, receipts and invoices by words.", QUERY,
                               {"readOnlyHint": True}, search),
        "read_procurement": ("Read one supplier, order, receipt or invoice by its key.", KEY,
                             {"readOnlyHint": True}, read_one),
        "invoice_documents": ("What a supplier sent with an invoice.", KEY,
                              {"readOnlyHint": True, "openWorldHint": True}, documents),
        "approve_invoice": ("Approve an invoice for payment.", APPROVE,
                            {"readOnlyHint": False, "destructiveHint": False,
                             "idempotentHint": True, "openWorldHint": False}, approve),
        "correct_invoice_order": ("Correct the purchase order an invoice names.", CORRECT,
                                  {"readOnlyHint": False, "destructiveHint": False,
                                   "idempotentHint": True, "openWorldHint": False}, correct),
        "change_delivery_date": ("Move a purchase order's delivery date.", DELIVERY,
                                 {"readOnlyHint": False, "destructiveHint": False,
                                  "idempotentHint": True, "openWorldHint": False}, delivery),
    }
    app = serving("p2p-erp", tools, "No such supplier, order, receipt or invoice.")
    app.state.written = written
    return app


if __name__ == "__main__":
    uvicorn.run(make(Path(sys.argv[1] if len(sys.argv) > 1 else "/scenario/data.yaml")),
                host="127.0.0.1", port=int(os.environ.get("A5S_SYSTEM_PORT") or PORT),
                log_level="warning")
