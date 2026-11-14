"""Every page's sidebar in the channels app (webchat/shell.js): who signed in, and the pages they
may use, each by the same check its own page's router makes. Every page still checks for itself,
so the sidebar only leaves out the pages that would refuse them.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header

from a5s.contract import DATA_PROTECTION, INSTANCE_APPROVER, PART_DELEGATE, PART_OWNER, Person
from a5s.core import administration, audit, notebook_api, registry, samples, web


def router(gw: Any) -> APIRouter:
    """The sidebar's API, for the channels app to include."""

    def someone(authorization: str | None = Header(default=None)) -> Person:
        return web.known(gw, authorization)

    api = APIRouter(dependencies=[Depends(someone)])

    @api.get("/shell/api")
    def shell(person: Annotated[Person, Depends(someone)]) -> dict:
        """Who signed in, and the pages they may use, for the sidebar every page shows."""
        roles = set(person.roles)
        decides = INSTANCE_APPROVER in roles or any(
            r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:")) for r in roles)
        found = {"chat": True, "tasks": True, "notebook": bool(notebook_api.kept(gw, person)),
                 "studio": True, "decide": decides, "grade": samples.GRADER in roles,
                 "settings": registry.approves(person), "audit": audit.reads(person),
                 "admin": administration.administers(person, gw.cfg.team),
                 "officer": DATA_PROTECTION in roles}
        return {"you": person.name, "pages": [name for name, may in found.items() if may]}

    return api
