"""The data protection officer's page's API in the channels app (docs/data-protection.md): where
they ask to export, or erase, what a5s keeps about someone, signed in afresh for that request
alone, which someone from the team that runs a5s then carries out, once, within ten minutes
(core/officer.py). The page is the studio's, /studio/officer.
"""

import hashlib
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from a5s import db
from a5s.core import acting, approvals, customers, languages, ledger, officer, web
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say


class Asking(BaseModel):
    """What the officer's page sends with its sign-in: what it's to do, for whom, and the salt
    its nonce was made with; and, to erase, their id typed again, as the page asks for it, since
    an erasure can't be undone: checked here too, so no script skips it (docs/design.md)."""

    action: str
    person: str
    salt: str
    confirm: str | None = None


def router(gw: Any) -> APIRouter:
    """The officer's page's API, and its old address, for the channels app to include."""
    pages = web.acting(gw, "officer")

    @pages.get("/officer/api", **shapes.answers(shapes.OfficerNow))
    def officer_now(authorization: str | None = Header(default=None)) -> dict:
        """The officer's page, before they ask: who they are, and that they act there as the
        data protection officer, as nobody else may ask."""
        person = web.known(gw, authorization)
        found = acting.officer(person, languages.of(person))
        if found is None:
            raise HTTPException(403, f"only the data protection officer asks for someone's data, "
                                     f"and {person.name} isn't the officer")
        return {"you": person.name, "acting": found}

    @pages.post("/officer/requests", **shapes.answers(shapes.OfficerAsked))
    def officer_request(body: Asking, authorization: str | None = Header(default=None)) -> dict:
        """The officer's request, signed through the identity provider for it alone, and
        recorded for the gateway to check again and carry out, once."""
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to ask: send your sign-in as a bearer token")
        person = body.person.strip()
        if body.action == "erase" and (body.confirm or "").strip().casefold() != person.casefold():
            raise HTTPException(400, "type their id again, as the page asks, to erase what a5s "
                                     "keeps about them: an erasure can't be undone")
        try:
            who, claims = officer.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                        token, body.action, person, body.salt, time.time())
            with db.transaction(gw.url) as conn:
                officer.record(conn, body.action, person, who.id, token, body.salt, claims)
                whom = customers.subject(person)  # an address by its digest alone
                ledger.append(conn, {
                    "kind": "admin", "action": "ask", "run": None, "instance": None,
                    "acts_for": [] if whom != person else [person], "decision": "record",
                    "args": {"to": body.action, "person": whom, "by": who.id,
                             "identity": "verified: a sign-in to ask for this alone",
                             "issuer": claims["iss"],
                             "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
        except approvals.Refused as exc:
            raise web.refusal(gw, exc) from None
        named = gw.scenario.person(person)
        return {"asked": body.action, "person": person, "name": named.name if named else None,
                "by": who.name, "lasts": "ten minutes",
                "command": f"a5s export --person {person} --out <file>" if body.action == "export"
                else f"a5s erase --person {person} --confirm {person}"}

    return pages
