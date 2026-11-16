"""Round 13, reviewer C (and A4): the studio's pages as people read them.

C5: on a phone, the agent's and the instance's tables made the whole page scroll sideways: they
scroll in their own frame, and every page the tests check for accessibility must reflow.
C6: a request for settings refused after its review was said far above, out of sight: it's said
beside its button, and takes the focus.
C7: every page was "a5s: studio", and moving within the studio left the focus nowhere: each page
has its own title, and its heading takes the focus.
C8: declining an ask took away the words that said so: they're said where they stay, and focus.
C9: the palette said nothing was called what someone typed while it was still looking.
C10: an instance someone may not watch said so three times: once.
C14: a lone change offered to be decided with others ticked.
A4: a link put its own words in the heading of an agent's page."""

from __future__ import annotations

import json

import yaml

from conftest import PHONE, accessible
from test_agent_asks import listed
from test_agent_asks import send as ask_api
from test_proposals import asked

LINK_WORDS = "call-555-0100-your-account-is-locked"  # words an agent's id could be


def signed_in(browser, provider, approving, person: str, path: str, ready: str, **size):
    provider.person = person
    page = browser.new_page(**size)
    page.goto(f"{approving}{path}")
    page.wait_for_selector(ready, timeout=30000)
    return page


def test_each_page_has_its_title_and_moving_gives_its_heading_the_focus(stack, approving, provider, browser):
    page = signed_in(browser, provider, approving, "ana", "/studio/agents", ".agent-card a.agent-name")
    assert page.title() == "Agents · a5s studio"
    page.click(".agent-card a.agent-name:text-is('assistant')")
    page.wait_for_selector(".page-head h1 >> text=assistant", timeout=30000)
    assert page.title() == "assistant · a5s studio"
    assert page.evaluate("document.activeElement.tagName") == "H1"
    page.go_back()
    page.wait_for_selector(".page-head h1 >> text=Agents", timeout=30000)
    assert page.evaluate("document.activeElement.tagName") == "H1"


def test_on_a_phone_the_agents_and_instances_pages_dont_scroll_sideways(stack, approving, provider, browser):
    for path, ready in (("/studio/agents/assistant", "text=Where it runs"),
                        ("/studio/instances/assistant-finance", "#reach")):
        page = signed_in(browser, provider, approving, "ana", path, ready, viewport=PHONE)
        page.wait_for_timeout(500)
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0, path
        accessible(page)


def test_a_refused_request_for_settings_is_said_beside_its_button(stack, approving, provider, browser):
    page = signed_in(browser, provider, approving, "ana", "/studio/settings", "#in-force-title >> text=In force")
    page.click("#by-text")
    edited = yaml.safe_load(page.input_value("#text"))
    edited["instances"]["assistant-finance"]["serves"].append("chen")
    page.fill("#text", yaml.safe_dump(edited))
    page.click("#review")
    page.wait_for_selector("#send", timeout=30000)
    page.route("**/settings/api/requests", lambda route: route.fulfill(
        status=409, content_type="application/json",
        body=json.dumps({"detail": "a newer version is in force: review it again"})))
    page.click("#send")
    note = page.wait_for_selector("#send-refused", timeout=30000)
    assert note.inner_text() == "A newer version is in force: review it again"
    assert page.evaluate("document.activeElement.id") == "send-refused"


def test_declining_an_ask_says_so_where_it_stays(stack, approving, provider, browser, monkeypatch):
    listed(stack, monkeypatch)
    assert ask_api(approving, provider, "lena", "POST", "/studio/api/agents/assistant/ask").status_code == 200
    page = signed_in(browser, provider, approving, "ana", "/studio/agents/assistant", "#asks button:text-is('Decline')")
    page.click("#asks button:text-is('Decline')")
    said = page.wait_for_selector("#asks-said", timeout=30000)
    assert "declined" in said.inner_text() and page.evaluate("document.activeElement.id") == "asks-said"
    page.wait_for_selector("#toasts >> text=declined", timeout=30000)


def test_the_palette_says_its_looking_while_it_first_finds(stack, approving, provider, browser):
    provider.person = "ana"
    page = browser.new_page()
    held = []  # what waits on Ana, still on its way, as on a slow day
    page.route("**/studio/api/home", lambda route: held.append(route))
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#find-anything", timeout=30000)
    page.keyboard.press("Control+k")
    page.keyboard.type("assistant-finance")
    assert "Looking for what you may open" in page.inner_text("dialog.palette")


def test_an_instance_someone_may_not_watch_says_so_once(stack, approving, provider, browser):
    page = signed_in(browser, provider, approving, "chen", "/studio/instances/assistant-finance", "p.problem")
    page.wait_for_timeout(1000)
    assert page.locator("p.problem").count() == 1
    assert page.inner_text("p.problem")[0].isupper()  # a sentence


def test_a_lone_change_isnt_offered_to_be_decided_with_others(stack, approving, provider, browser):
    asked(stack)
    page = signed_in(browser, provider, approving, "ana", "/studio/decide", ".approval")
    assert page.locator("text=Decide it with the others ticked").count() == 0


def test_a_links_words_never_head_an_agents_page(stack, approving, provider, browser):
    page = signed_in(browser, provider, approving, "ana", f"/studio/agents/{LINK_WORDS}", "p.problem")
    assert LINK_WORDS not in page.inner_text(".page-head h1")
