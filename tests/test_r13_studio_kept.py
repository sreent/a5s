"""Round 13, reviewer C: the studio keeps people's work, and their way back, when a sign-in runs
out or doesn't work.

C1: the studio kept its sign-in in memory and never said when it ran out: every keep on the
workbench failed after it, and the only way on, a reload, lost what the author had typed. It
now asks them to sign in again, over the page, back to it, and what they'd changed and a5s
hadn't kept, in a draft, the settings or the grades chosen, waits in the tab and comes back.
C2: an edit made just before leaving the workbench was dropped: it's sent as they leave.
C3: a sign-in for an act that didn't work at the identity provider left the studio a line of
words, with no way on: it says nothing was done, and signs them in again.
C4: the officer's refused request left no way to ask again: the form comes back as they filled
it, and after a request, for another.
C13: dropping a draft asked through the browser's own box, and said nothing after: it asks as
the studio asks for what can't be undone, and says the draft is gone."""

from __future__ import annotations

import time

from test_mfa import PASSWORD, asking

TYPED = "Answer billing questions, from what Q- records say, and nothing else."


def a_draft(browser, approving, provider, claims: dict | None = None):
    provider.person = "priya"
    provider.claims = claims or {}
    page = browser.new_page()
    page.goto(f"{approving}/studio/new")
    page.wait_for_selector(".template >> text=assistant", timeout=30000)
    page.fill("#agent-name", "finance-helper")
    page.click(".template:has-text('assistant') >> nth=0")
    page.click("#make")
    page.wait_for_selector("#kept >> text=Kept", timeout=30000)
    return page


def instructions(page) -> str:
    page.click(".modes button:text-is('Instructions')")
    return page.input_value("#instructions")


def test_a_sign_in_run_out_on_the_workbench_is_signed_in_again_keeping_what_was_typed(
        stack, approving, provider, browser):
    page = a_draft(browser, approving, provider, {"exp": int(time.time()) + 6})
    page.wait_for_selector("dialog#sign-in-again[open]", timeout=30000)  # it says so as it runs out
    provider.claims = {}  # and their next sign-in lasts as long as any other
    page.keyboard.press("Escape")  # they look first, and type on
    page.click(".modes button:text-is('Instructions')")
    page.fill("#instructions", TYPED)
    page.wait_for_timeout(1500)
    page.evaluate("document.querySelector('dialog#sign-in-again').showModal()")
    page.click("dialog#sign-in-again button:text-is('Sign in again')")
    page.wait_for_selector("#kept >> text=Kept", timeout=30000)
    assert instructions(page) == TYPED  # back, from the tab, and kept
    page.reload()
    page.wait_for_selector("#kept >> text=Kept", timeout=30000)
    assert instructions(page) == TYPED  # kept by a5s, not the tab alone


def test_an_edit_made_just_before_leaving_the_workbench_is_kept(stack, approving, provider, browser):
    page = a_draft(browser, approving, provider)
    draft = page.evaluate("location.pathname")
    page.click(".modes button:text-is('Instructions')")
    page.fill("#instructions", TYPED)
    page.click(".wb-bar a.crumb")  # straight to the agents, within the wait before a keep
    page.wait_for_selector(".page-head h1 >> text=Agents", timeout=30000)
    page.goto(f"{approving}{draft}")
    page.wait_for_selector("#kept >> text=Kept", timeout=30000)
    assert instructions(page) == TYPED


def test_a_sign_in_for_an_act_refused_at_the_provider_has_a_way_back(stack, approving, provider, browser):
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}/studio/instances/assistant-finance")
    page.wait_for_selector("#suspend", timeout=30000)
    provider.refusing = ("access_denied", "The user cancelled the second factor.")
    page.click("#suspend")
    card = page.wait_for_selector("#sign-in-failed", timeout=30000)
    assert "cancelled the second factor" in card.inner_text() and "Nothing was done" in card.inner_text()
    provider.refusing = None
    page.click("#sign-in-failed button:text-is('Sign in again')")
    page.wait_for_selector(".page-head h1 >> text=assistant-finance", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/instances/assistant-finance"
    page.wait_for_selector("#suspend", timeout=30000)  # still theirs to do


def test_the_officers_refused_request_can_be_asked_again(stack, approving, provider, browser):
    asking(stack)  # the deployment counts a request only with a second factor
    provider.person = "noor"
    provider.claims = PASSWORD  # the provider let this sign-in through without one
    page = browser.new_page()
    page.goto(f"{approving}/studio/officer")
    page.wait_for_selector("#person", timeout=30000)
    page.fill("#person", "ben")
    page.click("button:has-text('Sign in and ask')")
    page.wait_for_selector("#status:has-text(\"didn't take your request\")", timeout=30000)
    assert page.locator("#whom").count() == 1 and page.input_value("#person") == "ben"


def test_dropping_a_draft_asks_first_and_says_its_gone(stack, approving, provider, browser):
    page = a_draft(browser, approving, provider)
    page.click(".wb-bar button:text-is('Drop the draft')")
    dialog = page.wait_for_selector("dialog[open]", timeout=30000)
    assert "Drop the draft of finance-helper?" in dialog.inner_text()
    assert page.evaluate("document.activeElement.textContent") == "Keep it"  # what can't be undone waits
    page.click("dialog[open] button.danger:text-is('Drop the draft')")
    page.wait_for_selector("#toasts >> text=The draft of finance-helper is gone.", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/agents"
