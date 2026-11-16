"""Every page people use, in a browser, signed in: each opens, axe finds nothing amiss on it,
light or dark, and with A5S_SCREENSHOTS naming a folder, it's saved there as a screenshot, light
and dark, for people to review how a5s looks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import PHONE, accessible

PAGES = ("chat", "tasks", "notebook", "studio", "settings", "decide", "grade", "audit", "admin",
         "officer")


def shot(page, name: str) -> None:
    """The page as it looks, light and dark, and on a phone, into A5S_SCREENSHOTS, if it names
    a folder."""
    if folder := os.environ.get("A5S_SCREENSHOTS"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        size = page.viewport_size
        for width, suffix in ((None, ""), (PHONE, "-phone")):
            if width:
                page.set_viewport_size(width)
            page.evaluate("window.scrollTo(0, 0)")  # from its top, where its sidebar sits
            for scheme in ("light", "dark"):
                page.emulate_media(color_scheme=scheme)
                page.screenshot(path=f"{folder}/{name}{suffix}-{scheme}.png", full_page=True)
        if size:
            page.set_viewport_size(size)


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
AT = {"settings": "/studio/settings"}  # in the studio, where its old address goes


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
        assert page.locator("#pages a[aria-current=page]").get_attribute("href") == AT.get(name, f"/{name}/")
        assert page.locator("#me").inner_text().endswith("Ana Ortiz")
    accessible(page)
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
    # of a5s's own; Chen is served; Kofi is assurance, who reads the trail. The studio's home and
    # its catalogue are everyone's
    assert listed("ana") == ["chat", "tasks", "notebook", "studio", "decide", "settings", "admin"]
    assert listed("ben") == ["chat", "tasks", "notebook", "studio"]
    assert "audit" in listed("kofi")
    assert listed("chen") == ["chat", "tasks", "studio"]
    assert httpx.get(f"{approving}/shell/api", timeout=30).status_code == 401
