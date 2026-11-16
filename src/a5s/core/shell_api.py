"""Every page's sidebar in the channels app (webchat/shell.js) and the studio's: who signed in,
and the pages they may use, each by the same check its own page's router makes. Every page still
checks for itself, so the sidebar only leaves out the pages that would refuse them.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header

from a5s.contract import DATA_PROTECTION, INSTANCE_APPROVER, PART_DELEGATE, PART_OWNER, Person
from a5s.core import administration, audit, notebook_api, registry, samples, web
from a5s.core import studio_models as shapes

# Each page, in the order the sidebars show it: its key, its name, its icon, the heading it's
# under, and its address, in the studio for most. The studio's sidebar and its palette, and every
# plain page's sidebar, show the pages from here alone, so each is named, and found, the same
# everywhere, as each had a list of its own (round 13's deferral).
PAGES = (
    ("chat", "Chat", "chat", "Work", "/chat/"),
    ("tasks", "Tasks", "tasks", "Work", "/studio/tasks"),
    ("notebook", "Notebook", "book", "Work", "/studio/notebook"),
    ("studio", "Studio", "studio", "Build", "/studio/"),
    ("decide", "Decisions", "decide", "Decide", "/studio/decide"),
    ("grade", "Grading", "grade", "Decide", "/studio/grade"),
    ("settings", "Settings", "settings", "Decide", "/studio/settings"),
    ("audit", "Audit trail", "audit", "Oversee", "/studio/audit"),
    ("admin", "Administration", "admin", "Oversee", "/studio/admin"),
    ("officer", "Data protection", "officer", "Oversee", "/studio/officer"),
)


def router(gw: Any) -> APIRouter:
    """The sidebar's API, for the channels app to include."""

    def someone(authorization: str | None = Header(default=None)) -> Person:
        return web.known(gw, authorization)

    api = APIRouter(dependencies=[Depends(someone)])

    @api.get("/shell/api", **shapes.answers(shapes.Shell))
    def shell(person: Annotated[Person, Depends(someone)]) -> dict:
        """Who signed in, and the pages they may use, for the sidebar every page shows, in its
        order."""
        roles = set(person.roles)
        decides = INSTANCE_APPROVER in roles or any(
            r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:")) for r in roles)
        found = {"chat": True, "tasks": True, "notebook": bool(notebook_api.kept(gw, person)),
                 "studio": True, "decide": decides, "grade": samples.GRADER in roles,
                 "settings": registry.approves(person), "audit": audit.reads(person),
                 "admin": administration.administers(person, gw.cfg.team),
                 "officer": DATA_PROTECTION in roles}
        return {"you": person.name, "pages": [
            {"page": key, "name": name, "icon": icon, "group": group, "at": at}
            for key, name, icon, group, at in PAGES if found[key]]}

    return api
