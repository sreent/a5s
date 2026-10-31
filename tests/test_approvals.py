"""Approving settings where people work: a card in each instance approver's chat, and the
decision on the core's own page, signed through the identity provider for that one version,
once. The core seals what it checked, checks the seal again at every run, and applies the
version once an instance approver has approved it."""

import base64
import hashlib
import secrets
import time
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest
import yaml

from a5s import db
from a5s.core import approvals, inbox
from a5s.core.identity import IdentityConfig, Verifier
from conftest import CLIENT, SEAL_KEY, free_port, serve

CHEN_TOO = ["ana", "ben", "chen"]


def in_force_serial(stack) -> int:
    return yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())["serial"]


@pytest.fixture
def approving(stack, provider):
    """The core, signing people in through the provider: the channels, where approvers
    decide, and the gateway, which asks them and applies what they approve."""
    verifier = Verifier(IdentityConfig(issuer=provider.url, audience=("a5s", CLIENT)))
    port = free_port()
    stack.gateway.identity = verifier
    stack.gateway.cfg = replace(stack.gateway.cfg, webchat_client_id=CLIENT,
                                public_url=f"http://127.0.0.1:{port}")
    cfg = replace(stack.as_role("channels"), webchat_client_id=CLIENT, development=False)
    with serve(inbox.create_app(replace(stack.gateway, cfg=cfg, identity=verifier)), port) as url:
        yield url


def proposed(stack, **changes) -> dict:
    """Ask the instance approvers to approve the next version of the sample's settings, with
    these changes to assistant-finance."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    settings["instances"]["assistant-finance"].update(changes)
    raw = yaml.safe_dump({**settings, "serial": settings["serial"] + 1}).encode()
    with stack.client() as c:
        r = c.post("/settings/proposals", json={"raw": base64.b64encode(raw).decode()})
    r.raise_for_status()
    return r.json()


def sign_in(url: str, provider, version: str, person: str = "ana") -> tuple[str, str]:
    """A sign-in to approve a version, made as the page makes one: the token, and its salt."""
    salt, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = person
    went = httpx.get(f"{provider.url}/auth", params={
        "client_id": CLIENT, "redirect_uri": f"{url}/approve/", "state": "s",
        "nonce": approvals.nonce(version, salt), "code_challenge": challenge.decode(),
        "code_challenge_method": "S256", "max_age": "0"})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    tokens = httpx.post(f"{url}/approve/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/approve/"}).json()
    assert set(tokens) == {"id_token"}  # nothing to make more sign-ins like it with
    return tokens["id_token"], salt


def decide(url: str, version: str, token: str | None, salt: str, *, review: bool = False):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.post(f"{url}/approve/settings/{version}{'/review' if review else ''}",
                      json={"salt": salt}, headers=headers)


def serves(stack) -> list[str]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select serves from instances where id = 'assistant-finance'"
                            ).fetchone()["serves"]


def test_an_approver_is_asked_where_they_work_and_what_they_approve_is_applied(stack, approving,
                                                                               provider):
    now = in_force_serial(stack)
    asked = proposed(stack, serves=CHEN_TOO)
    assert (asked["serial"], asked["asked"], asked["new"]) == (now + 1, ["ana"], True)
    assert asked["changes"] == [{"text": "assistant-finance serves Chen Wei as well.", "widens": True}]
    assert asked["link"] == f"{approving}/approve/?settings={asked['digest']}"
    [told] = stack.inbox("ana")  # she's not written to a5s anywhere, so it waits in her inbox
    assert told["from"] == "a5s" and told["text"] == (
        f"Serial {now + 1} of a5s's settings waits for an instance approver to approve it.\n"
        "What it changes:\n- assistant-finance serves Chen Wei as well.\n"
        f"Review it, and approve it only if you mean it, at {asked['link']}")

    token, salt = sign_in(approving, provider, asked["digest"])
    seen = decide(approving, asked["digest"], token, salt, review=True).json()
    assert (seen["status"], seen["you"], seen["you_approved"], seen["in_force"]) == (
        "waiting", "Ana Ortiz", False, now)
    assert seen["changes"] == asked["changes"] and seen["approved_by"] == []
    approved = decide(approving, asked["digest"], token, salt)
    assert approved.json() == {"approved": True, "serial": now + 1, "by": "Ana Ortiz"}
    assert provider.asked[-1]["max_age"] == "0"  # she signed in afresh for it

    assert "chen" not in serves(stack)  # not until the gateway applies it
    stack.scheduler().apply_approved()
    assert serves(stack) == CHEN_TOO
    stack.model.reply("Hello, Chen.")
    assert stack.say("Hello", person="chen") == "Hello, Chen."
    assert decide(approving, asked["digest"], token, salt, review=True).json()["status"] == "applied"

    entries = stack.ledger()
    [approval] = [e for e in entries if e["action"] == "approve"]
    assert approval["args"]["by"] == "ana" and approval["args"]["serial"] == now + 1
    assert token not in str(entries)  # the ledger keeps a hash of the sign-in, not the sign-in
    applied = [e for e in entries if e["action"] == "apply" and e.get("instance") == "assistant-finance"]
    assert (applied[-1]["args"]["serial"], applied[-1]["args"]["signed_by"]) == (now + 1, ["ana"])
    assert [e["args"]["to"] for e in entries if e["action"] == "ask-approval"] == ["ana"]
    assert stack.verify().ok


def test_a_version_is_asked_about_once(stack, approving):
    first = proposed(stack, level=0)
    again = proposed(stack, level=0)
    assert (again["new"], again["asked"], again["digest"]) == (False, [], first["digest"])
    assert len(stack.inbox("ana")) == 1


def test_a_sign_in_approves_only_the_version_it_was_for_and_only_once(stack, approving, provider):
    lower = proposed(stack, level=0)
    fewer = proposed(stack, serves=["ana"])
    token, salt = sign_in(approving, provider, lower["digest"])
    other = decide(approving, fewer["digest"], token, salt)
    assert other.status_code == 403 and "wasn't to approve this version" in other.json()["detail"]
    assert decide(approving, lower["digest"], token, "another salt, made up").status_code == 403
    assert decide(approving, lower["digest"], token, salt).status_code == 200
    again = decide(approving, lower["digest"], token, salt)
    assert again.status_code == 409 and "approved this version already" in again.json()["detail"]
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) from settings_approvals").fetchone()["count"] == 1


def test_only_an_instance_approvers_fresh_sign_in_for_this_approves(stack, approving, provider):
    asked = proposed(stack, serves=CHEN_TOO)
    version = asked["digest"]
    token, salt = sign_in(approving, provider, version, person="ben")
    ben = decide(approving, version, token, salt)
    assert ben.status_code == 403 and "Ben Okafor isn't one" in ben.json()["detail"]

    salt = secrets.token_urlsafe(32)
    bound = approvals.nonce(version, salt)
    stale = provider.id_token(bound, "ana", signed_in_at=int(time.time()) - 3600)
    assert decide(approving, version, stale, salt).status_code == 401
    elsewhere = provider.id_token(bound, "ana", aud="a5s")  # a sign-in for the API, not the page
    assert decide(approving, version, elsewhere, salt).json()["detail"] == "that sign-in is for something else"
    assert decide(approving, version, None, salt).status_code == 401
    forged = provider.id_token(bound, "ana")
    forged = forged.rsplit(".", 1)[0] + "." + base64.urlsafe_b64encode(b"x" * 256).rstrip(b"=").decode()
    assert decide(approving, version, forged, salt).status_code == 401
    assert decide(approving, "f" * 64, provider.id_token(bound, "ana"), salt).status_code == 403

    stack.scheduler().apply_approved()
    assert serves(stack) == ["ana", "ben"]
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) from settings_approvals").fetchone()["count"] == 0


def test_editing_the_database_approves_nothing(stack, approving, provider):
    asked = proposed(stack, serves=CHEN_TOO)
    with db.transaction(stack.admin) as conn:  # an approval the core didn't seal
        conn.execute(
            "insert into settings_approvals (scenario, digest, person, token, nonce, salt, issuer, "
            "subject, seal) values ('sample', %s, 'ana', 'made up', 'n', 's', 'i', 'u', 'forged')",
            (asked["digest"],))
    stack.scheduler().apply_approved()
    assert serves(stack) == ["ana", "ben"]

    with db.transaction(stack.admin) as conn:
        conn.execute("delete from settings_approvals")
    token, salt = sign_in(approving, provider, asked["digest"])
    assert decide(approving, asked["digest"], token, salt).status_code == 200
    stack.scheduler().apply_approved()
    assert serves(stack) == CHEN_TOO
    with db.transaction(stack.admin) as conn:  # her approval, moved to someone else
        conn.execute("update settings_approvals set subject = 'u-someone-else'")
    stack.gateway._checked.clear()  # as a gateway that has just started
    with stack.client() as c:
        refused = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello", "chen")}})
    assert refused.status_code == 409
    assert "no instance approver signed the settings in force" in refused.json()["detail"]["reasons"]


def test_an_approval_outlasts_the_providers_keys_but_not_the_cores(stack, approving, provider):
    asked = proposed(stack, level=0)
    token, salt = sign_in(approving, provider, asked["digest"])
    assert decide(approving, asked["digest"], token, salt).status_code == 200
    stack.scheduler().apply_approved()

    def in_force(*keys: str) -> tuple:
        stack.gateway.cfg = replace(stack.gateway.cfg, seal_keys=keys)
        stack.gateway._checked.clear()  # as a gateway that has just started
        with db.transaction(stack.cfg.database_url) as conn:
            settings, problem = stack.gateway.settings_in_force(conn)
        return settings and settings.serial, problem

    provider.rotate()  # the key that signed her sign-in is withdrawn
    approved = asked["serial"]
    assert in_force(SEAL_KEY) == (approved, None)
    assert in_force("a new seal key", SEAL_KEY) == (approved, None)  # the core moving to a new key
    assert in_force("a new seal key") == (None, "no instance approver signed the settings in force")


def test_a_version_waiting_for_approval_is_let_go_once_a_newer_one_is_in_force(stack, approving,
                                                                               provider):
    asked = proposed(stack, level=0)
    stack.settle(serves=["ana"])  # the same serial, signed with Ana's key, applied first
    token, salt = sign_in(approving, provider, asked["digest"])
    assert decide(approving, asked["digest"], token, salt, review=True).json()["status"] == "superseded"
    late = decide(approving, asked["digest"], token, salt)
    assert late.status_code == 409 and "it's superseded" in late.json()["detail"]
    stack.scheduler().apply_approved()
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select outcome from settings_proposals").fetchone()["outcome"] == "superseded"
    assert serves(stack) == ["ana"]


def test_the_core_asks_nobody_about_a_version_it_couldnt_apply(stack, approving):
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    unknown = {**settings, "serial": settings["serial"] + 1,
               "instances": {"helper": {"definition": "helper", "serves": ["ana"]}}}
    with stack.client() as c:
        garbled = c.post("/settings/proposals", json={"raw": "not base64 at all!"})
        older = c.post("/settings/proposals", json={
            "raw": base64.b64encode(yaml.safe_dump(settings).encode()).decode()})
        nobody = c.post("/settings/proposals", json={
            "raw": base64.b64encode(yaml.safe_dump(unknown).encode()).decode()})
    assert garbled.status_code == 400
    assert older.status_code == 409
    assert f"isn't above {settings['serial']}" in older.json()["detail"]["reasons"][0]
    assert nobody.status_code == 409
    assert "helper names helper, which no release here has" in nobody.json()["detail"]["reasons"]
    assert stack.inbox("ana") == []
    assert [e["decision"] for e in stack.ledger() if e["action"] == "propose"] == ["deny", "deny"]


def test_approving_where_people_work_needs_sign_in_and_the_cores_seal(stack, provider):
    with stack.client() as c:
        r = c.post("/settings/proposals", json={"raw": base64.b64encode(b"serial: 9").decode()})
    assert r.status_code == 503 and "identity provider" in r.json()["detail"]
    assert httpx.get(f"{stack.channels_url}/approve/").status_code == 404  # in development

    stack.gateway.identity = Verifier(IdentityConfig(issuer=provider.url, audience=("a5s", CLIENT)))
    stack.gateway.cfg = replace(stack.gateway.cfg, webchat_client_id=CLIENT, seal_keys=())
    with stack.client() as c:
        r = c.post("/settings/proposals", json={"raw": base64.b64encode(b"serial: 9").decode()})
    assert r.status_code == 503 and "seal key" in r.json()["detail"]


def test_the_page_runs_only_its_own_script_and_shows_only_text(approving):
    page = httpx.get(f"{approving}/approve/")
    script = httpx.get(f"{approving}/approve/approve.js")
    assert page.status_code == script.status_code == 200
    policy = page.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe" not in policy and "innerHTML" not in script.text
    assert httpx.get(f"{approving}/approve/config").json()["signin"]["client_id"] == CLIENT


def test_an_approver_reviews_and_approves_in_the_browser(stack, approving, provider, browser):
    asked = proposed(stack, serves=CHEN_TOO, level=0)
    page = browser.new_page()
    page.goto(asked["link"])  # to the provider, afresh, and straight back
    page.wait_for_selector("#changes >> text=Chen Wei", timeout=30000)
    assert page.inner_text("#who") == "Ana Ortiz"
    assert page.locator("#changes li").all_inner_texts() == [
        "assistant-finance serves Chen Wei as well. This widens what agents do.",
        "assistant-finance's level goes from 1 to 0."]
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    page.click("#approve")
    page.wait_for_selector(f"#status >> text=You approved serial {asked['serial']}", timeout=30000)
    assert not page.is_visible("#approve")
    stack.scheduler().apply_approved()
    assert serves(stack) == CHEN_TOO
    assert provider.asked[-1]["max_age"] == "0"
