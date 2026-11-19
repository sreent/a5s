"""What the channels app's pages and APIs for people share: the headers each page goes with,
and who's signed in, as the identity provider says, or, in development alone, as they say.

Each set of pages is a router of its own, such as the studio's (core/studio_api.py) and the
auditors' (core/audit_api.py). Such a router's API is behind its own check of who's signed in,
so a route added to it can't be reached by someone who isn't. A page where someone signs in
afresh for one act, such as approving a version of the settings, is made by `acting`: each of
its acts checks a sign-in made for that act alone (core/approve_api.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from a5s import db
from a5s.contract import Person
from a5s.core import status
from a5s.core.identity import IdentityError, UnknownPerson, asked_claims, asked_level, signed_in

log = logging.getLogger(__name__)

WEBCHAT = Path(__file__).parent / "webchat"
PAGE_HEADERS = {  # the page runs only its own script, shows only text, and goes in no frame
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                               "font-src 'self'; connect-src 'self'; img-src 'self'; "
                               "base-uri 'none'; "
                               "form-action 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-cache",
}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".woff2": "font/woff2"}
# Ocean, the look a5s shares, as a5s copies it from sreent/ocean (deploy/ocean.sh): its tokens,
# its pieces, its chart colours and IBM Plex, each by its path there, as ocean.json pins them
OCEAN = WEBCHAT / "ocean"
OCEAN_FILES = tuple(path for path in json.loads((OCEAN / "ocean.json").read_text(encoding="utf-8"))["files"]
                    if Path(path).suffix in (".css", ".woff2"))


def webchat(gw: Any) -> bool:
    """The web chat is on where people can sign in to it, or in development. The pages people
    sign in to are on where it is."""
    if gw.identity is None:
        return gw.cfg.development
    return bool(gw.cfg.webchat_client_id)


def page(gw: Any, name: str) -> Response:
    """The web chat's page, or one of its files, as webchat/ holds it: every other page is the
    studio's."""
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


class TokenRequest(BaseModel):
    """A page's sign-in, passed on to the identity provider."""

    grant_type: str
    code: str | None = None
    code_verifier: str | None = None
    redirect_uri: str | None = None
    refresh_token: str | None = None


def exchange(gw: Any, form: dict, kept: tuple[str, ...]) -> JSONResponse:
    """A code or refresh token, passed on to the identity provider, and what it gives back
    that the page may keep: never the provider's access token."""
    try:
        answer = gw.identity.http.post(gw.identity.endpoints()["token_endpoint"], data=form,
                                       timeout=15)
        tokens = answer.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(502, "the identity provider didn't answer") from exc
    return JSONResponse(status_code=answer.status_code if answer.status_code < 500 else 502,
                        content={k: tokens[k] for k in (*kept, "error", "error_description")
                                 if k in tokens})


def refusal(gw: Any, exc: Any) -> HTTPException:
    """A sign-in's refusal as the page gets it: one for want of a second factor counted."""
    if exc.second_factor:
        counted(gw, exc.second_factor)
    return HTTPException(exc.status, exc.reason)


def signing(gw: Any, at: str) -> APIRouter:
    """Where the studio signs someone in, at `at`: where the identity provider is, at the level
    what counts asks it for, and the provider's code, passed on to it, for the signed sign-in
    alone, with no refresh token to make more like it. Neither holds anyone's data. An act's
    sign-in comes this way too, its nonce committing to the act."""

    def available() -> None:
        approving(gw)

    pages = APIRouter(dependencies=[Depends(available)])

    @pages.get(f"{at}/config")
    def sign_in_config() -> dict:
        """Where the studio signs someone in, at the level what counts asks the provider for."""
        try:
            where = gw.identity.endpoints()
        except Exception as exc:  # the provider's down: the page says so, and nothing else
            raise HTTPException(503, "the identity provider can't be reached") from exc
        level, claims = asked_level(gw.identity.cfg), asked_claims(gw.identity.cfg)
        return {"signin": {"authorization_endpoint": where["authorization_endpoint"],
                           "client_id": gw.cfg.webchat_client_id, "scope": "openid profile",
                           **({"acr_values": level} if level else {}),
                           **({"claims": claims} if claims else {})}}

    @pages.post(f"{at}/token")
    def sign_in_token(body: TokenRequest) -> JSONResponse:
        """The studio's sign-in, passed on to the identity provider: the signed sign-in alone."""
        if body.grant_type != "authorization_code" or not (body.code and body.code_verifier
                                                            and body.redirect_uri):
            raise HTTPException(400, "send a code and its verifier")
        return exchange(gw, {"grant_type": "authorization_code",
                             "client_id": gw.cfg.webchat_client_id, "code": body.code,
                             "code_verifier": body.code_verifier,
                             "redirect_uri": body.redirect_uri}, ("id_token",))

    return pages


def acting(gw: Any, name: str) -> APIRouter:
    """The acts of a page where someone signs in afresh for one act, such as approving a version
    of the settings: each act's route checks its own sign-in, whose nonce commits to the act, so
    the provider signs it. The page is the studio's, /studio/<name>, which signs in as the
    studio does; its old address goes there, with what it asked for, for the links already
    sent."""

    def available() -> None:
        approving(gw)

    pages = APIRouter(dependencies=[Depends(available)])

    @pages.get(f"/{name}/", include_in_schema=False)
    def act_moved(request: Request) -> Response:
        asked = request.url.query
        return RedirectResponse(f"/studio/{name}{'?' + asked if asked else ''}", status_code=303,
                                headers=PAGE_HEADERS)

    return pages
