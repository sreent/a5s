"""The administrators' page (core/administration.py, docs/administration.md): someone with one
of a5s's roles, or from the team that runs it, sees who holds each role and by what, the
directory or a group; what waits for whom; and the latest administrative acts, with whom an act
was about as a stand-in. It changes nothing, and nobody else sees it."""

import httpx

from test_group_roles import OWNERS, approve, mapped, version
from test_proposals import asked, held


def admin(url: str, provider, person: str, *groups: str) -> httpx.Response:
    token = provider.id_token(person=person, groups=list(groups))
    return httpx.get(f"{url}/admin/api", headers={"Authorization": f"Bearer {token}"}, timeout=30)


def test_only_someone_with_a_role_or_who_runs_a5s_sees_it(stack, approving, provider):
    assert httpx.get(f"{approving}/admin/api", timeout=30).status_code == 401
    refused = admin(approving, provider, "chen")  # who holds no role of a5s's
    assert refused.status_code == 403 and "roles" in refused.json()["detail"]
    for who in ("ana", "priya", "kofi"):  # an approver, the team that runs a5s, assurance
        assert admin(approving, provider, who).status_code == 200
    served = httpx.get(f"{approving}/admin/", timeout=30)
    assert "script-src 'self'" in served.headers["Content-Security-Policy"]


def test_it_shows_who_holds_each_role_and_by_what(stack, approving, provider):
    mapped(stack, approving, provider)
    admin(approving, provider, "ben", OWNERS)  # his sign-in shows he's in the group
    page = admin(approving, provider, "ana").json()
    owners = next(r for r in page["roles"] if r["role"] == "part-owner:billing")["held_by"]
    assert {(h["id"], tuple(h["by"])) for h in owners} == {
        ("ana", ("the directory",)), ("ben", (f"group {OWNERS}",))}
    assert {"group": OWNERS, "roles": ["part-owner:billing"], "people": 1} in page["groups"]
    assert page["claim"] == "groups"


def test_it_shows_what_waits_for_whom(stack, approving, provider):
    waiting = version(stack, level=0)
    asked(stack)  # a change the assistant asked for, held for billing's deciders
    assert held(stack)
    page = admin(approving, provider, "ana").json()
    [settings] = page["waiting"]["settings"]
    assert settings["serial"] == waiting["serial"] and settings["needs"]
    [changes] = page["waiting"]["held_changes"]
    assert changes["part"] == "billing" and changes["waiting"] == 1 and "ana" in changes["deciders"]
    assert page["waiting"]["release"] == []  # in development, whatever it is


def test_it_shows_the_latest_acts_and_is_itself_in_the_ledger(stack, approving, provider):
    asked_for = version(stack, level=0)
    approve(stack, approving, provider, asked_for["digest"], "ana")
    page = admin(approving, provider, "kofi").json()
    assert page["latest"][0]["action"] in ("apply", "approve")
    assert any(a["action"] == "approve" and a["by"] == "ana" for a in page["latest"])
    [read] = [e for e in stack.ledger() if e["kind"] == "audit"]
    assert (read["action"], read["args"]["by"], read["args"]["page"]) == (
        "administration", "kofi", True)


def test_an_administrator_reads_it_in_the_browser(stack, approving, provider, browser):
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}/admin/")
    page.wait_for_selector("#shown:not([hidden])", timeout=30000)
    assert page.inner_text("#who") == "Ana Ortiz"
    assert "instance-approver: Ana Ortiz (the directory)" in page.inner_text("#roles")
    assert "None: the settings in force give no group a role." in page.inner_text("#groups")
    assert page.evaluate("window.location.search") == ""
