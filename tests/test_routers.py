"""The pages people sign in to for one thing are each a router of their own in the channels app,
whose API checks who's signed in for every route, before the route's own check (core/web.py):
the studio's, the settings app's, the notebook's, people's own tasks', the auditors' and the
administrators'. So a route added to one of them can't be reached by someone who isn't signed
in, and a route outside them must be one of those that check for themselves.

The sidebar every page shows lists a page by the check its router makes, so it lists exactly the
pages whose API lets each person in."""

import re

import httpx
import pytest

SIGNED_IN = ("/studio/api", "/settings/api", "/notebook/api", "/tasks/api", "/audit/api",
             "/admin/api")
# The routes that check for themselves: the chats', each with its own token; the web chat's;
# each act's page, whose sign-in is for that act alone, and its sign-in; and the sidebar
OWN = ("/channels/", "/chat/", "/approve/", "/decide/", "/grade/", "/officer/", "/shell/api")
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


def test_the_sidebar_lists_exactly_the_pages_whose_api_lets_each_person_in(approving, provider):
    for person in PEOPLE:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        listed = httpx.get(f"{approving}/shell/api", headers=headers, timeout=30).json()["pages"]
        for page, api in PAGES.items():
            answer = httpx.get(f"{approving}{api}", headers=headers, timeout=30)
            assert answer.status_code in (200, 403), (person, api, answer.text)
            assert (answer.status_code == 200) == (page in listed), (person, page, listed)
