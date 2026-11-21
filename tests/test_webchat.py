"""The web chat: a page the core serves, where people sign in with any OpenID Connect
provider and talk to the agents through the local channel."""

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest

from a5s.core import inbox
from a5s.core.identity import IdentityConfig, Verifier
from conftest import CLIENT, PHONE, accessible, free_port, serve
from test_ui_pages import shot


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
    assert config == {"signin": None, "development": True,  # nothing of the agents
                      "links": ["https://sample.a5s.dev/", f"{stack.gateway.public_url}/"]}


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


def test_a_conversation_starts_with_what_the_agent_does_for_whoever_it_serves(stack):
    with channels(stack) as url:
        def does(person: str, agent: str = "assistant") -> str | None:
            return httpx.get(f"{url}/channels/local/conversation",
                             params={"agent": agent, "person": person}).json()["does"]

        assert does("ana").startswith("Keeps one conversation with each person")
        assert does("chen") is None  # it serves neither them, nor anyone with the watcher
        assert does("ana", "watcher") is None  # no instance runs it here


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


def test_a_person_attaches_a_file_and_the_agent_asks_a5s_reader_about_it(stack, browser, answering):
    stack.model.reply(None, ("ask_about", {"document": "D-1", "question": "What's the total?"}))
    stack.model.reply("The total row says 860.00.")  # a5s's reader
    stack.model.reply("Your costs come to 860.00, as the total says.")
    with channels(stack) as url:
        page = browser.new_page()
        page.goto(f"{url}/chat/")
        page.fill("#person", "ana")
        page.click("#name button")
        with page.expect_file_chooser() as chosen:
            page.click("#attach")
        chosen.value.set_files([{"name": "costs.csv", "mimeType": "text/csv",
                                 "buffer": b"item,amount\nhotel,612.00\ntaxi,248.00\ntotal,860.00\n"}])
        assert page.inner_text("#attached li span") == "costs.csv, 1 KB"
        page.fill("#text", "Do these add up?")
        page.keyboard.press("Enter")
        page.wait_for_selector("li.agent >> text=as the total says", timeout=30000)
        said = page.locator("#conversation li").all_inner_texts()
        assert not page.is_visible("#attached")  # sent with it, and gone from the box
    assert "Do these add up?" in said[0] and "Sent costs.csv" in said[0]
    assert "hotel,612.00" in json.dumps(stack.model.requests[1]["body"])  # a5s's reader read it
    assert "hotel,612.00" not in json.dumps(stack.model.requests[0]["body"])  # the agent didn't


def test_a_person_signs_in_chats_and_hears_reminders_in_the_browser(stack, browser, answering,
                                                                     signing_in, provider):
    stack.model.reply("Hello, **Ana**. See https://sample.a5s.dev/records/Q-1001")
    stack.model.reply("Hello, **Ana**. See https://sample.a5s.dev/records/Q-1001")
    page = browser.new_page()
    page.goto(f"{signing_in}/chat/")  # to the provider, and straight back, signed in
    page.wait_for_selector("#who >> text=Ana Ortiz", timeout=30000)
    assert not page.is_visible("#name")  # nobody's asked who they are, once signed in
    # With nothing said yet, it starts with the agent, what it does, and what to do
    page.wait_for_selector("#welcome >> text=The assistant", timeout=30000)
    assert "Keeps one conversation with each person" in page.inner_text("#welcome")
    assert page.locator("#welcome .avatar.agent").count() == 1
    shot(page, "chat-welcome")
    page.fill("#text", "Hello")
    page.keyboard.press("Enter")
    page.wait_for_selector("li.agent >> text=Ana", timeout=30000)
    reply = page.locator("li.agent").last
    assert not page.is_visible("#welcome")  # once something's said
    assert reply.locator(".avatar.agent").count() == 1  # an agent said it, as its mark says
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


def test_a_message_the_conversation_and_the_inbox_both_give_shows_once(stack, browser):
    """Round 14 (E-L6): a message a5s wrote someone, such as that their conversation was handed
    over, can come both in their conversation and from their inbox: it shows once."""
    with channels(stack) as url:
        page = browser.new_page()
        page.goto(f"{url}/chat/")
        page.fill("#person", "ana")
        page.click("#name button")
        page.wait_for_selector(".welcome-name", timeout=30000)  # its conversation is open
        page.evaluate("""() => {
            const told = {by: "a5s", from: "a5s", id: 7, text: "Handed over.", at: new Date().toISOString()};
            say(told);
            say({...told});
        }""")
        assert page.locator("#conversation li", has_text="Handed over.").count() == 1


def test_why_a_file_wont_go_is_said_beside_what_they_write(stack, browser):
    """Round 14 (E-M6): on a phone, in a conversation that's going, why a file wasn't attached is
    said beside what they write, where they're looking, never only at the top of the page; and
    it goes once they attach one the web chat takes."""
    with channels(stack) as url:
        page = browser.new_page(viewport=PHONE)
        page.goto(f"{url}/chat/")
        page.fill("#person", "ana")
        page.click("#name button")
        page.wait_for_selector(".welcome-name", timeout=30000)  # its conversation is open
        page.evaluate("""() => { for (let n = 0; n < 40; n += 1) say({by: "a5s", from: "a5s",
            id: 100 + n, text: `Earlier, ${n}`, at: new Date().toISOString()}); }""")
        with page.expect_file_chooser() as chosen:
            page.click("#attach")
        chosen.value.set_files([{"name": "setup.zip", "mimeType": "application/zip",
                                 "buffer": b"PK\x03\x04"}])
        said = page.locator("#refused")
        assert said.inner_text() == "setup.zip: a5s reads text files, PDFs and images."
        box = said.bounding_box()
        assert box is not None and 0 <= box["y"] and box["y"] + box["height"] <= PHONE["height"]
        accessible(page)
        with page.expect_file_chooser() as chosen:
            page.click("#attach")
        chosen.value.set_files([{"name": "costs.csv", "mimeType": "text/csv",
                                 "buffer": b"item,amount\nhotel,612.00\n"}])
        assert not said.is_visible() and page.inner_text("#attached li span") == "costs.csv, 1 KB"


def test_on_a_phone_the_newest_message_is_above_what_they_write(stack, browser):
    """Round 14 (E-L7): the web chat scrolls to its end, so the newest message, with its
    "That's wrong", is above the composer at the foot of a phone's screen, never under it."""
    with channels(stack) as url:
        page = browser.new_page(viewport=PHONE)
        page.goto(f"{url}/chat/")
        page.fill("#person", "ana")
        page.click("#name button")
        page.wait_for_selector(".welcome-name", timeout=30000)  # its conversation is open
        page.evaluate("""() => { for (let n = 0; n < 30; n += 1) say({by: "a5s", from: "a5s",
            id: 200 + n, text: `Earlier, ${n}`, at: new Date().toISOString()}); }""")
        newest = page.locator("#conversation li").last.bounding_box()
        composer = page.locator("footer").bounding_box()
        assert newest is not None and composer is not None
        assert newest["y"] + newest["height"] <= composer["y"] + 1


def test_what_the_web_chat_writes_itself_is_in_the_language_they_read(stack, browser):
    """Round 14 (E-L4): the web chat's own words beside what it shows are in the language
    someone reads: a message of theirs that was only a file, and what another agent wrote
    them, which it says is about that agent."""
    from a5s import db

    with channels(stack) as url:
        page = browser.new_page()
        page.goto(f"{url}/chat/")
        page.fill("#person", "ana")
        page.click("#name button")
        page.wait_for_selector(".welcome-name", timeout=30000)  # its conversation is open
        page.evaluate("""() => { speak("th"); say({by: "person", from: "you",
            text: "(a file, with no words)", at: new Date().toISOString()}); }""")
        assert page.locator("#conversation li.you", has_text="(ไฟล์ ไม่มีข้อความ)").count() == 1
        with db.transaction(stack.admin) as conn:  # the watcher writes her, unasked
            conn.execute("insert into outbox (person, channel, agent, text) "
                         "values ('ana', 'local', 'watcher', 'Q-1001 is overdue.')")
        page.wait_for_selector("#conversation li >> text=(เกี่ยวกับ watcher) Q-1001 is overdue.",
                               timeout=40000)
