"""What the channels app's pages and APIs for people share: the headers each page goes with,
and who's signed in, as the identity provider says, or, in development alone, as they say.

Each set of pages is a router of its own, such as the studio's (core/studio_api.py) and the
auditors' (core/audit_api.py). Such a router's API is behind its own check of who's signed in,
so a route added to it can't be reached by someone who isn't.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import psycopg
from fastapi import HTTPException, Response

from a5s import db
from a5s.contract import Person
from a5s.core import status
from a5s.core.identity import IdentityError, UnknownPerson, signed_in

log = logging.getLogger(__name__)

WEBCHAT = Path(__file__).parent / "webchat"
PAGE_HEADERS = {  # the page runs only its own script, shows only text, and goes in no frame
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                               "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                               "form-action 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-cache",
}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}


def webchat(gw: Any) -> bool:
    """The web chat is on where people can sign in to it, or in development. The pages people
    sign in to are on where it is."""
    if gw.identity is None:
        return gw.cfg.development
    return bool(gw.cfg.webchat_client_id)


def page(gw: Any, name: str) -> Response:
    """One of the pages people sign in to, or its script, as webchat/ holds it."""
    if not webchat(gw):
        raise HTTPException(404, "the web chat isn't set up here")
    path = WEBCHAT / name
    return Response(path.read_bytes(), media_type=TYPES[path.suffix], headers=PAGE_HEADERS)


def sender(gw: Any, authorization: str | None, claimed: str | None) -> tuple[str, str]:
    """Who's writing, and how a5s knows."""
    if gw.identity is not None:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in first: send your token as a bearer token")
        try:
            person = signed_in(gw.identity, gw.scenario, token)
        except UnknownPerson as exc:
            raise HTTPException(403, str(exc)) from None
        except IdentityError as exc:
            raise HTTPException(401, f"your token doesn't check out: {exc}") from None
        if claimed and claimed != person:
            raise HTTPException(403, f"you're signed in as {person}, not {claimed}")
        return person, "verified"
    if not gw.cfg.development:
        raise HTTPException(503, "the local channel needs sign-in: set A5S_OIDC_ISSUER, "
                                 "or A5S_DEVELOPMENT=1 to develop without it")
    if not claimed:
        raise HTTPException(400, "say who the message is from")
    if gw.scenario.person(claimed) is None:
        raise HTTPException(403, "a5s doesn't know who you are")
    return claimed, "unverified (development)"


def approving(gw: Any) -> None:
    """Refuse, as though there were nothing here, where the channels app takes no approvals:
    the pages people sign in to are all behind it."""
    if problem := gw.approving(sealing=False):  # the gateway seals, never the channels app
        raise HTTPException(404, problem)


def known(gw: Any, authorization: str | None) -> Person:
    """Whoever signed in, whom the directory knows."""
    approving(gw)
    who, _ = sender(gw, authorization, None)
    person = gw.scenario.person(who)
    if person is None:
        raise HTTPException(403, "a5s doesn't know who you are")
    return person


def counted(gw: Any, doing: str) -> None:
    """Count a refusal for want of a second factor, for the status: the identity provider's
    policy, not the person refused, decides when a sign-in asks for one."""
    try:
        with db.transaction(gw.url) as conn:
            status.second_factor_refused(conn, doing)
    except psycopg.Error:  # counting never stands in the refusal's way
        log.warning("couldn't count a refusal for want of a second factor", exc_info=True)
