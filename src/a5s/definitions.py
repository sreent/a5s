"""Agent definitions: a folder in git, and each release a tested version of it."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# a5s's own tools: for an agent whose release records reminders (core/reminders.py), for the
# preferences people may set through it, such as their digest's time (core/digests.py) and
# how they like to work (core/profiles.py), and for searching its conversation with the person
# it acts for (core/recall.py)
REMINDER_TOOLS = ("offer_reminder", "confirm_reminder", "list_reminders", "cancel_reminder",
                  "note_waiting")
PREFERENCE_TOOLS = {"digest-time": ("set_digest_time",),
                    "how-i-work": ("offer_note", "confirm_note", "forget_note")}
SEARCH_TOOLS = ("search_conversation",)
_DAY_NAMES = {f"{d}{rest}": d for d, rest in zip(DAYS, ("day", "sday", "nesday", "rsday", "day",
                                                       "urday", "day"), strict=True)}


def _time(value: Any) -> str:
    """A time of day, such as "09:00". YAML reads an unquoted 9:00 as a number, so times
    need quotes."""
    hours, _, minutes = value.partition(":") if isinstance(value, str) else ("", "", "")
    if not (hours.isdigit() and minutes.isdigit() and int(hours) < 24 and int(minutes) < 60
            and len(minutes) == 2):
        raise ValueError(f"{value} isn't a time in quotes, such as \"09:00\"")
    return f"{int(hours):02d}:{minutes}"


class Autonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(1, ge=0, le=1)  # level 2 only ever comes from the settings
    max: int = Field(1, ge=0, le=2)


class Schedule(BaseModel):
    """When the agent works on its own, and what it's asked to do each time.

    Times are in the time zone of the instance's owner. A schedule run acts for
    nobody, so it writes to nobody [TBC: whose digest a schedule's findings go in].
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9-]+$")
    at: list[str]  # such as ["09:00"]
    days: list[str] = list(DAYS)  # or "weekdays"
    task: str

    @field_validator("at", mode="before")
    @classmethod
    def _times(cls, value: Any) -> list[str]:
        return [_time(t) for t in (value if isinstance(value, list) else [value])]

    @field_validator("days", mode="before")
    @classmethod
    def _days(cls, value: Any) -> list[str]:
        if value == "weekdays":
            return list(DAYS[:5])
        days = [_DAY_NAMES.get(d, d) for d in
                (str(d).lower() for d in (value if isinstance(value, list) else [value]))]
        if unknown := [d for d in days if d not in DAYS]:
            raise ValueError(f"{', '.join(unknown)} isn't a day such as mon")
        return days


class Report(BaseModel):
    """What the agent tells each person it serves about their own records of a kind, once a
    day, in their digest: what changed since it last told them, and what fell due.

    Code works the facts out from the records, so the run only puts them into words, and
    a day with nothing new starts no model. The run acts for the person, so it writes to
    them and to nobody else.
    """

    model_config = ConfigDict(extra="forbid")

    source: str  # the kind of record, such as records


class Context(BaseModel):
    """What each run of the agent is given beside its instructions."""

    model_config = ConfigDict(extra="forbid")

    budget_tokens: int = Field(30000, ge=1000)  # for the conversation, split by part
    search: bool = False  # whether it may search its conversation with the person it acts for


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    release: str
    works_for: str
    does: str
    owner: str | None = None
    deputy: str | None = None
    scope: str = "none"
    model: str
    autonomy: Autonomy = Autonomy()
    tools: dict[str, list[str]] = {}
    triggers: list[dict[str, Any]] = []
    schedules: list[Schedule] = []
    obligations: list[str] = []  # the kinds of obligation it chases, such as records
    reports: list[Report] = []  # what it tells each person about their own records, daily
    reminders: bool = False
    preferences: list[str] = []
    channels: list[str] = ["teams"]
    context: Context = Context()
    budget: dict[str, Any] = {}

    # Filled in from the folder, not from agent.yaml.
    instructions: str = ""
    pins: dict[str, str] = {}
    digest: str = ""

    @property
    def tool_names(self) -> list[str]:
        return [name for names in self.tools.values() for name in names]

    @property
    def grants(self) -> list[str]:
        """The tools its instances may use: the scenario's it names, and a5s's own for
        reminders, if it records them, for the preferences people may set through it, and for
        searching its conversation with the person it acts for, if it may."""
        return [*self.tool_names, *(REMINDER_TOOLS if self.reminders else ()),
                *(tool for p in self.preferences for tool in PREFERENCE_TOOLS.get(p, ())),
                *(SEARCH_TOOLS if self.context.search else ())]

    @property
    def release_id(self) -> str:
        return f"{self.release}+{self.digest[:12]}"


def _folder_digest(folder: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        sha.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes() + b"\0")
    return sha.hexdigest()


def load(folder: Path) -> Definition:
    spec = yaml.safe_load((folder / "agent.yaml").read_text())
    lock = folder / "tools.lock"
    return Definition(
        **spec,
        instructions=(folder / "AGENTS.md").read_text(),
        pins=yaml.safe_load(lock.read_text()) or {} if lock.exists() else {},
        digest=_folder_digest(folder),
    )


def load_all(agents_dir: Path) -> dict[str, Definition]:
    found = [load(f) for f in sorted(agents_dir.iterdir()) if (f / "agent.yaml").exists()]
    return {d.id: d for d in found}


def pin(folder: Path, schema_hashes: dict[str, str]) -> Path:
    """Record the schema of every tool the definition uses, as part of its release."""
    definition = load(folder)
    missing = [t for t in definition.tool_names if t not in schema_hashes]
    if missing:
        raise ValueError(f"the scenario doesn't provide: {', '.join(missing)}")
    lock = folder / "tools.lock"
    pins = {t: schema_hashes[t] for t in definition.tool_names}
    lock.write_text(
        "# Written by `a5s pin`. A tool whose schema no longer matches is refused.\n"
        + yaml.safe_dump(pins, sort_keys=True)
    )
    return lock
