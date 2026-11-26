"""The studio's routes in the channels app (docs/studio.md): its page, built from studio/, which
holds nobody's data, and its API, for people signed in.

Every route of the API is behind the router's own check that whoever asks is signed in and
someone the directory knows, so a route added to it can't be reached by anyone else. Each route
then says what of the studio it's for, as a dependency: watching agents (`studying`), making
them (`drafting`), or anyone's own (`someone`). What someone sees is worked out in core/studio.py,
as the core's API works it out for the team that runs a5s.
"""

import re
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from a5s import authoring, cases, db, definitions, describing
from a5s.connectors import libraries
from a5s.contract import Person
from a5s.core import (
    acting,
    admin_api,
    administration,
    approvals,
    approve_api,
    asks,
    audit_api,
    budgets,
    decide_api,
    delegation,
    dependencies,
    drafts,
    feedback,
    grade_api,
    handover,
    health_api,
    languages,
    ledger,
    memberships,
    notebook_api,
    officer_api,
    publishing,
    registry,
    run_cases,
    samples,
    settings_api,
    settings_app,
    shadows,
    shell_api,
    spending,
    status_api,
    studio,
    suspension,
    tasks_api,
    typescript,
    undoing,
    web,
    words,
)
from a5s.core import home as homes  # the studio's home: `home` is the site's
from a5s.core import studio_models as shapes  # what each route answers
from a5s.core.releases import agent_owner

STUDIO = web.WEBCHAT / "studio"  # as `npm run build` in studio/ builds it, which the image does
STUDIO_UNBUILT = ("The studio isn't built here. Build it from the repository with "
                  "`npm ci --prefix studio && npm run build --prefix studio`, as the image does.")
_ASSET = re.compile(r"[\w-]+\.(js|css|woff2)")  # its own files, by name alone: nothing else


class DraftStart(BaseModel):
    """A new draft: a new agent's name and the template it starts from, or what it's for in
    its author's words, for the sandbox's model to propose what it needs; an agent of the
    release to change; or a co-author's draft to copy."""

    name: str | None = None
    template: str | None = None
    describe: str | None = None  # what a new agent is for, in its author's words
    model: str | None = None  # the sandbox's model that proposes what it needs: its stand-in, unless said
    agent: str | None = None
    copy_of: str | None = None  # a co-author's draft


class HandOver(BaseModel):
    """Whom to hand one's draft over to: someone who may author its agent too."""

    to: str


class DraftFiles(BaseModel):
    """A draft's agent's folder: each file's text, by its path in it, and, if it changes, its
    authors' plan for its first instance."""

    files: dict[str, str]
    plan: shapes.Plan | None = None
    loaded: datetime | None = None  # when the tab last had the draft, as it was then saved


class DraftTry(BaseModel):
    """Trying a draft in the sandbox: who to be, of its made-up people, what to say, and on
    which of the models it offers."""

    person: str
    text: str
    model: str = "stand-in"


class Serve(BaseModel):
    """Which of an agent's instances is to serve someone who asked for it."""

    instance: str


class StatusAct(BaseModel):
    """Suspending or resuming an instance from its page: which, and the salt the page made its
    sign-in's nonce with."""

    action: str
    salt: str


class CaseRun(BaseModel):
    """Running one of a draft's test cases in the sandbox: on which of the models it offers."""

    model: str = "stand-in"


def may_study(gw: Any, person: Person) -> bool:
    """Whether someone may use the studio's catalogue and dashboards: they may watch an
    instance, own an agent, or make agents."""
    with db.transaction(gw.url) as conn:
        theirs = studio.instances(conn, person)
    return (bool(theirs) or any(r.startswith("agent-owner:") for r in person.roles)
            or drafts.authors(person, gw.cfg.team))


class RunCaseAsked(BaseModel):
    """A run kept as a test case: its name, the made-up person who says it, what they say, as
    its author checked it, what a right answer is, if they say, and that they checked it."""

    name: str
    speaker: str
    say: str
    judged: str | None = None
    checked: bool = False


class ShadowGrade(BaseModel):
    grade: str  # better, same, worse or wrong


class HandoverReply(BaseModel):
    """What someone of a team answers a person whose conversation was handed to it."""

    text: str


class UndoAct(BaseModel):
    """Undoing a change, signed in afresh for that act alone: the salt its nonce was made with."""

    salt: str


class ConnectionReturn(BaseModel):
    """What a system sent someone back to a5s with, once they said whether a5s may act for them
    there: the start's state, and its code, or the error it gave for a no."""

    state: str
    code: str | None = None
    error: str | None = None


class AnswerGrade(BaseModel):
    """An owner's grade of an answer someone said was wrong: right, wrong or critical."""

    grade: str


STAND_IN = "stand-in"  # the sandbox's model that answers itself, which costs nothing
# The tokens someone's tries of drafts in the sandbox may take a day on real models, in all:
# as much as an agent that names no budget gives one person a day [starting value]
SANDBOX_DAY = definitions.Budget().per_person_per_day
# What the channels app lets the sandbox take of it: one try at a time for each person, and a
# few at a time in all, so tries hold few of the threads its chats are answered on; and what a
# try on a real model counts as towards someone's day when the sandbox couldn't say what it took,
# such as one it didn't answer in time
SANDBOX_AT_ONCE = 4
SANDBOX_UNSAID = SANDBOX_DAY // 10


class Spent(HTTPException):
    """The sandbox's refusal of a try, or its failure to answer one, with the tokens the try
    took on a real model before it, as the sandbox says: None where it can't say."""

    def __init__(self, status: int, detail: str, tokens: int | None) -> None:
        super().__init__(status, detail)
        self.tokens = tokens
SANDBOX_SPENT = ("your tries in the sandbox have taken the {n} tokens a day's may take on real "
                 "models: try again tomorrow, or on the stand-in, which costs nothing")


def router(gw: Any) -> APIRouter:
    """The studio's page and its API, for the channels app to include."""

    def available() -> None:
        web.approving(gw)

    def someone(authorization: str | None = Header(default=None)) -> Person:
        """Whoever signed in, whom the directory knows: the studio's home is everyone's."""
        return web.known(gw, authorization)

    def studying(person: Annotated[Person, Depends(someone)]) -> Person:
        """Who signed in to the studio: someone who may watch an instance, or owns an agent."""
        if not may_study(gw, person):
            raise HTTPException(403, "the studio's dashboards are for the people who run an "
                                     "instance, own an agent, own or decide for one of its "
                                     "parts, approve instances, or make agents")
        return person

    def drafting(person: Annotated[Person, Depends(someone)]) -> Person:
        """Who signed in to make agents: an agent's owner or named author, or an engineer,
        anyone in the team that runs a5s (round 17, C3)."""
        if not drafts.authors(person, gw.cfg.team):
            raise HTTPException(403, "making agents is for their owners, the people the "
                                     "organisation names their authors, and the team that "
                                     "runs a5s")
        return person

    pages = APIRouter(dependencies=[Depends(available)])  # the page alone, which holds no data
    api = APIRouter(dependencies=[Depends(available), Depends(someone)])  # all of it signed in

    # The studio's pages: what someone may watch, read only, worked out as the core's API works
    # it out for the team that runs a5s (core/studio.py)

    def watched(conn: Any, person: Person, instance: str) -> dict:
        found = next((i for i in studio.instances(conn, person) if i["id"] == instance), None)
        if found is None:
            raise HTTPException(404, "there's no such instance that you may watch")
        return found

    # The studio itself: one page, built from studio/ (`npm run build`, as the image does),
    # which keeps someone's sign-in in memory as they move between its agents, instances and
    # runs, each at an address of its own

    def built(name: str) -> Response:
        if not (STUDIO / "index.html").is_file():
            return Response(STUDIO_UNBUILT, status_code=503, media_type="text/plain; charset=utf-8")
        path = STUDIO / name
        if not path.is_file():
            raise HTTPException(404, "no such file")
        return Response(path.read_bytes(), media_type=web.TYPES[path.suffix],
                        headers=web.PAGE_HEADERS)

    @pages.get("/studio/", include_in_schema=False)
    def studio_page() -> Response:
        return built("index.html")

    @pages.get("/studio/agents/{name}", include_in_schema=False)
    @pages.get("/studio/instances/{name}", include_in_schema=False)
    @pages.get("/studio/runs/{name}", include_in_schema=False)
    @pages.get("/studio/drafts/{name}", include_in_schema=False)
    @pages.get("/studio/handovers/{name}", include_in_schema=False)
    def studio_view(name: str) -> Response:
        """The studio, at the address of one of its agents, instances, runs or drafts."""
        return built("index.html")

    @pages.get("/studio/new", include_in_schema=False)
    @pages.get("/studio/agents", include_in_schema=False)
    @pages.get("/studio/you", include_in_schema=False)
    @pages.get("/studio/settings", include_in_schema=False)
    @pages.get("/studio/notebook", include_in_schema=False)
    @pages.get("/studio/tasks", include_in_schema=False)
    @pages.get("/studio/admin", include_in_schema=False)
    @pages.get("/studio/audit", include_in_schema=False)
    @pages.get("/studio/decide", include_in_schema=False)
    @pages.get("/studio/grade", include_in_schema=False)
    @pages.get("/studio/officer", include_in_schema=False)
    @pages.get("/studio/approve", include_in_schema=False)
    @pages.get("/studio/design", include_in_schema=False)
    @pages.get("/studio/map", include_in_schema=False)
    @pages.get("/studio/spending", include_in_schema=False)
    @pages.get("/studio/health", include_in_schema=False)
    @pages.get("/studio/connections", include_in_schema=False)
    @pages.get("/studio/undo", include_in_schema=False)
    @pages.get("/studio/handovers", include_in_schema=False)
    @pages.get("/studio/shadows", include_in_schema=False)
    @pages.get("/studio/status", include_in_schema=False)
    def studio_new() -> Response:
        """The studio, where someone starts a new agent, sees all the agents they may, what they
        may do, or the design system's showcase."""
        return built("index.html")

    @pages.get("/studio/assets/{name}", include_in_schema=False)
    def studio_asset(name: str) -> Response:
        """One of the studio's own files, named by its digest, so it never changes."""
        if not _ASSET.fullmatch(name):
            raise HTTPException(404, "no such file")
        found = built(f"assets/{name}")
        if found.status_code == 200:
            found.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return found

    @api.get("/studio/api/home", **shapes.answers(shapes.Home))
    def studio_home(person: Annotated[Person, Depends(someone)]) -> dict:
        """What waits for whoever signed in, their drafts, and what of the studio they may
        use, whether or not they hold a role: the catalogue is everyone's."""
        with db.transaction(gw.url) as conn:
            asks.settle(conn, gw.scenario, studio.instances(conn))  # served since, or lapsed
            return {"you": person.name,
                    "waiting": homes.waiting(conn, gw, person, languages.of(person)),
                    "drafts": drafts.mine(conn, person),
                    # a new agent, as the catalogue says
                    "authoring": drafts.may_author(person, None, gw.cfg.team),
                    "changes": sorted(a for a in gw.definitions if drafts.may_author(person, a))}

    @api.get("/studio/api/you", **shapes.answers(shapes.You))
    def studio_you(person: Annotated[Person, Depends(someone)]) -> dict:
        """Each role whoever signed in holds, what gave it them, the directory or a group of
        the identity provider's, and what it lets them do; and the groups their sign-in
        showed, of those the settings name."""
        with db.transaction(gw.url) as conn:
            return {"you": person.name, "id": person.id,
                    "roles": homes.roles(conn, gw, person, languages.of(person)),
                    "groups": list(memberships.stored(conn, person.id).get(person.id, ()))}

    @api.get("/studio/api/shadows", **shapes.answers(shapes.Shadows))
    def studio_shadows(person: Annotated[Person, Depends(someone)]) -> dict:
        """What new versions answered beside those at work, for whoever signed in to grade, as
        for samples, those whose records they may all see; and how each shadow they may see did,
        in counts (core/shadows.py). Refused where no shadow is theirs to grade or follow, as
        their sidebar leaves the page out (round 17, C5)."""
        with db.transaction(gw.url) as conn:
            if not shadows.theirs(conn, gw.scenario, person):
                raise HTTPException(403, "no new version answers beside an instance for you to "
                                         "grade or follow")
            choices = gw.data_protection(conn)
            pairs = shadows.gradeable(conn, gw.scenario, person, may=choices.shadow_runs,
                                      names=choices.studio_names, fewest=choices.fewest_people)
            every = studio.instances(conn)
            known = {n for n, d in gw.definitions.items()
                     if studio.layers(n, d, every, person, gw.scenario)}
            return {"pairs": [{"id": r["id"], "agent": r["agent"], "shadow": r["definition"],
                               "asked": r["asked"], "sent": r["sent"], "answer": r["answer"],
                               "at": r["at"].isoformat()} for r in pairs],
                    "shadows": shadows.figures(conn, gw.scenario, person, known=known,
                                               offered={r["instance_id"] for r in pairs}),
                    **acting.shown(acting.grading(person, shadows=True) if pairs else None)}

    @api.post("/studio/api/shadows/{pair}/grade", **shapes.answers(shapes.ShadowGraded))
    def studio_shadow_grade(pair: int, body: ShadowGrade,
                            person: Annotated[Person, Depends(someone)]) -> dict:
        """Grade what a shadow answered beside the answer sent: better, as good, worse, or
        wrong, once, as someone who may grade it. The core notes it in the ledger."""
        try:
            with db.transaction(gw.url) as conn:
                choices = gw.data_protection(conn)
                shadows.grade(conn, gw.scenario, person, pair, body.grade,
                              may=choices.shadow_runs, names=choices.studio_names,
                              fewest=choices.fewest_people)
        except LookupError:
            raise HTTPException(404, "there's no such answer for you to grade") from None
        except shadows.Refused as e:
            raise HTTPException(409, str(e)) from None
        return {"graded": True}

    @api.get("/studio/api/handovers", **shapes.answers(shapes.Handovers))
    def studio_handovers(person: Annotated[Person, Depends(someone)]) -> dict:
        """The conversations handed over to the teams whoever signed in is in, still open
        (core/handover.py): each record they may not see, as such. Refused to anyone in none of
        the teams agents hand to, as their sidebar leaves the page out (round 17, C5)."""
        with db.transaction(gw.url) as conn:
            if not handover.answers_any(conn, gw.scenario, person):
                raise HTTPException(403, "conversations handed over are for the teams agents "
                                         "hand them to, and you're in none of them")
            return {"handovers": handover.waiting(conn, gw.scenario, person)}

    @api.get("/studio/api/handovers/{handover_id}", **shapes.answers(shapes.Handover))
    def studio_handover(handover_id: int, person: Annotated[Person, Depends(someone)]) -> dict:
        """A conversation handed to one of their teams: its brief, what the person said before
        and since, their own words alone, and the team's answers."""
        with db.transaction(gw.url) as conn:
            found = handover.one(conn, gw.scenario, person, handover_id)
        if found is None:
            raise HTTPException(404, "there's no such conversation handed to your teams")
        answers = not found["ended"] and (found["taken_by"] is None or found["mine"])
        return {**found, **acting.shown(acting.answering(found["team"], found["person"])
                                        if answers else None)}

    def handing(handover_id: int, person: Person, act: Any) -> dict:
        try:
            with db.transaction(gw.url) as conn:
                act(conn, gw.scenario, person, handover_id)
        except LookupError:
            raise HTTPException(404, "there's no such conversation handed to your teams") from None
        except handover.Refused as e:
            raise HTTPException(409, str(e)) from None
        return {"done": True}

    @api.post("/studio/api/handovers/{handover_id}/take", **shapes.answers(shapes.HandoverDone))
    def studio_take(handover_id: int, person: Annotated[Person, Depends(someone)]) -> dict:
        """Take a conversation handed to one of their teams, to answer the person."""
        return handing(handover_id, person, handover.take)

    @api.post("/studio/api/handovers/{handover_id}/answer", **shapes.answers(shapes.HandoverDone))
    def studio_answer(handover_id: int, body: HandoverReply,
                      person: Annotated[Person, Depends(someone)]) -> dict:
        """Answer the person, as whoever took it: the core puts it in their chat within a
        minute, as the agent's bot, with their name."""
        return handing(handover_id, person,
                       lambda conn, scenario, who, h: handover.answer(conn, scenario, who, h, body.text))

    @api.post("/studio/api/handovers/{handover_id}/back", **shapes.answers(shapes.HandoverDone))
    def studio_back(handover_id: int, person: Annotated[Person, Depends(someone)]) -> dict:
        """Hand it back to the agent, which answers the person again."""
        return handing(handover_id, person, handover.back)

    @api.get("/studio/api/changes/{change}", **shapes.answers(shapes.ChangeMade))
    def studio_change(change: int, person: Annotated[Person, Depends(someone)]) -> dict:
        """A change an agent made, which its tool says how to undo (core/undoing.py), for
        whoever it was for, and whoever decides changes like it in its record's part: what it
        did, until when it can be undone, whether they may, and how it stands."""
        with db.transaction(gw.url) as conn:
            found = undoing.shown(conn, gw.scenario, person, change)
        if found is None:
            raise HTTPException(404, "there's no such change of yours to undo")
        return found

    @api.post("/studio/api/changes/{change}/undo", **shapes.answers(shapes.UndoAsked))
    def studio_undo(change: int, body: UndoAct, person: Annotated[Person, Depends(someone)],
                    authorization: str | None = Header(default=None)) -> dict:
        """Undo a change, signed in afresh for that act alone, which the core checks again and
        carries out within a minute, while its record is as the change left it: whoever it was
        for, or decides changes like it in its record's part."""
        token = (authorization or "").removeprefix("Bearer ").strip()
        try:
            who, claims = undoing.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                        token, change, body.salt, time.time())
            with db.transaction(gw.url) as conn:
                row = undoing.found(conn, change)
                if row is None or undoing.shown(conn, gw.scenario, who, change) is None:
                    raise HTTPException(404, "there's no such change of yours to undo")
                if why := undoing.may(gw.scenario, who, row, bool(row["open"])):
                    raise HTTPException(409, words.say(languages.of(who), why))
                asked = undoing.record(conn, change, who.id, token, body.salt, claims)
        except approvals.Refused as exc:
            raise web.refusal(gw, exc) from None
        return {"change": change, "at": asked["asked_at"].isoformat()}

    @api.get("/studio/api/you/connections", **shapes.answers(shapes.Connections))
    def studio_connections(person: Annotated[Person, Depends(someone)]) -> dict:
        """Each system whoever signed in may connect their own account in, so agents act there
        as them, with their permissions (core/delegation.py), and whether they have: none,
        where the deployment connects none."""
        with db.transaction(gw.url) as conn:
            found = delegation.connections(conn, gw.delegation, person.id)
        reads = libraries.read_in(gw.scenario)  # what connecting each is for
        return {"connections": [{**c, "reads": reads.get(c["system"], [])} for c in found]}

    @api.post("/studio/api/you/connections/{system}/start", **shapes.answers(shapes.ConnectionStarted))
    def studio_connect(system: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """Begin connecting their account in a system: the system's own page, where it asks
        them whether a5s may act for them, with the scopes the deployment names."""
        if gw.delegation is None:
            raise HTTPException(404, "this deployment connects no accounts")
        with db.transaction(gw.url) as conn:
            try:
                go = delegation.start(conn, gw.delegation, person.id, system,
                                      f"{gw.public_url}{delegation.BACK}")
            except delegation.Refused as e:
                raise HTTPException(404, str(e)) from None
        return {"go": go}

    @api.post("/studio/api/you/connections/back", **shapes.answers(shapes.ConnectionBack))
    def studio_connected(body: ConnectionReturn, person: Annotated[Person, Depends(someone)]) -> dict:
        """What a system sent them back with: its code, for the core to exchange for their
        tokens within a minute, or their no."""
        if gw.delegation is None:
            raise HTTPException(404, "this deployment connects no accounts")
        with db.transaction(gw.url) as conn:
            try:
                found = delegation.came_back(conn, gw.delegation, person.id, body.state,
                                             None if body.error else body.code)
            except delegation.Refused as e:
                raise HTTPException(400, str(e)) from None
        return {"system": found.name, "title": found.title,
                "connecting": bool(body.code and not body.error)}

    @api.delete("/studio/api/you/connections/{system}", **shapes.answers(shapes.Disconnected))
    def studio_disconnect(system: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """Forget their tokens in a system: a5s acts as them there no more, until they connect
        it again. The system may keep its own record of a5s's access, which they end there."""
        with db.transaction(gw.url) as conn:
            return {"forgotten": delegation.forget(conn, person.id, system, "they disconnected it")}

    @api.get("/studio/api", **shapes.answers(shapes.Catalogue))
    def studio_now(person: Annotated[Person, Depends(someone)]) -> dict:
        """The catalogue: every agent someone may know exists, each as far as the layers they
        see of it go, with the instances they may watch, and why."""
        with db.transaction(gw.url) as conn:
            return {"you": person.name, "agents": studio.catalogue(
                conn, gw.scenario, gw.definitions, gw.scenario.tools(), person),
                    "authoring": {"new": drafts.may_author(  # what they may make
                        person, None, gw.cfg.team),
                                  "agents": sorted(a for a in gw.definitions
                                                   if drafts.may_author(person, a))}}

    @api.get("/studio/api/agents/{agent}/feedback", **shapes.answers(shapes.AnswersSaidWrong))
    def studio_said_wrong(agent: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """The agent's answers people said were wrong, for its owners to check (core/feedback.py):
        those whose runs they may see, and who said each only once the officer agrees to names."""
        if agent not in gw.definitions or not feedback.owns(person, agent):
            raise HTTPException(404, "there's no such agent of yours")
        with db.transaction(gw.url) as conn:
            choices = gw.data_protection(conn)
            return feedback.shown(conn, gw.scenario, person, agent, names=choices.studio_names,
                                  fewest=choices.fewest_people)

    @api.post("/studio/api/feedback/{answer}/grade", **shapes.answers(shapes.AnswerGraded))
    def studio_grade_answer(answer: int, body: AnswerGrade,
                            person: Annotated[Person, Depends(someone)]) -> dict:
        """An owner's grade of an answer someone said was wrong: right, wrong or critical."""
        with db.transaction(gw.url) as conn:
            try:
                choices = gw.data_protection(conn)
                return feedback.grade(conn, gw.scenario, person, answer, body.grade,
                                      names=choices.studio_names, fewest=choices.fewest_people)
            except feedback.Refused as exc:
                raise HTTPException(404 if "no such" in str(exc) else 400, str(exc)) from None

    @api.get("/studio/api/runs/{run_id}/case", **shapes.answers(shapes.RunCaseOffered))
    def studio_run_case(run_id: str, person: Annotated[Person, Depends(studying)]) -> dict:
        """A run as a test case, masked by code, for its agent's author to check and keep, once
        the data protection officer agrees (core/run_cases.py)."""
        with db.transaction(gw.url) as conn:
            try:
                return run_cases.proposed(conn, gw.scenario, person, run_id, gw.definitions,
                                          gw.data_protection(conn))
            except run_cases.Refused as exc:
                raise HTTPException(404 if "no such" in str(exc) else 403, str(exc)) from None

    @api.post("/studio/api/runs/{run_id}/case", **shapes.answers(shapes.RunCaseKept))
    def studio_keep_run_case(run_id: str, body: RunCaseAsked,
                             person: Annotated[Person, Depends(studying)]) -> dict:
        """Keep a run as a test case in someone's draft of its agent, as they checked it."""
        with db.transaction(gw.url) as conn:
            try:
                kept = run_cases.keep(conn, gw.scenario, person, run_id, gw.definitions,
                                      gw.data_protection(conn), gw.cfg.agents_dir,
                                      name=body.name, as_=body.speaker, say=body.say,
                                      judged=body.judged, checked=body.checked)
            except (run_cases.Refused, drafts.Refused) as exc:
                raise HTTPException(404 if "no such" in str(exc) else 409, str(exc)) from None
        case = kept["case"]
        return {**kept, "case": {"name": case["name"], "speaker": case["as"],
                                 "steps": case["steps"]}}

    @api.get("/studio/api/spending", **shapes.answers(shapes.Spending))
    def studio_spending(person: Annotated[Person, Depends(someone)],
                        month: str | None = None) -> dict:
        """What agents' model calls cost in a calendar month, this one unless another is named,
        such as 2026-10: each part's and agent's against its budget, with its forecast to the
        month's end, and each instance someone may watch, with what a message answered cost.
        Only what's theirs to see (core/spending.py)."""
        if not spending.sees_any(gw.url, person):
            raise HTTPException(403, "spending is for the people who own a part or an agent, "
                                     "decide for a part, approve instances, or run one")
        with db.transaction(gw.url) as conn:
            try:
                return spending.report(conn, gw.models, gw.spending_in_force(conn), person,
                                       None, month, gw.currency)
            except spending.Refused as e:
                raise HTTPException(400, str(e)) from None

    @api.get("/studio/api/map", **shapes.answers(shapes.DependsOn))
    def studio_map(person: Annotated[Person, Depends(someone)]) -> dict:
        """What depends on what, as far as someone may see it: the parts, instances, agents,
        tools, systems and models, each joined to what it depends on (core/dependencies.py)."""
        with db.transaction(gw.url) as conn:  # level 2, as policy weighs it, and the caps as
            shown: dict[tuple[str, str | None], dict[tuple[str, str], int]] = {}  # a page
            # shows them, each release's on a model, as each model earns its own (round 16)

            def caps_of(release: str, model: str | None) -> dict[tuple[str, str], int]:
                if (release, model) not in shown:
                    shown[(release, model)] = samples.shown_caps(
                        conn, gw.cfg.seal_keys, release, [model] if model else None)
                return shown[(release, model)]

            return dependencies.drawn(conn, gw.scenario, gw.definitions, gw.scenario.tools(),
                                      gw.models, person, languages.of(person),
                                      approved=gw.approvers_in_force(conn), caps_of=caps_of)

    @api.get("/studio/api/agents/{agent}", **shapes.answers(shapes.Agent))
    def studio_agent(agent: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """One agent, as far as the layers someone sees of it go: its instructions only if
        they see how it's built. The same refusal for one they may not know exists as for
        one there isn't, so asking says nothing of it."""
        definition = gw.definitions.get(agent)
        with db.transaction(gw.url) as conn:
            every = studio.instances(conn)
        if definition is None or not (view := studio.layers(agent, definition, every, person,
                                                             gw.scenario)):
            raise HTTPException(404, "there's no such agent that you may see")
        watched = [i for i in every if studio.watches(i, person)]
        shown = studio.seen(gw.scenario, definition, gw.scenario.tools(), watched, view)
        with db.transaction(gw.url) as conn:  # asking for it, or the asks that wait on them
            asks.settle(conn, gw.scenario, every)
            if not asks.serving(gw.scenario, every, agent, person.id):
                mine = asks.theirs(conn, gw.scenario.name, person.id, agent)
                shown["ask"] = asks.shown(mine) if mine else None
            if waiting := [a for a in asks.waiting(conn, gw.scenario, every, person,
                                                   languages.of(person))
                           if a["agent"] == agent]:
                shown["asks"] = waiting
        return shown

    # Asking for an agent (core/asks.py): someone who knows of it asks to be served by it, and
    # the people it waits on answer it with a version of the settings, or decline it

    def known_agent(conn: Any, person: Person, agent: str) -> tuple[Any, list[dict]]:
        """An agent someone may know of, and the instances there are; refused as for one there
        isn't, if they may not."""
        definition = gw.definitions.get(agent)
        every = studio.instances(conn)
        if definition is None or not studio.layers(agent, definition, every, person, gw.scenario):
            raise HTTPException(404, "there's no such agent that you may see")
        return definition, every

    @api.post("/studio/api/agents/{agent}/ask", **shapes.answers(shapes.Ask))
    def studio_ask(agent: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """Ask to be served by an agent someone knows of: their open ask, if they have one."""
        with db.transaction(gw.url) as conn:
            _, every = known_agent(conn, person, agent)
            try:
                return asks.shown(asks.ask(conn, gw.scenario, every, person, agent))
            except asks.Refused as e:
                raise HTTPException(409, str(e)) from None

    @api.delete("/studio/api/agents/{agent}/ask", **shapes.answers(shapes.Ask))
    def studio_unask(agent: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """Withdraw someone's open ask for an agent."""
        with db.transaction(gw.url) as conn:
            mine = asks.theirs(conn, gw.scenario.name, person.id, agent)
            ended = asks.end(conn, gw.scenario.name, str(mine["id"]), "withdrawn",
                             person.id) if mine else None
        if ended is None:
            raise HTTPException(404, "you haven't asked for it")
        return asks.shown(ended)

    def waiting_on(conn: Any, person: Person, ask: str) -> dict:
        """An open ask that waits on someone, with whose it is."""
        every = studio.instances(conn)
        found = next((a for a in asks.waiting(conn, gw.scenario, every, person) if a["id"] == ask),
                     None)
        if found is None:
            raise HTTPException(404, "there's no such ask waiting on you")
        return found

    @api.post("/studio/api/asks/{ask}/decline", **shapes.answers(shapes.Ask))
    def studio_decline(ask: str, person: Annotated[Person, Depends(someone)]) -> dict:
        """Decline an ask that waits on someone."""
        with db.transaction(gw.url) as conn:
            waiting_on(conn, person, ask)
            ended = asks.end(conn, gw.scenario.name, ask, "declined", person.id)
        if ended is None:
            raise HTTPException(404, "there's no such ask waiting on you")
        return asks.shown(ended)

    @api.post("/studio/api/asks/{ask}/serve", status_code=202,
              **shapes.answers(shapes.Requested))
    def studio_serve(ask: str, body: Serve, person: Annotated[Person, Depends(someone)]) -> dict:
        """Answer an ask that waits on someone with a version of the settings that serves its
        asker through one of the agent's instances: a request, as the settings app makes, for
        the core to propose to everyone it needs, which takes effect once they approve it."""
        if not registry.approves(person):
            raise HTTPException(403, "answering an ask is for the people who approve versions of "
                                     "the settings")
        with db.transaction(gw.url) as conn:
            found = waiting_on(conn, person, ask)
            instance = next((i for i in studio.instances(conn) if i["id"] == body.instance
                             and i["definition"] == found["agent"]), None)
            if instance is None:
                raise HTTPException(404, f"there's no instance {body.instance} of the "
                                         f"{found['agent']}")
            try:
                text = settings_app.serving(conn, gw, body.instance, found["asker"])
                return settings_app.request(conn, gw, person, text, ask=ask)
            except settings_app.Refused as e:  # in words, as the studio shows them
                raise HTTPException(e.status, "; ".join(e.problems)) from None

    @api.get("/studio/api/agents/{agent}/measures", **shapes.answers(shapes.Figures))
    def studio_agent_measures(agent: str, person: Annotated[Person, Depends(studying)], days: studio.Days = 30,
                              zone: str = "UTC") -> dict:
        """How the instances of an agent that someone may watch are doing, with their runs on
        each day in `zone`, such as their own time zone."""
        with db.transaction(gw.url) as conn:
            insts = [i for i in studio.instances(conn, person, retired=True)  # as the core counts
                     if i["definition"] == agent]
            if not insts:
                raise HTTPException(404, "there's no instance of that agent that you may watch")
            try:
                return studio.figures(conn, gw.scenario, gw.models, insts, days, gw.clock(), zone)
            except studio.UnknownZone as e:
                raise HTTPException(400, str(e)) from e

    @api.get("/studio/api/instances/{instance}", **shapes.answers(shapes.Figures))
    def studio_instance(instance: str, person: Annotated[Person, Depends(studying)], days: studio.Days = 30,
                        zone: str = "UTC") -> dict:
        """How an instance someone may watch is doing, over the last `days` days, with its
        runs on each day in `zone`, such as their own time zone."""
        with db.transaction(gw.url) as conn:
            try:
                return studio.figures(conn, gw.scenario, gw.models,
                                      [watched(conn, person, instance)], days, gw.clock(), zone)
            except studio.UnknownZone as e:
                raise HTTPException(400, str(e)) from e

    def stood(conn: Any, person: Person, instance: str) -> dict:
        """An instance someone may watch, with who suspended it, if anyone did."""
        watched(conn, person, instance)
        found = conn.execute(f"select {suspension.COLUMNS} from instances where id = %s",
                             (instance,)).fetchone()
        if found is None:
            raise HTTPException(404, "there's no such instance that you may watch")
        return found

    def asked_line(found: dict | None) -> dict | None:
        if found is None:
            return None
        who = gw.scenario.person(found["person"])
        return {"action": found["action"], "by": who.name if who else found["person"],
                "at": found["asked_at"]}

    @api.get("/studio/api/instances/{instance}/standing", **shapes.answers(shapes.Standing))
    def instance_standing(instance: str, person: Annotated[Person, Depends(studying)]) -> dict:
        """How an instance stands, for someone who may watch it: what of it waits, the changes
        it asked for, for their decision and others', its samples for their grade and others',
        and its notebook, if they keep it, each where it's done (core/home.py); who suspended
        it; and whether they may suspend it or resume it from its page (core/suspension.py)."""
        with db.transaction(gw.url) as conn:
            inst = stood(conn, person, instance)
            pending = suspension.asked(conn, instance)
            waiting = homes.of_instance(conn, gw, person, inst)
        by = gw.scenario.person(inst["suspended_by"] or "")
        may = None if pending else next(
            (a for a in suspension.ACTIONS
             if suspension.may(gw.scenario, person, inst, a, gw.cfg.team) is None), None)
        return {"waiting": waiting, "may": may, "asked": asked_line(pending),
                "suspended_by": (by.name if by else inst["suspended_by"])
                if inst["status"] == "suspended" else None,
                **acting.shown(acting.suspending(person, inst, may, gw.cfg.team) if may else None)}

    @api.post("/studio/api/instances/{instance}/status", **shapes.answers(shapes.StatusAsked))
    def instance_status(instance: str, body: StatusAct,
                        person: Annotated[Person, Depends(studying)],
                        authorization: str | None = Header(default=None)) -> dict:
        """Suspend or resume an instance, signed in afresh for that act alone, which the gateway
        checks again and carries out within a minute (core/suspension.py): someone who runs it,
        owns its agent or one of its parts, or is on the team that runs a5s suspends it; whoever
        suspended it resumes it, or the release approver."""
        token = (authorization or "").removeprefix("Bearer ").strip()
        try:
            who, claims = suspension.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                           token, body.action, instance, body.salt, time.time())
            with db.transaction(gw.url) as conn:
                inst = stood(conn, who, instance)
                if suspension.asked(conn, instance):
                    raise HTTPException(409, "a5s is carrying out what was asked for it already: "
                                             "look again in a minute")
                if refused := suspension.may(gw.scenario, who, inst, body.action, gw.cfg.team):
                    raise refused
                found = suspension.record(conn, body.action, instance, who.id, token,
                                          body.salt, claims)
        except approvals.Refused as exc:
            raise web.refusal(gw, exc) from None
        return {"action": body.action, "by": who.name, "at": found["asked_at"]}

    @api.get("/studio/api/instances/{instance}/runs", **shapes.answers(shapes.RunsPage))
    def studio_runs(instance: str, person: Annotated[Person, Depends(studying)], before: str | None = None,
                    limit: int = studio.RUNS) -> dict:
        """An instance's runs that someone may see, newest first, and how many others: whom
        each acted for named only once the officer agrees."""
        with db.transaction(gw.url) as conn:
            try:
                choices = gw.data_protection(conn)
                return studio.runs(conn, gw.scenario, watched(conn, person, instance), person,
                                   before, limit, names=choices.studio_names,
                                   fewest=choices.fewest_people,
                                   key=studio.cursor_key(gw.cfg.service_token))
            except ValueError:
                raise HTTPException(400, "before is where the page before ended, as it said")

    @api.get("/studio/api/runs/{run_id}", **shapes.answers(shapes.Run))
    def studio_run(run_id: str, person: Annotated[Person, Depends(studying)]) -> dict:
        """What a run did, if someone may watch its instance and see every record it named."""
        with db.transaction(gw.url) as conn:
            choices = gw.data_protection(conn)
            found = studio.run(conn, gw.scenario, run_id, person, names=choices.studio_names)
            if found is not None and not choices.studio_names:  # one of few people's, alone
                row = conn.execute("select serves from instances where id = %s",
                                   (found["instance"],)).fetchone()
                if row and len(registry.served(gw.scenario, row["serves"])) < choices.fewest_people:
                    found = None
        if found is None:
            raise HTTPException(404, "there's no such run that you may see")
        return found

    # Making agents (core/drafts.py, docs/studio.md, step 2): drafts the studio keeps for their
    # authors, each an agent's folder, file by file, checked as `a5s agent check` checks one.
    # None is in force, nothing about one is signed, and publishing one is a pull request.

    def checked(draft: dict) -> dict:
        """A draft, what would stop its release, and, if it loads, how it would look in the
        catalogue, for its map."""
        tools = gw.scenario.tools()
        shown = {k: v for k, v in draft.items() if k not in ("base", "before")}  # a5s's own
        return {"yours": True, "author": None, **shown, "drafted_before": drafted_before(draft),
                "problems": drafts.check(draft["agent"], draft["files"], tools, gw.models),
                "preview": drafts.preview(gw.scenario, draft["agent"], draft["files"], tools),
                "signers": drafts.signers(draft["agent"], draft["files"], gw.cfg.agents_dir,
                                          gw.definitions, memberships.rooted(gw.scenario).holders),
                "publishing": publishing.configured(gw.cfg),  # or its author opens it
                **journey(draft)}

    def drafted_before(draft: dict) -> list[dict]:
        """Who drafted a draft before whoever holds it, oldest first, by name, and how it went
        on: handed over to its holder, or copied into a draft of theirs."""
        return [{"name": named(b["person"]) if b.get("person") else "someone a5s no longer names",
                 "at": b["at"], "how": b["how"]} for b in draft.get("before") or []]

    def journey(draft: dict) -> dict:
        """Where a draft is on its way to work, past publishing it: released here as it is, and
        its agent at work through an instance, running or paused."""
        with db.transaction(gw.url) as conn:
            at_work = conn.execute("select 1 from instances where definition = %s and status in "
                                   "('active', 'suspended') limit 1", (draft["agent"],)).fetchone()
        return {"released": drafts.released(draft["agent"], draft["files"], draft.get("based_on"),
                                            gw.cfg.agents_dir, gw.definitions),
                "at_work": at_work is not None,
                # a change to an agent the release here has, not a new one, for the sidebar
                # to mark Agents for, not New agent (round 17, C8)
                "changes": draft["agent"] in gw.definitions}

    def offer(person: Person) -> dict:
        """What a draft may be given, and what follows from it, for this person."""
        with db.transaction(gw.url) as conn:  # as the data protection officer's choices are read
            settings, _ = gw.settings_in_force(conn, seal=False)
            if settings is None and not gw.cfg.seal_keys:
                settings = gw.sealed_in_force(conn)
            watched = studio.instances(conn, person)
        return {"tools": studio.offered(gw.scenario.tools()), "models": sorted(gw.models),
                **studio.rules(gw.scenario, settings),
                "servable": studio.servable(gw.scenario, settings, person, [i["id"] for i in watched]),
                "askable": studio.askable(watched),
                "owed": sorted({o.source for o in gw.scenario.obligations()})}  # an agent may chase

    @api.get("/studio/api/tools", **shapes.answers(shapes.Offer))
    def studio_tools(person: Annotated[Person, Depends(drafting)]) -> dict:
        """The scenario's tools an agent may be given, each with what it reads, writes or
        changes, the models the deployment approves, and what follows from what it may do, as
        the settings in force say: who decides its changes in each part, who approves an
        instance there, and the limits; and, for a draft's plan of its first instance, whom it
        could serve and the instances it could ask, of those the person may see already."""
        return offer(person)

    def in_ledger(conn: Any, person: Person, action: str, draft: dict, **more: str) -> None:
        ledger.append(conn, {"kind": "admin", "action": action, "run": None, "instance": None,
                             "acts_for": [], "decision": "record",
                             "args": {"agent": draft["agent"], "draft": draft["id"],
                                      "based_on": draft["based_on"], "by": person.id, **more}})

    def coauthored(person: Person) -> list[str]:
        """The agents of the release someone may author: their co-authors' drafts of them
        they may read."""
        return [a for a in gw.definitions if drafts.may_author(person, a)]

    def named(pid: str) -> str:
        found = gw.scenario.person(pid)
        return found.name if found else pid

    def readable(conn: Any, person: Person, draft: str) -> dict | None:
        """One of someone's drafts, theirs to change; or a co-author's, of an agent of the
        release they may author too, to read."""
        try:
            uuid.UUID(draft)  # before asking, so a bad one doesn't spoil the transaction
        except ValueError:
            return None
        found = drafts.get(conn, person, draft)
        if found is not None:
            return {**found, "yours": True, "author": person.name}
        other = drafts.by_id(conn, draft)
        if other is None or other["agent"] not in coauthored(person):
            return None
        author = other.pop("person")
        return {**other, "yours": False, "author": named(author)}

    @api.get("/studio/api/templates", **shapes.answers(shapes.Templates))
    def studio_templates(_: Annotated[Person, Depends(drafting)]) -> dict:
        """The agents a new one may start from, and the tools each needs that this scenario
        hasn't got: none, if it fits."""
        tools = gw.scenario.tools()
        found = []
        for name, folder in authoring.templates(gw.cfg.root).items():
            definition = definitions.load(folder)
            found.append({"name": name, "works_for": definition.works_for, "does": definition.does,
                          "model": definition.model, "tools": definition.tool_names,
                          "lacks": authoring.lacks(folder, tools)})
        return {"templates": found}

    @api.get("/studio/api/drafts", **shapes.answers(shapes.Drafts))
    def studio_drafts(person: Annotated[Person, Depends(drafting)]) -> dict:
        """Someone's drafts, latest first."""
        with db.transaction(gw.url) as conn:
            return {"drafts": drafts.mine(conn, person), "theirs": [
                {**{k: v for k, v in d.items() if k != "person"}, "author": named(d["person"])}
                for d in drafts.theirs(conn, person, coauthored(person))]}

    @api.post("/studio/api/drafts", **shapes.answers(shapes.Draft))
    def studio_draft_start(body: DraftStart, person: Annotated[Person, Depends(drafting)]) -> dict:
        """A new draft: of a new agent, from a template, or of a change to an agent of the
        release, from its folder as released."""
        tools = gw.scenario.tools()
        copied: dict | None = None
        described: dict | None = None  # how a new agent's was described in words, if it was
        plan: dict = {}  # its first instance's, as a copy's draft planned it
        before: list[dict] = []  # who drafted it before them: for a copy of someone else's
        if body.copy_of and not (body.name or body.template or body.agent):
            with db.transaction(gw.url) as conn:
                copied = readable(conn, person, body.copy_of)
            if copied is None or copied["yours"]:
                raise HTTPException(404, "there's no such draft of a co-author's for you to copy")
            name, files, base = copied["agent"], copied["files"], copied.get("base")
            plan = copied.get("plan") or {}
            based_on = f"a co-author's draft, from {copied['based_on']}"
            with db.transaction(gw.url) as conn:  # who drafted it, theirs before them included
                source = drafts.by_id(conn, body.copy_of) or {}
            before = [*(source.get("before") or []),
                      {"person": source.get("person"), "at": gw.clock().isoformat(), "how": "copied"}]
        elif body.agent and not (body.name or body.template):
            if body.agent not in gw.definitions:
                raise HTTPException(404, f"there's no agent {body.agent} here")
            if not drafts.may_author(person, body.agent):
                raise HTTPException(403, f"changing {body.agent} is for its owners and the people "
                                         "the organisation names its authors")
            name, files = body.agent, drafts.folder_files(gw.cfg.agents_dir / body.agent)
            base = dict(files)  # as released: what a publish merges against what's merged since
            with db.transaction(gw.url) as conn:  # without cases whose words were erased since
                files = run_cases.cleared(conn, files)
            based_on = f"{body.agent} {gw.definitions[body.agent].release_id}"
        elif body.name and body.describe and not (body.template or body.agent):
            if not drafts.may_author(person, None, gw.cfg.team):
                raise HTTPException(403, "a new agent is for the people who own one, and engineers")
            if body.name in gw.definitions:
                raise HTTPException(409, f"there's an agent {body.name} already: draft a change "
                                         "to it instead")
            words = body.describe.strip()[:describing.WORDS]
            with tempfile.TemporaryDirectory() as there:  # from the blank start, on its own model
                try:  # its name, and room for it, checked before any model is asked
                    made = authoring.new(authoring.templates(gw.cfg.root)[authoring.BLANK], body.name,
                                         Path(there), tools, model=next(iter(gw.models), None))
                except ValueError as e:
                    raise HTTPException(400, str(e)) from None
                blank = drafts.folder_files(made)
            with db.transaction(gw.url) as conn:
                try:
                    drafts.room(conn, person, body.name)
                except drafts.Refused as e:
                    raise HTTPException(409, str(e)) from None
            asked = body.model or STAND_IN
            with trying(person, asked) as spent:
                try:
                    said = sandboxed("/sandbox/descriptions", {"words": words, "model": asked})
                    spent["tokens"] = said.get("tokens")
                finally:  # the words went to the model whatever comes of them: the ledger says so
                    with db.transaction(gw.url) as conn:
                        ledger.append(conn, {"kind": "admin", "action": "describe", "run": None,
                                             "instance": None, "acts_for": [], "decision": "record",
                                             "args": {"agent": body.name, "model": asked,
                                                      "by": person.id,
                                                      "words_sha256": ledger.digest(words)}})
            proposed = found if isinstance(found := said.get("proposal"), dict) else {}
            owed = sorted({o.source for o in gw.scenario.obligations()})
            files, notes = describing.drafted(blank, body.name, proposed, tools, owed)
            files = drafts.pinned(body.name, files, tools)  # what it was given, as the scenario has it
            name, base, based_on = body.name, {}, f"a description, on {said.get('model')}"
            described = {"words": words, "model": str(said.get("model")), "notes": notes}
        elif body.name and body.template and not body.agent:
            if not drafts.may_author(person, None, gw.cfg.team):
                raise HTTPException(403, "a new agent is for the people who own one, and engineers")
            if body.name in gw.definitions:
                raise HTTPException(409, f"there's an agent {body.name} already: draft a change "
                                         "to it instead")
            template = authoring.templates(gw.cfg.root).get(body.template)
            if template is None:
                raise HTTPException(404, f"there's no template {body.template}")
            with tempfile.TemporaryDirectory() as there:
                try:
                    made = authoring.new(template, body.name, Path(there), tools, model=(  # its own
                        next(iter(gw.models), None) if body.template == authoring.BLANK else None))
                except ValueError as e:
                    raise HTTPException(400, str(e)) from None
                name, files = body.name, drafts.folder_files(made)
            base = {}  # a new agent's: nothing of it anywhere yet
            based_on = f"template {body.template}"
        else:
            raise HTTPException(400, "name a new agent and the template it starts from, or what "
                                     "it's for in your words; an agent of the release to change; "
                                     "or a co-author's draft to copy")
        with db.transaction(gw.url) as conn:
            try:
                draft = drafts.start(conn, person, name, based_on, files, base, before, plan, described)
            except drafts.Refused as e:
                raise HTTPException(409, str(e)) from None
            if copied is not None:
                in_ledger(conn, person, "copy draft", draft, copied=copied["id"])
            elif described is not None:  # who described it, on which model, and what it gave it
                in_ledger(conn, person, "describe draft", draft, model=described["model"],
                          given=", ".join(n["what"] for n in described["notes"] if n["given"]))
            else:
                in_ledger(conn, person, "draft", draft)
        return checked(draft)

    @api.get("/studio/api/drafts/{draft}", **shapes.answers(shapes.Draft))
    def studio_draft(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """One of someone's drafts, or a co-author's, to read: its files, and what would stop
        its release."""
        with db.transaction(gw.url) as conn:
            found = readable(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        return checked(found)

    @api.get("/studio/api/drafts/{draft}/co-authors", **shapes.answers(shapes.CoAuthors))
    def studio_draft_co_authors(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """Whom someone may hand one of their drafts over to: those who may author its agent
        too, as the directory and their latest sign-ins' groups have it, with none of it."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
            if found is None:
                raise HTTPException(404, "you have no such draft")
            agent = found["agent"]
            roles = ([agent_owner(agent), drafts.agent_author(agent)] if agent in gw.definitions
                     else [agent_owner(a) for a in gw.definitions])
            holders = {h["id"]: h["name"] for row in administration.held(gw.scenario, conn, roles)
                       for h in row["held_by"]}
            if agent not in gw.definitions:  # a new agent's, which the engineers may make too
                holders.update({p.id: p.name for p in gw.scenario.team(gw.cfg.team)})
            busy = {r["person"] for r in conn.execute(
                "select person from agent_drafts where agent = %s", (agent,))}
        return {"people": [{"id": pid, "name": name} for pid, name
                           in sorted(holders.items(), key=lambda h: h[1])
                           if pid != person.id and pid not in busy]}

    @api.post("/studio/api/drafts/{draft}/hand-over", **shapes.answers(shapes.HandedOver))
    def studio_draft_hand_over(draft: str, body: HandOver,
                               person: Annotated[Person, Depends(drafting)]) -> dict:
        """Hand one of someone's drafts over to a co-author, who may author its agent too: it's
        theirs to change, and publish, then."""
        taker = gw.scenario.person(body.to)
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
            if found is None:
                raise HTTPException(404, "you have no such draft")
            agent = found["agent"]
            if taker is None or taker.id == person.id or not drafts.may_author(
                    taker, agent if agent in gw.definitions else None, gw.cfg.team):
                raise HTTPException(400, f"{named(body.to)} may not author the {agent}")
            if len(drafts.mine(conn, taker)) >= drafts.MOST_DRAFTS:
                raise HTTPException(409, f"{taker.name} keeps {drafts.MOST_DRAFTS} drafts already")
            handed = drafts.hand_over(conn, person, draft, taker.id)
            if handed is None:
                raise HTTPException(409, f"{taker.name} has a draft of the {agent} already")
            in_ledger(conn, person, "hand over draft", handed, to=taker.id)
        return {"handed": handed["id"], "to": taker.name}

    @api.put("/studio/api/drafts/{draft}", **shapes.answers(shapes.Draft))
    def studio_draft_save(draft: str, body: DraftFiles,
                          person: Annotated[Person, Depends(drafting)]) -> dict:
        """Keep a draft's files as they are now, its tools pinned as the scenario has them, as
        `a5s pin` pins them, and say what would stop its release."""
        if problems := drafts.shape(body.files):
            raise HTTPException(400, "; ".join(problems))
        plan = body.plan.model_dump() if body.plan is not None else None
        if plan is not None and (wrong := studio.plan_problems(plan, offer(person))):
            raise HTTPException(400, "its plan: " + "; ".join(wrong))
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
            if found is None:
                raise HTTPException(404, "you have no such draft")
            files = drafts.pinned(found["agent"], {path: text for path, text in body.files.items()
                                                   if path != "tools.lock"}, gw.scenario.tools())
            files = run_cases.kept_since(conn, found["files"], files, body.loaded)  # none lost
            saved = drafts.save(conn, person, draft, files, plan)
        if saved is None:  # let go meanwhile, as from another tab
            raise HTTPException(404, "you have no such draft")
        return checked(saved)

    @api.delete("/studio/api/drafts/{draft}", **shapes.answers(shapes.Dropped))
    def studio_draft_drop(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """Let one of someone's drafts go."""
        with db.transaction(gw.url) as conn:
            gone = drafts.drop(conn, person, draft)
            if gone is not None:
                in_ledger(conn, person, "drop draft", gone)
        if gone is None:
            raise HTTPException(404, "you have no such draft")
        return {"dropped": gone["id"]}

    # Trying a draft in the sandbox, a deployment of its own (a5s/sandbox.py): the draft's
    # files go there, with who to be of its made-up people and what to say, and what came of
    # it comes back. Nothing of this deployment's goes, nor comes back to be kept

    def sandboxed(path: str, body: dict | None = None) -> dict:
        if not gw.cfg.sandbox_url:
            raise HTTPException(503, "there's no sandbox here to try drafts in: the team that "
                                     "runs a5s sets one up (A5S_SANDBOX_URL)")
        try:
            answer = httpx.request("GET" if body is None else "POST", f"{gw.cfg.sandbox_url}{path}",
                                   json=body, timeout=30 if body is None else 300,
                                   headers={"Authorization": f"Bearer {gw.cfg.sandbox_token}"})
        except (httpx.ConnectError, httpx.ConnectTimeout):  # it never had it
            raise Spent(502, "the sandbox didn't answer: try again in a moment", 0) from None
        except httpx.HTTPError:  # it may have worked on it all the same, for all a5s knows
            raise Spent(502, "the sandbox didn't answer: try again in a moment", None) from None
        try:
            said = answer.json()
        except ValueError:
            said = None
        if not isinstance(said, dict):
            raise Spent(502, f"the sandbox said {answer.status_code}", None)
        if answer.status_code in (400, 429):  # why not, with what it took before it knew
            tokens = said.get("tokens")
            raise Spent(answer.status_code, str(said.get("detail")),
                        int(tokens) if isinstance(tokens, int) and tokens > 0 else 0)
        if answer.status_code != 200:
            raise Spent(502, f"the sandbox said {answer.status_code}", None)
        return said

    in_sandbox: set[str] = set()  # whose tries are in the sandbox now, one each
    gate = threading.Lock()

    @contextmanager
    def trying(person: Person, model: str | None) -> Iterator[dict]:
        """Someone's try in the sandbox, once theirs before has ended, and while few others'
        are under way, so tries hold few of the threads this app's chats are answered on, and
        nobody's tries sent at once pass a day's tokens many times over: refused, until then.
        What it took on a real model, which the work in it says as `tokens`, counts towards
        their day however it ends: as much as the sandbox says, or, where it can't say, such
        as when it didn't answer in time, SANDBOX_UNSAID."""
        with gate:
            if person.id in in_sandbox:
                raise HTTPException(429, "you have a try in the sandbox already: wait for it to "
                                         "end, then try again")
            if len(in_sandbox) >= SANDBOX_AT_ONCE:
                raise HTTPException(429, "the sandbox is busy with others' tries: try again in a "
                                         "minute")
            in_sandbox.add(person.id)
        try:
            affordable(person, model)
            spent: dict = {"tokens": 0}
            try:
                yield spent
            except Spent as e:
                spent["tokens"] = e.tokens
                raise
            finally:
                n = spent["tokens"]
                with db.transaction(gw.url) as conn:
                    took(conn, person, model, SANDBOX_UNSAID if n is None else n)
        finally:
            with gate:
                in_sandbox.discard(person.id)

    def affordable(person: Person, model: str | None) -> None:
        """Refuse a try on a real model once someone's tries in the sandbox have taken a day's
        tokens: each case runs there as an instance of its own, whose own budget for a person's
        day starts afresh, and a judge's calls count towards none. The stand-in costs nothing."""
        if (model or STAND_IN) == STAND_IN:
            return
        with db.transaction(gw.url) as conn:
            day = budgets.day_of(gw.scenario, person.id, gw.clock())
            row = conn.execute("select tokens from sandbox_spend where person = %s and day = %s",
                               (person.id, day)).fetchone()
        if row and int(row["tokens"]) >= SANDBOX_DAY:
            raise HTTPException(429, SANDBOX_SPENT.format(n=f"{SANDBOX_DAY:,}"))

    def took(conn: Any, person: Person, model: str | None, tokens: Any) -> None:
        """Count what a try took on a real model towards someone's day in the sandbox."""
        n = int(tokens or 0) if isinstance(tokens, int | float) else 0
        if (model or STAND_IN) == STAND_IN or n <= 0:
            return
        conn.execute("insert into sandbox_spend (person, day, tokens) values (%s, %s, %s) "
                     "on conflict (person, day) do update set tokens = sandbox_spend.tokens + "
                     "excluded.tokens", (person.id, budgets.day_of(gw.scenario, person.id,
                                                                   gw.clock()), n))

    @api.get("/studio/api/sandbox", **shapes.answers(shapes.Sandbox))
    def studio_sandbox(_: Annotated[Person, Depends(drafting)]) -> dict:
        """Whom a draft may be tried as in the sandbox, of its made-up people, and on which
        models, with the currency models.yaml prices them in, if it names one."""
        return {**sandboxed("/sandbox"), "currency": gw.currency}

    @api.post("/studio/api/drafts/{draft}/try", **shapes.answers(shapes.Tried))
    def studio_draft_try(draft: str, body: DraftTry,
                         person: Annotated[Person, Depends(drafting)]) -> dict:
        """Say something to one of someone's drafts in the sandbox, as one of its made-up
        people: what it answered, each call it made with the policy's decision, and what the
        model was sent and said."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        with trying(person, body.model) as spent:
            said = sandboxed("/sandbox/tries", {"key": found["id"].replace("-", "")[:12],
                                                "files": found["files"], "person": body.person,
                                                "text": body.text, "model": body.model})
            spent["tokens"] = said.get("tokens")
        with db.transaction(gw.url) as conn:
            ledger.append(conn, {"kind": "admin", "action": "try draft", "run": None,
                                 "instance": None, "acts_for": [], "decision": "record",
                                 "args": {"agent": found["agent"], "draft": found["id"],
                                          "as": body.person, "model": body.model,
                                          "by": person.id}})
        return said

    @api.get("/studio/api/drafts/{draft}/cases", **shapes.answers(shapes.Cases))
    def studio_draft_cases(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """One of someone's drafts' test cases, as its suite runs them, and of each, what only
        the suite does, if anything, which the sandbox doesn't."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        try:
            listed = cases.found(found["files"])
        except cases.Unreadable as e:
            return {"cases": [], "problem": str(e)}
        return {"cases": [{"number": n, "name": case["name"], "file": case["file"],
                           "suite_alone": cases.suite_alone(case)}
                          for n, case in enumerate(listed)]}

    @api.post("/studio/api/drafts/{draft}/cases/{number}", **shapes.answers(shapes.CaseRan))
    def studio_draft_case(draft: str, number: int, body: CaseRun,
                          person: Annotated[Person, Depends(drafting)]) -> dict:
        """Run one of someone's drafts' test cases in the sandbox, on the scenario's made-up
        records: what it answered at each step, the tools it used, and whether that's as the
        case says."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
            settings, _ = gw.settings_in_force(conn, seal=False)
            if settings is None and not gw.cfg.seal_keys:
                settings = gw.sealed_in_force(conn)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        # A case kept from a real run goes only to a model approved for the deployment's data
        classes = sorted({settings.data_class, *settings.classified.values()}) if settings \
            else [cases.UNKNOWN]  # while they can't be read: none a model is approved for
        with trying(person, body.model) as spent:
            ran = sandboxed("/sandbox/cases", {"key": found["id"].replace("-", "")[:12],
                                               "files": found["files"], "number": number,
                                               "model": body.model, "classes": classes})
            spent["tokens"] = (int(ran.get("tokens") or 0)  # the case's runs, and its judge's
                               + int(ran.get("judge_tokens") or 0))
        with db.transaction(gw.url) as conn:
            ledger.append(conn, {"kind": "admin", "action": "run draft case", "run": None,
                                 "instance": None, "acts_for": [], "decision": "record",
                                 "args": {"agent": found["agent"], "draft": found["id"],
                                          "case": ran.get("name"), "model": body.model,
                                          "passed": ran.get("passed"), "by": person.id}})
        return ran

    # Publishing a draft (core/publishing.py): a pull request to the agents' repository, opened
    # as its author, once they let a5s's GitHub App act as them at GitHub's own sign-in. The
    # token GitHub gives is used for that publish alone, in this app's memory, and kept nowhere.
    # Where publishing isn't set up, its author downloads its folder instead

    publishes = publishing.Publishing(gw.cfg)

    @api.post("/studio/api/drafts/{draft}/publish", **shapes.answers(shapes.Publish))
    def studio_draft_publish(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """Start publishing one of someone's drafts: the code they enter at GitHub's sign-in,
        to let a5s publish it as them, and where to enter it."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        if not publishing.configured(gw.cfg):
            raise HTTPException(503, "publishing isn't set up here: download its folder, and open "
                                     "a pull request with it yourself. The team that runs a5s sets "
                                     "up a5s's GitHub App for it (A5S_GITHUB_CLIENT_ID and "
                                     "A5S_GITHUB_REPO)")
        new = found["agent"] not in gw.definitions
        if not drafts.may_author(person, None if new else found["agent"], gw.cfg.team):
            raise HTTPException(403, f"publishing {found['agent']} is for its owners and the "
                                     "people the organisation names its authors")
        shown = checked(found)
        if shown["problems"]:
            raise HTTPException(409, "put right what would stop its release first: "
                                     + "; ".join(shown["problems"]))
        title, body, message = publishing.described(found, person, shown["signers"] or [], new,
                                                     drafted=shown["drafted_before"])
        try:
            return publishes.start(person.id, found, title, body, message).shown()
        except publishing.Refused as e:
            raise HTTPException(502, str(e)) from None

    @api.get("/studio/api/publishes/{publish}", **shapes.answers(shapes.Publish))
    def studio_publish(publish: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """How a publish of someone's stands: waiting for them at GitHub's sign-in, its pull
        request once it's open, or why it isn't."""
        try:
            found, opened = publishes.poll(person.id, publish)
        except KeyError:
            raise HTTPException(404, "you have no such publish under way") from None
        if opened and found.pull:  # opened, so its pull request is there
            with db.transaction(gw.url) as conn:
                drafts.published(conn, person, found.draft, found.pull)
                ledger.append(conn, {"kind": "admin", "action": "publish draft", "run": None,
                                     "instance": None, "acts_for": [], "decision": "record",
                                     "args": {"agent": found.agent, "draft": found.draft,
                                              "based_on": found.based_on, "pull": found.pull,
                                              "by": person.id}})
        return found.shown()

    @api.get("/studio/api/drafts/{draft}/pull-request", **shapes.answers(shapes.PullRequest))
    def studio_draft_pull_request(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """The pull request one of someone's drafts makes, for them to open it with on any git
        host: where its folder goes in the agents' repository, its title, and its description,
        which says who must sign its release, and why."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        new = found["agent"] not in gw.definitions
        shown = checked(found)
        title, body, _ = publishing.described(found, person, shown["signers"] or [], new,
                                              shown["problems"], drafted=shown["drafted_before"])
        return {"folder": publishing.folder(gw.cfg, found["agent"]), "title": title, "body": body,
                "ready": not shown["problems"]}

    @api.get("/studio/api/drafts/{draft}/folder")
    def studio_draft_folder(draft: str, person: Annotated[Person, Depends(drafting)]) -> Response:
        """One of someone's drafts, as its agent's folder in a zip, to open a pull request with
        themselves."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        return Response(drafts.zipped(found), media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{found["agent"]}.zip"'})

    pages.include_router(api)
    return pages


def described() -> dict:
    """The studio API's own description, its OpenAPI document: what each route takes and
    answers, with no deployment behind it."""
    app = FastAPI(title="a5s studio")
    app.include_router(router(SimpleNamespace(cfg=None)))  # nothing it serves is asked
    app.include_router(settings_api.router(SimpleNamespace(cfg=None)))  # the settings, folded in
    app.include_router(notebook_api.router(SimpleNamespace(cfg=None)))  # and the notebook
    app.include_router(tasks_api.router(SimpleNamespace(cfg=None)))  # and people's tasks
    app.include_router(admin_api.router(SimpleNamespace(cfg=None)))  # and the administrators' page
    app.include_router(audit_api.router(SimpleNamespace(cfg=None)))  # and the audit trail
    app.include_router(decide_api.router(SimpleNamespace(cfg=None)))  # and deciding held changes
    app.include_router(grade_api.router(SimpleNamespace(cfg=None)))  # and grading samples
    app.include_router(health_api.router(SimpleNamespace(cfg=None)))  # and the model health
    app.include_router(status_api.router(SimpleNamespace(cfg=None)))  # and the Status page
    app.include_router(officer_api.router(SimpleNamespace(cfg=None)))  # and the officer's requests
    app.include_router(approve_api.router(SimpleNamespace(cfg=None)))  # and approving settings
    app.include_router(shell_api.router(SimpleNamespace(cfg=None)))  # and every page's sidebar
    app.include_router(shell_api.environment_router(SimpleNamespace(cfg=None)))  # and its band
    return app.openapi()


if __name__ == "__main__":  # uv run python -m a5s.core.studio_api > studio/src/api.gen.ts
    print(typescript.types(described()), end="")
