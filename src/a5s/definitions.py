"""Agent definitions: a folder in git, and each release a tested version of it."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from a5s import levels

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
# and for handing a conversation over to the people of a team the settings name (core/handover.py)
HANDOVER_TOOLS = ("hand_over",)
# and for the long tasks people ask it for, over more than one run (core/tasking.py): offered,
# confirmed, listed, cancelled and resumed in a person's own chat, and kept, in each run of
# a task
TASK_TOOLS = ("offer_task", "confirm_task", "list_tasks", "cancel_task", "resume_task")
SLICE_TOOLS = ("checkpoint_task", "finish_task", "split_task")
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
    """Where an agent's instances start, and the most they may do: reads only, asks first or
    acts on its own, by name or, as before, by number (levels.py)."""

    model_config = ConfigDict(extra="forbid")

    start: Annotated[int, BeforeValidator(levels.parse)] = levels.ASKS_FIRST
    max: Annotated[int, BeforeValidator(levels.parse), Field(ge=0, le=2)] = levels.ASKS_FIRST

    @field_validator("start")
    @classmethod
    def _starts(cls, value: int) -> int:
        if not levels.READS_ONLY <= value <= levels.ASKS_FIRST:
            raise ValueError("an agent starts reading only or asking first: acting on its own "
                             "only ever comes from the settings")
        return value


class Schedule(BaseModel):
    """When the agent works on its own, and what it's asked to do each time.

    Times are in the time zone of the instance's owner. A schedule run acts for
    nobody, so it writes to nobody, and whose digest its findings might go in is still an open question.
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


class Event(BaseModel):
    """What the agent does when another system says something happened, such as a ticket
    opened (core/events.py): the kind of event, the system that sends it, as the deployment
    names it, and what the agent's asked to do each time.

    An event names its records, and the person it's about, if any: nothing else, so nothing a
    system was told can reach a run as words. The run reads the records itself, through its
    tools, as any run does. It acts for the person the event names, where the directory knows
    them and the instance serves them, and writes to them; else for nobody, as a schedule run
    does, and works through its tools alone.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")  # such as ticket-opened
    source: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,30}$")  # such as itsm
    task: str = Field(min_length=1, max_length=2000)


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

    budget_tokens: int = Field(default=24000, ge=1000)  # for the conversation, split by part
    # whether it may search its conversation with the person it acts for, and correct its
    # summaries at their word
    recall: bool = False
    # whether it may ask a5s's reader questions about documents from outside its run has read
    documents: bool = False
    # whether it may ask other agents questions, whom the settings name
    agents: bool = False
    # whether it notes what it learns from records, on its schedules, for its later runs
    notebook: bool = False
    # whether it may hand a conversation over to the people of a team its settings name, such
    # as the service desk, who answer the person in the same chat until they hand it back
    handover: bool = False


class Tasks(BaseModel):
    """Long tasks the agent takes on for someone, over more than one run, once they say yes
    (docs/phase-4.md): the most one may spend, and how long it has, from when it's offered."""

    model_config = ConfigDict(extra="forbid")

    budget_tokens: int = Field(default=400_000, ge=10_000)
    days: int = Field(default=3, ge=1, le=30)


# Each model call in a run carries the whole context and, beside it, the instructions, the
# tools, the run's records and its tool results, about BESIDE tokens. A release's budgets must
# fit CALLS_A_RUN such calls in a run, and ANSWERS_A_DAY answers of two calls each in the part
# of a person's day that isn't KEPT for chases and reminders, or the release is refused.
BESIDE = 6000
CALLS_A_RUN = 6
ANSWERS_A_DAY = 12
KEPT = 0.2  # of each person's day, for chases and reminders
ASKED = 0.2  # and beside it, for what they ask themselves, which their tasks never spend


# Names no agent may have: in a conversation, the person's own words are by "you", and a5s's by
# "a5s" (core/inbox.py)
RESERVED = frozenset({"you", "a5s"})


class Budget(BaseModel):
    """How much model work an instance may do, in tokens as the providers count them: in one
    run, and for each person it acts for, each day (core/budgets.py)."""

    model_config = ConfigDict(extra="forbid")

    per_run: int = Field(default=200_000, ge=1000)
    per_person_per_day: int = Field(default=1_000_000, ge=1000)


class Evaluation(BaseModel):
    """The judge of an agent's work: an approved model that grades each sample of it beside
    people, never instead of them, and what a right change is for this agent (core/judging.py)."""

    model_config = ConfigDict(extra="forbid")

    judge: str  # an approved model's alias, best another than the agent's own
    rubric: str = Field(default="", max_length=2000)  # what's right, in its owners' words


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
    # Other approved models a run falls back to when its model isn't answering: tried in
    # order, each after the one before it failed, so one provider's outage costs a retry,
    # not the work. Approved with the release, like the model itself.
    fallbacks: list[str] = []
    autonomy: Autonomy = Autonomy()
    tools: dict[str, list[str]] = {}
    triggers: list[dict[str, Any]] = []
    schedules: list[Schedule] = []
    events: list[Event] = []  # what it does when another system says something happened
    obligations: list[str] = []  # the kinds of obligation it chases, such as records
    reports: list[Report] = []  # what it tells each person about their own records, daily
    reminders: bool = False
    preferences: list[str] = []
    channels: list[str] = ["teams"]
    context: Context = Context()
    budget: Budget = Budget()
    tasks: Tasks | None = None  # if it takes on long tasks for people
    evaluation: Evaluation | None = None  # a judge of its work, beside people's grades
    # Whether the studio's catalogue shows everyone signed in that it exists: its name, what it
    # does, its owner, and how to ask for it. Unlisted, only those with a role on it, and the
    # people it serves, know of it, as a name such as redundancy planning says too much alone
    listed: bool = False

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

    @field_validator("id")
    @classmethod
    def _not_reserved(cls, given: str) -> str:
        if given in RESERVED:
            raise ValueError(f"an agent can't be called {given}: in a conversation, that's who "
                             "the other words are by")
        return given

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
                *(NOTEBOOK_TOOLS if self.context.notebook else ()),
                *(HANDOVER_TOOLS if self.context.handover else ()),
                *(TASK_TOOLS + SLICE_TOOLS if self.tasks else ())]

    @property
    def release_id(self) -> str:
        return f"{self.release}+{self.digest[:12]}"


def _folder_digest(folder: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        sha.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes() + b"\0")
    return sha.hexdigest()


class _Once(yaml.SafeLoader):
    """YAML that names each key of a mapping once. A reviewer reads the first of two, and YAML
    takes the last, so an agent.yaml naming its model twice would run on the one nobody read."""


def _named_once(loader: yaml.SafeLoader, node: yaml.MappingNode) -> Any:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"it names {key} twice", key_node.start_mark)
            seen.add(key)
        except TypeError:  # a key that can't be one, which the mapping refuses itself
            pass
    return loader.construct_mapping(node, deep=True)


_Once.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _named_once)


def spec_of(text: str) -> Any:
    """An agent.yaml, as a5s reads it: each key once."""
    return yaml.load(text, Loader=_Once)  # a SafeLoader, with each key once


def load(folder: Path) -> Definition:
    spec = spec_of((folder / "agent.yaml").read_text(encoding="utf-8"))
    lock = folder / "tools.lock"
    return Definition(
        **spec,
        instructions=(folder / "AGENTS.md").read_text(encoding="utf-8"),
        pins=yaml.safe_load(lock.read_text(encoding="utf-8")) or {} if lock.exists() else {},
        digest=_folder_digest(folder),
        skills=skills_of(folder / "skills"),
    )


# What a skill's folder may hold: its instructions, and text they refer to. A run reads them,
# and runs nothing, so a skill that brings a script is refused, not offered with a script no run
# can run.
SKILL_FILES = (".md", ".txt", ".csv", ".json", ".yaml", ".yml")
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)  # as Deep Agents reads it
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")  # as Agent Skills names one: such as sign-in-help


def skills_of(folder: Path) -> dict[str, str]:
    """A definition's Agent Skills: each a folder with a SKILL.md, whose YAML front matter
    names it, as its folder is named, and says what it's for, which is all a run sees of it
    until it reads it. Each file in the folder, by its path in a run's files."""
    found: dict[str, str] = {}
    for skill in sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []:
        if not SKILL_NAME.fullmatch(skill.name) or len(skill.name) > 64:
            raise ValueError(f"name the skill {skill.name[:64]} as Agent Skills names one: in lower-case "
                             "letters and digits, with single hyphens between, 64 characters at most")
        told = skill / "SKILL.md"
        if not told.is_file():
            raise ValueError(f"the skill {skill.name} has no SKILL.md")
        head = _FRONT.match(told.read_text(encoding="utf-8"))
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
                found[f"/skills/{path.relative_to(folder).as_posix()}"] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ValueError(f"the skill {skill.name}'s {path.name} isn't text") from None
    return found


def load_all(agents_dir: Path) -> dict[str, Definition]:
    """Every agent in a folder of agents, each by its folder's name, which is its id: one that
    names itself otherwise would load as another agent, in its place, so it's refused."""
    found = {}
    for folder in sorted(agents_dir.iterdir()):
        if (folder / "agent.yaml").exists():
            definition = load(folder)
            if definition.id != folder.name:
                raise ValueError(f"the agent in {folder.name} names itself {definition.id}: an "
                                 "agent's id is its folder's name")
            found[definition.id] = definition
    return found


def pin(folder: Path, schema_hashes: dict[str, str]) -> Path:
    """Record the schema of every tool the definition uses, as part of its release."""
    definition = load(folder)
    missing = [t for t in definition.tool_names if t not in schema_hashes]
    if missing:
        raise ValueError(f"the scenario doesn't provide: {', '.join(missing)}")
    lock = folder / "tools.lock"
    lock.write_text(lock_text({t: schema_hashes[t] for t in definition.tool_names}), encoding="utf-8")
    return lock


def lock_text(pins: dict[str, str]) -> str:
    """A tools.lock, as `a5s pin` writes it: each tool's schema, by its hash."""
    return ("# Written by `a5s pin`. A tool whose schema no longer matches is refused.\n"
            + yaml.safe_dump(pins, sort_keys=True))
