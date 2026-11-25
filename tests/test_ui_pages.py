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
AT = {"settings": "/studio/settings", "notebook": "/studio/notebook",  # in the studio, where their
      "tasks": "/studio/tasks", "admin": "/studio/admin", "audit": "/studio/audit",
      "decide": "/studio/decide", "grade": "/studio/grade",
      "officer": "/studio/officer"}  # old addresses go


@pytest.mark.parametrize("name", PAGES)
def test_each_page_opens_signed_in_beside_a_sidebar(seen, approving, browser, name):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/{name}/")
    if name == "chat":  # it listens for what comes next, so the network never goes quiet
        page.wait_for_selector("#who:not(:empty)", timeout=30000)
    else:
        page.wait_for_load_state("networkidle", timeout=30000)
    assert "a5s" in page.title()  # each page its own title, the chat's and the studio's (round 13, C7)
    assert page.locator("aside.sidebar .brand").count() == 1
    if name in LISTED:
        page.wait_for_selector("#pages a[aria-current=page]", timeout=30000)
        assert page.locator("#pages a[aria-current=page]").get_attribute("href") == AT.get(name, f"/{name}/")
        me = page.locator("#me").inner_text()  # who she is, and her roles, leading to what each lets her do
        assert "Ana Ortiz" in me and "Instance approver · Owner of billing" in me, me
        assert page.locator("#me a").get_attribute("href") == "/studio/you"
    accessible(page)
    shot(page, name)


def test_the_sidebar_lists_only_the_pages_each_person_may_use(stack, approving, provider):
    import httpx

    def listed(person: str) -> list[str]:
        token = provider.id_token(person=person)
        answer = httpx.get(f"{approving}/shell/api", timeout=30,
                           headers={"Authorization": f"Bearer {token}"})
        assert answer.status_code == 200, answer.text
        return [place["page"] for place in answer.json()["pages"]]

    # Ana approves instances and owns billing; Ben deputises for the instance, which is no role
    # of a5s's own, but sees what it spends; Chen is served; Kofi is assurance, who reads the
    # trail. Home, the agents and the map of what depends on what are everyone's, each as far
    # as they see; New agent is for whoever may start one, Priya, who owns two
    assert listed("ana") == ["home", "chat", "tasks", "notebook", "agents", "map", "decide",
                             "settings", "admin", "spending"]
    assert listed("ben") == ["home", "chat", "tasks", "notebook", "agents", "map", "spending"]
    assert "audit" in listed("kofi")
    assert "health" in listed("rosa")  # the release approver: whose evidence a model change is
    assert listed("chen") == ["home", "chat", "tasks", "agents", "map"]
    assert listed("priya")[:7] == ["home", "chat", "tasks", "notebook", "agents", "new", "map"]
    assert httpx.get(f"{approving}/shell/api", timeout=30).status_code == 401


def test_the_health_page_shows_each_models_day(stack, approving, provider, browser):
    """Engineers and the release approver see each model's day, measured (core/health_api.py):
    its calls, failures, stalls, mean time, whether its SLO gates it, and its canary scores."""
    import httpx

    token = provider.id_token(person="rosa")
    answer = httpx.get(f"{approving}/health/api", timeout=30,
                       headers={"Authorization": f"Bearer {token}"})
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"days": 1, "models": []}  # this stack's models haven't been called
    provider.person = "rosa"  # the page signs her in through the provider, as any page does
    page = browser.new_page()
    page.goto(f"{approving}/studio/health")
    try:
        page.wait_for_selector("table.health", timeout=30000)
    except Exception as exc:  # what the page said instead, for the failure's words
        raise AssertionError(f"the health page didn't render: {page.inner_text('body')[:600]}"
                             ) from exc
    assert "Model health" in page.inner_text("body")
    # its note leads to where each instance's model is set: the settings
    assert page.locator("p.note a").get_attribute("href") == "/studio/settings"
    accessible(page)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{approving}/studio/")  # and the sidebar leads to it, not back to her home
    page.locator("#pages a", has_text="Model health").click()
    page.wait_for_selector("table.health", timeout=30000)
    assert page.url == f"{approving}/studio/health"


def test_the_health_page_is_for_the_release_approver_and_engineers_alone(approving, provider):
    """Nobody else reads it: a model's health is the evidence for a model change, not a
    public chart (core/health_api.py)."""
    import httpx

    for person in ("ana", "ben", "chen", "kofi"):
        token = provider.id_token(person=person)
        answer = httpx.get(f"{approving}/health/api", timeout=30,
                           headers={"Authorization": f"Bearer {token}"})
        assert answer.status_code == 403, person


def test_every_sidebar_and_the_palette_show_the_pages_as_a5s_lists_them(seen, approving, provider,
                                                                        browser):
    """One list of the pages, a5s's own (core/shell_api.py): the studio's sidebar and palette,
    and the chat's sidebar, name, order and place each page as /shell/api gives them, where each
    kept a list of its own (round 13's deferral)."""
    import httpx

    token = provider.id_token(person="ana")
    places = httpx.get(f"{approving}/shell/api", timeout=30,
                       headers={"Authorization": f"Bearer {token}"}).json()["pages"]
    assert [p["page"] for p in places] == ["home", "chat", "tasks", "notebook", "agents", "map",
                                          "decide", "settings", "admin", "spending"]
    for start in ("/studio/", "/chat/"):  # the studio's sidebar, and the plain pages' (shell.js)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{approving}{start}")
        page.wait_for_selector("#pages a", timeout=30000)
        links = page.locator("#pages a")
        shown = [(links.nth(n).inner_text().strip(), links.nth(n).get_attribute("href"))
                 for n in range(links.count())]
        assert shown == [(p["name"], p["at"]) for p in places], start
        headings = [h.strip() for h in page.locator("#pages .group").all_text_contents()]  # as written
        assert headings == list(dict.fromkeys(p["group"] for p in places)), start
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#find-anything", timeout=30000)
    page.locator("#find-anything").click()
    palette = page.get_by_role("dialog", name="Find anything")
    palette.locator("[role=option]").first.wait_for()
    offered = palette.locator("[role=option]").all_inner_texts()
    for place in places:  # each by the sidebar's own name
        assert any(o.startswith(place["name"]) for o in offered), (place["name"], offered)
