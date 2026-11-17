"""The auditors' page's API in the channels app (docs/administration.md), whose page is the
studio's, /studio/audit: the ledger as an auditor reads it, read only, from the same module as the core's API (core/audit.py). Whoever acted in
one of a5s's roles shows as themselves; whom agents acted for, as a stand-in until the data
protection officer agrees to names.

Every route of its API is behind the router's own check of who's signed in: an auditor, or
assurance, with a second factor where the deployment asks for one, as for what counts, since
the trail is the most of a5s anyone reads.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from a5s import db
from a5s.contract import Person
from a5s.core import audit, web
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say
from a5s.core.identity import (
    IdentityError,
    UnknownPerson,
    second_factor,
    whose,
    without_second_factor,
)


def auditor(gw: Any, authorization: str | None) -> Person:
    """Who signed in to the audit trail: an auditor, or assurance, with a second factor where
    the deployment asks for one."""
    web.approving(gw)
    token = (authorization or "").removeprefix("Bearer ").strip()
    if gw.identity is None or not token:
        web.sender(gw, authorization, None)  # says what's missing, as everywhere
        raise HTTPException(401, "sign in first")
    try:
        claims = gw.identity.claims(token)
        person = whose(gw.identity, gw.scenario, claims)
    except UnknownPerson as exc:
        raise HTTPException(403, str(exc)) from None
    except IdentityError as exc:
        raise HTTPException(401, f"your token doesn't check out: {exc}") from None
    if not audit.reads(person):
        raise HTTPException(403, "only an auditor, or assurance, reads the audit trail")
    if not second_factor(gw.identity.cfg, claims):
        web.counted(gw, "read the audit trail")
        raise HTTPException(401, without_second_factor("read the audit trail"))
    return person


def period(since: datetime | None, until: datetime | None) -> dict:
    return {"since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None}


def router(gw: Any) -> APIRouter:
    """The auditors' page and its API, for the channels app to include."""

    def available() -> None:
        web.approving(gw)

    def auditing(authorization: str | None = Header(default=None)) -> Person:
        return auditor(gw, authorization)

    pages = APIRouter(dependencies=[Depends(available)])  # the page alone, which holds no data
    api = APIRouter(dependencies=[Depends(available), Depends(auditing)])  # all of it signed in

    def shown(conn: Any) -> audit.Shown:
        return audit.Shown(gw.scenario, audit.key(conn),
                           names=gw.data_protection(conn).audit_names, left=audit.left(conn))

    @pages.get("/audit/", include_in_schema=False)
    def audit_page(request: Request) -> Response:
        """The audit trail is in the studio now: its old address goes there."""
        asked = request.url.query
        return RedirectResponse(f"/studio/audit{'?' + asked if asked else ''}", status_code=303,
                                headers=web.PAGE_HEADERS)

    @api.get("/audit/api", **shapes.answers(shapes.AuditNow))
    def audit_now(person: Annotated[Person, Depends(auditing)]) -> dict:
        """Who's reading, and how the page shows people: by name, or by stand-in."""
        with db.transaction(gw.url) as conn:
            names = gw.data_protection(conn).audit_names
        return {"you": person.name, "names": names, "exports": names,
                "kinds": list(audit.KINDS)}

    @api.get("/audit/api/entries", **shapes.answers(shapes.AuditEntries))
    def audit_entries(person: Annotated[Person, Depends(auditing)],
                      since: datetime | None = None, until: datetime | None = None,
                      kind: str | None = None, action: str | None = None,
                      decision: str | None = None, instance: str | None = None,
                      acted_for: Annotated[str | None, Query(alias="for")] = None,
                      by: str | None = None, after: int = 0, limit: int = audit.MOST) -> dict:
        """A page of a period's entries, as an auditor asks for them: whom agents acted for
        as a stand-in, which finds them too, until the officer agrees to names."""
        with db.transaction(gw.url) as conn:
            showing = shown(conn)
            whom = showing.whom(conn, acted_for, since, until) if acted_for else None
            found = {"entries": [], "next": None} if acted_for and whom is None else audit.search(
                conn, since=since, until=until, kind=kind, action=action, decision=decision,
                instance=instance, acted_for=whom, by=by, after=after, limit=limit)
            audit.noted(conn, person.id, "search", "their sign-in", **period(since, until),
                        kind=kind, action=action, decision=decision, instance=instance,
                        acted_for=acted_for, acted_by=by, after=after or None,
                        found=len(found["entries"]), page=True)
        return {"entries": [showing.entry(e) for e in found["entries"]], "next": found["next"]}

    @api.get("/audit/api/report", **shapes.answers(shapes.AuditReport))
    def audit_report(person: Annotated[Person, Depends(auditing)],
                     since: datetime | None = None, until: datetime | None = None) -> dict:
        """Who holds each role, and who did what of a period's administration."""
        with db.transaction(gw.url) as conn:
            found = audit.report(conn, gw.scenario, gw.definitions.keys(), since=since,
                                 until=until)
            audit.noted(conn, person.id, "report", "their sign-in", **period(since, until),
                        acts=len(found["acts"]), page=True)
            return shown(conn).report(found)

    @api.get("/audit/api/export", **shapes.answers(shapes.AuditExport))
    def audit_export(person: Annotated[Person, Depends(auditing)],
                     since: datetime | None = None, until: datetime | None = None,
                     after: int = 0) -> dict:
        """A page of a period's entries exactly as the ledger holds them, to check and keep:
        only once the officer agrees to names, since they hold whom agents acted for."""
        with db.transaction(gw.url) as conn:
            names = gw.data_protection(conn).audit_names
        if not names:
            raise HTTPException(403, "exports hold whom agents acted for, so they're on this "
                                     "page only once the data protection officer agrees; until "
                                     "then, the team that runs a5s exports a period for you "
                                     "with `a5s audit export`")
        with db.transaction(gw.url) as conn:
            found = audit.export(conn, since=since, until=until, after=after)
            audit.noted(conn, person.id, "export", "their sign-in", **period(since, until),
                        after=after or None, entries=len(found["entries"]), page=True)
        return found

    pages.include_router(api)
    return pages
