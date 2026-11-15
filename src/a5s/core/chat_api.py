"""The web chat in the channels app (docs/architecture.md#channels): a page where people sign in
with their organisation's identity provider and talk to the agents through the local channel,
as the command line does (core/inbox.py). The page holds nobody's data: what someone says and
hears goes through the local channel, which checks their sign-in at every call.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse

from a5s.core import web

FILES = ("app.js", "app.css", "shell.js")  # the page's own files, by name alone


def router(gw: Any) -> APIRouter:
    """The web chat's page, its files, and where it signs people in."""
    pages = APIRouter()

    @pages.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        if not web.webchat(gw):
            raise HTTPException(404, "the web chat isn't set up here")
        return RedirectResponse("/chat/")

    @pages.get("/chat/", include_in_schema=False)
    def chat() -> Response:
        return web.page(gw, "index.html")

    @pages.get("/chat/config")
    def chat_config() -> dict:
        """How the page signs people in, and which agents they can talk to."""
        if not web.webchat(gw):
            raise HTTPException(404, "the web chat isn't set up here")
        signin = None
        if gw.identity is not None and gw.cfg.webchat_client_id:
            try:
                where = gw.identity.endpoints()
            except Exception as exc:  # the provider's down: the page says so, and nothing else
                raise HTTPException(503, "the identity provider can't be reached") from exc
            signin = {"authorization_endpoint": where["authorization_endpoint"],
                      "end_session_endpoint": where.get("end_session_endpoint"),
                      "client_id": gw.cfg.webchat_client_id, "scope": "openid profile"}
        return {"signin": signin, "development": gw.identity is None and gw.cfg.development,
                "agents": sorted(gw.definitions)}

    @pages.post("/chat/token")
    def chat_token(body: web.TokenRequest) -> JSONResponse:
        """The web chat's sign-in, passed on to the identity provider, which checks the code
        and its PKCE verifier. It needs no secret, and the page never calls the provider
        itself, so the provider needn't allow it to."""
        if gw.identity is None or not gw.cfg.webchat_client_id:
            raise HTTPException(404, "the web chat's sign-in isn't set up")
        form = {"grant_type": body.grant_type, "client_id": gw.cfg.webchat_client_id}
        if (body.grant_type == "authorization_code" and body.code and body.code_verifier
                and body.redirect_uri):
            form |= {"code": body.code, "code_verifier": body.code_verifier,
                     "redirect_uri": body.redirect_uri}
        elif body.grant_type == "refresh_token" and body.refresh_token:
            form |= {"refresh_token": body.refresh_token, "scope": "openid profile"}
        else:
            raise HTTPException(400, "send a code and its verifier, or a refresh token")
        return web.exchange(gw, form, ("id_token", "refresh_token", "expires_in"))

    @pages.get("/chat/{name}", include_in_schema=False)
    def chat_file(name: str) -> Response:
        if name not in FILES:
            raise HTTPException(404, "no such file")
        return web.page(gw, name)

    @pages.get("/chat/fonts/{name}", include_in_schema=False)
    def chat_font(name: str) -> Response:
        """The pages' type, IBM Plex, which a5s bundles: no page loads a font from outside."""
        if name not in web.FONTS:
            raise HTTPException(404, "no such font")
        found = web.page(gw, f"fonts/{name}")
        found.headers["Cache-Control"] = "public, max-age=604800"
        return found

    return pages
