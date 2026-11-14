"""What the studio's API answers (docs/studio.md), as types. Each of its routes is checked
against its model as it answers, so the API's own description says exactly what it answers, and
the studio's TypeScript types are made from that description (studio/src/api.gen.ts), so the two
can't drift apart.

Each model refuses a field it doesn't name: a field added to an answer without its model fails
in the tests, rather than reaching the studio unknown, or anyone else unseen. A route sends only
the fields it set, so a field a layer of an agent leaves out stays out, rather than going as
null (`response_model_exclude_unset`, as `answers` gives each route), and its description says so:
a field that may be left out, but is never null, is optional there (`SkipJsonSchema[None]`).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.json_schema import SkipJsonSchema


class Shape(BaseModel):
    """An answer's shape, or a part of one: nothing it doesn't name."""

    model_config = ConfigDict(extra="forbid")


def answers(model: type[BaseModel]) -> dict[str, Any]:
    """What a route's decorator takes to answer with `model`: checked against it, with only
    the fields the route set."""
    return {"response_model": model, "response_model_exclude_unset": True}


# The studio's home, and someone's own roles (core/home.py)


class Waiting(Shape):
    """Something that waits for someone: what it is, why it's theirs, and where they do it, a
    page of a5s's, or the command line."""

    kind: str
    what: str
    why: list[str]
    go: str | None
    how: str | SkipJsonSchema[None] = None  # the command, for what's done at the command line


class DraftLine(Shape):
    """One of someone's drafts, or a co-author's, without its files (core/drafts.py)."""

    id: str
    agent: str
    based_on: str | None
    created_at: datetime
    updated_at: datetime
    published: str | None  # the pull request it was last published as, if it has been
    author: str | SkipJsonSchema[None] = None  # a co-author's, whose agent they may author too


class Home(Shape):
    you: str
    waiting: list[Waiting]
    drafts: list[DraftLine]
    catalogue: bool
    authoring: bool  # whether they may author anything at all


class Role(Shape):
    """A role someone holds, what gave it them, and what it lets them do."""

    role: str
    by: list[str]
    may: str


class You(Shape):
    you: str
    id: str
    roles: list[Role]
    groups: list[str]


# Each agent as someone sees it, layer by layer (core/studio.py)


class Tool(Shape):
    """One of an agent's tools, with what it reads, writes or changes."""

    name: str
    group: str
    description: str | None
    reads: bool | SkipJsonSchema[None] = None
    writes: bool | SkipJsonSchema[None] = None
    destructive: bool | SkipJsonSchema[None] = None
    sends_outside: bool | SkipJsonSchema[None] = None
    changes: str | None  # the type of change it makes, which people decide at level 1
    handles: list[str]
    outside: list[str]
    pinned: str | None
    missing: bool


class Instance(Shape):
    """One of an agent's instances, which someone may watch."""

    id: str
    agent: str
    status: str
    release: str
    current: bool
    level: int
    parts: dict[str, Any]
    actions: dict[str, Any]
    model: str | None
    serves: list[str]
    people: int
    owner: str | None
    deputy: str | None
    asks: list[str]


class Autonomy(Shape):
    """The levels an agent's release lets its instances act at: where they start, and the most."""

    start: int
    max: int


class Schedule(Shape):
    """When an agent works on its own, in its instance owner's time zone, and what it's asked."""

    name: str
    at: list[str]
    days: list[str]
    task: str


class Context(Shape):
    """What an agent's runs are given beyond the conversation."""

    budget_tokens: int
    recall: bool
    documents: bool
    agents: bool
    notebook: bool


class Budget(Shape):
    """The tokens an instance may use, in one run, and for one person in a day."""

    per_run: int
    per_person_per_day: int


class Ask(Shape):
    """Someone's own ask for an agent, as they see it: never who declined it (core/asks.py)."""

    id: str
    agent: str
    asked_at: str
    ended_at: str | None
    outcome: str | None


class Asked(Shape):
    """An open ask that waits on someone, with whose it is, and why it's theirs."""

    id: str
    agent: str
    asker: str
    person: str
    asked_at: str
    why: list[str]


class Agent(Shape):
    """An agent as someone sees it: each layer of it they see, with why. What a layer they
    don't see would add is left out, not null."""

    layers: dict[str, list[str]]
    listed: bool  # whether its owner lists it for everyone
    why: list[str]
    instances: list[Instance]  # those they may watch, if they see how it's doing
    # That it exists
    id: str
    release: str
    works_for: str
    does: str
    owners: list[str]
    # What it may do
    tools: list[Tool] | SkipJsonSchema[None] = None
    a5s_tools: list[str] | SkipJsonSchema[None] = None
    model: str | SkipJsonSchema[None] = None
    autonomy: Autonomy | SkipJsonSchema[None] = None
    triggers: list[dict[str, Any]] | SkipJsonSchema[None] = None
    schedules: list[Schedule] | SkipJsonSchema[None] = None
    reports: list[str] | SkipJsonSchema[None] = None
    obligations: list[str] | SkipJsonSchema[None] = None
    reminders: bool | SkipJsonSchema[None] = None
    preferences: list[str] | SkipJsonSchema[None] = None
    channels: list[str] | SkipJsonSchema[None] = None
    context: Context | SkipJsonSchema[None] = None
    budget: Budget | SkipJsonSchema[None] = None
    # How it's built
    skills: list[str] | SkipJsonSchema[None] = None
    instructions: str | SkipJsonSchema[None] = None
    # Asking for it: their own open ask, and the asks for it that wait on them
    ask: Ask | None = None  # null if they haven't asked; absent if it serves them
    asks: list[Asked] | SkipJsonSchema[None] = None  # only if any wait on them


class Authoring(Shape):
    new: bool  # whether they may start an agent
    agents: list[str]  # which they may change


class Catalogue(Shape):
    you: str
    agents: list[Agent]
    authoring: Authoring


class Requested(Shape):
    """A version of the settings asked for, which the core proposes to everyone it needs."""

    request: int
    serial: int


# How instances are doing, over a period (core/studio.py's figures, core/measures.py)


class Obligations(Shape):
    due: int
    on_time: int
    late: int
    unknown: int
    open: int
    chased: int
    escalated: int
    on_time_share: float | None
    late_hours_p50: float | None
    late_hours_p90: float | None


class Reminders(Shape):
    due: int
    on_time: int
    missed: int
    on_time_share: float | None


class Returning(Shape):
    agent: str
    wrote_before: int
    came_back: int
    share: float | None
    served: int
    came_back_served: int
    served_share: float | None


class ReturningTeam(Shape):
    served: int
    came_back: int
    share: float | None


class GroupChats(Shape):
    agent: str
    messages: int
    chats: int
    people: int


class ModelRuns(Shape):
    instance: str
    model: str | None
    runs: int
    tokens_per_run: int
    tokens_p90: int
    cached_share: float | None
    cost_per_run: float | None


class Held(Shape):
    held: int
    approved: int
    rejected: int
    lapsed: int
    waiting: int
    approved_share: float | None
    decided_hours_p50: float | None
    decided_hours_p90: float | None


class Samples(Shape):
    graded: int
    right: int
    wrong: int
    critical: int
    lapsed: int
    right_share: float | None


class Questions(Shape):
    instance: str
    asked: int
    answered: int
    unanswered: int
    answered_seconds_p90: float | None


class Notebook(Shape):
    instance: str
    notes: int
    kept: int
    refused: int
    let_go: int
    given: int
    runs_given: int


class Ended(Shape):
    kind: str | None
    outcome: str
    runs: int


class Day(Shape):
    """One day's runs, by how each ended, in the viewer's own time zone."""

    day: str
    runs: int
    ended: dict[str, int]


class Denied(Shape):
    kind: str
    action: str
    reasons: list[str]
    times: int


class Reported(Shape):
    source: str
    outcome: str
    reports: int


class Figures(Shape):
    """How some instances are doing over the last `days` days."""

    days: int
    obligations: Obligations
    reminders: Reminders
    returning: list[Returning]
    returning_team: ReturningTeam
    groups: list[GroupChats]
    runs: list[ModelRuns]
    held: Held
    samples: Samples
    questions: list[Questions]
    notebook: list[Notebook]
    ended: list[Ended]
    daily: list[Day]
    zone: str
    denied: list[Denied]
    denied_partial: bool
    reports: list[Reported]
    instances: list[str]


# What runs did (core/studio.py)


class ActedFor(Shape):
    id: str
    name: str | None


class RunLine(Shape):
    run: str
    instance: str
    trigger: str | None
    acts_for: list[ActedFor]  # named only once the data protection officer agrees
    people: int
    opened_at: str
    closed_at: str | None
    outcome: str
    tokens: int
    model: str | None
    read_outside: bool


class RunsPage(Shape):
    instance: str
    runs: list[RunLine]
    hidden: int  # the runs on the page whose every record the viewer may not see
    before: str | None  # where the next page starts, if there's one


class Call(Shape):
    """One tool call a run made, with the policy's decision, and how it ended."""

    seq: int
    at: str
    tool: str
    decision: str
    reasons: list[str]
    outcome: str | None


class Run(RunLine):
    agent: str | None
    started_by: dict[str, Any]
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    records: list[str]
    calls: list[Call]
