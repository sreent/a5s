"""Roles from the identity provider's groups (core/memberships.py, docs/administration.md):
the settings map groups to a5s's roles, and a sign-in that shows someone's in a group gives
them its roles, until a later sign-in shows they've left it. Giving a group a role needs the
role's owner as the directory names them; a version's own map gives nothing towards its
approval, and the one before it counts only once the core sealed it; and what a5s keeps of
someone's groups goes with them."""

import base64

import httpx
import pytest
import yaml

from a5s import db
from a5s.contract import SettingsError, parse_settings
from a5s.core import departures, erasure, export, memberships
from test_approvals import decide, sign_in

OWNERS, AUDITORS = "billing-owners", "a5s-auditors"
MAP = {OWNERS: ["part-owner:billing"], AUDITORS: ["auditor"]}


def version(stack, groups: dict | None = None, **changes) -> dict:
    """The next version of the sample's settings, proposed: with `groups`, and these changes
    to assistant-finance."""
    with db.transaction(stack.admin) as conn:
        raw = bytes(conn.execute("select raw from settings_versions order by serial desc "
                                 "limit 1").fetchone()["raw"])
    settings = yaml.safe_load(raw)
    settings["instances"]["assistant-finance"].update(changes)
    if groups is not None:
        settings["groups"] = groups
    raw = yaml.safe_dump({**settings, "serial": settings["serial"] + 1}).encode()
    with stack.client() as c:
        r = c.post("/settings/proposals", json={"raw": base64.b64encode(raw).decode()})
    r.raise_for_status()
    return r.json()


def approve(stack, approving, provider, digest: str, person: str, *groups: str) -> dict:
    """Someone approves a version on the page, signed in with these groups; then the core
    seals what they did, and applies the version if it has all it needs."""
    provider.claims = {"groups": list(groups)}
    token, salt = sign_in(approving, provider, digest, person)
    r = decide(approving, digest, token, salt)
    provider.claims = {}
    stack.scheduler().apply_approved()
    stack.gateway.scenario.forget()
    return r.json()


def in_force(stack) -> tuple[int, str | None]:
    """The serial in force, and why it can't run, if it can't, as the core checks it at each
    run, sealing it if it's approved."""
    with db.transaction(stack.cfg.database_url) as conn:
        _, problem = stack.gateway.settings_in_force(conn)
        serial = conn.execute("select max(serial) as n from settings_versions").fetchone()["n"]
    stack.gateway.scenario.forget()
    return serial, problem


def mapped(stack, approving, provider, groups: dict = MAP) -> int:
    """A version that gives groups roles, approved by Ana, who owns billing and approves
    instances in the directory, and in force."""
    asked = version(stack, groups)
    approve(stack, approving, provider, asked["digest"], "ana")
    serial, problem = in_force(stack)
    assert serial == asked["serial"] and problem is None
    return serial


def kept(stack, person: str) -> list[str] | None:
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select groups from sign_in_groups where person = %s",
                           (person,)).fetchone()
    return list(row["groups"]) if row else None


def reading(url: str, provider, person: str, *groups: str) -> httpx.Response:
    token = provider.id_token(person=person, groups=list(groups))
    return httpx.get(f"{url}/audit/api", headers={"Authorization": f"Bearer {token}"}, timeout=30)


def test_the_settings_give_groups_only_the_roles_people_use_by_signing_in():
    base = b"instances:\n  a: {definition: assistant, serves: [ana], parts: [billing]}\n"
    found = parse_settings(base + b"groups:\n  g1: [part-owner:billing, auditor, auditor]\n")
    assert found.groups == {"g1": ("auditor", "part-owner:billing")}
    for wrong in (b"groups: {g1: [release-approver]}", b"groups: {g1: [assurance]}",
                  b"groups: {g1: [agent-owner:assistant]}", b"groups: {g1: [part-owner:orders]}"):
        with pytest.raises(SettingsError):
            parse_settings(base + wrong)


def test_a_sign_in_gives_the_roles_its_groups_map_until_one_shows_they_left(
        stack, approving, provider):
    assert reading(approving, provider, "ben", AUDITORS).status_code == 403  # nothing maps it
    mapped(stack, approving, provider)
    assert reading(approving, provider, "ben", AUDITORS, "the-canteen").status_code == 200
    assert kept(stack, "ben") == [AUDITORS]  # only the groups the settings name
    auditors = {p.id for p in stack.gateway.scenario.holders("auditor")}
    assert "ben" in auditors  # who holds it, for those who ask, from his latest sign-in
    assert reading(approving, provider, "ben").status_code == 403  # he's left it
    assert kept(stack, "ben") == [] and "ben" not in {
        p.id for p in stack.gateway.scenario.holders("auditor")}
    assert "ben" not in {p.id for p in memberships.rooted(stack.gateway.scenario).holders(
        "auditor")}  # and the directory never named him


def test_giving_a_group_a_role_needs_its_owner_in_the_directory(stack, approving, provider):
    asked = version(stack, {AUDITORS: ["auditor"], "orders-owners": ["part-owner:orders"]})
    assert {"text": "Everyone in the group a5s-auditors holds auditor, as their sign-ins show "
                    "they're in it.", "widens": True} in asked["changes"]  # what they approve
    told = approve(stack, approving, provider, asked["digest"], "omar")  # who owns orders
    assert any("instance-approver named in the directory hasn't approved giving a5s-auditors"
               in need for need in told["needs"])
    assert in_force(stack)[0] < asked["serial"]  # it waits
    approve(stack, approving, provider, asked["digest"], "ana")  # who approves instances
    assert in_force(stack) == (asked["serial"], None)


def test_someone_a_group_makes_an_owner_approves_their_part_while_theyre_in_it(
        stack, approving, provider):
    mapped(stack, approving, provider)
    asked = version(stack, level=0)  # billing's: its owner's to approve
    assert approve(stack, approving, provider, asked["digest"], "ben", OWNERS)["needs"] == []
    assert in_force(stack) == (asked["serial"], None)
    httpx.get(f"{approving}/tasks/api", timeout=30, headers={  # he signs in, out of the group
        "Authorization": f"Bearer {provider.id_token(person='ben', groups=[])}"})
    serial, problem = in_force(stack)
    assert serial == asked["serial"] and "aren't approved" in problem  # what he approved


def test_a_versions_own_map_gives_nothing_towards_it(stack, approving, provider):
    asked = version(stack, {"newcomers": ["part-owner:billing"]}, level=0)
    told = approve(stack, approving, provider, asked["digest"], "chen", "newcomers")
    assert told.get("approved") is not True or told["needs"]
    assert in_force(stack)[0] < asked["serial"]


def test_the_map_before_counts_only_once_the_core_sealed_it(stack, approving, provider):
    before = mapped(stack, approving, provider)
    asked = version(stack, level=0)
    approve(stack, approving, provider, asked["digest"], "ben", OWNERS)
    assert in_force(stack) == (asked["serial"], None)
    with db.transaction(stack.admin) as conn:  # as someone who writes into the database would
        conn.execute("update settings_versions set sealed = 'made-up' where serial = %s",
                     (before,))
    serial, problem = in_force(stack)
    assert serial == asked["serial"] and "aren't approved" in problem  # his role gives nothing


def test_a_sign_in_with_too_many_groups_to_show_gives_none(stack, approving, provider):
    mapped(stack, approving, provider)
    token = provider.id_token(person="ben", _claim_names={"groups": "src1"})
    r = httpx.get(f"{approving}/audit/api", headers={"Authorization": f"Bearer {token}"},
                  timeout=30)
    assert r.status_code == 403 and kept(stack, "ben") in (None, [])


def test_someones_groups_go_with_them(stack, approving, provider):
    mapped(stack, approving, provider)
    assert reading(approving, provider, "ben", AUDITORS).status_code == 200
    with db.transaction(stack.admin) as conn:
        found = export.gather(conn, "ben")
    assert [r["groups"] for r in found["groups"]] == [[AUDITORS]]
    with db.transaction(stack.cfg.database_url) as conn:  # as the officer's erasure does
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert gone.get("sign_in_groups") == 1 and kept(stack, "ben") is None
    assert reading(approving, provider, "ana", AUDITORS).status_code == 200
    with db.transaction(stack.cfg.database_url) as conn:  # and archiving someone who left
        departures.archive(conn, "ana", stack.gateway.clock())
    assert kept(stack, "ana") is None
