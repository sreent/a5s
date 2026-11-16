"""Suspending and resuming an instance from its page in the studio (core/suspension.py,
docs/studio.md): signed in afresh for that act alone, by those who run it, own its agent, or
are on the team that runs a5s, to suspend it; by whoever suspended it, with a second factor
where the deployment asks for one, to resume it. The channels app records it with the sign-in,
changing nothing; the gateway checks it again and carries it out at its next sweep."""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs

import httpx

from a5s import db
from a5s.core import suspension
from conftest import CLIENT
from test_mfa import WITH_MFA, asking
from test_proposals import sweep
from test_studio_home import api


def act(url: str, provider, action: str, person: str, instance: str = "assistant-finance",
        fresh: bool = True, nonce: str | None = None) -> httpx.Response:
    """An act asked for on the instance's page, with a sign-in made for it as the page makes
    one: through the provider, afresh, its nonce bound to the act."""
    salt, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = person
    query = {"client_id": CLIENT, "redirect_uri": f"{url}/studio/", "state": "s",
             "nonce": nonce or suspension.nonce(action, instance, salt),
             "code_challenge": challenge.decode(), "code_challenge_method": "S256",
             **({"max_age": "0"} if fresh else {})}
    went = httpx.get(f"{provider.url}/auth", params=query)
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    token = httpx.post(f"{url}/studio/sign-in/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/studio/"}).json()["id_token"]
    return httpx.post(f"{url}/studio/api/instances/{instance}/status",
                      json={"action": action, "salt": salt},
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)


def status(stack, instance: str = "assistant-finance") -> tuple[str, str | None]:
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select status, suspended_by from instances where id = %s",
                           (instance,)).fetchone()
    return row["status"], row["suspended_by"]


def standing(url: str, provider, person: str) -> dict:
    found = api(url, provider, person, "instances/assistant-finance/standing")
    found.raise_for_status()
    return found.json()


def test_its_deputy_suspends_it_from_its_page_and_resumes_it(stack, approving, provider):
    assert standing(approving, provider, "ben")["may"] == "suspend"
    asked = act(approving, provider, "suspend", "ben")
    assert asked.status_code == 200, asked.text
    assert (asked.json()["action"], asked.json()["by"]) == ("suspend", "Ben Okafor")
    assert status(stack) == ("active", None)  # the channels app changes nothing itself
    now = standing(approving, provider, "ana")  # its owner sees it asked, and may do nothing more
    assert now["asked"]["by"] == "Ben Okafor" and now["may"] is None
    assert act(approving, provider, "suspend", "ana").status_code == 409  # one at a time
    sweep(stack)  # the gateway checks the sign-in again, and carries it out
    assert status(stack) == ("suspended", "ben")
    assert stack.say("Hello?", person="ben") == (
        "The assistant is suspended, because you suspended it. Resume it to carry on.")
    now = standing(approving, provider, "ana")
    assert (now["suspended_by"], now["may"], now["asked"]) == ("Ben Okafor", None, None)
    refused = act(approving, provider, "resume", "ana")  # only Ben resumes his suspension
    assert refused.status_code == 403 and "only Ben Okafor" in refused.json()["detail"]
    assert standing(approving, provider, "ben")["may"] == "resume"
    assert act(approving, provider, "resume", "ben").status_code == 200
    sweep(stack)
    assert status(stack) == ("active", None)
    kept = [(e["action"], e["args"]["by"], e["args"]["identity"]) for e in stack.ledger()
            if e["kind"] == "admin" and e["action"] in ("ask", "suspend", "resume")]
    assert kept == [("ask", "ben", "verified: a sign-in to suspend it alone"),
                    ("suspend", "ben", "verified: a sign-in to suspend it alone"),
                    ("ask", "ben", "verified: a sign-in to resume it alone"),
                    ("resume", "ben", "verified: a sign-in to resume it alone")]
    [made] = [e for e in stack.ledger() if e["action"] == "suspend"]
    assert len(made["args"]["token_sha256"]) == 64 and made["args"]["issuer"] == provider.url
    with db.transaction(stack.admin) as conn:  # each sign-in let go, kept by its hash alone
        assert {(r["outcome"], r["proof"]) for r in conn.execute(
            "select outcome, proof from status_requests")} == {("made", None)}


def test_only_those_who_run_it_own_its_agent_or_run_a5s_may_suspend_it(stack, approving, provider):
    for person in ("ana", "ben", "priya"):  # its owner and deputy, and its agent's owner
        assert standing(approving, provider, person)["may"] == "suspend", person
    assert act(approving, provider, "suspend", "priya").status_code == 200
    sweep(stack)
    assert status(stack) == ("suspended", "priya")
    # Omar owns orders, so he may watch no instance here: nor suspend one
    assert api(approving, provider, "omar", "instances/assistant-finance/standing").status_code == 403
    assert act(approving, provider, "suspend", "omar").status_code == 403


def test_the_team_that_runs_a5s_may_suspend_any_instance_it_sees(stack):
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        inst = conn.execute(f"select {suspension.COLUMNS} from instances where id = "
                            "'assistant-finance'").fetchone()
    tomas, chen = scenario.person("tomas"), scenario.person("chen")
    assert suspension.may(scenario, tomas, inst, "suspend", "platform") is None  # on the team
    refused = suspension.may(scenario, chen, inst, "suspend", "platform")
    assert refused is not None and refused.status == 403
    resumed = suspension.may(scenario, tomas, {**inst, "status": "suspended", "suspended_by": "ben"},
                             "resume", "platform")  # the team resumes only its own suspensions
    assert resumed is not None and "only Ben Okafor, who suspended it" in resumed.reason


def test_a_sign_in_not_made_for_it_is_refused(stack, approving, provider):
    stale = act(approving, provider, "suspend", "ben", fresh=False)  # one the browser kept
    assert stale.status_code == 401 and "sign in again" in stale.json()["detail"]
    other = act(approving, provider, "suspend", "ben",
                nonce=suspension.nonce("suspend", "watcher-finance", "x" * 20))
    assert other.status_code == 403 and "wasn't to suspend assistant-finance" in other.json()["detail"]
    wrong = act(approving, provider, "retire", "ben")
    assert wrong.status_code == 404
    assert status(stack) == ("active", None)


def test_resuming_asks_for_a_second_factor_and_suspending_doesnt(stack, approving, provider):
    asking(stack)  # the deployment asks for one for what counts
    assert act(approving, provider, "suspend", "ben").status_code == 200  # safer, so none needed
    sweep(stack)
    assert status(stack) == ("suspended", "ben")
    refused = act(approving, provider, "resume", "ben")
    assert refused.status_code == 401 and "second factor" in refused.json()["detail"]
    provider.claims = dict(WITH_MFA)
    assert act(approving, provider, "resume", "ben").status_code == 200
    sweep(stack)
    assert status(stack) == ("active", None)


def test_the_gateway_checks_it_again_and_refuses_what_no_longer_holds(stack, approving, provider):
    """Recorded, then Ben is no longer its deputy when the gateway comes to it: it isn't made,
    and he hears why in his digest."""
    assert act(approving, provider, "suspend", "ben").status_code == 200
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set deputy = 'chen' where id = 'assistant-finance'")
    sweep(stack)
    assert status(stack) == ("active", None)
    with db.transaction(stack.admin) as conn:
        [row] = conn.execute("select outcome, proof from status_requests").fetchall()
        told = conn.execute("select text from digest_items where person = 'ben'").fetchall()
    assert row["proof"] is None and row["outcome"].startswith("suspending it is for those who run it")
    assert any("a5s didn't suspend assistant-finance" in t["text"] for t in told), told
    [refusal] = [e for e in stack.ledger() if e["action"] == "refuse-sign-in"]
    assert refusal["args"]["what"].startswith("suspend assistant-finance: suspending it is for")


def test_someone_suspends_it_from_its_page_in_the_browser(stack, approving, provider, browser):
    """Ben, its deputy, suspends it from its page: asked first, then signed in afresh for that
    alone; once the gateway has carried it out, he may resume it, and nobody else may."""
    from conftest import accessible
    from test_ui_pages import shot

    provider.person = "ben"
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/studio/instances/assistant-finance")
    page.wait_for_selector("button:has-text('Suspend it')", timeout=30000)
    before = len(provider.asked)
    page.click("button:has-text('Suspend it')")
    dialog = page.locator("dialog[open]")
    assert "stops at its next step" in dialog.inner_text()
    dialog.locator("button:has-text('Sign in and suspend it')").click()
    page.wait_for_selector("#asked", timeout=30000)  # back, and asked: a5s carries it out
    assert "Ben Okafor asked to suspend it" in page.inner_text("#asked")
    assert page.locator("button:has-text('Suspend it')").count() == 0
    went = provider.asked[before:]  # the sign-in went afresh, with the act's own nonce
    assert went and went[-1].get("max_age") == "0"
    assert page.evaluate("location.pathname") == "/studio/instances/assistant-finance"
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    sweep(stack)
    assert status(stack) == ("suspended", "ben")
    page.reload()
    page.wait_for_selector("button:has-text('Resume it')", timeout=30000)
    assert "suspended by Ben Okafor" in page.inner_text(".page-head .meta")
    assert page.locator(".page-head .badge.warn").first.inner_text().strip().endswith("suspended")
    accessible(page)
    shot(page, "studio-instance-suspended")
