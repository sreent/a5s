"""Every page's sidebar in the channels app (webchat/shell.js) and the studio's: who signed in,
the roles they hold, in words, and the pages they may use, each by the same check its own page's
router makes. Every page still checks for itself, so the sidebar only leaves out the pages that
would refuse them. a5s has no administrator's mode: what anyone sees follows from their roles,
which the sidebar's foot names, so nobody need guess.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header

from a5s import db
from a5s.contract import (
    DATA_PROTECTION,
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    RELEASE_APPROVER,
    Person,
)
from a5s.core import (
    administration,
    audit,
    drafts,
    environment,
    handover,
    notebook_api,
    registry,
    samples,
    shadows,
    spending,
    web,
)
from a5s.core import studio_models as shapes
from a5s.core.releases import ENGINEER

# Each page, in the order the sidebars show it: its key, its name, its icon, the heading it's
# under, and its address, in the studio for most. The studio's sidebar and its palette, and every
# plain page's sidebar, show the pages from here alone, so each is named, and found, the same
# everywhere, as each had a list of its own (round 13's deferral). Home, what waits on whoever
# signed in, comes first; under Build, the agents come before the page that starts a new one,
# so how to build an agent is in the sidebar of whoever may, not only a button on another page.
PAGES = (
    ("home", "Home", "home", "Work", "/studio/"),
    ("chat", "Chat", "chat", "Work", "/chat/"),
    ("handovers", "Handed over", "people", "Work", "/studio/handovers"),
    ("tasks", "Tasks", "tasks", "Work", "/studio/tasks"),
    ("notebook", "Notebook", "book", "Work", "/studio/notebook"),
    ("agents", "Agents", "agent", "Build", "/studio/agents"),
    ("new", "New agent", "plus", "Build", "/studio/new"),
    ("map", "Map", "map", "Build", "/studio/map"),
    ("decide", "Decisions", "decide", "Decide", "/studio/decide"),
    ("grade", "Grading", "grade", "Decide", "/studio/grade"),
    ("shadows", "Shadows", "grade", "Decide", "/studio/shadows"),
    ("settings", "Settings", "settings", "Decide", "/studio/settings"),
    ("status", "Status", "bell", "Oversee", "/studio/status"),
    ("audit", "Audit trail", "audit", "Oversee", "/studio/audit"),
    ("admin", "Administration", "admin", "Oversee", "/studio/admin"),
    ("spending", "Spending", "spend", "Oversee", "/studio/spending"),
    ("health", "Model health", "model", "Oversee", "/studio/health"),
    ("officer", "Data protection", "officer", "Oversee", "/studio/officer"),
)

TEAM_NAME = "The team that runs a5s"  # as the studio's own page, What you may do, names it (core/home.py)


def held(person: Person, team: str) -> list[str]:
    """The roles someone holds, in words, as What you may do names them, for the foot of every
    sidebar: the team that runs a5s first, if they're in it, and none if they hold none."""
    named = [TEAM_NAME] if person.team == team else []
    return list(dict.fromkeys(named + [administration.named(role) for role in person.roles]))


def router(gw: Any) -> APIRouter:
    """The sidebar's API, for the channels app to include."""

    def someone(authorization: str | None = Header(default=None)) -> Person:
        return web.known(gw, authorization)

    api = APIRouter(dependencies=[Depends(someone)])

    @api.get("/shell/api", **shapes.answers(shapes.Shell))
    def shell(person: Annotated[Person, Depends(someone)]) -> dict:
        """Who signed in, the roles they hold, and the pages they may use, for the sidebar every
        page shows, in its order."""
        roles = set(person.roles)
        decides = INSTANCE_APPROVER in roles or any(
            r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:")) for r in roles)
        found = {"chat": True, "tasks": True, "notebook": bool(notebook_api.kept(gw, person)),
                 "home": True, "agents": True, "new": drafts.may_author(person, None),
                 "map": True, "decide": decides, "grade": samples.GRADER in roles,
                 "settings": registry.approves(person), "audit": audit.reads(person),
                 "admin": administration.administers(person, gw.cfg.team),
                 "spending": spending.sees_any(gw.url, person),
                 "officer": DATA_PROTECTION in roles,
                 "status": person.team == gw.cfg.team,  # as `a5s status` is theirs
                 "health": bool(roles & {RELEASE_APPROVER, ENGINEER}) or any(
                     r.startswith(ENGINEER + ":") for r in roles)}
        with db.transaction(gw.url) as conn:
            found["handovers"] = handover.answers_any(conn, gw.scenario, person)
            found["shadows"] = shadows.exists(conn) and (  # a new version's answers to grade,
                samples.GRADER in roles or bool(shadows.figures(conn, gw.scenario, person)))
        return {"you": person.name, "roles": held(person, gw.cfg.team), "pages": [
            {"page": key, "name": name, "icon": icon, "group": group, "at": at}
            for key, name, icon, group, at in PAGES if found[key]]}

    return api


def environment_router(gw: Any) -> APIRouter:
    """Which deployment this is, for the band across the top of every page, the sign-in's too:
    so it asks no sign-in, and says nothing but the deployment's kind and name, which every
    page shows whoever's on it (core/environment.py)."""
    api = APIRouter()

    @api.get("/shell/environment", **shapes.answers(shapes.Environment))
    def where() -> dict:
        return environment.here(gw.cfg.development)

    return api
