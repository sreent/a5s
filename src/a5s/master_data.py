"""SAP master data governance: change requests, validation, data quality and data owners.

A synthetic SAP MDG, after the LEAN data governance framework: master data for suppliers, their
bank and payment data, customers and materials, each data object with one named owner, and the
change requests people raise against it. Code, never the model, validates a request, finds its
likely duplicates and measures each data object's quality against its owner's target. A
sensitive change, or a new record, waits for its data object's owner to confirm it in SAP's own
workflow, and a5s chases them for it as it falls due, and up the line when it's late. An agent
prepares, checks, chases, drafts and proposes: a correction it proposes waits for the data
object's owner to decide it, and it approves nothing in SAP. Bank details reach it only as
handles, and what suppliers write reaches it only through a5s's reader.

SAP's own tools, its change requests and master records, what suppliers sent, and updates to
what a request proposes, are its MCP server's, which the scenario's mcp.yaml declares
(deploy/systems/sap.py makes one up). This is a5s's side: the directory, who may see what, what
people owe, code's checks and its measures of quality, drafts and the handbook, over SAP's
requests as SAP holds them now.
"""

from __future__ import annotations

import math
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

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

LINK = "https://mdg.sap.test/"
TERMS = ("NT30", "NT45", "NT60")  # the approved payment terms
UNITS = ("EA", "PC", "KG", "M", "L")  # base units of measure
TYPES = ("ROH", "HALB", "FERT")  # material types: raw, semi-finished, finished
VAT = {"GB": r"GB(\d{9}|\d{12})", "DE": r"DE\d{9}", "FR": r"FR[0-9A-Z]{2}\d{9}",
       "NL": r"NL\d{9}B\d{2}"}  # where a VAT number is required, and its form
FIELDS = {"supplier": ("name", "country", "postcode", "vat"),
          "supplier-bank": ("supplier", "iban", "payment_terms"),
          "customer": ("name", "country", "postcode", "vat", "payment_terms"),
          "material": ("description", "base_unit", "material_type")}
# Fields whose change its data object's owner confirms, as the framework's sensitive changes
SENSITIVE = {"supplier": ("name", "country", "postcode", "vat"),
             "supplier-bank": ("supplier", "iban", "payment_terms"),
             "customer": ("country", "vat", "payment_terms"), "material": ()}
# What an agent may correct in a request, for the owner to decide: no object's sensitive field.
# Not a country, which decides the VAT rule a supplier's or customer's number is checked by
CORRECTABLE = ("description", "base_unit", "material_type")
HANDLED = ("iban",)  # what reaches an agent only as a handle, and no record's fields hold
SUFFIXES = {"ltd", "limited", "gmbh", "inc", "llc", "plc", "ag", "sa", "co"}


def iban_ok(iban: str) -> bool:
    """An IBAN's form and check digits, as ISO 13616 sets them."""
    found = re.sub(r"\s+", "", iban or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", found):
        return False
    return int("".join(str(int(c, 36)) for c in found[4:] + found[:4])) % 97 == 1


def percent(share: float) -> str:
    """A share as people read it, cut to a tenth and never rounded up to a target it misses:
    97.9%, not 98%."""
    return f"{math.floor(share * 1000 + 1e-9) / 10:g}%"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").casefold()) if w not in SUFFIXES}


def _like(a: str, b: str) -> bool:
    """Whether two names or descriptions are alike: most of their words the same."""
    x, y = _words(a), _words(b)
    return bool(x and y) and len(x & y) / len(x | y) >= 0.6


def failures(kind: str, values: dict[str, Any]) -> list[dict[str, str]]:
    """What fails the critical-field rules of a data object, field by field."""
    failed: list[dict[str, str]] = []

    def fail(name: str, why: str) -> None:
        failed.append({"field": name, "why": why})

    def present(*names: str) -> None:
        for name in names:
            if not str(values.get(name) or "").strip():
                fail(name, "it's mandatory, and empty")

    if kind in ("supplier", "customer"):
        present("name", "country", "postcode")
        rule = VAT.get(str(values.get("country") or ""))
        vat = str(values.get("vat") or "")
        if rule and not vat:
            fail("vat", f"a VAT number is required in {values.get('country')}")
        elif rule and not re.fullmatch(rule, vat):
            fail("vat", f"it isn't a VAT number in {values.get('country')}'s form")
    if kind in ("supplier-bank", "customer") and values.get("payment_terms") not in TERMS:
        fail("payment_terms", f"{values.get('payment_terms') or 'none'} isn't an approved "
                              f"payment term: {', '.join(TERMS)}")
    if kind == "supplier-bank" and not iban_ok(str(values.get("iban") or "")):
        fail("iban", "its form or check digits are wrong")
    if kind == "material":
        present("description")
        if values.get("base_unit") not in UNITS:
            fail("base_unit", f"it must be one of {', '.join(UNITS)}")
        if values.get("material_type") not in TYPES:
            fail("material_type", f"it must be one of {', '.join(TYPES)}")
    return failed


class MasterDataScenario:
    name = "master-data"
    record_links = (LINK,)
    record_pattern = r"\b(?:CR\d{7}|[SBCM]-\d{6}|DQ-[a-z]+(?:-[a-z]+)*)\b"

    def __init__(self, folder: Path, database_url: str):
        self.folder = folder
        self.database_url = database_url
        data = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
        self._people = {p["id"]: Person.listed(p, folder) for p in data["people"]}
        self._objects: dict[str, dict] = data["objects"]
        self._records = {r["key"]: r for r in data["records"]}
        self._requests = {r["key"]: r for r in data["requests"]}  # as they were raised
        self.drafts: list[dict] = []
        self._draft_lock = threading.Lock()

    def _now(self) -> dict[str, dict]:
        """The change requests as SAP holds them now: what's been changed through its server,
        such as a correction an owner approved, over the requests as they were raised."""
        changed = changed_through("sap")
        return {k: {**r, **changed[k]} if k in changed else r for k, r in self._requests.items()}

    def request(self, key: str) -> dict | None:
        """One change request, as SAP holds it now."""
        return self._now().get(key)

    # The directory

    def person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    def find(self, identity: str) -> Person | None:
        return next((p for p in self._people.values() if identity in p.identities), None)

    def holders(self, role: str) -> list[Person]:
        return [p for p in self._people.values() if role in p.roles]

    def team(self, name: str) -> list[Person]:
        return [p for p in self._people.values() if p.team == name]

    # Data objects, their owners, and who may see what

    def owner(self, kind: str) -> Person | None:
        """The one named owner of a data object, as the directory's role says."""
        return next(iter(self.holders(f"part-owner:{kind}")), None)

    def part_of(self, record: str) -> str | None:
        if record.startswith("DQ-"):
            return record[3:] if record[3:] in self._objects else None
        found = self._requests.get(record) or self._records.get(record)
        return found["object"] if found else None

    def sees(self, person: str, record: str) -> bool:
        who, kind = self._people.get(person), self.part_of(record)
        if who is None or kind is None:
            return False
        rule = self._objects[kind]
        stewards = who.team in ("data-team", rule["team"])  # its owner's team, and the data team
        if record in self._requests:
            found = self._requests[record]
            return stewards or person in (found["requester"], found["steward"])
        if record.startswith("DQ-"):
            return stewards
        return stewards or who.team in (rule.get("seen_by") or ())

    def sees_part(self, person: str, part: str) -> bool:
        who, rule = self._people.get(person), self._objects.get(part) or {}
        return bool(who and rule and (who.team in ("data-team", rule["team"])
                                      or who.team in (rule.get("seen_by") or ())))

    def setup(self, conn, tools_role: str) -> None:
        pass

    # What people owe: the next step of each request, and each data object below its target

    def _owes(self, request: dict) -> str:
        if request["status"] == "awaiting owner":
            owner = self.owner(request["object"])
            return owner.id if owner else request["steward"]
        return request["requester"] if request["status"] == "needs info" else request["steward"]

    @staticmethod
    def _owed_for(found: dict[str, Any]) -> str | None:
        """What a data object's owner owes for its quality, in words, if anything."""
        said = []
        if found["below_target"]:
            said.append(f"bring it back to its target of {found['target']} of records passing "
                        f"({found['share']} now)")
        if n := len(found["duplicates"]):
            said.append(f"resolve {n} likely duplicate{'s' if n != 1 else ''}")
        return f"{found['name']}: {' and '.join(said)}" if said else None

    def quality(self, kind: str) -> dict[str, Any]:
        """A data object's quality, worked out by code: how many of its records pass every
        critical-field rule, against its owner's target, which fail and why, and its likely
        duplicates."""
        rule, owner = self._objects[kind], self.owner(kind)
        records = [r for r in self._records.values() if r["object"] == kind]
        failing = [{"key": r["key"], "failed": f} for r in records
                   if (f := failures(kind, r))]
        share = (len(records) - len(failing)) / len(records) if records else 1.0
        return {"object": kind, "name": rule["name"], "owner": owner.name if owner else None,
                "records": len(records), "passing": len(records) - len(failing),
                "share": percent(share), "target": percent(rule["target"]),
                "below_target": share < rule["target"], "failing": failing,
                "duplicates": self._duplicates_within(records),
                "link": f"{LINK}quality/{kind}"}

    def obligations(self) -> list[Obligation]:
        owed = [Obligation("records", r["key"], self._owes(r), r["title"],
                           _at(r["opened"], "09:00:00"), _at(r["due"], "17:00:00"),
                           LINK + r["key"])
                for r in self._now().values() if r["status"] not in ("approved", "rejected")]
        for kind, rule in self._objects.items():
            found, owner = self.quality(kind), self.owner(kind)
            if owner and (title := self._owed_for(found)):
                owed.append(Obligation("quality", f"DQ-{kind}", owner.id, title,
                                       _at(rule["measured"], "09:00:00"),
                                       _at(rule["fix_by"], "17:00:00"), found["link"]))
        return owed

    def watched(self) -> list[Record]:
        """Each request, as whoever owes its next step stands to it, and each data object's
        quality, as its owner does: what the watcher's reports tell each of them changed."""
        found = [self._record(r) for r in self._now().values()]
        for kind in self._objects:
            if (owner := self.owner(kind)) is not None:
                q = self.quality(kind)
                found.append(Record("quality", f"DQ-{kind}", owner.id, f"Data quality: {q['name']}",
                                    {"records passing": f"{q['passing']} of {q['records']}",
                                     "share passing": q["share"], "target": q["target"],
                                     "below target": "yes" if q["below_target"] else "no",
                                     "likely duplicates": str(len(q["duplicates"]))},
                                    q["link"]))
        return found

    def record(self, key: str) -> Record | None:
        if key.startswith("DQ-"):
            return next((r for r in self.watched() if r.key == key), None)
        if (request := self._now().get(key)) is not None:
            return self._record(request)
        found = self._records.get(key)
        if found is None:
            return None
        owner = self.owner(found["object"])  # a master record, its data object's owner's
        title = found.get("name") or found.get("description") or (
            f"Bank and payment data of {found.get('supplier')}")
        return Record("master", key, owner.id if owner else "", title,
                      {k: str(v) for k, v in found.items() if k not in ("key", *HANDLED)},
                      LINK + key)

    def _record(self, request: dict) -> Record:
        return Record("records", request["key"], self._owes(request), request["title"],
                      {"status": request["status"], **{
                          f"proposed {k}": str(v) for k, v in request["values"].items()
                          if k not in HANDLED}},
                      LINK + request["key"])

    # Checking a request

    def _merged(self, request: dict) -> dict[str, Any]:
        """A request's values over the record it changes: the record as it would be."""
        return {**(self._records.get(request.get("record") or "") or {}), **request["values"]}

    def _duplicates(self, kind: str, values: dict, other_than: str | None) -> list[dict]:
        """Existing records a request's record looks like, by the framework's match rules."""
        found = []
        for r in self._records.values():
            if r["object"] != kind or r["key"] == other_than:
                continue
            why = []
            if kind in ("supplier", "customer"):
                if values.get("vat") and values.get("vat") == r.get("vat"):
                    why.append("the same VAT number")
                if (values.get("country"), values.get("postcode")) == (
                        r.get("country"), r.get("postcode")) and _like(values.get("name", ""),
                                                                       r.get("name", "")):
                    why.append("a similar name in the same country and postcode")
            if kind == "supplier-bank" and values.get("iban") and r.get("supplier") != values.get(
                    "supplier") and re.sub(r"\s", "", values["iban"]) == r.get("iban"):
                why.append(f"the same bank account as supplier {r['supplier']}")
            if kind == "material" and _like(values.get("description", ""),
                                            r.get("description", "")):
                why.append("a similar description")
            if why:
                found.append({"key": r["key"], "why": "; ".join(why)})
        return found

    def _duplicates_within(self, records: list[dict]) -> list[dict]:
        """Each pair of records alike by the match rules, once."""
        keys, pairs = [r["key"] for r in records], []
        for i, a in enumerate(records):
            later = set(keys[i + 1:])
            pairs += [{"key": a["key"], "with": d["key"], "why": d["why"]}
                      for d in self._duplicates(a["object"], a, a["key"]) if d["key"] in later]
        return pairs

    def check(self, key: str) -> dict[str, Any]:
        """What code finds of a change request: which critical-field rules it fails, which
        sensitive fields it touches, its likely duplicates, and where it goes next."""
        request = self._now().get(key)
        if request is None:
            return {"error": "no such change request"}
        kind, owner = request["object"], self.owner(request["object"])
        values = self._merged(request)
        failed = failures(kind, values)
        touched = [f for f in SENSITIVE.get(kind, ()) if f in request["values"]]
        alike = self._duplicates(kind, values, request.get("record"))
        requester = self._people.get(request["requester"])
        if request["status"] in ("approved", "rejected"):
            route = f"nowhere: it's {request['status']} already"
        elif failed:
            route = (f"back to its requester, {requester.name if requester else 'who raised it'}, "
                     "to correct " + ", ".join(f["field"] for f in failed))
        elif touched or alike or request["kind"] == "create":
            route = (f"{owner.name if owner else 'its owner'}, who owns "
                     f"{self._objects[kind]['name'].lower()}, confirms it in SAP")
        else:
            route = ("SAP's workflow approves it with no owner's confirmation: it touches no "
                     "sensitive field, passes every check, and has no likely duplicate")
        return {"key": key, "object": kind, "owner": owner.name if owner else None,
                "failed": failed, "passed": not failed, "sensitive": touched,
                "duplicates": alike, "route": route, "link": LINK + key}

    def settings(self) -> Settings:
        sig = self.folder / "settings.sig"
        signed = (yaml.safe_load(sig.read_text(encoding="utf-8")) or {}).get("signatures", []) if sig.exists() else []
        return parse_settings((self.folder / "settings.yaml").read_bytes(),
                              tuple(Signature(s["signer"], s["value"]) for s in signed))

    def policy_pack(self) -> None:
        return None

    # Tools

    def tools(self) -> dict[str, Tool]:
        """a5s's side of the scenario's tools: code's checks, drafts and the handbook. SAP's own,
        to search and read its requests and records, read what suppliers sent, and correct
        what a request proposes, come from its MCP server, as mcp.yaml declares them."""
        def checked(call: ToolCall) -> dict:
            return self.check(str(call.args.get("key", "")))

        def measured(call: ToolCall) -> dict:
            kind = str(call.args.get("object", ""))
            if kind not in self._objects:
                return {"error": f"the data objects are {', '.join(self._objects)}"}
            return {**self.quality(kind), "key": f"DQ-{kind}"}

        def draft(call: ToolCall) -> dict:
            return draft_once(call, self.drafts, LINK, self._draft_lock)

        key = {"type": "object", "required": ["key"], "properties": {"key": {
            "type": "string", "description": "A change request, such as CR0000101"}}}
        tools = {t.name: t for t in (
            Tool("check_request", "Check a change request by code: the critical-field rules it "
                 "fails, the sensitive fields it touches, its likely duplicates, and whether it's "
                 "approved automatically, goes back to its requester, or waits for its data "
                 "object's owner.", key, checked, record_arg="key", record_field="key"),
            Tool("check_quality", "Measure a data object's quality by code: its records "
                 "passing every critical-field rule, against its owner's target, which fail and "
                 "why, and its likely duplicates.",
                 {"type": "object", "required": ["object"], "properties": {"object": {
                     "type": "string", "enum": list(self._objects),
                     "description": "The data object"}}},
                 measured, record_field="key"),
            Tool("create_draft", "Save a draft, such as a note to a requester or a data quality "
                 "report, for a person to read, change and send.",
                 {"type": "object", "required": ["title", "body"], "properties": {
                     "title": {"type": "string"}, "body": {"type": "string"},
                     "record": {"type": "string"}}},
                 draft, writes=True, text_fields=("title", "body"), record_arg="record",
                 idempotent=True),
        )}
        tools.update(MarkdownKnowledge(self.folder / "knowledge",
                                       sees_part=self.sees_part, person=self.person).tools())
        return tools


def _at(day: str, hour: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour}+00:00")
