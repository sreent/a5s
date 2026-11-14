"""Every page people use, in a browser, signed in: each opens, and with A5S_SCREENSHOTS naming a
folder, is saved there as a screenshot, light and dark, for people to review how a5s looks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PAGES = ("chat", "tasks", "notebook", "studio", "settings", "decide", "grade", "audit", "admin",
         "officer")


def shot(page, name: str) -> None:
    """The page as it looks, light and dark, into A5S_SCREENSHOTS, if it names a folder."""
    if folder := os.environ.get("A5S_SCREENSHOTS"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.evaluate("window.scrollTo(0, 0)")  # from its top, where its sidebar sits
        for scheme in ("light", "dark"):
            page.emulate_media(color_scheme=scheme)
            page.screenshot(path=f"{folder}/{name}-{scheme}.png", full_page=True)


@pytest.fixture
def seen(stack):
    """A few runs, so pages have something to show."""
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")
    stack.say("Which questions mention an invoice?")
    stack.model.reply("Nothing's due today.")
    stack.say("What's due today?", person="ben")


# The pages signed in to read, whose sidebar lists the pages each person may use, and Ana may
# use. Those signed in for one act alone, deciding or grading, keep that sign-in to the act;
# and the audit trail, which Ana may not read, isn't in hers.
LISTED = ("chat", "tasks", "notebook", "studio", "settings", "admin")


@pytest.mark.parametrize("name", PAGES)
def test_each_page_opens_signed_in_beside_a_sidebar(seen, approving, browser, name):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/{name}/")
    if name == "chat":  # it listens for what comes next, so the network never goes quiet
        page.wait_for_selector("#who:not(:empty)", timeout=30000)
    else:
        page.wait_for_load_state("networkidle", timeout=30000)
    assert page.title().startswith("a5s")
    assert page.locator("aside.sidebar .brand").count() == 1
    if name in LISTED:
        page.wait_for_selector("#pages a[aria-current=page]", timeout=30000)
        assert page.locator("#pages a[aria-current=page]").get_attribute("href") == f"/{name}/"
        assert page.locator("#me").inner_text().endswith("Ana Ortiz")
    shot(page, name)


def test_the_sidebar_lists_only_the_pages_each_person_may_use(stack, approving, provider):
    import httpx

    def listed(person: str) -> list[str]:
        token = provider.id_token(person=person)
        answer = httpx.get(f"{approving}/shell/api", timeout=30,
                           headers={"Authorization": f"Bearer {token}"})
        assert answer.status_code == 200, answer.text
        return answer.json()["pages"]

    # Ana approves instances and owns billing; Ben deputises for the instance, which is no role
    # of a5s's own; Chen is served; Kofi is assurance, who reads the trail
    assert listed("ana") == ["chat", "tasks", "notebook", "studio", "decide", "settings", "admin"]
    assert listed("ben") == ["chat", "tasks", "notebook", "studio"]
    assert "audit" in listed("kofi")
    assert listed("chen") == ["chat", "tasks"]
    assert httpx.get(f"{approving}/shell/api", timeout=30).status_code == 401
