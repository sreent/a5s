"""Round 11, reviewer B (B-2): what someone does with a sign-in counts by the groups that
sign-in showed, and that their latest one shows too. The core's check of an older sign-in, to
seal what was done with it, put its groups back in the gateway's cache, though a later sign-in
showed the person had left the group; and an approval made with a sign-in that showed no group
counted, later, in the role a group gives, once a later sign-in showed the group."""

import time

import httpx

from a5s import db
from test_approvals import decide, sign_in
from test_group_roles import OWNERS, in_force, kept, mapped, version
from test_proposals import asked, due_of, held, sweep
from test_proposals import decide as decide_held


def test_an_older_sign_in_checked_again_gives_back_no_group_left_since(stack, approving, provider):
    before = mapped(stack, approving, provider)  # billing-owners -> part-owner:billing, in force
    asked = version(stack, level=0)  # billing's owner's to approve

    # Ben approves while he's in billing-owners: recorded by the channels app, not yet sealed
    provider.claims = {"groups": [OWNERS]}
    token, salt = sign_in(approving, provider, asked["digest"], "ben")
    provider.claims = {}
    r = decide(approving, asked["digest"], token, salt)
    assert r.status_code == 200, r.text
    assert kept(stack, "ben") == [OWNERS]

    # He leaves the group, and signs in again, to his tasks: a5s keeps that he's left
    time.sleep(1.2)  # a later sign-in, by its iat
    later = provider.id_token(person="ben", groups=[])
    assert httpx.get(f"{approving}/tasks/api", timeout=30,
                     headers={"Authorization": f"Bearer {later}"}).status_code in (200, 404)
    assert kept(stack, "ben") == []
    stack.gateway.scenario.forget()  # the gateway's cache as it is after its 10 s read
    assert "part-owner:billing" not in stack.gateway.scenario.person("ben").roles

    # The settings sweep: it seals his approval, re-checking the old sign-in, then counts it
    stack.scheduler().apply_approved()
    with db.transaction(stack.admin) as conn:
        newest = conn.execute("select max(serial) as n from settings_versions").fetchone()["n"]
        outcome = conn.execute("select outcome from settings_proposals where digest = %s",
                               (asked["digest"],)).fetchone()["outcome"]
    _, problem = in_force(stack)
    # His approval stopped counting at his later sign-in, so it waits, and the version
    # before stays in force and runs
    assert newest == before and problem is None, (newest, outcome, problem)

def test_a_group_left_since_decides_no_held_change(stack, approving, provider):
    mapped(stack, approving, provider)  # billing-owners -> part-owner:billing, in force
    asked(stack)  # Ben asks: P-1 waits for billing's deciders
    [p] = held(stack)

    provider.claims = {"groups": [OWNERS]}
    decided = decide_held(approving, provider, [p["digest"]], person="dana")
    provider.claims = {}
    assert decided.status_code == 200, decided.text
    assert kept(stack, "dana") == [OWNERS]

    time.sleep(1.2)  # she leaves the group, and signs in again
    later = provider.id_token(person="dana", groups=[])
    httpx.get(f"{approving}/tasks/api", timeout=30, headers={"Authorization": f"Bearer {later}"})
    assert kept(stack, "dana") == []
    stack.gateway.scenario.forget()
    assert "part-owner:billing" not in stack.gateway.scenario.person("dana").roles

    sweep(stack)
    [p] = held(stack)
    # Her decision stopped counting at her later sign-in: it waits for Ana
    assert p["status"] == "waiting" and due_of(stack) == "2026-11-06", (p["status"], due_of(stack))


def test_an_approval_counts_in_no_role_its_sign_in_didnt_show(stack, approving, provider):
    before = mapped(stack, approving, provider)
    asked = version(stack, level=0)  # billing's owner's to approve
    token, salt = sign_in(approving, provider, asked["digest"], "omar")  # orders' owner, no groups
    r = decide(approving, asked["digest"], token, salt)
    assert r.status_code == 200, r.text
    stack.scheduler().apply_approved()  # sealed; it waits for billing's owner
    assert in_force(stack) == (before, None)

    time.sleep(1.2)  # weeks later, a group makes him one of billing's owners; he opens his tasks
    later = provider.id_token(person="omar", groups=[OWNERS])
    httpx.get(f"{approving}/tasks/api", timeout=30, headers={"Authorization": f"Bearer {later}"})
    assert kept(stack, "omar") == [OWNERS]
    stack.gateway.scenario.forget()
    stack.scheduler().apply_approved()
    with db.transaction(stack.admin) as conn:
        outcome = conn.execute("select outcome from settings_proposals where digest = %s",
                               (asked["digest"],)).fetchone()["outcome"]
    assert outcome is None, outcome  # his approval was made with a sign-in that showed no group
