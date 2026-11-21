"""The pages people sign in to for one thing are each a router of their own in the channels app,
whose API checks who's signed in for every route, before the route's own check (core/web.py):
the studio's, the settings app's, the notebook's, people's own tasks', the auditors' and the
administrators'. So a route added to one of them can't be reached by someone who isn't signed
in, and a route outside them must be one of those that check for themselves.

The pages where someone signs in afresh for one act are routers too, whose acts each check a
sign-in made for that act alone (core/approve_api.py and the others): each act is listed here,
with a body of the shape it takes, and none is open to someone not signed in.

The sidebar every page shows lists a page by the check its router makes, so it lists exactly the
pages whose API lets each person in.

The core's own API is two routers, each guarded for every route (core/gateway.py): the service
token's, for the scheduler, the command line and the team that runs a5s, and the run token's, for
a worker's own run."""

import re
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from a5s.core import gateway

SIGNED_IN = ("/studio/api", "/settings/api", "/notebook/api", "/tasks/api", "/audit/api",
             "/admin/api", "/shell/api")
ACTING = ("/approve/", "/officer/", "/decide/", "/grade/")
# The routes that check for themselves: the chats', each with its own sign-in or token; the web
# chat's, which hold nobody's data; where the studio signs someone in, which holds nothing; and
# each act's
OWN = ("/channels/", "/chat/", "/studio/sign-in/", "/health/api", *ACTING)
DIGEST = "0" * 64
ACTS = {  # each act, with a body of the shape it takes, so it's refused for want of a sign-in
    ("get", "/approve/settings/{version}"): None,  # what an approver reads before approving
    ("post", "/approve/settings/{version}"): {"salt": "s"},
    ("post", "/officer/requests"): {"action": "export", "person": "ben", "salt": "s"},
    ("post", "/decide/review"): None,
    ("post", "/decide/proposals"): {"proposals": [DIGEST], "decision": "approve", "salt": "s"},
    ("post", "/grade/review"): None,
    ("post", "/grade/samples"): {"grades": {"1": "right"}, "salt": "s"},
}
PEOPLE = ("ana", "ben", "chen", "omar", "dana", "priya", "tomas", "lena", "rosa", "kofi", "noor")
PAGES = {"studio": "/studio/api/home", "settings": "/settings/api", "notebook": "/notebook/api",
         "tasks": "/tasks/api", "audit": "/audit/api", "admin": "/admin/api"}


def described(url: str) -> dict[str, dict]:
    """Every route the channels app serves, as its own description of its API lists them."""
    return httpx.get(f"{url}/openapi.json", timeout=30).json()["paths"]


def test_every_route_is_behind_its_routers_check_or_one_of_its_own(approving):
    loose = [path for path in described(approving) if not path.startswith(SIGNED_IN + OWN)]
    assert loose == []  # a route nobody has said who may reach


@pytest.mark.parametrize("api", SIGNED_IN)
def test_every_route_of_a_signed_in_api_refuses_someone_not_signed_in(approving, api):
    routes = {path: methods for path, methods in described(approving).items()
              if path == api or path.startswith(f"{api}/")}
    assert routes, api
    for path, methods in routes.items():
        address = re.sub(r"\{(\w+)\}", lambda m: "0" if m[1] == "number" else "x", path)
        for method in methods:
            answer = httpx.request(method.upper(), f"{approving}{address}", timeout=30)
            assert answer.status_code == 401, (method, path, answer.status_code, answer.text)


def test_every_act_refuses_someone_not_signed_in(approving):
    acts = {(method, path) for path, methods in described(approving).items()
            if path.startswith(ACTING) for method in methods}
    assert acts == set(ACTS)  # an act added says what it takes, and is refused unsigned
    for (method, path), body in ACTS.items():
        address = path.replace("{version}", DIGEST).replace("{sample}", "1")
        answer = httpx.request(method.upper(), f"{approving}{address}", json=body, timeout=30)
        assert answer.status_code == 401, (method, path, answer.status_code, answer.text)


def test_the_sidebar_lists_exactly_the_pages_whose_api_lets_each_person_in(approving, provider):
    for person in PEOPLE:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        listed = [place["page"] for place in httpx.get(
            f"{approving}/shell/api", headers=headers, timeout=30).json()["pages"]]
        for page, api in PAGES.items():
            answer = httpx.get(f"{approving}{api}", headers=headers, timeout=30)
            assert answer.status_code in (200, 403), (person, api, answer.text)
            assert (answer.status_code == 200) == (page in listed), (person, page, listed)


def test_every_route_of_the_cores_api_refuses_a_call_without_its_token(stack):
    """The core's API is two routers, each guarded for all of its routes (core/gateway.py): the
    service token's, for the scheduler, the command line and the team that runs a5s, and the
    run token's, for a worker's own run. So each route the core serves refuses a call with no
    token, and a route added outside the two, with no check, fails here."""
    routes = described(stack.url)
    assert {"/runs", "/status", "/run", "/run/tools/{name}", "/v1/messages"} <= set(routes)
    for path, methods in routes.items():
        address = re.sub(r"\{(\w+)\}", "x", path)
        for method in methods:
            answer = httpx.request(method.upper(), f"{stack.url}{address}", timeout=30)
            assert answer.status_code == 401, (method, path, answer.status_code, answer.text)


def test_the_core_serves_no_api_explorer_but_in_development(stack):
    """FastAPI's explorer pages load their scripts from a CDN, so the core serves them in
    development alone; its API's description stays."""
    deployed = TestClient(gateway.create_app(
        replace(stack.gateway, cfg=replace(stack.gateway.cfg, development=False))))
    assert [deployed.get(page).status_code for page in ("/docs", "/redoc")] == [404, 404]
    assert deployed.get("/openapi.json").status_code == 200


def test_the_channels_app_serves_no_api_explorer_but_in_development(approving):
    """FastAPI's explorer pages load their scripts from a CDN, so the channels app, the part of
    a5s people reach, serves them in development alone; its API's description stays."""
    assert [httpx.get(f"{approving}{page}", timeout=30).status_code
            for page in ("/docs", "/redoc")] == [404, 404]
    assert httpx.get(f"{approving}/openapi.json", timeout=30).status_code == 200
