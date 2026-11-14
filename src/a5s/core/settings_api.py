"""The settings app's pages in the channels app (docs/administration.md): where the people who
approve versions of the settings review the whole version in force, and ask for a new one. The
gateway proposes it to everyone it needs, who approve it on the approval page, so asking for a
version changes nothing by itself. What's asked for is checked and recorded in
core/settings_app.py, which the studio asks through too.

Every route of its API is behind the router's own check of who's signed in: someone who
approves versions of the settings.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from a5s import db
from a5s.contract import Person, parse_settings
from a5s.core import approvals, memberships, registry, settings_app, web


class Draft(BaseModel):
    """A version of the settings as someone wrote it in the settings app."""

    text: str


SETTLES = ("the settings app is for the people who approve versions of the settings: each "
           "part's owner, the instance approvers, agents' owners and the data protection "
           "officer, each for what's theirs")


def router(gw: Any) -> APIRouter:
    """The settings app's page and its API, for the channels app to include."""

    def available() -> None:
        web.approving(gw)

    def settling(authorization: str | None = Header(default=None)) -> Person:
        """Who signed in to the settings app: someone who approves versions of the settings."""
        person = web.known(gw, authorization)
        if not registry.approves(person):
            raise HTTPException(403, SETTLES)
        return person

    pages = APIRouter(dependencies=[Depends(available)])  # the page alone, which holds no data
    api = APIRouter(dependencies=[Depends(available), Depends(settling)])

    @pages.get("/settings/", include_in_schema=False)
    def settings_page() -> Response:
        return web.page(gw, "settings.html")

    @pages.get("/settings/settings.js", include_in_schema=False)
    def settings_script() -> Response:
        return web.page(gw, "settings.js")

    @api.get("/settings/api")
    def settings_now(person: Annotated[Person, Depends(settling)]) -> dict:
        """The whole version in force, in words and as written, the versions waiting for
        approval, and what the person asked for lately."""
        words = (gw.definitions, gw.scenario.person)
        with db.transaction(gw.url) as conn:
            last = approvals.latest(conn, gw.scenario.name)
            in_force = parse_settings(bytes(last["raw"])) if last else None
            waiting = []
            for row in conn.execute("select * from settings_proposals where scenario = %s and "
                                    "outcome is null and serial > %s order by serial desc",
                                    (gw.scenario.name, last["serial"] if last else -1)):
                settings = parse_settings(bytes(row["raw"]))
                approved = approvals.recorded(conn, gw.scenario.name, row["digest"])
                valid, _ = registry.signers(settings, gw.scenario.person, approved)
                waiting.append({
                    "serial": row["serial"], "link": f"/approve/?settings={row['digest']}",
                    "changes": approvals.changes(in_force, settings, *words),
                    "approved_by": [p.name if (p := gw.scenario.person(a)) else a for a in valid],
                    "needs": registry.missing(settings, gw.scenario.person, valid, in_force,
                                              memberships.rooted(gw.scenario).person)})
            asked = conn.execute("select * from settings_requests where scenario = %s and "
                                 "person = %s order by id desc limit 5",
                                 (gw.scenario.name, person.id)).fetchall()
        return {
            "you": person.name,
            "in_force": {"serial": last["serial"], "text": bytes(last["raw"]).decode(),
                         "whole": approvals.described(in_force, *words)}
            if last and in_force else None,
            "waiting": waiting,
            "requests": [{"asked_at": r["asked_at"].isoformat(),
                          "serial": parse_settings(bytes(r["raw"])).serial,
                          "outcome": r["outcome"] or "waiting for a5s to ask its approvers",
                          "link": f"/approve/?settings={r['digest']}" if r["digest"] else None}
                         for r in asked],
        }

    @api.post("/settings/api/review")
    def settings_review(body: Draft) -> dict:
        """What a version someone wrote would change, the whole of it in words, and who'd
        have to approve it, before they ask for it."""
        with db.transaction(gw.url) as conn:
            last = approvals.latest(conn, gw.scenario.name)
        settings, _, problems = settings_app.drafted(gw, body.text, last)
        if settings is None:
            return {"problems": problems}
        before = parse_settings(bytes(last["raw"])) if last else None
        words = (gw.definitions, gw.scenario.person)
        return {"serial": settings.serial, "problems": problems,
                "changes": approvals.changes(before, settings, *words),
                "whole": approvals.described(settings, *words),
                "approvers": [p.name for p in registry.approvers(
                    settings, gw.scenario.holders, before,
                    memberships.rooted(gw.scenario).holders)]}

    @api.post("/settings/api/requests", status_code=202)
    def settings_request(body: Draft, person: Annotated[Person, Depends(settling)]) -> dict:
        """Ask for a version: the gateway proposes it to everyone it needs within a minute."""
        with db.transaction(gw.url) as conn:
            try:
                return settings_app.request(conn, gw, person, body.text)
            except settings_app.Refused as e:
                raise HTTPException(e.status, {"problems": e.problems}) from None

    pages.include_router(api)
    return pages
