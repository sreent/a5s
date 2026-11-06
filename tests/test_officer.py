"""The data protection officer's requests: to export, or erase, all a5s keeps about someone,
asked on the core's page, signed in afresh for that request alone, and carried out once, within
ten minutes, by whoever holds the core's service token. Neither does it alone, and a sign-in
anyone sees does nothing else (core/officer.py; round 8 of the critique, A1)."""

import base64
import hashlib
import secrets
import time
from dataclasses import replace
from urllib.parse import parse_qs

import httpx

from a5s import db
from a5s.core import officer
from conftest import CLIENT
from test_erase import erase
from test_export import SAID, export


def sign_in(url: str, provider, action: str, person: str, by: str = "noor") -> tuple[str, str]:
    """A sign-in to ask for this alone, made as the officer's page makes one: the token, and
    its salt."""
    salt, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = by
    went = httpx.get(f"{provider.url}/auth", params={
        "client_id": CLIENT, "redirect_uri": f"{url}/officer/", "state": "s",
        "nonce": officer.nonce(action, person, salt), "code_challenge": challenge.decode(),
        "code_challenge_method": "S256", "max_age": "0"})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    tokens = httpx.post(f"{url}/officer/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/officer/"}).json()
    assert set(tokens) == {"id_token"}  # nothing to make more sign-ins like it with
    return tokens["id_token"], salt


def ask(url: str, action: str, person: str, token: str | None, salt: str) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.post(f"{url}/officer/requests", headers=headers,
                      json={"action": action, "person": person, "salt": salt})


def asked(url: str, provider, action: str, person: str) -> dict:
    """The officer asks for this on the core's page."""
    r = ask(url, action, person, *sign_in(url, provider, action, person))
    assert r.status_code == 200, r.text
    return r.json()


def test_the_officer_asks_and_the_team_carries_it_out_once(stack, approving, provider):
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    told = asked(approving, provider, "export", "ben")
    assert (told["name"], told["command"]) == ("Ben Okafor", "a5s export --person ben --out <file>")
    r = export(stack, "ben")  # the team's command: no sign-in of the officer's in it
    assert r.status_code == 200 and SAID in r.text
    again = export(stack, "ben")  # nothing more
    assert again.status_code == 403 and "hasn't asked" in again.text
    [request] = [e for e in stack.ledger() if e["action"] == "ask"]
    [done] = [e for e in stack.ledger() if e["action"] == "export"]
    assert (request["args"]["by"], request["args"]["to"], done["args"]["by"]) == (
        "noor", "export", "noor")
    assert done["args"]["identity"]["token_sha256"] == request["args"]["token_sha256"]
    with db.transaction(stack.admin) as conn:  # the sign-in itself, let go once it's used
        [row] = conn.execute("select proof, used_at from officer_requests").fetchall()
    assert row["proof"] is None and row["used_at"] is not None


def test_a_request_is_for_its_action_and_person_alone(stack, approving, provider):
    stack.model.reply("Hello, Ana.")
    stack.say("I'm on leave next week, for my operation.", person="ana")
    asked(approving, provider, "export", "ben")
    seen, gone = export(stack, "ana"), erase(stack, "ben")
    assert (seen.status_code, gone.status_code) == (403, 403)
    assert "operation" not in seen.text
    assert export(stack, "ben").status_code == 200  # what was asked for, still


def test_no_sign_in_but_the_officers_own_for_this_asks_for_anything(stack, approving, provider):
    kept = provider.id_token(person="noor")  # as the web chat keeps one: no nonce, no auth_time
    r = ask(approving, "erase", "ben", kept, secrets.token_urlsafe(32))
    assert r.status_code == 403 and "wasn't to erase" in r.text
    token, salt = sign_in(approving, provider, "erase", "ana")  # for someone else
    assert ask(approving, "erase", "ben", token, salt).status_code == 403
    token, salt = sign_in(approving, provider, "erase", "ben", by="ana")  # by someone else
    r = ask(approving, "erase", "ben", token, salt)
    assert r.status_code == 403 and "only the data protection officer" in r.text
    stale = provider.id_token(officer.nonce("erase", "ben", salt), "noor",
                              signed_in_at=int(time.time()) - 3600)
    assert ask(approving, "erase", "ben", stale, salt).status_code == 401
    token, salt = sign_in(approving, provider, "erase", "ben")
    assert ask(approving, "erase", "ben", token, salt).status_code == 200
    assert ask(approving, "erase", "ben", token, salt).status_code == 409  # once
    assert export(stack, "ben", identity=kept).status_code == 403  # a sign-in alone: nothing


def test_a_request_waits_ten_minutes_for_the_team(stack, approving, provider):
    asked(approving, provider, "export", "ben")
    with db.transaction(stack.admin) as conn:
        conn.execute("update officer_requests set asked_at = now() - interval '11 minutes'")
    r = export(stack, "ben")
    assert r.status_code == 403 and "in the last ten minutes" in r.text


def test_only_the_officer_now_has_a_request_carried_out(stack, approving, provider, monkeypatch):
    asked(approving, provider, "export", "ben")
    people = dict(stack.gateway.scenario._people)
    people["noor"] = replace(people["noor"], roles=())
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)  # no longer the officer
    r = export(stack, "ben")
    assert r.status_code == 403 and "isn't the data protection officer now" in r.text


def test_the_officer_asks_in_the_browser(stack, approving, provider, browser):
    stack.model.reply("Noted, Ben.")
    stack.say(SAID, person="ben")
    provider.person = "noor"  # who signs in at the provider
    page = browser.new_page()
    page.goto(f"{approving}/officer/")
    page.wait_for_selector("#ask", state="visible", timeout=30000)
    page.select_option("#action", "erase")
    page.fill("#person", "ben")
    page.fill("#confirm", "ben")
    page.click("button[type=submit]")  # to the provider, afresh, and straight back
    page.wait_for_selector("#status >> text=a5s erase --person ben --confirm ben", timeout=30000)
    assert "Ben Okafor (ben)" in page.inner_text("#status")
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    assert provider.asked[-1]["max_age"] == "0"
    r = erase(stack, "ben")
    assert r.status_code == 200 and r.json()["gone"]["turns"] == 2, r.text


def test_a_request_goes_a_day_after_it_was_asked(stack, approving, provider):
    asked(approving, provider, "export", "ben")
    with db.transaction(stack.admin) as conn:
        conn.execute("update officer_requests set asked_at = now() - interval '25 hours'")
    with stack.client() as c:
        assert c.post("/retention/sweep").json()["deleted"]["requests"] == 1
