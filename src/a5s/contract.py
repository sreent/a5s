"""The scenario contract: what a scenario gives a5s.

Phase 1 covers the directory, settings, tools, the obligations its records
give rise to, each person's records as they stand, how its records' keys look,
and the policy pack. Events from records, the governed process and the decision
surface follow in later steps.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import yaml

from a5s.core.ledger import canonical

INSTANCE_APPROVER = "instance-approver"  # approves instances with no parts, and sets their level
# a5s's own roles, for approving its releases. An agent's owner holds agent-owner:<agent>.
RELEASE_APPROVER = "release-approver"  # never from the team that runs a5s, nor above it
ASSURANCE = "assurance"


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    team: str
    in_audience: bool = True  # whether agents may message them at all
    roles: tuple[str, ...] = ()
    public_key: str | None = None  # for checking what they sign
    identities: tuple[str, ...] = ()  # their accounts elsewhere, such as entra:<object id>
    manager: str | None = None  # the next person up their reporting line
    timezone: str = "UTC"  # an IANA name, such as Europe/London
    hours: tuple[str, str] = ("09:00", "17:00")  # their working hours, in their time zone
    workdays: tuple[int, ...] = (1, 2, 3, 4, 5)  # ISO weekdays: Monday is 1


@dataclass(frozen=True)
class Obligation:
    """Something a person owes, worked out by code from the scenario's records."""

    source: str  # the kind of record it comes from, such as "records"
    record: str  # the record's key
    person: str  # who owes it
    title: str
    opened: datetime  # when it started, so half the time allowed is known
    due: datetime
    link: str | None = None


@dataclass(frozen=True)
class Record:
    """A record as its person stands to it now, for the core to tell them what changed."""

    source: str  # the kind of record it is, such as "records"
    key: str
    person: str  # whose it is, such as its owner
    title: str
    fields: dict[str, str]  # what a change in matters, named in words, such as {"status": "open"}
    link: str | None = None


@dataclass(frozen=True)
class ToolCall:
    """What a tool sees: its arguments, and who the run acts for."""

    args: dict[str, Any]
    instance: str
    run: str
    acts_for: tuple[str, ...]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[ToolCall], Any]
    reads: bool = True
    writes: bool = False
    destructive: bool = False
    sends_outside: bool = False
    text_fields: tuple[str, ...] = ()  # arguments that are outgoing text, such as a draft's body
    # Fields of what it returns that hold sensitive values, such as a contact, which the agent
    # gets as handles: it passes them on, and a5s puts the values in (core/handles.py)
    handles: tuple[str, ...] = ()

    @property
    def risk(self) -> dict[str, bool]:
        return {
            "reads": self.reads,
            "writes": self.writes,
            "destructive": self.destructive,
            "sends_outside": self.sends_outside,
        }

    @property
    def schema_hash(self) -> str:
        """Pinned in releases, so a changed tool, its risk flags included, needs a new release."""
        payload = {"name": self.name, "description": self.description, "schema": self.schema,
                   "risk": self.risk, "text_fields": list(self.text_fields)}
        if self.handles:  # so a tool that stops handing a value over needs a new release
            payload["handles"] = list(self.handles)
        return hashlib.sha256(canonical(payload).encode()).hexdigest()

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "schema": self.schema,
            "risk": self.risk,
            "text_fields": list(self.text_fields),
            "schema_hash": self.schema_hash,
        }


@dataclass(frozen=True)
class InstanceSettings:
    id: str
    definition: str
    serves: tuple[str, ...]
    level: int | None = None  # the release's starting level, if the settings set none
    owner: str | None = None  # who runs it here, and their deputy: people in this directory
    deputy: str | None = None


@dataclass(frozen=True)
class Signature:
    signer: str
    value: str


@dataclass(frozen=True)
class Settings:
    version: str
    instances: tuple[InstanceSettings, ...] = field(default_factory=tuple)
    serial: int = 0  # rises with every version, so an older one can't be replayed
    raw: bytes = b""  # exactly what was signed
    signatures: tuple[Signature, ...] = ()


def parse_settings(raw: bytes, signatures: tuple[Signature, ...] = ()) -> Settings:
    """A version of the settings, in a5s's own format, from exactly the bytes that were signed.

    The core reads the bytes it stored again at every run, so the format is a5s's,
    whichever scenario's settings they are.
    """
    data = yaml.safe_load(raw) or {}
    return Settings(
        version=hashlib.sha256(raw).hexdigest()[:16],
        serial=int(data.get("serial", 0)),
        raw=raw,
        signatures=signatures,
        instances=tuple(
            InstanceSettings(id=iid, definition=i["definition"], serves=tuple(i["serves"]),
                             level=i.get("level"), owner=i.get("owner"), deputy=i.get("deputy"))
            for iid, i in (data.get("instances") or {}).items()
        ),
    )


class Scenario(Protocol):
    name: str
    record_links: tuple[str, ...]  # the only link prefixes agents' messages may carry
    # A regular expression for its records' keys, such as Q-\d{4}, so a message that names
    # one goes in that record's case. None if its messages never name records.
    record_pattern: str | None

    def person(self, person_id: str) -> Person | None: ...

    def find(self, identity: str) -> Person | None:
        """Whose account elsewhere this is, such as entra:<object id> for Teams."""

    def holders(self, role: str) -> list[Person]:
        """The people the directory assigns a role to."""

    def team(self, name: str) -> list[Person]:
        """The people in a team, such as the one that runs a5s."""

    def setup(self, conn: Any, tools_role: str) -> None:
        """Set up anything the scenario keeps in a5s's database, such as a fake system's
        tables, for its tools, which run as `tools_role`. Most scenarios keep nothing there."""

    def tools(self) -> dict[str, Tool]: ...

    def obligations(self) -> list[Obligation]:
        """What people owe now, from the records: one for each record and person.
        Something that's done, such as a closed case, owes nothing. If the records
        can't be read, raise: an empty list means nothing is owed."""

    def watched(self) -> list[Record]:
        """Each person's records as they stand now, closed ones included, so an agent that
        reports on them can say what changed. If the records can't be read, raise: an
        empty list means nobody has any."""

    def settings(self) -> Settings: ...

    def policy_pack(self) -> str | None: ...
