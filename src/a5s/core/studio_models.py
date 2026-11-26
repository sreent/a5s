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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
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
    since: datetime | SkipJsonSchema[None] = None  # when the oldest of them began to wait


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
    authoring: bool  # whether they may start a new agent: an author of one may not (round 13, B4)
    changes: list[str]  # the agents they may draft a change to, as an owner or an author


# The sidebar every page of a5s has (core/shell_api.py)


class Place(Shape):
    """One of a5s's pages, as every sidebar and the studio's palette show it: its key, its
    name, its icon, the heading it's under, and its address."""

    page: str
    name: str
    icon: str
    group: str
    at: str


class Shell(Shape):
    """Who signed in, the roles they hold, in words, the team that runs a5s first, and the pages
    they may use, in the sidebar's order."""

    you: str
    roles: list[str]  # none for someone who holds none, who works with the agents that serve them
    pages: list[Place]


class Environment(Shape):
    """Which deployment this is, as the band across the top of every page says it: its kind,
    production, staging, test or development, its name, what that means here, and whether
    anyone named it, as one nobody named is taken as production (core/environment.py)."""

    kind: str
    name: str
    about: str
    named: bool


class Acting(Shape):
    """Whose power a page that changes things uses, for the line across its top: the roles its
    acts count as, in words, and what that lets someone do there (core/acting.py). A page that
    only shows, or whose acts are someone's own, has none."""

    role: str
    lets: str


class Role(Shape):
    """A role someone holds, what gave it them, and what it lets them do."""

    role: str
    name: str  # in words, such as "Owner of billing" for part-owner:billing
    by: list[str]
    may: str


class You(Shape):
    you: str
    id: str
    roles: list[Role]
    groups: list[str]


# Conversations handed over to people (core/handover.py)


class HandoverLine(Shape):
    """A conversation handed to one of someone's teams: whose, with which agent, its brief, who
    of the team has taken it, and how many of the person's messages wait for an answer."""

    id: int
    person: str
    agent: str
    team: str
    brief: str
    started_at: str
    taken_by: str | SkipJsonSchema[None] = None
    mine: bool  # whether whoever's looking took it
    unanswered: int


class Handovers(Shape):
    handovers: list[HandoverLine]


class HandoverSaid(Shape):
    at: str
    text: str


class HandoverSince(Shape):
    at: str
    text: str
    answered: bool


class HandoverAnswer(Shape):
    by: str
    text: str
    at: str
    sent: bool  # whether the core has put it in their chat yet


class Handover(HandoverLine):
    said: list[HandoverSaid]  # what they said before it was handed over, their own words
    since: list[HandoverSince]  # what they've written since
    answers: list[HandoverAnswer]
    ended: bool
    acting: Acting | SkipJsonSchema[None] = None  # while it holds an act a role gives them


class HandoverDone(Shape):
    done: bool


# What new versions answered beside those at work, for graders (core/shadows.py)

class ShadowPair(Shape):
    """What someone asked an instance, what it answered them, and what its shadow, a new
    version, answered beside it, which went nowhere: for a grader, never whose it was."""

    id: int
    agent: str  # the agent they spoke to
    shadow: str  # the new version's agent
    asked: str
    sent: str
    answer: str
    at: str


class ShadowCounts(Shape):
    better: int
    same: int
    worse: int
    wrong: int


class ShadowFigures(Shape):
    """How a shadow did: how many it answered, and how graders, and its judge, apart, graded
    its answers."""

    instance: str
    shadows: str  # the instance it answers beside
    agent: str
    status: str  # shadow, or suspended
    answered: int
    graded: ShadowCounts
    judged: ShadowCounts


class Shadows(Shape):
    pairs: list[ShadowPair]
    shadows: list[ShadowFigures]
    acting: Acting | SkipJsonSchema[None] = None  # while it holds an act a role gives them


class ShadowGraded(Shape):
    graded: bool


# A change an agent made, which its tool says how to undo (core/undoing.py)


class ChangeMade(Shape):
    """A change a5s made for someone, as its page shows whoever it was for, and whoever may undo
    it: what it did, until when it can be undone, and how it stands."""

    id: int
    agent: str
    instance: str
    record: str
    said: str
    made_at: str
    until: str
    whom: list[str]  # whom it was for
    may: bool  # whether whoever's looking may undo it now
    why_not: str | SkipJsonSchema[None] = None
    state: str  # kept, asked, undoing, undone, refused or failed
    by: str | SkipJsonSchema[None] = None  # who asked to undo it, or did
    outcome: str | SkipJsonSchema[None] = None
    acting: Acting | SkipJsonSchema[None] = None  # as a decider of its record's part, not whoever it was for


class UndoAsked(Shape):
    change: int
    at: str


# The accounts someone connects, so agents act as them there (core/delegation.py)


class Connection(Shape):
    """A system someone may connect their own account in, so agents act there as them, with
    their permissions: whether they have, since when, and when a5s last did."""

    system: str
    title: str
    connected: bool
    connecting: bool  # they came back with its code, which the core is exchanging
    scopes: list[str]  # what a5s may do as them there, as the system said, or asks for
    connected_at: str | SkipJsonSchema[None] = None
    used_at: str | SkipJsonSchema[None] = None
    reads: list[str]  # the libraries agents read there as them, by their titles


class Connections(Shape):
    connections: list[Connection]


class ConnectionStarted(Shape):
    go: str  # the system's own page, where they say a5s may act for them


class ConnectionBack(Shape):
    system: str
    title: str
    connecting: bool  # false where they said no there


class Disconnected(Shape):
    forgotten: bool


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
    marks: bool  # what it returns holds a few words from outside as they are: its run is marked
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
    people: int
    owner: str | None
    deputy: str | None


class StatusAsked(Shape):
    """Suspending or resuming an instance, asked for on its page, which a5s carries out within
    a minute, once it has checked the sign-in that asked for it again (core/suspension.py)."""

    action: str  # suspend or resume
    by: str  # who asked, by name
    at: datetime


class Standing(Shape):
    """How an instance stands, for someone who may watch it: what of it waits, each where it's
    done; who suspended it, if it's suspended; what they may do to it from its page, suspend it
    or resume it, if either; and what was asked for there that a5s hasn't carried out yet."""

    waiting: list[Waiting]
    suspended_by: str | None
    may: str | None  # suspend or resume, which they may do now, signed in afresh
    asked: StatusAsked | None
    acting: Acting | SkipJsonSchema[None] = None  # while it holds an act a role gives them


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


class EventTaken(Shape):
    """What another system may tell an agent happened, and what it's asked to do each time."""

    type: str
    source: str
    task: str


class Context(Shape):
    """What an agent's runs are given beyond the conversation."""

    budget_tokens: int
    recall: bool
    documents: bool
    agents: bool
    notebook: bool
    handover: bool  # whether it may hand a conversation over to people (core/handover.py)


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
    events: list[EventTaken] | SkipJsonSchema[None] = None
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


class MapNode(Shape):
    """A thing on the map of what depends on what (core/dependencies.py): its kind, part,
    instance, agent, tool, system, model or team; its name; what it is, in a few words; its page in
    the studio, if it has one; and, for a tool, what it does: reads, writes, sends outside or
    changes records."""

    key: str
    kind: str
    name: str
    about: str
    at: str | None
    tone: str | None


class MapEdge(Shape):
    """That one thing depends on another, and how, in words, such as "may call it"."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    says: str


class DependsOn(Shape):
    """The map, as someone may see it."""

    nodes: list[MapNode]
    edges: list[MapEdge]


# What agents' model calls cost each month, against their budgets (core/spending.py)


class Spend(Shape):
    """A month of an agent's or instance's model calls: what they cost so far at their
    models' prices, its budget, if the settings set one, and while the month lasts, the pace of
    the last week and the forecast to its end; its runs, those whose prices aren't known, the
    messages they answered, and what each message cost, all in."""

    key: str
    spent: float
    budget: float | None
    pace: float | None
    forecast: float | None
    runs: int
    unpriced: int
    answered: int
    tokens: int
    per_answer: float | None
    agent: str | SkipJsonSchema[None] = None  # an instance's agent
    parts: list[str] | SkipJsonSchema[None] = None  # and the parts it works in


class Spending(Shape):
    """A calendar month's spending, in UTC, as someone may see it: its agents and instances,
    in the currency models.yaml prices models in, if it names one."""

    month: str
    current: bool
    currency: str | None
    # The currency the signed budgets are in, if they name one, and whether it's the one
    # models.yaml prices models in, so a5s compares what's spent with them
    budget_currency: str | None = None
    compared: bool = True
    starts: str
    ends: str
    days: int
    day: int
    agents: list[Spend]
    instances: list[Spend]


class SaidWrong(Shape):
    """An agent's answer someone said was wrong (core/feedback.py): when, the instance and run
    behind it, the chat it was in, the answer, why, in their words, if they said, and its grade,
    if an owner has given one; who said it only once the officer agrees to names."""

    id: int
    at: str
    instance: str | None
    run: str
    channel: str
    answer: str
    said: str | None
    grade: Literal["right", "wrong", "critical"] | None
    graded_at: str | None
    graded_by: str | None
    by: str | None


class AnswersSaidWrong(Shape):
    """An agent's answers people said were wrong, as an owner of it may check them: newest
    first, how many others there are, how many wait, and how many have each grade."""

    agent: str
    answers: list[SaidWrong]
    hidden: int
    waiting: int
    graded: dict[str, int]


class AnswerGraded(Shape):
    id: int
    grade: Literal["right", "wrong", "critical"]


class RunCaseOffered(Shape):
    """A run as a test case, for its author to check and keep (core/run_cases.py): what was
    said to the agent and what it answered, masked by code; how many of each kind code masked,
    such as names; the tools it used, which a5s let it, or held for someone to decide; and
    whether the run read content from outside, which the case can't keep."""

    run: str
    agent: str
    say: str
    answer: str
    masked: dict[str, int]
    uses: list[str]
    read_outside: bool = False


class RunCaseStep(Shape):
    say: str
    uses: list[str] | SkipJsonSchema[None] = None
    judged: str | SkipJsonSchema[None] = None


class RunCase(Shape):
    name: str
    # whom the case speaks as, a made-up person: "as" in the file
    speaker: str
    steps: list[RunCaseStep]


class RunCaseKept(Shape):
    """A run kept as a test case: the draft it went in, its file, and the case as kept."""

    draft: str
    file: str
    case: RunCase


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


class Judge(Shape):
    """How far an agent's judge agrees with people, on the samples both graded (core/judging.py)."""

    both: int
    agreed: int
    missed: int  # it passed what people found wrong or critical
    false_alarms: int  # it failed what people found right
    agreed_share: float | None
    kappa: float | None  # agreement beyond chance, once it can be told


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
    judge: Judge
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
    before: str | None  # where the next page starts, if there's one, sealed: it says nothing
    # The fewest people an instance serves before its runs show one by one, without names, if
    # this one serves fewer: its daily figures say what it did
    fewer: int | None


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
    tokens_cache_written: int = 0
    records: list[str]
    calls: list[Call]


# Making agents: drafts, trying them in the sandbox, and publishing them (core/drafts.py,
# core/publishing.py, sandbox.py)


class Offered(Shape):
    """One of the scenario's tools an agent may be given, with what it reads, writes or
    changes."""

    name: str
    description: str | None
    reads: bool
    writes: bool
    destructive: bool
    sends_outside: bool
    changes: str | None
    handles: list[str]
    outside: list[str]
    marks: bool


class PartRule(Shape):
    """A part of the business, as the settings in force know it: who decides a change to one
    of its records below level 2, by name, who approves an instance that works in it, its
    owners, and how right graded samples must show an agent's changes there before a5s raises
    its cap to level 2, if it ever may."""

    name: str
    deciders: list[str]
    owners: list[str]
    threshold: float | None


class Servable(Shape):
    """Someone an instance could serve, as the settings name them, or whoever is signed in: a
    person by their name, or a team or a role as written."""

    id: str
    name: str


class Askable(Shape):
    """An instance a new one could ask, of those the person may watch: its agent, and the parts
    it works in."""

    id: str
    agent: str
    parts: list[str]


class Limit(Shape):
    """The scenario's limits for a type of change: past either, a change waits for a person,
    whatever the level."""

    per_run: int | None
    per_person_30_days: int | None


class Offer(Shape):
    tools: list[Offered]
    models: list[str]  # the models the deployment approves
    # What follows here from what an agent may do, as the settings in force say it
    parts: list[PartRule]
    no_part: list[str]  # who decides a change to a record in no part: the instance approvers
    limits: dict[str, Limit]  # by type of change
    # For a draft's plan of its first instance: whom it could serve, and the instances it
    # could ask, of those the person may see already
    servable: list[Servable]
    askable: list[Askable]
    owed: list[str] = []  # the kinds of what people owe that the scenario's records make, such as records


class Template(Shape):
    """An agent a new one may start from, and the tools it needs that the scenario hasn't."""

    name: str
    works_for: str
    does: str
    model: str
    tools: list[str]
    lacks: list[str]


class Templates(Shape):
    templates: list[Template]


class Drafts(Shape):
    drafts: list[DraftLine]  # someone's own, latest first
    theirs: list[DraftLine]  # their co-authors', of the agents they may author too


class Defined(Shape):
    """An agent as its folder defines it, whole, as the catalogue would show it: a draft's
    preview."""

    id: str
    release: str
    works_for: str
    does: str
    owners: list[str]
    model: str
    autonomy: Autonomy
    tools: list[Tool]
    a5s_tools: list[str]
    skills: list[str]
    triggers: list[dict[str, Any]]
    schedules: list[Schedule]
    events: list[EventTaken]
    reports: list[str]
    obligations: list[str]
    reminders: bool
    preferences: list[str]
    channels: list[str]
    context: Context
    budget: Budget
    instances: list[Instance]
    instructions: str


class Signer(Shape):
    """Whose signature a draft's release would need, and why: and who holds that role in the
    directory, by name, where a person holds it; for a new agent's owner, nobody, till the
    directory names someone."""

    role: str
    who: str
    why: str
    held_by: list[str] | None = None


class Drafter(Shape):
    """Someone who drafted a draft before whoever holds it now, and how it went on from them."""

    name: str
    at: datetime
    how: Literal["handed", "copied"]  # handed over to its holder, or copied into their draft


class Plan(Shape):
    """Its authors' plan for a draft's first instance: the parts it would work in, whom it
    would serve, and the instances it could ask. Never in force: the signed settings are, which
    those parts' owners approve, and putting it to work starts from it."""

    parts: list[str] = []
    serves: list[str] = []
    asks: list[str] = []


class DescribedNote(Shape):
    """One thing a draft described in words was given, and why, or wasn't, and why not."""

    what: str
    given: bool
    why: str


class Described(Shape):
    """How a draft was described in words: its author's words, the model that proposed what it
    needs, and a note on each thing it was given or not, for its author to check."""

    words: str
    model: str
    notes: list[DescribedNote]


class Draft(Shape):
    """A draft: its agent's folder, file by file, what would stop its release, and how the
    catalogue would show it, if it loads."""

    id: str
    agent: str
    based_on: str | None
    created_at: datetime
    updated_at: datetime
    published: str | None
    files: dict[str, str]  # each file's text, by its path in the agent's folder
    plan: Plan  # for its first instance, as its authors mean to ask for it
    described: Described | None = None  # if it began from its author's words
    yours: bool  # or a co-author's, read only
    author: str | None
    drafted_before: list[Drafter]  # who drafted it before its author, oldest first
    problems: list[str]  # what would stop its release, as `a5s agent check` says it
    preview: Defined | None
    signers: list[Signer] | None  # whom its release would need, if that can be worked out
    publishing: bool  # whether the studio opens its pull request, or its author does
    # Where it is on its way to work: whether the release here holds it as it is, and whether
    # an instance of its agent is at work, or paused
    released: bool
    at_work: bool
    changes: bool  # an agent the release here has, rather than a new one


class Named(Shape):
    id: str
    name: str


class CoAuthors(Shape):
    people: list[Named]  # whom a draft may be handed over to


class HandedOver(Shape):
    handed: str
    to: str


class Dropped(Shape):
    dropped: str


class Loose(BaseModel):
    """A model provider's own payload, as it went: the fields the studio reads, and whatever
    else the provider's format has."""

    model_config = ConfigDict(extra="allow")


class SentMessage(Loose):
    role: str
    content: Any = None
    tool_calls: list[dict[str, Any]] | SkipJsonSchema[None] = None


class Sent(Loose):
    messages: list[SentMessage]
    tools: list[dict[str, Any]] | SkipJsonSchema[None] = None


class ModelCall(Shape):
    """One call to the model a try made: what it was sent, what came back, and how."""

    sent: Sent
    came: Any
    status: int


class Sandbox(Shape):
    """Whom a draft may be tried as, of the sandbox's made-up people, and on which models, with
    the currency models.yaml prices them in, if it names one."""

    people: list[Named]
    models: list[str]
    currency: str | None = None


class TriedRun(Run):
    """A try's run, as the sandbox shows it: its entries in the sandbox's own ledger too, of
    made-up people alone."""

    entries: list[dict[str, Any]]


class Tried(Shape):
    agent: str
    reply: str
    run: TriedRun | None
    model_calls: list[ModelCall]
    tokens: int = 0  # what its run took, towards the day's tries on real models


class CaseLine(Shape):
    number: int
    name: str
    file: str
    suite_alone: list[str]  # what of it only the agent's suite does, which the sandbox doesn't


class Cases(Shape):
    cases: list[CaseLine]
    problem: str | SkipJsonSchema[None] = None  # why its cases can't be read, if they can't


class Judged(Shape):
    """What a judge said of a step a case says what a right answer is for, or why none did."""

    grade: Literal["right", "wrong", "critical"] | None
    why: str
    judge: str | None  # the model that judged it: the stand-in, or the draft's own judge


class CaseStep(Shape):
    say: str
    reply: str
    called: list[str]
    wrong: list[str]
    judged: Judged | SkipJsonSchema[None] = None


class CaseRan(Shape):
    """A test case run in the sandbox, or why it wasn't."""

    name: str
    file: str
    ran: bool
    why: str | SkipJsonSchema[None] = None
    passed: bool | SkipJsonSchema[None] = None
    problems: list[str] | SkipJsonSchema[None] = None
    steps: list[CaseStep] | SkipJsonSchema[None] = None
    # What running it took, on the model it ran on, for comparing models on an agent's own
    # cases: the seconds it took, its runs' tokens, and what they cost at the model's prices,
    # in the deployment's currency, or nothing where its prices aren't known
    model: str | SkipJsonSchema[None] = None
    seconds: float | SkipJsonSchema[None] = None
    tokens: int | SkipJsonSchema[None] = None
    cost: float | None = None
    judge_tokens: int = 0  # and its judge's, the same on any model, towards the day's tries


class Publish(Shape):
    """A publish under way: the code to enter at GitHub's sign-in, and how it stands."""

    id: str
    status: Literal["signing in", "opened", "refused", "lapsed"]
    agent: str
    user_code: str | None
    verify_at: str | None
    interval: int
    expires_in: int
    pull: str | None
    problem: str | None
    branch: str


class PullRequest(Shape):
    """A draft's pull request, for its author to open themselves: where its folder goes, and
    what it says."""

    folder: str
    title: str
    body: str
    ready: bool  # whether nothing would stop its release


# The settings app, folded into the studio (core/settings_api.py): the version in force, those
# waiting for approval, and what someone asked for; and a version they wrote, reviewed


class Change(Shape):
    """A change a version of the settings makes, in words code worked out, and whether it widens
    what agents do, as the page that approves it marks it."""

    text: str
    widens: bool


class InForce(Shape):
    """The version of the settings in force: as written, all of it in words, and as data, which
    the forms change."""

    serial: int
    text: str
    whole: list[str]
    data: dict[str, Any] | None


class ReleaseLevels(Shape):
    """What an agent's release lets its instances be set to: the level it starts at, the most it
    allows, and the types of change its own tools make."""

    starts: int
    most: int
    actions: list[str]


class VersionWaiting(Shape):
    """A version waiting for approval: what it changes, who approved it so far, and why it still
    waits, on its own page."""

    serial: int
    link: str
    changes: list[Change]
    approved_by: list[str]
    needs: list[str]


class SettingsRequest(Shape):
    """A version someone asked for, and what became of it."""

    asked_at: datetime
    serial: int
    outcome: str
    link: str | None


class SettingsNow(Shape):
    """The settings, for someone who approves versions of them: the version in force, what the
    forms offer, the versions waiting for approval, and what they asked for lately."""

    you: str
    me: str
    in_force: InForce | None
    names: dict[str, str]  # the people the settings name, and whoever signed in, by their names
    actions: list[str]  # the types of change this deployment's tools make
    models: list[str]  # the approved models the forms may put an instance on
    releases: dict[str, ReleaseLevels]
    waiting: list[VersionWaiting]
    requests: list[SettingsRequest]
    currency: str | None = None  # the one models.yaml prices models in, which budgets are in


class Shift(Shape):
    """Calls a version would decide differently from the one in force (core/impact.py): of one
    tool, by one instance, about records in these parts."""

    instance: str
    tool: str
    parts: list[str]
    was: str  # allow, hold or deny, as the version in force decides them
    would: str  # as this version would
    calls: int
    why: str  # policy's words for how this version would decide them


class Impact(Shape):
    """What a version would have done differently in the last weeks, decided again from the
    ledger's tool calls, and what it can't know."""

    days: int
    calls: int  # the calls it decided again
    limited: bool  # whether it read only the latest of the period's calls
    shifts: list[Shift]
    capped: list[str]  # levels it sets that a5s's caps hold back, in words
    about: str  # what it can't know, in words
    hidden: int  # calls of instances whoever reads it may not watch, left out of the shifts
    beyond: list[str] = []  # what the version changes that it doesn't decide again, in words


class HealthModel(Shape):
    """One model's day, for the health page: how its calls went, and whether it's gated."""

    model: str
    calls: int
    failed: int
    stalls: int
    mean_seconds: float | None = None
    gated_at: str | None = None  # as a time, or None when it may answer
    canary_passed: int = 0  # its canaries' latest day, for the drift it might hide
    canary_failed: int = 0
    reaches: str | SkipJsonSchema[None] = None  # once stopped, to whoever may put it back: whom that reaches


class HealthNow(Shape):
    """The health page: each model's day, measured rather than argued about."""

    days: int
    models: list[HealthModel]


class StatusNeed(Shape):
    """One thing that needs someone, for the Status page: now, out of hours too, or in working
    hours, what it is, and the runbook's section on what to do."""

    when: str
    said: str
    runbook: str


class StatusNow(Shape):
    """The Status page: how a5s is doing, as the core last said, and how long ago."""

    seen_seconds_ago: float | None = None  # None if the core never said yet
    verdict: str
    needs: list[StatusNeed]
    release: str | None = None  # the release a5s is, and whether it's approved here
    day: list[str]  # the last day's lines, as `a5s status` says them


class SettingsReview(Shape):
    """A version someone wrote, reviewed before they ask for it: why a5s couldn't propose it, or
    what it would change, all of it in words, and whose approval it needs."""

    problems: list[str]
    serial: int | SkipJsonSchema[None] = None  # the number it would have, once it reads
    in_force: int | None | SkipJsonSchema[None] = None  # the version it was reviewed against
    changes: list[Change] | SkipJsonSchema[None] = None
    whole: list[str] | SkipJsonSchema[None] = None
    approvers: list[str] | SkipJsonSchema[None] = None
    impact: Impact | SkipJsonSchema[None] = None  # what it would have done differently


class SettingsAsked(Shape):
    """A version asked for, which a5s proposes to everyone it needs within a minute."""

    request: int
    serial: int


# The notebook, folded into the studio (core/notebook_api.py): what agents noted from records,
# for those who keep each instance's notebook


class NoteSource(Shape):
    """A record a note comes from, by its key, and its link in its system, if it has one."""

    key: str
    link: str | None


class Note(Shape):
    """A note an agent kept, with the records it comes from, when it was noted, and when its
    records were last checked."""

    entry: str  # N-<number>
    instance: str
    text: str
    sources: list[NoteSource]
    noted: str  # a date
    checked: str  # a date


class NotebookNow(Shape):
    """The notes of the instances someone keeps, those whose every record they may see, how many
    more there are that they may not, and who else keeps those."""

    you: str
    instances: list[str]
    names: dict[str, str]  # each instance as people say it, such as "the assistant in billing"
    entries: list[Note]
    hidden: int
    others: list[str]
    acting: Acting | SkipJsonSchema[None] = None  # while it holds an act a role gives them


class NoteRemoved(Shape):
    """A note removed, by its keeper."""

    removed: str


# Someone's own tasks, folded into the studio (core/tasks_api.py): what they asked agents to do
# over more than one run, and what they asked to be done again and again


class PlanStep(Shape):
    """A step of a task's plan, as its run keeps it, and how it stands."""

    content: str
    status: str  # pending, in_progress or completed


class TaskLine(Shape):
    """One of someone's tasks, with an agent: how it stands, what it waits on, and what it has
    spent; or, where its words name records they may no longer see, how it stands alone."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task: str  # T-<number>
    agent: str
    status: str
    ended: bool
    progress: int  # percent
    has_until: str = Field(alias="has until")
    spent: str
    updated: str  # a date
    parts: str | SkipJsonSchema[None] = None  # how many of its parts are done, if it has any
    withheld: bool | SkipJsonSchema[None] = None
    what: str | SkipJsonSchema[None] = None
    plan: list[PlanStep] | SkipJsonSchema[None] = None
    why: str | SkipJsonSchema[None] = None  # why it stopped, as its run said
    needed: str | None | SkipJsonSchema[None] = None  # what it asked its owner for
    said: str | None | SkipJsonSchema[None] = None  # and what they said
    found: Any = None  # what it found, as its run gave it
    so_far: list[Any] | SkipJsonSchema[None] = Field(default=None, alias="so far")


class RepeatLine(Shape):
    """A task someone asked to be done again and again: when, how it stands, and its last task;
    or, where its words name records they may no longer see, how it stands alone."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repeat: str  # E-<number>
    agent: str
    when: str
    status: str
    last_task: str | SkipJsonSchema[None] = Field(default=None, alias="last task")
    what: str | SkipJsonSchema[None] = None
    withheld: bool | SkipJsonSchema[None] = None


class TasksNow(Shape):
    """Someone's own tasks, with every agent, and what they asked to be done again and again."""

    you: str
    tasks: list[TaskLine]
    repeats: list[RepeatLine]


class TaskStopped(Shape):
    """A task cancelled, or a repeat stopped, at its owner's word."""

    cancelled: str | SkipJsonSchema[None] = None
    stopped: str | SkipJsonSchema[None] = None


# The administrators' page, folded into the studio (core/admin_api.py): who holds each role and
# by what, what waits for whom, what nobody answers for, and the latest administrative acts


class Holder(Shape):
    """Someone who holds a role, and what gave it them: the directory, or a group."""

    id: str
    name: str
    by: list[str]


class RoleHeld(Shape):
    """A role, in words, and who holds it."""

    role: str
    name: str
    held_by: list[Holder]


class GroupGives(Shape):
    """A group of the identity provider's that the settings give roles, and how many it holds."""

    group: str
    roles: list[str]
    people: int


class VersionNeeds(Shape):
    """A version of the settings waiting, who approved it, and whose approval it still needs."""

    serial: int
    approved_by: list[str]
    needs: list[str]


class HeldIn(Shape):
    """Changes agents asked for in a part, waiting, and who may decide them."""

    part: str
    waiting: int
    deciders: list[str]


class AdminWaiting(Shape):
    """What waits for whom: versions of the settings, the release, and held changes."""

    settings: list[VersionNeeds]
    release: list[str]
    held_changes: list[HeldIn]


class Nobodys(Shape):
    """Something nobody answers for any more, what's wrong, and what to do."""

    what: str
    do: str
    agent: str | SkipJsonSchema[None] = None
    instance: str | SkipJsonSchema[None] = None
    part: str | SkipJsonSchema[None] = None


class Ownerless(Shape):
    """The agents, instances and parts nobody answers for."""

    agents: list[Nobodys]
    instances: list[Nobodys]
    parts: list[Nobodys]


class AdminAct(Shape):
    """An administrative act, as the ledger records it: who did it, when, and to what, with whom
    it was about as a stand-in until the officer agrees to names."""

    seq: int
    at: str | None
    action: str
    what: str
    by: str | list[str] | None  # whoever did it, or each who signed it
    instance: str | None
    about: dict[str, Any]


class AdminNow(Shape):
    """The administrators' page: who holds each role and by what, what waits for whom, what
    nobody answers for, and the latest acts."""

    you: str
    roles: list[RoleHeld]
    groups: list[GroupGives]
    claim: str | None  # the claim sign-ins show their groups in, if the deployment reads one
    waiting: AdminWaiting
    ownerless: Ownerless
    days: int
    latest: list[AdminAct]


# The audit trail, folded into the studio (core/audit_api.py): the ledger as an auditor reads it


class AuditTrail(Shape):
    """Whether the trail checks out, as the copier last found it (round 15, E8): it checks out
    once the copier has checked the whole ledger, its chain and every locked copy, and found
    nothing wrong, while it isn't stopped, and while that check isn't long overdue."""

    checks_out: bool
    problems: list[str]  # what's wrong, in a5s's words, if anything
    copied_through: int | None  # the last entry the locked copies hold
    uncopied: int  # entries written since, which someone could still rewrite unseen
    copied_minutes_ago: int | None
    checked_minutes_ago: int | None  # since the copier last checked the whole ledger; None: not yet
    failing: bool  # the copier's last try failed, and it tries again
    stale: bool  # its last check is two days old or more, as when the copier stopped running
    late: bool  # entries have waited to be copied twice as long as they should


class AuditNow(Shape):
    """Who's reading the trail, how it shows people, by name or by stand-in, and whether the
    trail checks out."""

    you: str
    names: bool  # whom agents acted for shows by name, as the officer agreed
    exports: bool  # whether a period may be exported here, which only names allow
    kinds: list[str]
    trail: AuditTrail | None  # None: no copier keeps locked copies of the ledger here


class AuditEntries(Shape):
    """A page of a period's entries, as the auditor asked, and where the next begins."""

    entries: list[dict[str, Any]]  # each as the ledger holds it, whom it acted for as a stand-in
    next: int | None
    copied_through: int | None  # those past it aren't in the locked copies yet (round 15, E8)
    broken: list[int]  # those of the page that don't check out as the ledger holds them


class RoleHolders(Shape):
    """A role, and who holds it now."""

    role: str
    held_by: list[str]


class AuditReport(Shape):
    """Who holds each role, and who did what of a period's administration."""

    roles: list[RoleHolders]
    acts: list[AdminAct]


class AuditExport(Shape):
    """A page of a period's entries exactly as the ledger holds them, to check and keep, with what
    proves they're its own: the entries either side, and the chain's head."""

    entries: list[dict[str, Any]]
    next: int | None
    head: dict[str, Any] | None
    bounds: dict[str, Any]


# Deciding the changes agents asked for, folded into the studio (core/decide_api.py)


class RecordLink(Shape):
    """A record a held change names, and its address in its system."""

    key: str
    link: str


class HeldChange(Shape):
    """A change an agent asked for, held for a person to decide: in the words code worked out when
    it was asked for, who asked and for whom, what to know, and whether the viewer may decide it."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str  # P-<number>
    digest: str  # what a decision's sign-in commits to
    said: str
    agent: str
    acts_for: list[str] = Field(alias="for")  # whom it was asked for, by name
    flags: list[str]
    sensitive: bool  # decided on its own, never with others
    status: str
    yours: str | None  # the viewer's decision, if they made one that counts
    may_decide: bool
    undoable: bool  # whether a5s can reverse it once it's made, as its tool says
    outcome: str | None
    proposed_at: str
    lapses_at: str
    links: list[str]
    records: list[RecordLink]
    changed: list[str]  # the records that changed since it was asked for, in words


class DecideNow(Shape):
    """The held changes someone may decide now, those they were told of, and those they decided
    lately."""

    you: str
    proposals: list[HeldChange]
    acting: Acting | SkipJsonSchema[None] = None  # while it holds an act a role gives them


class Decided(Shape):
    """A decision recorded, for the core to check again, seal and act on: and the changes an
    approval leaves waiting for another of their deciders, such as one that needs two of a
    part's, or a part's of its own."""

    decided: list[str]
    decision: str
    by: str
    waits: list[str] = []


# Grading samples of agents' changes, folded into the studio (core/grade_api.py)


class SampleLine(Shape):
    """A sample of an agent's change, waiting for a grade: in the words code worked out when it was
    asked for or made, how it went, what code flagged, and its records as they stood then."""

    id: int
    kind: str  # "proposal", a held change someone decided, or "action", made at level 2
    agent: str
    part: str
    action: str
    said: str
    records: dict[str, dict[str, Any] | None]
    flags: list[str]
    decided: str | None  # a decider's approve or reject, for a held change
    drawn_at: str
    asked: str | None = None  # what the people it answered said, masked until names are agreed


class GradeNow(Shape):
    """The samples someone may grade now, oldest first."""

    you: str
    samples: list[SampleLine]
    acting: Acting | SkipJsonSchema[None] = None  # while it holds an act a role gives them


class Graded(Shape):
    """Grades recorded, for the core to check again and seal."""

    graded: list[int]
    grades: dict[str, str]
    by: str


# Approving a version of the settings, folded into the studio (core/approve_api.py)


class VersionReview(Shape):
    """A version of the settings as its approvers see it before approving it: what it changes
    from the one in force, in words code worked out, all of it, who approved it so far and what
    it still needs, who asked for it, and where it stands."""

    serial: int
    proposed_at: str
    in_force: int | None  # the version in force, if any
    changes: list[Change]
    whole: list[str]
    needs: list[str]
    approved_by: list[str]
    asked_by: str | None  # who asked for it in the settings, if anyone did
    you: str
    you_approved: bool
    status: str  # waiting, applied, superseded, or why a5s couldn't apply it
    impact: Impact | SkipJsonSchema[None] = None  # while it waits: what it would do differently
    acting: Acting | SkipJsonSchema[None] = None  # while it waits for their approval
    retires: list[str] = []  # the instances in force that it leaves out, which it retires
    needs_you: bool = False  # whether it waits for their approval, which counts towards it


class Approved(Shape):
    """An approval recorded, for the gateway to check again, seal, and count."""

    approved: bool
    serial: int
    by: str
    needs: list[str]


# The data protection officer's requests, folded into the studio (core/officer_api.py)


class OfficerNow(Shape):
    """The officer's page, before they ask: who they are, and the line that says they act as
    the data protection officer there."""

    you: str
    acting: Acting


class OfficerWhom(Shape):
    """Whose an id is, for the officer before they ask about it: someone in the directory, by
    name and team, an archive, an address, a group chat, or nobody it knows by it now."""

    kind: str  # person, archive, address, group or nobody
    said: str
    name: str | SkipJsonSchema[None] = None  # theirs in the directory, for a person


class OfficerAsked(Shape):
    """The officer's request, recorded for the team that runs a5s to carry out, once, with the
    command it's carried out with."""

    asked: str  # export or erase
    person: str
    name: str | None  # whose the id is in the directory now, if anyone's
    by: str
    lasts: str
    command: str
