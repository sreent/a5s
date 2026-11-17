"""The settings app's API in the channels app (docs/administration.md), whose page is the studio's,
/studio/settings: where the people who approve versions of the settings review the whole version
in force, and ask for a new one. The gateway proposes it to everyone it needs, who approve it on
the approval page, so asking for a version changes nothing by itself. What's asked for is checked
and recorded in core/settings_app.py, which the studio's other ways to ask go through too.

Every route of its API is behind the router's own check of who's signed in: someone who
approves versions of the settings.
"""

from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from a5s import db
from a5s.contract import Person, parse_settings
from a5s.core import approvals, impact, memberships, registry, settings_app, web
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say


class Written(BaseModel):
    """A version of the settings as someone wrote it in the settings app, and the version in
    force they reviewed it against, by its serial, once they have."""

    text: str
    base: int | None = None


SETTLES = ("the settings app is for the people who approve versions of the settings: each "
           "part's owner, the instance approvers, agents' owners, the data protection officer "
           "and assurance, each for what's theirs")


def named(data: dict | None, person: Person, directory: Any = None) -> dict[str, str]:
    """The people the settings name, as owners, deputies and whom instances serve, and whoever
    is signed in, by their names, for the page's forms to offer: a team or a role an instance
    serves keeps its name as written."""
    ids = {person.id}
    for instance in ((data or {}).get("instances") or {}).values():
        if isinstance(instance, dict):
            ids |= {i for i in (instance.get("owner"), instance.get("deputy")) if isinstance(i, str)}
            ids |= {i for i in instance.get("serves") or [] if isinstance(i, str)}
    found = {}
    for i in sorted(ids):
        known = directory(i) if directory and ":" not in i else None
        found[i] = known.name if known else (person.name if i == person.id else i)
    return found


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
    def settings_page(request: Request) -> Response:
        """The settings are in the studio now: an address of the settings app's, such as a card's
        or a bookmark's, goes there, with what it asked for, such as an agent to put to work."""
        asked = request.url.query
        return RedirectResponse(f"/studio/settings{'?' + asked if asked else ''}", status_code=303,
                                headers=web.PAGE_HEADERS)

    @api.get("/settings/api", **shapes.answers(shapes.SettingsNow))
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
                    "serial": row["serial"], "link": f"/studio/approve?settings={row['digest']}",
                    "changes": approvals.changes(in_force, settings, *words),
                    "approved_by": [p.name if (p := gw.scenario.person(a)) else a for a in valid],
                    "needs": registry.missing(settings, gw.scenario.person, valid, in_force,
                                              memberships.rooted(gw.scenario).person)})
            asked = conn.execute("select * from settings_requests where scenario = %s and "
                                 "person = %s order by id desc limit 5",
                                 (gw.scenario.name, person.id)).fetchall()
        data = (yaml.safe_load(bytes(last["raw"])) or {}) if last and in_force else None
        tools = gw.scenario.tools()
        return {
            "you": person.name, "me": person.id,
            "in_force": {"serial": last["serial"], "text": bytes(last["raw"]).decode(),
                         "whole": approvals.described(in_force, *words),
                         "data": data}  # as the page's forms change it
            if last and in_force else None,
            # What the forms offer: the people the settings name, the types of change this
            # deployment's tools make, and for each release, the level it starts at, the most
            # it allows, and the types of change its own tools make
            "names": named(data, person, gw.scenario.person),
            "actions": sorted({t.action for t in tools.values() if t.action}),
            "releases": {name: {"starts": d.autonomy.start, "most": d.autonomy.max,
                                "actions": sorted({tools[t].action for t in d.tool_names
                                                   if t in tools and tools[t].action})}
                         for name, d in sorted(gw.definitions.items())},
            "waiting": waiting,
            "currency": gw.currency,  # which budgets the forms set are in
            "requests": [{"asked_at": r["asked_at"].isoformat(),
                          "serial": parse_settings(bytes(r["raw"])).serial,
                          "outcome": r["outcome"] or "waiting for a5s to ask its approvers",
                          "link": f"/studio/approve?settings={r['digest']}" if r["digest"] else None}
                         for r in asked],
        }

    @api.post("/settings/api/review", **shapes.answers(shapes.SettingsReview))
    def settings_review(body: Written, person: Annotated[Person, Depends(settling)]) -> dict:
        """What a version someone wrote would change, the whole of it in words, and who'd
        have to approve it, before they ask for it."""
        with db.transaction(gw.url) as conn:
            last = approvals.latest(conn, gw.scenario.name)
        settings, _, problems = settings_app.drafted(gw, body.text, last)
        if settings is None:
            return {"problems": problems}
        before = parse_settings(bytes(last["raw"])) if last else None
        words = (gw.definitions, gw.scenario.person)
        preview = impact.shown(gw, before, settings, person) if not problems else None
        return {"serial": settings.serial, "problems": problems,
                **({"impact": preview} if preview is not None else {}),
                "in_force": last["serial"] if last else None,  # what it's reviewed against
                "changes": approvals.changes(before, settings, *words),
                "whole": approvals.described(settings, *words),
                "approvers": [p.name for p in registry.approvers(
                    settings, gw.scenario.holders, before,
                    memberships.rooted(gw.scenario).holders)]}

    @api.post("/settings/api/requests", status_code=202, **shapes.answers(shapes.SettingsAsked))
    def settings_request(body: Written, person: Annotated[Person, Depends(settling)]) -> dict:
        """Ask for a version: the gateway proposes it to everyone it needs within a minute."""
        with db.transaction(gw.url) as conn:
            try:
                if "base" in body.model_fields_set:  # reviewed against that version in force
                    return settings_app.request(conn, gw, person, body.text, base=body.base)
                return settings_app.request(conn, gw, person, body.text)
            except settings_app.Refused as e:
                raise HTTPException(e.status, {"problems": e.problems}) from None

    pages.include_router(api)
    return pages
