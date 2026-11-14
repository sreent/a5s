"""What the channels app's pages and APIs for people share: the headers each page goes with,
and who's signed in, as the identity provider says, or, in development alone, as they say.

Each set of pages is a router of its own where it's grown one, such as the studio's
(core/studio_api.py). Such a router's API is behind its own check of who's signed in, so a
route added to it can't be reached by someone who isn't.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from a5s.contract import Person
from a5s.core.identity import IdentityError, UnknownPerson, signed_in

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
