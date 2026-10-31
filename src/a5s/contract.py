"""The scenario contract: what a scenario gives a5s.

Phase 1 covers the directory, with what each person may see, settings, tools, the
obligations its records give rise to, each person's records as they stand, the part each
record is in, how its records' keys look, and the policy pack. Events from records, the
governed process and the decision surface follow in later steps.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError

from a5s.core.ledger import canonical

INSTANCE_APPROVER = "instance-approver"  # approves instances with no parts, and sets their level
# A part's owner holds part-owner:<part>, such as part-owner:billing: they approve the instances
# that work in their part, and how far each may act there.
PART_OWNER = "part-owner"
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
    # The argument that names the record a call is about, such as key, and the field of what it
    # returns that names each record in it. The core lets an instance work only on records in
    # its parts, and only on those everyone the run acts for may see.
    record_arg: str | None = None
    record_field: str | None = None

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
        if self.record_arg or self.record_field:  # and one that stops naming its records
            payload["records"] = [self.record_arg, self.record_field]
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
    # The parts it works in, its scope, each with its level there, or None for `level`. Their
    # owners approve it. With none, it works on no part's records, and an instance approver
    # approves it.
    parts: dict[str, int | None] = field(default_factory=dict)

    def level_in(self, part: str, start: int, most: int) -> int:
        """How far it may act in a part, between a release's starting level and its maximum."""
        wanted = self.parts.get(part)
        if wanted is None:
            wanted = start if self.level is None else self.level
        return min(wanted, most)


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
    # The class of the scenario's data: a model must be approved for it to see any. Without
    # one, it's internal, so no model approved only for made-up data sees real data.
    data_class: str = "internal"
    # Fields of a class of their own, such as {"contact": "personal"}: a model not approved
    # for it gets each as a handle instead (core/handles.py)
    classified: dict[str, str] = field(default_factory=dict)


class SettingsError(ValueError):
    """Why bytes aren't a version of the settings a5s can use."""


_ID = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]
_PERSON = Annotated[str, StringConstraints(strict=True,
                                           pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")]
# Whom an instance serves: a person, or everyone in a team or holding a role, as the directory
# says when each run opens, such as team:sales or role:part-owner:billing
_WHO = Annotated[str, StringConstraints(strict=True, pattern=(
    r"^(?:(?:team|role):[A-Za-z0-9][A-Za-z0-9._@:-]{0,127}|[A-Za-z0-9][A-Za-z0-9._@-]{0,127})$"))]
_FIELD = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z][A-Za-z0-9 _-]{0,62}$")]
_LEVEL = Annotated[StrictInt, Field(ge=0, le=2)]


class _Instance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    definition: _ID
    serves: list[_WHO]
    level: _LEVEL | None = None
    owner: _PERSON | None = None
    deputy: _PERSON | None = None
    parts: list[_ID] | dict[_ID, _LEVEL | None] = Field(default_factory=list)


class _Version(BaseModel):
    """a5s's own settings format, checked strictly: names are plain words, levels are whole
    numbers from 0 to 2, and nothing else may be there."""

    model_config = ConfigDict(extra="forbid", strict=True)

    serial: Annotated[StrictInt, Field(ge=0)] = 0
    data_class: _ID = "internal"
    classified: dict[_FIELD, _ID] = Field(default_factory=dict)
    instances: dict[_ID, _Instance] = Field(default_factory=dict)


def _plain_yaml(raw: bytes) -> Any:
    """YAML without anchors or aliases, which can make a few bytes into gigabytes."""
    try:
        for event in yaml.parse(raw, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise SettingsError("settings may not use YAML anchors or aliases")
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SettingsError(f"it isn't YAML a5s can read: {exc}") from None


def parse_settings(raw: bytes, signatures: tuple[Signature, ...] = ()) -> Settings:
    """A version of the settings, in a5s's own format, from exactly the bytes that were signed.
    SettingsError, which is a ValueError, if they aren't one.

    The core reads the bytes it stored again at every run, so the format is a5s's,
    whichever scenario's settings they are.
    """
    data = _plain_yaml(raw)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SettingsError("settings are a mapping, such as serial: and instances:")
    try:
        version = _Version.model_validate(data)
    except ValidationError as exc:
        raise SettingsError("; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'settings'}: "
                                      f"{e['msg']}" for e in exc.errors())) from None
    return Settings(
        version=hashlib.sha256(raw).hexdigest()[:16],
        serial=version.serial,
        raw=raw,
        signatures=signatures,
        data_class=version.data_class,
        classified=dict(version.classified),
        instances=tuple(
            InstanceSettings(id=iid, definition=i.definition, serves=tuple(i.serves),
                             level=i.level, owner=i.owner, deputy=i.deputy,
                             parts=(dict(i.parts) if isinstance(i.parts, dict)
                                    else dict.fromkeys(i.parts)))
            for iid, i in version.instances.items()
        ),
    )


class Scenario(Protocol):
    """What a scenario gives a5s. One may also have record(key) -> Record | None, which reads
    one record, as watched() stands to it, or None if there's no such record; a5s reads that
    one record with it, such as for a case's brief, and without it reads every record with
    watched() to find the one."""

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

    def part_of(self, record: str) -> str | None:
        """The part a record is in, by its key, or None if it's in none."""

    def sees(self, person: str, record: str) -> bool:
        """Whether the directory lets someone see a record, by its key. False for a record
        that doesn't exist."""

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


def record_of(scenario: Scenario, key: str) -> Record | None:
    """One record, by its key, as it stands now: from the scenario's record(key) if it has
    one, else from every record it watches. None if there's no such record."""
    one = getattr(scenario, "record", None)
    if callable(one):
        return one(key)
    return next((r for r in scenario.watched() if r.key == key), None)
