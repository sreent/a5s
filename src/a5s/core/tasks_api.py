"""People's own tasks' API in the channels app (docs/phase-4.md), whose page is the studio's,
/studio/tasks: what they asked agents to do over more than one run, with every agent, and a way
to cancel each (core/tasking.py).

Every route of its API is behind the router's own check of who's signed in: anyone the
directory knows, each for their own tasks alone.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from a5s import db
from a5s.contract import Person
from a5s.core import repeats, tasking, web
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say
from a5s.core.tasks import TaskError


def router(gw: Any) -> APIRouter:
    """The tasks' page and its API, for the channels app to include."""

    def available() -> None:
        web.approving(gw)

    def tasked(authorization: str | None = Header(default=None)) -> Person:
        """Who signed in to their tasks' page: anyone the directory knows."""
        return web.known(gw, authorization)

    pages = APIRouter(dependencies=[Depends(available)])  # the page alone, which holds no data
    api = APIRouter(dependencies=[Depends(available), Depends(tasked)])

    @pages.get("/tasks/", include_in_schema=False)
    def tasks_page(request: Request) -> Response:
        """Someone's tasks are in the studio now: the old address, such as a reply's, goes there."""
        asked = request.url.query
        return RedirectResponse(f"/studio/tasks{'?' + asked if asked else ''}", status_code=303,
                                headers=web.PAGE_HEADERS)

    @api.get("/tasks/api", **shapes.answers(shapes.TasksNow))
    def tasks_now(person: Annotated[Person, Depends(tasked)]) -> dict:
        """Someone's own tasks, with every agent: how each stands, what it waits on, and
        what it has spent. One whose words name a record they may no longer see shows how it
        stands alone."""
        with db.transaction(gw.url) as conn:
            return {"you": person.name,
                    "tasks": tasking.theirs(conn, gw.scenario, person, gw.clock()),
                    "repeats": repeats.listed(conn, gw.scenario, person)}

    @api.post("/tasks/api/{task}/cancel", **shapes.answers(shapes.TaskStopped))
    def tasks_cancel(task: str, person: Annotated[Person, Depends(tasked)]) -> dict:
        """Cancel one of someone's own tasks, at their word, and the parts of it still open."""
        try:
            with db.transaction(gw.url) as conn:
                return tasking.cancel_theirs(conn, person, task, gw.clock())
        except TaskError as exc:
            raise HTTPException(404 if "isn't one of" in str(exc) else 409, str(exc)) from None

    pages.include_router(api)
    return pages
