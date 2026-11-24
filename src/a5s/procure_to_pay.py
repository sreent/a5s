"""A procure-to-pay scenario: a made-up distributor's purchasing, warehouse and accounts payable,
each a part with its own team, on a synthetic ERP behind its MCP server (deploy/systems/erp.py).

Its ERP's tools come through the scenario's mcp.yaml: searching and reading suppliers, purchase
orders, goods receipts and suppliers' invoices, what a supplier sent with an invoice, through
a5s's reader, and three changes a5s holds for the deciders of each part: approving an invoice for
payment, correcting the order an invoice names, and moving an order's delivery date. What stays
here is the scenario's own: the directory and who may see what, the obligations its invoices and
orders make, the records as the ERP holds them now, with what was done through it laid over the
data, a three-way match by code, which says what an invoice's order and the warehouse's receipts
show, so no agent's own reading of them decides a payment, the short deliveries the warehouse's
watcher reports, a draft for a person to send, the accounts payable handbook, and its policy pack,
pack.cedar in its folder, under which no invoice is ever approved for payment on an agent's word
alone. Its settings give payables four eyes: above an amount, two of its deciders approve.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from a5s.effects import changed_through, draft_once
from a5s.knowledge import MarkdownKnowledge

ERP = "https://erp.harbour.test/"
SYSTEM = "erp"  # the made-up ERP, as mcp.yaml names it, whose changes its code lays over the data
PARTS = {"SUP-": "purchasing", "PO-": "purchasing", "GR-": "receiving", "INV-": "payables"}
KINDS = {"SUP-": "suppliers", "PO-": "orders", "GR-": "receipts", "INV-": "invoices"}
OWNER = {"suppliers": "owner", "orders": "buyer", "receipts": "clerk", "invoices": "clerk"}
FIELDS = {  # what each kind of record shows of itself, to agents, deciders and graders
    "suppliers": ("name", "terms"),
    "orders": ("status", "supplier", "item", "quantity", "price", "amount", "delivery"),
    "receipts": ("order", "received", "at", "note"),
    "invoices": ("status", "supplier", "order", "quantity", "amount", "due"),
}
KEY = re.compile(r"^(?:SUP-\d{3}|PO-\d{4}|GR-\d{4}|INV-\d{4})$")
CLOSED = ("approved for payment", "paid", "rejected")  # an invoice no longer waiting on anyone


def _amount(value: object) -> float:
    return float(str(value).replace(",", ""))


@dataclass(frozen=True)
class _Held:
    """The scenario's people, parts and records, as its data holds them."""

    people: dict[str, Person]
    parts: dict[str, dict]
    records: dict[str, dict]  # each record's own fields, by its key, as data.yaml has them


class ProcureToPayScenario:
    name = "procure-to-pay"
    record_links = (ERP,)
    record_pattern = r"\b(?:PO|GR|INV)-\d{4}\b|\bSUP-\d{3}\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        self._held: _Held | None = None
        self._seen: tuple[int, int] | None = None
        self._reading = threading.Lock()
        self.drafts: list[dict] = []
        self._draft_lock = threading.Lock()

    def _data(self) -> _Held:
        """The scenario's data, read again whenever the file changes."""
        path = self.folder / "data.yaml"
        with self._reading:
            seen = path.stat()
            if self._held is None or (seen.st_mtime_ns, seen.st_size) != self._seen:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                self._held = _Held(
                    people={p["id"]: Person.listed(p, self.folder) for p in data["people"]},
                    parts=dict(data.get("parts") or {}),
                    records={r["key"]: r for kind in KINDS.values() for r in data.get(kind) or []})
                self._seen = (seen.st_mtime_ns, seen.st_size)
            return self._held

    @property
    def _records(self) -> dict[str, dict]:
        """Every record as the ERP holds it now: the data's, with what was done through the ERP
        laid over each, and the receipts the warehouse booked in since, so what a5s shows of a
        record, and its deciders, is what the ERP holds."""
        found = dict(self._data().records)
        for key, changed in changed_through(SYSTEM).items():
            if key in found:
                found[key] = {**found[key], **changed}
            elif changed.get("added") and KEY.match(key):
                found[key] = {k: v for k, v in changed.items() if k != "added"}
        return found

    def person(self, person_id: str) -> Person | None:
        return self._data().people.get(person_id)

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._data().people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._data().people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._data().people.values() if p.team == name]

    @staticmethod
    def _kind(key: str) -> str | None:
        return next((k for p, k in KINDS.items() if key.startswith(p)), None)

    def part_of(self, record: str) -> str | None:
        if record not in self._records:
            return None
        return next((part for p, part in PARTS.items() if record.startswith(p)), None)

    def sees_part(self, person: str, part: str) -> bool:
        """Whether someone may read what's in a part: its team's, and the teams it names."""
        who = self.person(person)
        found = self._data().parts.get(part)
        return bool(who and found and (who.team == found["team"]
                                       or who.team in (found.get("seen_by") or [])))

    def sees(self, person: str, record: str) -> bool:
        found = self._records.get(record)
        kind = self._kind(record)
        if found is None or kind is None:
            return False
        part = self.part_of(record)
        return found.get(OWNER[kind]) == person or bool(part and self.sees_part(person, part))

    def setup(self, conn, tools_role: str) -> None:
        pass

    def record(self, key: str) -> Record | None:
        found = self._records.get(key)
        kind = self._kind(key)
        if found is None or kind is None:
            return None
        title = {"suppliers": lambda r: r["name"],
                 "orders": lambda r: f"{r['item']}, {r['quantity']} from {self._name(r['supplier'])}",
                 "receipts": lambda r: f"{r['received']} received on {r['order']}",
                 "invoices": lambda r: f"{self._name(r['supplier'])}'s invoice for {r['amount']} GBP"}
        return Record(kind, key, found.get(OWNER[kind]), title[kind](found),
                      {f: str(found[f]) for f in FIELDS[kind] if found.get(f) is not None},
                      ERP + key)

    def _name(self, supplier: str) -> str:
        return (self._records.get(supplier) or {}).get("name", supplier)

    def watched(self) -> list[Record]:
        return [r for key in self._records if (r := self.record(key)) is not None]

    def obligations(self) -> list[Obligation]:
        """What falls due: each invoice still waiting, for its clerk, by its due date, and each
        open order, for its buyer, by its delivery date."""
        found = []
        for key, r in self._records.items():
            due = r.get("due") if key.startswith("INV-") else (
                r.get("delivery") if key.startswith("PO-") and r.get("status") == "open" else None)
            if due is None or (key.startswith("INV-") and r.get("status") in CLOSED):
                continue
            ends = datetime.fromisoformat(f"{due}T17:00:00+00:00")
            owner = r.get("clerk") if key.startswith("INV-") else r.get("buyer")
            record = self.record(key)
            found.append(Obligation("records", key, owner, record.title if record else key,
                                    ends - timedelta(days=30), ends, ERP + key))
        return found

    def match(self, key: str) -> dict | None:
        """A three-way match by code: what an invoice's order and the warehouse's receipts on
        it show, and what's wrong, if anything, so whether an invoice may be paid is never an
        agent's own reading of them. None for a key that's no invoice."""
        records = self._records
        invoice = records.get(key)
        if invoice is None or not key.startswith("INV-"):
            return None
        problems: list[str] = []
        maybe: list[str] = []
        order = records.get(invoice["order"])
        quantity, amount = int(invoice["quantity"]), _amount(invoice["amount"])
        received = sum(int(r["received"]) for k, r in records.items()
                       if k.startswith("GR-") and r.get("order") == invoice["order"])
        if order is None:
            problems.append(f"it names {invoice['order']}, which is no purchase order")
            maybe = [k for k, o in records.items() if k.startswith("PO-")
                     and o["supplier"] == invoice["supplier"] and int(o["quantity"]) == quantity
                     and _amount(o["amount"]) == amount]
        else:
            if order["supplier"] != invoice["supplier"]:
                problems.append(f"{order['key']} is another supplier's order")
            if quantity > int(order["quantity"]):
                problems.append(f"it invoices {quantity}, more than the {order['quantity']} ordered")
            if amount > _amount(order["amount"]):
                problems.append(f"it invoices {invoice['amount']} GBP, more than the order's "
                                f"{order['amount']} GBP")
            if received < quantity:
                problems.append(f"the warehouse received {received} of the {quantity} invoiced")
            before = sorted(  # one that came first, or that's approved already: a duplicate
                k for k, r in records.items() if k.startswith("INV-") and k != key
                and r.get("order") == invoice["order"] and r.get("status") != "rejected"
                and (k < key or r.get("status") in CLOSED))
            if before:
                problems.append(f"{invoice['order']} is invoiced already, by {', '.join(before)}")
        return {"invoice": key, "order": invoice["order"], "supplier": invoice["supplier"],
                "invoiced": quantity, "amount": invoice["amount"],
                "ordered": int(order["quantity"]) if order else None, "received": received,
                "matched": not problems, "problems": problems,
                **({"maybe": maybe} if maybe else {}), "link": ERP + key}

    def short(self) -> list[dict]:
        """Each order the warehouse has received less of than was ordered, with how much less."""
        records = self._records
        found = []
        for key, order in sorted(records.items()):
            if not key.startswith("PO-") or order.get("status") == "open":
                continue
            received = sum(int(r["received"]) for k, r in records.items()
                           if k.startswith("GR-") and r.get("order") == key)
            if received < int(order["quantity"]):
                found.append({"order": key, "supplier": order["supplier"],
                              "ordered": int(order["quantity"]), "received": received,
                              "short": int(order["quantity"]) - received, "link": ERP + key})
        return found

    def settings(self) -> Settings:
        sig = self.folder / "settings.sig"
        signed = (yaml.safe_load(sig.read_text(encoding="utf-8")) or {}).get("signatures", []) if sig.exists() else []
        return parse_settings((self.folder / "settings.yaml").read_bytes(),
                              tuple(Signature(s["signer"], s["value"]) for s in signed))

    def policy_pack(self) -> str | None:
        pack = self.folder / "pack.cedar"
        return pack.read_text(encoding="utf-8") if pack.exists() else None

    def tools(self) -> dict[str, Tool]:
        def draft(call: ToolCall) -> dict:
            return draft_once(call, self.drafts, ERP, self._draft_lock)

        def matching(call: ToolCall) -> dict:
            found = self.match(str(call.args.get("key")))
            return found if found is not None else {"error": f"{call.args.get('key')} is no invoice"}

        def shortfalls(call: ToolCall) -> dict:
            return {"short": self.short()}

        body = {"type": "object", "required": ["title", "body"], "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "record": {"type": "string"}}}
        invoice = {"type": "object", "required": ["key"], "additionalProperties": False,
                   "properties": {"key": {"type": "string", "pattern": r"^INV-\d{4}$",
                                          "description": "The invoice, such as INV-9001"}}}
        tools = {
            "create_draft": Tool(
                "create_draft", "Save a draft, such as a note to a supplier, for a person to "
                "review and send.", body, draft, writes=True, text_fields=("title", "body"),
                record_arg="record", idempotent=True),
            "match_invoice": Tool(
                "match_invoice", "Match an invoice with its purchase order and what the warehouse "
                "received, by code: whether it matches, and what's wrong if it doesn't.",
                invoice, matching, record_arg="key"),
            "short_deliveries": Tool(
                "short_deliveries", "The orders the warehouse has received less of than was "
                "ordered, by code, with how many fewer.", {"type": "object", "properties": {}},
                shortfalls),
        }
        tools.update(MarkdownKnowledge(self.folder / "knowledge",
                                       sees_part=self.sees_part, person=self.person).tools())
        return tools
