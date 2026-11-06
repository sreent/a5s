"""Agent definitions: a folder in git, and each release a tested version of it."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# a5s's own tools: for an agent whose release records reminders (core/reminders.py), for the
# preferences people may set through it, such as their digest's time (core/digests.py) and
# how they like to work (core/profiles.py), and for recalling its conversation with the person
# it acts for: searching it, and correcting its summaries at their word (core/recall.py)
REMINDER_TOOLS = ("offer_reminder", "confirm_reminder", "list_reminders", "cancel_reminder",
                  "note_waiting")
PREFERENCE_TOOLS = {"digest-time": ("set_digest_time",),
                    "how-i-work": ("offer_note", "confirm_note", "forget_note")}
RECALL_TOOLS = ("search_conversation", "correct_summary")
# and for asking a5s's reader about a document from outside that a run has read (core/extractor.py)
DOCUMENT_TOOLS = ("ask_about",)
# and for asking another agent, whom the settings name (core/asking.py)
ASKING_TOOLS = ("ask_agent",)
# and for noting what it learns from records, in a run that acts for nobody (core/notebook.py)
NOTEBOOK_TOOLS = ("note_learned",)
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

    budget_tokens: int = Field(24000, ge=1000)  # for the conversation, split by part
    # whether it may search its conversation with the person it acts for, and correct its
    # summaries at their word
    recall: bool = False
    # whether it may ask a5s's reader questions about documents from outside its run has read
    documents: bool = False
    # whether it may ask other agents questions, whom the settings name
    agents: bool = False
    # whether it notes what it learns from records, on its schedules, for its later runs
    notebook: bool = False


# Each model call in a run carries the whole context and, beside it, the instructions, the
# tools, the run's records and its tool results, about BESIDE tokens. A release's budgets must
# fit CALLS_A_RUN such calls in a run, and ANSWERS_A_DAY answers of two calls each in the part
# of a person's day that isn't KEPT for chases and reminders, or the release is refused.
BESIDE = 6000
CALLS_A_RUN = 6
ANSWERS_A_DAY = 12
KEPT = 0.2  # of each person's day, for chases and reminders


class Budget(BaseModel):
    """How much model work an instance may do, in tokens as the providers count them: in one
    run, and for each person it acts for, each day (core/budgets.py)."""

    model_config = ConfigDict(extra="forbid")

    per_run: int = Field(200_000, ge=1000)
    per_person_per_day: int = Field(1_000_000, ge=1000)


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
    budget: Budget = Budget()

    # Filled in from the folder, not from agent.yaml.
    instructions: str = ""
    pins: dict[str, str] = {}
    digest: str = ""
    # Agent Skills, one folder each under skills/, as files by their path in a run's read-only
    # files, such as /skills/refunds/SKILL.md; the folder's digest and the release pin them
    skills: dict[str, str] = {}

    @property
    def tool_names(self) -> list[str]:
        return [name for names in self.tools.values() for name in names]

    @model_validator(mode="after")
    def _budgets_fit_the_context(self) -> Definition:
        call = self.context.budget_tokens + BESIDE
        if self.budget.per_run < CALLS_A_RUN * call:
            raise ValueError(f"budget.per_run must fit {CALLS_A_RUN} model calls of about "
                             f"{call:,} tokens each, with a context of "
                             f"{self.context.budget_tokens:,}: at least {CALLS_A_RUN * call:,}")
        if self.budget.per_person_per_day * (1 - KEPT) < ANSWERS_A_DAY * 2 * call:
            least = round(ANSWERS_A_DAY * 2 * call / (1 - KEPT))
            raise ValueError(f"budget.per_person_per_day must fit {ANSWERS_A_DAY} answers of two "
                             f"model calls, beside what's kept for chases and reminders: at "
                             f"least {least:,}")
        return self

    @property
    def grants(self) -> list[str]:
        """The tools its instances may use: the scenario's it names, and a5s's own for
        reminders, if it records them, for the preferences people may set through it, and for
        recalling its conversation with the person it acts for, if it may."""
        return [*self.tool_names, *(REMINDER_TOOLS if self.reminders else ()),
                *(tool for p in self.preferences for tool in PREFERENCE_TOOLS.get(p, ())),
                *(RECALL_TOOLS if self.context.recall else ()),
                *(DOCUMENT_TOOLS if self.context.documents else ()),
                *(ASKING_TOOLS if self.context.agents else ()),
                *(NOTEBOOK_TOOLS if self.context.notebook else ())]

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
        skills=skills_of(folder / "skills"),
    )


# What a skill's folder may hold: its instructions, and text they refer to. A run reads them,
# and runs nothing, so a skill that brings a script is refused, not offered with a script no run
# can run.
SKILL_FILES = (".md", ".txt", ".csv", ".json", ".yaml", ".yml")
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)  # as Deep Agents reads it


def skills_of(folder: Path) -> dict[str, str]:
    """A definition's Agent Skills: each a folder with a SKILL.md, whose YAML front matter
    names it, as its folder is named, and says what it's for, which is all a run sees of it
    until it reads it. Each file in the folder, by its path in a run's files."""
    found: dict[str, str] = {}
    for skill in sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []:
        told = skill / "SKILL.md"
        if not told.is_file():
            raise ValueError(f"the skill {skill.name} has no SKILL.md")
        head = _FRONT.match(told.read_text())
        try:
            meta = yaml.safe_load(head.group(1)) if head else None
        except yaml.YAMLError:
            meta = None
        about = str(meta.get("description") or "").strip() if isinstance(meta, dict) else ""
        if not isinstance(meta, dict) or meta.get("name") != skill.name or not about:
            raise ValueError(f"the skill {skill.name}'s SKILL.md must begin with front matter, "
                             f"between lines of ---, naming it {skill.name} and saying what "
                             "it's for")
        if len(about) > 1024:  # past which Deep Agents cuts what a run is told of it
            raise ValueError(f"say what the skill {skill.name} is for in 1,024 characters or "
                             "fewer")
        for path in sorted(p for p in skill.rglob("*") if p.is_file()):
            if path.suffix.lower() not in SKILL_FILES:
                raise ValueError(f"the skill {skill.name} brings {path.name}, which no run can "
                                 "run: a skill holds instructions, and text they refer to, as "
                                 + ", ".join(SKILL_FILES))
            try:
                found[f"/skills/{path.relative_to(folder).as_posix()}"] = path.read_text()
            except UnicodeDecodeError:
                raise ValueError(f"the skill {skill.name}'s {path.name} isn't text") from None
    return found


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
