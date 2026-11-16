"""The administrators' page's API in the channels app (docs/administration.md), whose page is the
studio's, /studio/admin: who holds each role,
and by what, what waits for whom, what nobody answers for any more, and the latest
administrative acts (core/administration.py). It shows; it changes nothing.

Every route of its API is behind the router's own check of who's signed in: someone with one
of a5s's roles, or from the team that runs it.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from a5s import db
from a5s.contract import Person
from a5s.core import administration, audit, web
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say


def router(gw: Any) -> APIRouter:
    """The administrators' page and its API, for the channels app to include."""

    def available() -> None:
        web.approving(gw)

    def administering(authorization: str | None = Header(default=None)) -> Person:
        """Who signed in to the administrators' page: someone with one of a5s's roles, or
        from the team that runs it."""
        person = web.known(gw, authorization)
        if not administration.administers(person, gw.cfg.team):
            raise HTTPException(403, "the administrators' page is for people who hold one of "
                                     "a5s's roles, or run it")
        return person

    pages = APIRouter(dependencies=[Depends(available)])  # the page alone, which holds no data
    api = APIRouter(dependencies=[Depends(available), Depends(administering)])

    @pages.get("/admin/", include_in_schema=False)
    def admin_page(request: Request) -> Response:
        """The administrators' page is in the studio now: its old address goes there."""
        asked = request.url.query
        return RedirectResponse(f"/studio/admin{'?' + asked if asked else ''}", status_code=303,
                                headers=web.PAGE_HEADERS)

    @api.get("/admin/api", **shapes.answers(shapes.AdminNow))
    def admin_now(person: Annotated[Person, Depends(administering)]) -> dict:
        """Who holds each role and by what, what waits for whom, and the latest acts, read
        from the trail, with whom each was about as a stand-in until the officer agrees."""
        with db.transaction(gw.url) as conn:
            found = administration.page(conn, gw, gw.clock(), viewer=person)
            audit.noted(conn, person.id, "administration", "their sign-in", page=True,
                        acts=len(found["latest"]))
        return {"you": person.name, **found}

    pages.include_router(api)
    return pages
