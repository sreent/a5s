"""The studio's Status page: how a5s is doing, as the core last said, for the team that runs it.

The channels app serves it, and can't ask the core, which its network policy keeps it from and
whose seal keys the status needs: so the core records its status each minute, as the scheduler
asks it to (core/status.py), and this page reads what it last recorded. What needs someone comes
first, now or in working hours, each with its runbook, then the release and the last day's lines,
as `a5s status` says them. A record gone stale is itself what needs someone: the scheduler, which
asks for it, or the core may be away."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException

from a5s import db
from a5s.contract import Person
from a5s.core import status, web
from a5s.core import studio_models as shapes

AWAY = ("The core last said how a5s is doing {minutes} minutes ago. The scheduler asks it each "
        "minute, so one of them may be away: read their logs, and see that each can reach the "
        "other and the database")
NEVER = ("The core hasn't said how a5s is doing yet. The scheduler asks it each minute, once "
         "both are running: if they are, read their logs")


def status_page(gw: Any) -> dict:
    """The page's data: what needs someone, the release, and the last day, as the core last
    recorded them, with how long ago."""
    with db.transaction(gw.url) as conn:
        found = status.last_seen(conn)
    if found is None:
        return {"seen_seconds_ago": None, "verdict": NEVER + ".",
                "needs": [{"when": status.LATER, "said": NEVER,
                           "runbook": "docs/runbooks.md#messages-are-waiting"}],
                "release": None, "day": []}
    told, age = found
    needs = list(told.get("needs") or status.needs(told))
    if age > status.SEEN_LATE:
        needs.insert(0, {"when": status.LATER, "said": AWAY.format(minutes=round(age / 60)),
                         "runbook": "docs/runbooks.md#messages-are-waiting"})
    lines = status.told({**told, "needs": needs}).splitlines()
    day = [line.strip() for line in lines[lines.index("a5s over the last day:") + 1:]]
    return {"seen_seconds_ago": age, "verdict": status.verdict({"needs": needs}),
            "needs": [{**n, "said": n["said"].rstrip(".")} for n in needs],  # the page ends each
            "release": status.released(told.get("release")), "day": day}


def router(gw: Any) -> APIRouter:
    """The Status page's API, for the channels app to include."""

    def someone(authorization: str | None = Header(default=None)) -> Person:
        person = web.known(gw, authorization)
        if person.team != gw.cfg.team:
            raise HTTPException(403, "the Status page is for the team that runs a5s, as "
                                     "`a5s status` is")
        return person

    api = APIRouter()

    @api.get("/status/api", **shapes.answers(shapes.StatusNow))
    def status_now(person: Annotated[Person, Depends(someone)]) -> dict:
        return status_page(gw)

    return api
