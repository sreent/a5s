"""The scenario contract: what a scenario gives a5s.

Phase 1 covers the directory, with what each person may see, settings, tools, the
obligations its records give rise to, each person's records as they stand, the part each
record is in, how its records' keys look, and the policy pack. Events from records, the
governed process and the decision surface follow in later steps.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Protocol, cast

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from a5s import levels
from a5s.core.ledger import canonical

INSTANCE_APPROVER = "instance-approver"  # approves instances with no parts, and sets their level
# A part's owner holds part-owner:<part>, such as part-owner:billing: they approve the instances
# that work in their part, and how far each may act there.
PART_OWNER = "part-owner"
# Someone a part's owner names to decide the changes agents ask for there, beside them, such
# as while they're away: part-delegate:<part>. They approve no settings.
PART_DELEGATE = "part-delegate"
# An agent's own roles, each for one agent, such as agent-owner:assistant. Its owner owns its
# definition and releases, by the directory alone; its authors draft changes to it; and its
# viewers see how it's built, read only (docs/studio.md#people-roles-and-spaces).
AGENT_OWNER = "agent-owner"
AGENT_AUTHOR = "agent-author"
AGENT_VIEWER = "agent-viewer"
# a5s's own roles, for approving its releases
RELEASE_APPROVER = "release-approver"  # never from the team that runs a5s, nor above it
ASSURANCE = "assurance"
AUDITOR = "auditor"  # reads the ledger; only assurance gives a group it (core/memberships.py)
DATA_PROTECTION = "data-protection-officer"  # answers requests for someone's data (core/export.py)
# The roles the identity provider's groups may give, as the settings map them: those people use
# by signing in, each with a part's or an agent's where it's theirs. The roles a release needs,
# which people use by signing with keys of their own, stay the directory's, an agent's owner
# among them (core/memberships.py).
GROUP_ROLES = (INSTANCE_APPROVER, DATA_PROTECTION, AUDITOR, "grader")
GROUP_PART_ROLES = (PART_OWNER, PART_DELEGATE)
GROUP_AGENT_ROLES = (AGENT_AUTHOR, AGENT_VIEWER)


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
    # When their authenticator was last reset, if the directory says: how a stolen identity
    # usually starts, so their decisions wait a day after it
    reset_at: datetime | None = None
    # The language they read, as a BCP 47 code, such as th, which they can choose otherwise on
    # their own page in the studio (core/languages.py)
    language: str = "en"

    @classmethod
    def listed(cls, entry: Mapping[str, Any], folder: Path) -> Person:
        """Someone as a scenario's directory lists them, its lists as tuples, with the public
        key its folder keeps for them in keys/<id>.pub, if there is one."""
        given: dict[str, Any] = {k: tuple(v) if isinstance(v, list) else v
                                 for k, v in entry.items()}
        key = folder / "keys" / f"{entry['id']}.pub"
        return cls(**given, public_key=key.read_text(encoding="utf-8").strip() if key.exists() else None)


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
    person: str  # who is responsible for its next step, such as its owner
    title: str
    # What a change in matters, named in words, such as {"status": "open"}: what a person
    # deciding a change to it weighs, never values that change by themselves, such as a time
    # it was last read, since a held change is made only if its fields are as they stood.
    fields: dict[str, str]
    link: str | None = None


# What a field of the extractor's form may be, besides a choice from a list: never free text
EXTRACT_KINDS = ("key", "amount", "date", "flag")


@dataclass(frozen=True)
class ToolCall:
    """What a tool sees: its arguments, and who the run acts for."""

    args: dict[str, Any]
    instance: str
    run: str
    acts_for: tuple[str, ...]
    # For a change, or a tool marked idempotent, the same whenever the same effect is asked for
    # in a run or task: a system that adds something makes it once for each key
    key: str | None = None
    # For a run that acts for nobody, such as one a system's event or a schedule started:
    # everyone its instance serves, as the directory says now, whom what it finds may reach
    serves: tuple[str, ...] = ()


UNDO_WITHIN = timedelta(days=7)  # the longest a change may be undone after it's made [starting value]


@dataclass(frozen=True)
class Undo:
    """How a change a tool makes is reversed (core/undoing.py): by calling `tool`, one of the
    scenario's own, such as the same one, with each of its arguments from the change's own
    (`args.<name>`) or from its record as it stood before it (`before.<field>`, a field of the
    record, as the scenario gives it), within `within` of its being made."""

    tool: str
    args: tuple[tuple[str, str], ...]
    within: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if not self.args:
            raise ValueError(f"undoing with {self.tool} takes the arguments that reverse it")
        for name, source in self.args:
            kind, _, of = source.partition(".")
            if kind not in ("args", "before") or not of:
                raise ValueError(f"undoing with {self.tool}: {name} comes from args.<name> or "
                                 f"before.<field>, not {source}")
        if not timedelta(minutes=1) <= self.within <= UNDO_WITHIN:
            raise ValueError(f"undoing with {self.tool}: a change may be undone for a minute to "
                             f"{UNDO_WITHIN.days} days after it's made")

    def described(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": dict(self.args), "within": self.within.total_seconds()}


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
    # The part it works in when a call names no record, such as a team's shared mailbox: a call
    # to it works at the instance's level in that part, and only where the instance works in it.
    # None: at the instance's own level, which with parts is the lowest of theirs.
    part: str | None = None
    # The type of action it takes, if it changes a part's data, such as change-due-date. It
    # names the record it changes, by record_arg. At level 1, a5s holds such a call for the
    # owner of the record's part to decide, and makes it once they approve it.
    action: str | None = None
    # Whether the tool makes the same effect only once for the task or run's key, returning its
    # original result if another slice asks again. The gateway supplies that key; the tool honors it.
    idempotent: bool = False
    # Fields of what it returns that hold content from outside the organisation, such as an
    # email's body, whatever their type, and the fixed form a5s's extractor fills from them
    # instead, each field typed: key, amount, date, flag, or choice:<one>|<another>. The agent
    # gets the form, never the content, and its run is marked as having read outside content.
    outside: tuple[str, ...] = ()
    extract: dict[str, str] = field(default_factory=dict)
    # Whether what it returns holds a few words written outside the organisation as they are,
    # such as the titles and links of an outside library's documents, which the agent reads to
    # choose one: its run is marked once it's had them, as if it had read outside content
    marks: bool = False
    # For text it writes that people check before it goes to someone outside the organisation,
    # such as a reply left among a shared mailbox's drafts: who checks it (people,
    # team:<team> or role:<role>), and where, in a few words. a5s's notes on what the agent
    # wrote, such as a date it gave itself, go to them, in a5s's own words, never into the
    # text, which someone outside would read; and a5s puts no value a handle stands for in it,
    # such as another customer's address: only they add what's needed (round 15)
    checked_by: tuple[str, ...] = ()
    checked_in: str = ""
    # How a change it makes is reversed, if it says: someone it was for, or who decides its
    # changes in the record's part, may undo it for a while after it's made (core/undoing.py)
    undo: Undo | None = None

    def __post_init__(self) -> None:
        if self.undo is not None and not (self.action and self.record_arg):
            raise ValueError(f"{self.name}: only a tool that changes a record says how to undo it")
        if bool(self.outside) != bool(self.extract):
            raise ValueError(f"{self.name}: a tool that returns outside content names the form "
                             "a5s's extractor fills from it, and only such a tool names one")
        for name, kind in self.extract.items():
            choices = kind.removeprefix("choice:").split("|") if kind.startswith("choice:") else []
            if kind not in EXTRACT_KINDS and not (choices and all(choices)):
                raise ValueError(f"{self.name}: the form's field {name} is a {kind}, which a5s's "
                                 f"extractor doesn't fill: use {', '.join(EXTRACT_KINDS)} or "
                                 "choice:<one>|<another>")

    @property
    def risk(self) -> dict[str, bool]:
        return {
            "reads": self.reads,
            "writes": self.writes or bool(self.action),  # a change always writes
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
        if self.action:  # or that changes another type of thing
            payload["action"] = self.action
        if self.idempotent:  # or that promises to return its original effect on a retry
            payload["idempotent"] = True
        if self.outside:  # or reads outside content another way
            payload["outside"] = [list(self.outside), self.extract]
        if self.marks:  # or stops marking its run
            payload["marks"] = True
        if self.undo:  # or is undone another way, or for longer
            payload["undo"] = self.undo.described()
        return hashlib.sha256(canonical(payload).encode()).hexdigest()

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "schema": self.schema,
            "risk": self.risk,
            "text_fields": list(self.text_fields),
            "action": self.action,
            "schema_hash": self.schema_hash,
        }


@dataclass(frozen=True)
class InstanceSettings:
    id: str
    definition: str
    serves: tuple[str, ...]
    # The approved model it runs on: none, and it runs its release's own. It can only name
    # one config/models.yaml approves, and never sees more than that model may.
    model: str | None = None
    level: int | None = None  # the release's starting level, if the settings set none
    owner: str | None = None  # who runs it here, and their deputy: people in this directory
    deputy: str | None = None
    # The parts it works in, its scope, each with its level there, or None for `level`. Their
    # owners approve it. With none, it works on no part's records, and an instance approver
    # approves it.
    parts: dict[str, int | None] = field(default_factory=dict)
    # Its level for a type of action in a part, such as {"billing": {"change-due-date": 2}}: the
    # only way to level 2, which a5s's cap for the release can still hold at 1
    actions: dict[str, dict[str, int]] = field(default_factory=dict)
    # The instances it may ask a question, for the people it acts for (core/asking.py)
    asks: tuple[str, ...] = ()
    # The directory's teams it may hand a conversation over to, whose people answer the person
    # in the same chat until they hand it back (core/handover.py)
    hands_to: tuple[str, ...] = ()
    # The instance it answers beside, if it's a shadow: it answers what that one is asked,
    # sending and changing nothing, for graders to compare (core/shadows.py)
    shadows: str | None = None

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
class DataProtection:
    """What the data protection officer decides about people's data, in the signed settings:
    a version that changes any of it needs their approval (core/registry.py). Each starts
    private, as here, until they choose otherwise."""

    # How long a5s keeps what's said, after a conversation's last message, and what goes with
    # it: summaries, notes, reminders, what people owed, held changes and their decisions,
    # samples, questions agents asked each other, and tasks (core/retention.py)
    kept_for: str = "12 months"
    # The fewest people an instance serves before its own figures go out to the team's
    # dashboards: fewer, and its figures could say what one person did (core/metrics.py)
    fewest_people: int = 5
    # Whether the studio's pages name whom each run acted for, rather than how many
    studio_names: bool = False
    # Whether the auditors' page names whom agents acted for, and exports the ledger there
    audit_names: bool = False
    # Whether the status names deciders whose approvals are graded wrong far more often than
    # others': profiling people
    flag_rubber_stamps: bool = False
    # Whether those who author an agent may keep one of its runs as a test case, where every
    # one of them may see the run: what someone said to it, masked by code and checked by whoever
    # keeps it, in the agent's folder from then, which every author reads, and once released, the
    # agents' repository (core/run_cases.py)
    cases_from_runs: bool = False
    # Whether a shadow may answer what people ask the instance it shadows, beside it, sending
    # nothing: it reads what they say and what their records hold, and graders read what it
    # answered beside what was sent (core/shadows.py)
    shadow_runs: bool = False


@dataclass(frozen=True)
class Spending:
    """What each agent's model calls may cost a calendar month, in whole cents of the currency
    it names, which the studio's forms take from models.yaml: a budget a5s shows spending
    against, with a forecast to the month's end, and tells its owners of once the forecast
    passes it, never one that stops work, which the token budgets each release sets do
    (core/spending.py). One in a currency models.yaml doesn't price models in, a5s compares
    with nothing. Without a currency, it's in the one models.yaml prices models in. An agent's
    owner approves its budget. A part has none: a run's cost is its instance's and its
    agent's, whole, never shared out among parts, a figure few could check."""

    agents: dict[str, float] = field(default_factory=dict)
    currency: str | None = None  # as its ISO 4217 code, such as GBP


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
    # The scenario's limits for each type of action: how many one run may take, and how many
    # for each person acted for in 30 days, such as {"change-due-date": {"per_run": 5,
    # "per_person_30_days": 20}}. Past one, a change waits for a person, whatever the level.
    limits: dict[str, dict[str, int]] = field(default_factory=dict)
    # How accurate an agent's work in a part must be, as graded samples show, before a5s raises
    # its cap to level 2 there, such as {"billing": 0.98}. A part with none never earns it.
    thresholds: dict[str, float] = field(default_factory=dict)
    # Where a held change needs two of its part's deciders, by what its record holds: for each
    # part, the record's field with the amount, and the amount above which a second decider
    # approves too, such as {"payables": ("amount", 10000.0)}. Four eyes, set by its owners.
    two_deciders: dict[str, tuple[str, float]] = field(default_factory=dict)
    # Roles that come from the identity provider's groups: each group's id, as sign-ins show
    # it, and the roles its members hold, such as {"<group id>": ("part-owner:billing",)}.
    # A version's own map gives nothing towards its approval: the one in force before it does.
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    data_protection: DataProtection = field(default_factory=DataProtection)
    # What each agent's model calls may cost a month, such as {"agents": {"assistant": 300}}:
    # a run's cost is its instance's and its agent's, whole, so no part has a budget
    spending: Spending = field(default_factory=Spending)


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
# A model's alias, as config/models.yaml names it: lowercase words, hyphens and, where the
# provider dates one, dots and digits, such as qwen3.7-max
_MODEL = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z0-9][a-z0-9.-]{0,62}$")]
# reads only, asks first or acts on its own, by name or, as before, by number (levels.py)
_LEVEL = Annotated[StrictInt, BeforeValidator(levels.parse), Field(ge=0, le=2)]
_COUNT = Annotated[StrictInt, Field(ge=1, le=100_000)]
_THRESHOLD = Annotated[float, Field(strict=True, ge=0.5, le=0.999)]
# A month's budget, in the currency models.yaml prices models in: more than nothing, and at most
# ten million, a whole number or one with cents
_AMOUNT = Annotated[float, Field(gt=0, le=10_000_000, allow_inf_nan=False)]
_CURRENCY = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z]{3}$")]  # ISO 4217
# A group, by the id its sign-ins show it by: an Entra ID object id, or a group's name or path
_GROUP = Annotated[str, StringConstraints(strict=True, pattern=(
    r"^[A-Za-z0-9/_](?:[A-Za-z0-9._@:/ -]{0,254}[A-Za-z0-9._@:/-])?$"))]
_GROUP_ROLE = Annotated[str, StringConstraints(strict=True, pattern=(
    rf"^(?:{'|'.join(GROUP_ROLES)}|(?:{'|'.join(GROUP_PART_ROLES + GROUP_AGENT_ROLES)})"
    r":[a-z0-9][a-z0-9-]{0,62})$"))]


class _Part(BaseModel):
    """An instance's level in a part, and for each type of action there."""

    model_config = ConfigDict(extra="forbid", strict=True)

    level: _LEVEL | None = None
    actions: dict[_ID, _LEVEL] = Field(default_factory=dict)


class _Instance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    definition: _ID
    serves: list[_WHO]
    model: _MODEL | None = None  # the approved model it runs on: none, its release's own
    level: _LEVEL | None = None
    owner: _PERSON | None = None
    deputy: _PERSON | None = None
    parts: list[_ID] | dict[_ID, _LEVEL | _Part | None] = Field(default_factory=list)
    asks: list[_ID] = Field(default_factory=list)
    hands_to: list[_ID] = Field(default_factory=list)  # teams of the directory
    shadows: _ID | None = None  # the instance it answers beside, as a shadow


class _Limit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    per_run: _COUNT | None = None
    per_person_30_days: _COUNT | None = None


def _ten_years_at_most(given: str) -> str:
    n, unit = given.split()
    if int(n) > (3650 if unit.startswith("day") else 120):
        raise ValueError("a5s keeps things ten years at most: 3650 days, or 120 months")
    return given


# How long a5s keeps what's said: a number of days or months, from a day to ten years
_KEPT = Annotated[str, StringConstraints(strict=True, pattern=r"^[1-9][0-9]{0,3} (?:day|month)s?$"),
                  AfterValidator(_ten_years_at_most)]


class _DataProtection(BaseModel):
    """The data protection officer's choices: what a5s keeps, and whom it names."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kept_for: _KEPT = DataProtection.kept_for
    fewest_people: Annotated[StrictInt, Field(ge=3, le=1000)] = DataProtection.fewest_people
    studio_names: bool = DataProtection.studio_names
    audit_names: bool = DataProtection.audit_names
    flag_rubber_stamps: bool = DataProtection.flag_rubber_stamps
    cases_from_runs: bool = DataProtection.cases_from_runs
    shadow_runs: bool = DataProtection.shadow_runs


class _Spending(BaseModel):
    """What each agent's model calls may cost a month, in whole cents, so the words approvers
    read are the amount itself, and the currency they're in."""

    model_config = ConfigDict(extra="forbid", strict=True)

    agents: dict[_ID, _AMOUNT] = Field(default_factory=dict)
    currency: _CURRENCY | None = None

    @model_validator(mode="before")
    @classmethod
    def _no_parts(cls, found: Any) -> Any:
        if isinstance(found, dict) and "parts" in found:
            raise ValueError("a5s budgets each agent, not each part: a run's cost is its "
                             "instance's and its agent's, whole, so a budget goes in "
                             "spending.agents, which the agent's owner approves")
        return found

    @field_validator("agents")
    @classmethod
    def _cents(cls, found: dict[str, float]) -> dict[str, float]:
        for name, amount in found.items():
            if abs(amount * 100 - round(amount * 100)) > 1e-6:
                raise ValueError(f"{name}'s budget is in whole cents, such as 520.40, "
                                 f"not {amount!r}")
        return found


class _TwoDeciders(BaseModel):
    """A part's four eyes: the field of a record that holds its amount, and the amount above
    which a held change to it needs two of the part's deciders."""

    model_config = ConfigDict(extra="forbid", strict=True)

    field: _FIELD
    above: Annotated[float, Field(strict=False, gt=0)]


class _Version(BaseModel):
    """a5s's own settings format, checked strictly: names are plain words, levels are reads
    only, asks first or acts on its own, or their numbers, 0 to 2, and nothing else may be
    there."""

    model_config = ConfigDict(extra="forbid", strict=True)

    serial: Annotated[StrictInt, Field(ge=0)] = 0
    data_class: _ID = "internal"
    classified: dict[_FIELD, _ID] = Field(default_factory=dict)
    limits: dict[_ID, _Limit] = Field(default_factory=dict)
    thresholds: dict[_ID, _THRESHOLD] = Field(default_factory=dict)
    two_deciders: dict[_ID, _TwoDeciders] = Field(default_factory=dict)
    instances: dict[_ID, _Instance] = Field(default_factory=dict)
    groups: dict[_GROUP, list[_GROUP_ROLE]] = Field(default_factory=dict)
    data_protection: _DataProtection = Field(default_factory=_DataProtection)
    spending: _Spending = Field(default_factory=_Spending)


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
    for iid, i in version.instances.items():  # whom it asks: another instance in this version
        if wrong := [a for a in i.asks if a == iid or a not in version.instances]:
            raise SettingsError(f"instances.{iid}.asks: {', '.join(wrong)} isn't another instance "
                                "in these settings")
    parts = {p for i in version.instances.values() for p in _part_levels(i.parts)} | set(
        version.thresholds) | set(version.two_deciders)
    for group, roles in version.groups.items():  # a part's role, for a part these settings name
        if wrong := sorted({r for r in roles if r.partition(":")[0] in GROUP_PART_ROLES
                            and r.partition(":")[2] not in parts}):
            raise SettingsError(f"groups.{group}: {', '.join(wrong)} names a part no instance "
                                "here works in, nor has a threshold")
    return Settings(
        version=hashlib.sha256(raw).hexdigest()[:16],
        serial=version.serial,
        raw=raw,
        signatures=signatures,
        data_class=version.data_class,
        classified=dict(version.classified),
        limits={a: {k: v for k, v in limit.model_dump().items() if v is not None}
                for a, limit in version.limits.items()},
        thresholds=dict(version.thresholds),
        two_deciders={p: (t.field, float(t.above)) for p, t in version.two_deciders.items()},
        groups={g: tuple(sorted(set(roles))) for g, roles in version.groups.items() if roles},
        data_protection=DataProtection(**version.data_protection.model_dump()),
        spending=Spending(agents={a: float(v) for a, v in version.spending.agents.items()},
                          currency=version.spending.currency),
        instances=tuple(
            InstanceSettings(id=iid, definition=i.definition, serves=tuple(i.serves),
                             model=i.model, level=i.level, owner=i.owner, deputy=i.deputy,
                             parts=_part_levels(i.parts), actions=_action_levels(i.parts),
                             asks=tuple(i.asks), hands_to=tuple(dict.fromkeys(i.hands_to)),
                             shadows=i.shadows)
            for iid, i in version.instances.items()
        ),
    )


def _part_levels(parts: list[str] | dict[str, Any]) -> dict[str, int | None]:
    if not isinstance(parts, dict):
        return dict.fromkeys(parts)
    return {p: v.level if isinstance(v, _Part) else v for p, v in parts.items()}


def _action_levels(parts: list[str] | dict[str, Any]) -> dict[str, dict[str, int]]:
    if not isinstance(parts, dict):
        return {}
    return {p: dict(v.actions) for p, v in parts.items() if isinstance(v, _Part) and v.actions}


class Scenario(Protocol):
    """What a scenario gives a5s. One may also have record(key) -> Record | None, which reads
    one record, as watched() stands to it, or None if there's no such record; a5s reads that
    one record with it, such as for a case's brief, and without it reads every record with
    watched() to find the one. And sees_part(person, part) -> bool, whether someone may read
    what's in a part, for documents that name their readers by part, such as a docs
    repository's (connectors/libraries.py): without it, no part names a reader."""

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
        ...

    def part_of(self, record: str) -> str | None:
        """The part a record is in, by its key, or None if it's in none."""

    def sees(self, person: str, record: str) -> bool:
        """Whether the directory lets someone see a record, by its key. False for a record
        that doesn't exist."""
        ...

    def team(self, name: str) -> list[Person]:
        """The people in a team, such as the one that runs a5s."""
        ...

    def setup(self, conn: Any, tools_role: str) -> None:
        """Set up anything the scenario keeps in a5s's database, such as a fake system's
        tables, for its tools, which run as `tools_role`. Most scenarios keep nothing there."""

    def tools(self) -> dict[str, Tool]: ...

    def obligations(self) -> list[Obligation]:
        """What people owe now, from the records: one for each record and person.
        Something that's done, such as a closed case, owes nothing. If the records
        can't be read, raise: an empty list means nothing is owed."""
        ...

    def watched(self) -> list[Record]:
        """Each person's records as they stand now, closed ones included, so an agent that
        reports on them can say what changed. If the records can't be read, raise: an
        empty list means nobody has any."""
        ...

    def settings(self) -> Settings: ...

    def policy_pack(self) -> str | None: ...


def record_of(scenario: Scenario, key: str) -> Record | None:
    """One record, by its key, as it stands now: from the scenario's record(key) if it has
    one, else from every record it watches. None if there's no such record."""
    one = getattr(scenario, "record", None)
    if callable(one):
        return cast("Record | None", one(key))
    return next((r for r in scenario.watched() if r.key == key), None)
