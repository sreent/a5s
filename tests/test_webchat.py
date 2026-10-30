"""The web chat: a page the core serves, where people sign in with any OpenID Connect
provider and talk to the agents through the local channel."""

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest

from a5s.core import inbox
from a5s.core.identity import IdentityConfig, Verifier
from conftest import CLIENT, free_port, serve


def channels(stack, **gateway) -> serve:
    return serve(inbox.create_app(replace(stack.gateway, cfg=stack.as_role("channels"), **gateway)),
                 free_port())


@pytest.fixture
def signing_in(stack, provider):
    """The core's channels, as deployed, with the web chat signing in through the provider."""
    verifier = Verifier(IdentityConfig(issuer=provider.url, audience=("a5s", CLIENT)))
    cfg = replace(stack.as_role("channels"), webchat_client_id=CLIENT, development=False)
    with serve(inbox.create_app(replace(stack.gateway, cfg=cfg, identity=verifier)),
               free_port()) as url:
        yield url


# The page and the core's side of it

def test_the_page_runs_only_its_own_script_and_shows_only_text(stack):
    with channels(stack) as url:
        page = httpx.get(f"{url}/chat/")
        script = httpx.get(f"{url}/chat/app.js")
        assert httpx.get(f"{url}/").headers["location"] == "/chat/"
        assert httpx.get(f"{url}/chat/settings.py").status_code == 404
    assert page.status_code == script.status_code == 200
    policy = page.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe" not in policy and "innerHTML" not in script.text
    assert script.headers["content-type"].startswith("text/javascript")


def test_in_development_the_page_asks_who_you_are(stack):
    with channels(stack) as url:
        config = httpx.get(f"{url}/chat/config").json()
    assert config == {"signin": None, "development": True, "agents": ["assistant", "watcher"]}


def test_the_web_chat_is_off_where_nobody_could_sign_in_to_it(stack):
    deployed = replace(stack.as_role("channels"), development=False)  # no provider, no client id
    with serve(inbox.create_app(replace(stack.gateway, cfg=deployed)), free_port()) as url:
        found = [httpx.get(f"{url}{path}").status_code for path in ("/", "/chat/", "/chat/config",
                                                                     "/chat/app.js")]
    assert found == [404] * 4
    assert inbox.chats_on(replace(stack.gateway, cfg=deployed)) == ["the command line"]


def test_people_sign_in_through_the_organisations_own_provider(signing_in, provider):
    config = httpx.get(f"{signing_in}/chat/config").json()
    assert config["development"] is False
    assert config["signin"] == {"authorization_endpoint": f"{provider.url}/auth",
                                "end_session_endpoint": f"{provider.url}/logout",
                                "client_id": CLIENT, "scope": "openid profile"}


def test_the_core_passes_on_the_sign_in_and_keeps_the_providers_access_token(signing_in, provider):
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    back = f"{signing_in}/chat/"
    went = httpx.get(f"{provider.url}/auth", params={
        "client_id": CLIENT, "redirect_uri": back, "state": "s", "nonce": "n",
        "code_challenge": challenge, "code_challenge_method": "S256"})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]

    wrong = httpx.post(f"{signing_in}/chat/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": "not it",
        "redirect_uri": back})
    assert wrong.status_code == 400  # the provider checks the verifier
    went = httpx.get(f"{provider.url}/auth", params={
        "client_id": CLIENT, "redirect_uri": back, "state": "s", "nonce": "n",
        "code_challenge": challenge, "code_challenge_method": "S256"})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    tokens = httpx.post(f"{signing_in}/chat/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": back}).json()
    assert set(tokens) == {"id_token", "refresh_token"}  # never the provider's access token
    assert provider.forms[-1]["client_id"] == CLIENT and "client_secret" not in provider.forms[-1]

    signed_in = httpx.post(f"{signing_in}/channels/local/messages", json={"agent": "assistant",
                                                                            "text": "Hi"},
                           headers={"Authorization": f"Bearer {tokens['id_token']}"})
    assert signed_in.status_code == 202  # the core takes the web chat's sign-in
    assert httpx.post(f"{signing_in}/chat/token", json={"grant_type": "password"}).status_code == 400


def test_a_person_sees_only_their_own_conversation(stack):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))  # it looks first
    stack.model.reply("Q-1001 mentions an invoice.")
    assert stack.say("Which questions mention an invoice?") == "Q-1001 mentions an invoice."
    stack.model.reply("Hello, Ben.")
    stack.say("Hello", person="ben")
    with channels(stack) as url:
        ana = httpx.get(f"{url}/channels/local/conversation",
                        params={"agent": "assistant", "person": "ana"}).json()["messages"]
    assert [(m["from"], m["text"]) for m in ana] == [
        ("you", "Which questions mention an invoice?"), ("assistant", "Q-1001 mentions an invoice.")]


def test_a_wait_the_person_left_takes_nothing_they_wont_see(stack):
    from a5s import db

    with channels(stack) as url:
        with pytest.raises(httpx.ReadTimeout):  # such as a page closed while it waited
            httpx.get(f"{url}/channels/local/inbox", params={"person": "ana", "wait": 20}, timeout=1)
        time.sleep(0.5)
        with db.transaction(stack.admin) as conn:
            conn.execute("insert into outbox (person, channel, agent, text) "
                         "values ('ana', 'local', 'assistant', 'Q-1001 is due on Wednesday.')")
        time.sleep(1)  # long enough for the wait that was left to have taken it
        found = httpx.get(f"{url}/channels/local/inbox", params={"person": "ana"}).json()
    assert [m["text"] for m in found["messages"]] == ["Q-1001 is due on Wednesday."]


# In a browser

@pytest.fixture
def answering(stack):
    """A scheduler answering messages as they arrive, as deployed."""
    stop = threading.Event()
    listener = threading.Thread(target=stack.scheduler().listen, args=(stop,),
                                kwargs={"sweep_every": 3600}, daemon=True)
    listener.start()
    yield
    stop.set()
    listener.join(10)


def test_a_person_chats_in_the_browser_in_development(stack, browser, answering):
    stack.model.reply(None, ("search_records", {"query": "invoice"}))  # it looks first
    stack.model.reply("Q-1001 is about an invoice sent to the wrong address.")
    with channels(stack) as url:
        page = browser.new_page()
        page.goto(f"{url}/chat/")
        assert not page.is_visible("#compose")  # not until they've said who they are
        page.fill("#person", "ana")
        page.click("#name button")
        page.fill("#text", "Which questions mention an invoice?")
        page.keyboard.press("Enter")
        page.wait_for_selector("li.agent >> text=wrong address", timeout=30000)
        said = page.locator("#conversation li").all_inner_texts()
    assert said[0].startswith("You") and "Which questions mention an invoice?" in said[0]
    assert said[1].startswith("assistant") and "wrong address" in said[1]


def test_a_person_signs_in_chats_and_hears_reminders_in_the_browser(stack, browser, answering,
                                                                     signing_in, provider):
    stack.model.reply("Hello, **Ana**. See https://sample.a5s.dev/records/Q-1001")
    page = browser.new_page()
    page.goto(f"{signing_in}/chat/")  # to the provider, and straight back, signed in
    page.wait_for_selector("#who >> text=Ana Ortiz", timeout=30000)
    assert not page.is_visible("#name")  # nobody's asked who they are, once signed in
    page.fill("#text", "Hello")
    page.keyboard.press("Enter")
    page.wait_for_selector("li.agent >> text=Ana", timeout=30000)
    reply = page.locator("li.agent").last
    assert reply.locator("strong").nth(1).inner_text() == "Ana"  # bold, as text
    assert reply.locator("a").get_attribute("href") == "https://sample.a5s.dev/records/Q-1001"
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger

    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's and Ben's questions has passed
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    page.wait_for_selector("li.agent >> text=Q-1001 is due on Wednesday", timeout=30000)
    page.reload()  # and the conversation is still there
    page.wait_for_selector("li.agent >> text=Q-1001 is due on Wednesday", timeout=30000)
    assert [f["grant_type"] for f in provider.forms] == ["authorization_code"]
