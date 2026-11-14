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
import uuid
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from a5s import authoring, cases, db, definitions
from a5s.contract import Person
from a5s.core import administration, drafts, ledger, memberships, publishing, studio, web
from a5s.core import home as homes  # the studio's home: `home` is the site's
from a5s.core.releases import ENGINEER, agent_owner

STUDIO = web.WEBCHAT / "studio"  # as `npm run build` in studio/ builds it, which the image does
STUDIO_UNBUILT = ("The studio isn't built here. Build it from the repository with "
                  "`npm ci --prefix studio && npm run build --prefix studio`, as the image does.")
_ASSET = re.compile(r"[\w-]+\.(js|css)")  # its own files, by name alone: nothing else


class DraftStart(BaseModel):
    """A new draft: a new agent's name and the template it starts from, an agent of the
    release to change, or a co-author's draft to copy."""

    name: str | None = None
    template: str | None = None
    agent: str | None = None
    copy_of: str | None = None  # a co-author's draft


class HandOver(BaseModel):
    """Whom to hand one's draft over to: someone who may author its agent too."""

    to: str


class DraftFiles(BaseModel):
    """A draft's agent's folder: each file's text, by its path in it."""

    files: dict[str, str]


class DraftTry(BaseModel):
    """Trying a draft in the sandbox: who to be, of its made-up people, what to say, and on
    which of the models it offers."""

    person: str
    text: str
    model: str = "stand-in"


class CaseRun(BaseModel):
    """Running one of a draft's test cases in the sandbox: on which of the models it offers."""

    model: str = "stand-in"


def may_study(gw: Any, person: Person) -> bool:
    """Whether someone may use the studio's catalogue and dashboards: they may watch an
    instance, own an agent, or make agents."""
    with db.transaction(gw.url) as conn:
        theirs = studio.instances(conn, person)
    return (bool(theirs) or any(r.startswith("agent-owner:") for r in person.roles)
            or drafts.authors(person))


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
            raise HTTPException(403, "the studio is for the people who run an instance, own an "
                                     "agent, own or decide for one of its parts, approve "
                                     "instances, or make agents")
        return person

    def drafting(person: Annotated[Person, Depends(someone)]) -> Person:
        """Who signed in to make agents: an agent's owner or named author, or an engineer."""
        if not drafts.authors(person):
            raise HTTPException(403, "making agents is for their owners, the people the "
                                     "organisation names their authors, and engineers")
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
    def studio_view(name: str) -> Response:
        """The studio, at the address of one of its agents, instances, runs or drafts."""
        return built("index.html")

    @pages.get("/studio/new", include_in_schema=False)
    @pages.get("/studio/agents", include_in_schema=False)
    @pages.get("/studio/you", include_in_schema=False)
    def studio_new() -> Response:
        """The studio, where someone starts a new agent, sees all the agents they may, or what
        they may do."""
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

    @api.get("/studio/api/home")
    def studio_home(person: Annotated[Person, Depends(someone)]) -> dict:
        """What waits for whoever signed in, their drafts, and what of the studio they may
        use, whether or not they hold a role."""
        with db.transaction(gw.url) as conn:
            watched = studio.instances(conn, person)
            return {"you": person.name, "waiting": homes.waiting(conn, gw, person),
                    "drafts": drafts.mine(conn, person),
                    "catalogue": bool(watched) or any(r.startswith("agent-owner:")
                                                      for r in person.roles)
                    or drafts.authors(person),
                    "authoring": drafts.authors(person)}

    @api.get("/studio/api/you")
    def studio_you(person: Annotated[Person, Depends(someone)]) -> dict:
        """Each role whoever signed in holds, what gave it them, the directory or a group of
        the identity provider's, and what it lets them do; and the groups their sign-in
        showed, of those the settings name."""
        with db.transaction(gw.url) as conn:
            return {"you": person.name, "id": person.id, "roles": homes.roles(conn, gw, person),
                    "groups": list(memberships.stored(conn, person.id).get(person.id, ()))}

    @api.get("/studio/api")
    def studio_now(person: Annotated[Person, Depends(studying)]) -> dict:
        """The agents someone may watch, and where each runs: the instances they may watch."""
        with db.transaction(gw.url) as conn:
            return {"you": person.name, "agents": studio.catalogue(
                conn, gw.scenario, gw.definitions, gw.scenario.tools(), person),
                    "authoring": {"new": drafts.may_author(person, None),  # what they may make
                                  "agents": sorted(a for a in gw.definitions
                                                   if drafts.may_author(person, a))}}

    @api.get("/studio/api/agents/{agent}")
    def studio_agent(agent: str, person: Annotated[Person, Depends(studying)]) -> dict:
        """One agent someone owns, or watches an instance of, with its instructions."""
        definition = gw.definitions.get(agent)
        with db.transaction(gw.url) as conn:
            insts = studio.instances(conn, person)
        if definition is None or (not {agent_owner(agent), drafts.agent_author(agent)} & set(person.roles)
                                  and not any(i["definition"] == agent for i in insts)):
            raise HTTPException(404, "there's no such agent that you may watch")
        return studio.agent(gw.scenario, definition, gw.scenario.tools(), insts, whole=True)

    @api.get("/studio/api/agents/{agent}/measures")
    def studio_agent_measures(agent: str, person: Annotated[Person, Depends(studying)], days: int = 30,
                              zone: str = "UTC") -> dict:
        """How the instances of an agent that someone may watch are doing, with their runs on
        each day in `zone`, such as their own time zone."""
        with db.transaction(gw.url) as conn:
            insts = [i for i in studio.instances(conn, person) if i["definition"] == agent]
            if not insts:
                raise HTTPException(404, "there's no instance of that agent that you may watch")
            try:
                return studio.figures(conn, gw.scenario, gw.models, insts, days, gw.clock(), zone)
            except studio.UnknownZone as e:
                raise HTTPException(400, str(e)) from e

    @api.get("/studio/api/instances/{instance}")
    def studio_instance(instance: str, person: Annotated[Person, Depends(studying)], days: int = 30,
                        zone: str = "UTC") -> dict:
        """How an instance someone may watch is doing, over the last `days` days, with its
        runs on each day in `zone`, such as their own time zone."""
        with db.transaction(gw.url) as conn:
            try:
                return studio.figures(conn, gw.scenario, gw.models,
                                      [watched(conn, person, instance)], days, gw.clock(), zone)
            except studio.UnknownZone as e:
                raise HTTPException(400, str(e)) from e

    @api.get("/studio/api/instances/{instance}/runs")
    def studio_runs(instance: str, person: Annotated[Person, Depends(studying)], before: str | None = None,
                    limit: int = studio.RUNS) -> dict:
        """An instance's runs that someone may see, newest first, and how many others: whom
        each acted for named only once the officer agrees."""
        with db.transaction(gw.url) as conn:
            try:
                return studio.runs(conn, gw.scenario, watched(conn, person, instance), person,
                                   before, limit, names=gw.data_protection(conn).studio_names)
            except ValueError:
                raise HTTPException(400, "before is where the page before ended, as it said")

    @api.get("/studio/api/runs/{run_id}")
    def studio_run(run_id: str, person: Annotated[Person, Depends(studying)]) -> dict:
        """What a run did, if someone may watch its instance and see every record it named."""
        with db.transaction(gw.url) as conn:
            found = studio.run(conn, gw.scenario, run_id, person,
                               names=gw.data_protection(conn).studio_names)
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
        return {"yours": True, "author": None, **draft,
                "problems": drafts.check(draft["agent"], draft["files"], tools, gw.models),
                "preview": drafts.preview(gw.scenario, draft["agent"], draft["files"], tools),
                "signers": drafts.signers(draft["agent"], draft["files"], gw.cfg.agents_dir,
                                          gw.definitions),
                "publishing": publishing.configured(gw.cfg)}  # or its author opens it

    @api.get("/studio/api/tools")
    def studio_tools(_: Annotated[Person, Depends(drafting)]) -> dict:
        """The scenario's tools an agent may be given, each with what it reads, writes or
        changes, and the models the deployment approves."""
        return {"tools": studio.offered(gw.scenario.tools()), "models": sorted(gw.models)}

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

    @api.get("/studio/api/templates")
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

    @api.get("/studio/api/drafts")
    def studio_drafts(person: Annotated[Person, Depends(drafting)]) -> dict:
        """Someone's drafts, latest first."""
        with db.transaction(gw.url) as conn:
            return {"drafts": drafts.mine(conn, person), "theirs": [
                {**{k: v for k, v in d.items() if k != "person"}, "author": named(d["person"])}
                for d in drafts.theirs(conn, person, coauthored(person))]}

    @api.post("/studio/api/drafts")
    def studio_draft_start(body: DraftStart, person: Annotated[Person, Depends(drafting)]) -> dict:
        """A new draft: of a new agent, from a template, or of a change to an agent of the
        release, from its folder as released."""
        tools = gw.scenario.tools()
        copied: dict | None = None
        if body.copy_of and not (body.name or body.template or body.agent):
            with db.transaction(gw.url) as conn:
                copied = readable(conn, person, body.copy_of)
            if copied is None or copied["yours"]:
                raise HTTPException(404, "there's no such draft of a co-author's for you to copy")
            name, files = copied["agent"], copied["files"]
            based_on = f"a co-author's draft, from {copied['based_on']}"
        elif body.agent and not (body.name or body.template):
            if body.agent not in gw.definitions:
                raise HTTPException(404, f"there's no agent {body.agent} here")
            if not drafts.may_author(person, body.agent):
                raise HTTPException(403, f"changing {body.agent} is for its owners and the people "
                                         "the organisation names its authors")
            name, files = body.agent, drafts.folder_files(gw.cfg.agents_dir / body.agent)
            based_on = f"{body.agent} {gw.definitions[body.agent].release_id}"
        elif body.name and body.template and not body.agent:
            if not drafts.may_author(person, None):
                raise HTTPException(403, "a new agent is for the people who own one, and engineers")
            if body.name in gw.definitions:
                raise HTTPException(409, f"there's an agent {body.name} already: draft a change "
                                         "to it instead")
            template = authoring.templates(gw.cfg.root).get(body.template)
            if template is None:
                raise HTTPException(404, f"there's no template {body.template}")
            with tempfile.TemporaryDirectory() as there:
                try:
                    made = authoring.new(template, body.name, Path(there), tools)
                except ValueError as e:
                    raise HTTPException(400, str(e)) from None
                name, files = body.name, drafts.folder_files(made)
            based_on = f"template {body.template}"
        else:
            raise HTTPException(400, "name a new agent and the template it starts from, an agent "
                                     "of the release to change, or a co-author's draft to copy")
        with db.transaction(gw.url) as conn:
            try:
                draft = drafts.start(conn, person, name, based_on, files)
            except drafts.Refused as e:
                raise HTTPException(409, str(e)) from None
            if copied is not None:
                in_ledger(conn, person, "copy draft", draft, copied=copied["id"])
            else:
                in_ledger(conn, person, "draft", draft)
        return checked(draft)

    @api.get("/studio/api/drafts/{draft}")
    def studio_draft(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """One of someone's drafts, or a co-author's, to read: its files, and what would stop
        its release."""
        with db.transaction(gw.url) as conn:
            found = readable(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        return checked(found)

    @api.get("/studio/api/drafts/{draft}/co-authors")
    def studio_draft_co_authors(draft: str, person: Annotated[Person, Depends(drafting)]) -> dict:
        """Whom someone may hand one of their drafts over to: those who may author its agent
        too, as the directory and their latest sign-ins' groups have it, with none of it."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
            if found is None:
                raise HTTPException(404, "you have no such draft")
            agent = found["agent"]
            roles = ([agent_owner(agent), drafts.agent_author(agent)] if agent in gw.definitions
                     else [ENGINEER] + [agent_owner(a) for a in gw.definitions])
            holders = {h["id"]: h["name"] for row in administration.held(gw.scenario, conn, roles)
                       for h in row["held_by"]}
            busy = {r["person"] for r in conn.execute(
                "select person from agent_drafts where agent = %s", (agent,))}
        return {"people": [{"id": pid, "name": name} for pid, name
                           in sorted(holders.items(), key=lambda h: h[1])
                           if pid != person.id and pid not in busy]}

    @api.post("/studio/api/drafts/{draft}/hand-over")
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
                    taker, agent if agent in gw.definitions else None):
                raise HTTPException(400, f"{named(body.to)} may not author the {agent}")
            if len(drafts.mine(conn, taker)) >= drafts.MOST_DRAFTS:
                raise HTTPException(409, f"{taker.name} keeps {drafts.MOST_DRAFTS} drafts already")
            handed = drafts.hand_over(conn, person, draft, taker.id)
            if handed is None:
                raise HTTPException(409, f"{taker.name} has a draft of the {agent} already")
            in_ledger(conn, person, "hand over draft", handed, to=taker.id)
        return {"handed": handed["id"], "to": taker.name}

    @api.put("/studio/api/drafts/{draft}")
    def studio_draft_save(draft: str, body: DraftFiles,
                          person: Annotated[Person, Depends(drafting)]) -> dict:
        """Keep a draft's files as they are now, its tools pinned as the scenario has them, as
        `a5s pin` pins them, and say what would stop its release."""
        if problems := drafts.shape(body.files):
            raise HTTPException(400, "; ".join(problems))
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
            if found is None:
                raise HTTPException(404, "you have no such draft")
            files = drafts.pinned(found["agent"], {path: text for path, text in body.files.items()
                                                   if path != "tools.lock"}, gw.scenario.tools())
            saved = drafts.save(conn, person, draft, files)
        if saved is None:  # let go meanwhile, as from another tab
            raise HTTPException(404, "you have no such draft")
        return checked(saved)

    @api.delete("/studio/api/drafts/{draft}")
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
                                   json=body, timeout=300,
                                   headers={"Authorization": f"Bearer {gw.cfg.sandbox_token}"})
        except httpx.HTTPError:
            raise HTTPException(502, "the sandbox didn't answer: try again in a moment") from None
        if answer.status_code == 400:
            raise HTTPException(400, str(answer.json().get("detail")))
        if answer.status_code != 200:
            raise HTTPException(502, f"the sandbox said {answer.status_code}")
        return answer.json()

    @api.get("/studio/api/sandbox")
    def studio_sandbox(_: Annotated[Person, Depends(drafting)]) -> dict:
        """Whom a draft may be tried as in the sandbox, of its made-up people, and on which
        models."""
        return sandboxed("/sandbox")

    @api.post("/studio/api/drafts/{draft}/try")
    def studio_draft_try(draft: str, body: DraftTry,
                         person: Annotated[Person, Depends(drafting)]) -> dict:
        """Say something to one of someone's drafts in the sandbox, as one of its made-up
        people: what it answered, each call it made with the policy's decision, and what the
        model was sent and said."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        said = sandboxed("/sandbox/tries", {"key": found["id"].replace("-", "")[:12],
                                            "files": found["files"], "person": body.person,
                                            "text": body.text, "model": body.model})
        with db.transaction(gw.url) as conn:
            ledger.append(conn, {"kind": "admin", "action": "try draft", "run": None,
                                 "instance": None, "acts_for": [], "decision": "record",
                                 "args": {"agent": found["agent"], "draft": found["id"],
                                          "as": body.person, "model": body.model,
                                          "by": person.id}})
        return said

    @api.get("/studio/api/drafts/{draft}/cases")
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

    @api.post("/studio/api/drafts/{draft}/cases/{number}")
    def studio_draft_case(draft: str, number: int, body: CaseRun,
                          person: Annotated[Person, Depends(drafting)]) -> dict:
        """Run one of someone's drafts' test cases in the sandbox, on the scenario's made-up
        records: what it answered at each step, the tools it used, and whether that's as the
        case says."""
        with db.transaction(gw.url) as conn:
            found = drafts.get(conn, person, draft)
        if found is None:
            raise HTTPException(404, "you have no such draft")
        ran = sandboxed("/sandbox/cases", {"key": found["id"].replace("-", "")[:12],
                                           "files": found["files"], "number": number,
                                           "model": body.model})
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

    @api.post("/studio/api/drafts/{draft}/publish")
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
        if not drafts.may_author(person, None if new else found["agent"]):
            raise HTTPException(403, f"publishing {found['agent']} is for its owners and the "
                                     "people the organisation names its authors")
        shown = checked(found)
        if shown["problems"]:
            raise HTTPException(409, "put right what would stop its release first: "
                                     + "; ".join(shown["problems"]))
        title, body, message = publishing.described(found, person, shown["signers"] or [], new)
        try:
            return publishes.start(person.id, found, title, body, message).shown()
        except publishing.Refused as e:
            raise HTTPException(502, str(e)) from None

    @api.get("/studio/api/publishes/{publish}")
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

    @api.get("/studio/api/drafts/{draft}/pull-request")
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
                                              shown["problems"])
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
