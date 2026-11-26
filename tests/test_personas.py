"""People meeting the studio for the first time, as personas, by what's on their screen alone.

The newcomer holds no role, the builder may start an agent, and the administrator approves the
settings and decides what agents ask. Each starts on Home, signed in, and gets to what they
came for by clicking what the studio offers them, within a few clicks, never by typing an
address. Each is told plainly what they are, as a5s has no administrator's mode, only roles,
and how an agent gets built, or who builds them. Along the way each page passes as people read it:
- one heading, and a line saying what the page is for or its facts;
- the sidebar marking where they are;
- no internal words, such as a role's id or "undefined", outside the ids a page shows on purpose;
- nothing broken in the browser's console;
- axe's checks, light, dark and at a phone's width.

They answer what people asked of the studio: how do I build an agent, and am I an administrator
or a user? (docs/manual/README.md, Getting around)."""

from __future__ import annotations

import re

import httpx
import pytest

from a5s.core import shell_api
from conftest import accessible, listed_runs
from test_journeys import Journey
from test_proposals import asked, held

pytestmark = pytest.mark.usefixtures("approving")

# What a person must never read on a page: what code says to itself, or a role's id where its
# name belongs. Ids and digests a page shows on purpose are set in mono, and left out.
LEAKS = re.compile(r"\bundefined\b|\bnull\b|\bNaN\b|\[object Object\]|Traceback|Internal Server Error"
                   r"|\b(?:part|agent)-(?:owner|delegate|author|viewer):|\binstance-approver\b"
                   r"|\brelease-approver\b|\bdata-protection-officer\b")


def arrive(browser, url: str, provider, person: str, width: int = 1280):
    """The person, signed in, on Home, with what they are said at its top; and what goes wrong
    in the browser from then on."""
    provider.person = person
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.on("dialog", lambda dialog: dialog.accept())
    # What's broken: a script's error, or the server's own. A refusal the page expects, and says
    # in words, such as 503 for a sandbox this deployment hasn't got, the browser logs too: it
    # isn't broken.
    broken: list[str] = []
    page.on("console", lambda m: broken.append(m.text) if m.type == "error"
            and not m.text.startswith("Failed to load resource") else None)
    page.on("pageerror", lambda e: broken.append(str(e)))
    page.on("response", lambda r: broken.append(f"{r.status} {r.url}") if r.status >= 500
            and r.status != 503 else None)
    page.goto(f"{url}/studio/")
    page.wait_for_selector("#your-roles", timeout=30000)
    return page, broken


def sidebar(page) -> dict[str, list[str]]:
    """The sidebar's headings, as written, and the pages under each."""
    return {group.locator(".group").text_content().strip():
            [a.inner_text().strip() for a in group.locator("a").all()]
            for group in page.locator("#pages .nav-group").all()}


def reads_well(page, broken: list[str], *, marked: str | None) -> None:
    """The page as a person reads it: what it is, where they are, the sidebar marking the page
    it is, or is one of, and none for a page in no sidebar, such as What you may do (round 17,
    C5, C8), and nothing of the code's."""
    assert page.locator("main h1").count() == 1 and page.inner_text("main h1").strip()
    head = page.locator("main .page-head")
    assert head.locator(".about").count() + head.locator(".meta").count() > 0, (
        f"{page.url} doesn't say what it's for")
    current = page.locator("#pages a[aria-current=page]")
    assert [a.strip() for a in current.all_inner_texts()] == ([marked] if marked else []), (
        f"{page.url} marks {current.all_inner_texts()}, not {marked}")
    words = page.evaluate("""() => {
        const main = document.querySelector("main").cloneNode(true);
        main.querySelectorAll(".mono, code, pre, .role-id").forEach((e) => e.remove());
        return main.innerText + "\\n" + document.querySelector("#me").innerText;
    }""")
    leaked = LEAKS.findall(words)
    assert not leaked, f"{page.url} shows {leaked}"
    assert not broken, broken


def test_a_newcomer_learns_what_they_are_and_who_builds_agents(stack, approving, provider,
                                                               browser):
    page, broken = arrive(browser, approving, provider, "chen")  # who holds no role
    walk = Journey(page, "newcomer")
    # What they are, said at once, in words, and so no administrator's mode to look for
    assert "You hold none of a5s's roles" in page.inner_text("#your-roles")
    assert page.inner_text("#me .me-roles") == "No roles: you work with agents"
    # Only the pages that won't refuse them; nothing waits on them, and Home says so
    assert sidebar(page) == {"Work": ["Home", "Chat", "Tasks"], "Build": ["Agents", "Map"]}
    assert "Nothing waits on you now." in page.inner_text("#waiting")
    # How an agent gets built, where they look first: who may, and how to become one of them
    assert ("an agent's owner or someone in the team that runs a5s, and you're neither"
            in page.inner_text("#build"))
    assert page.locator("#start-agent").count() == 0
    reads_well(page, broken, marked="Home")
    accessible(page)

    walk.click("#your-roles a")  # what their roles let them do, from the line that names them
    page.wait_for_selector("h1:text-is('What you may do')", timeout=30000)
    assert "no administrator's mode" in page.inner_text(".page-head")
    assert "You hold none of a5s's roles" in page.inner_text("#roles")
    reads_well(page, broken, marked=None)
    walk.click("#pages a:has-text('Agents')")  # the agents anyone may know of
    page.wait_for_selector("#who-builds", timeout=30000)
    # none they may know of yet, and whom to ask, where a newcomer lands (round 17, C4)
    assert "ask your manager, or whoever runs a5s in your organisation" in page.inner_text(
        "#none-yet")
    reads_well(page, broken, marked="Agents")
    walk.click("#who-builds a")  # and back to how one is built
    page.wait_for_selector("#build", timeout=30000)
    assert (walk.clicks, walk.loads) == (3, 0)

    # A page that's an administrator's, by its address, says plainly whom it's for
    page.goto(f"{approving}/studio/admin")
    said = page.wait_for_selector("main .problem", timeout=30000).inner_text()  # once it's loaded
    assert "for those who own, approve, decide or oversee in a5s, and the team that runs it" in said
    assert "Grader" not in said and "authors" not in said  # whom it's for, never all who hold a role


def test_a_newcomer_on_a_phone_still_knows_who_they_are(stack, approving, provider, browser):
    page, broken = arrive(browser, approving, provider, "chen", width=390)
    me = page.locator("#me a")  # their initials, at the sidebar's end, leading to their roles
    assert me.is_visible() and me.get_attribute("href") == "/studio/you"
    assert "No roles: you work with agents" in me.inner_text()  # what a screen reader says
    assert "You hold none of a5s's roles" in page.inner_text("#your-roles")
    reads_well(page, broken, marked="Home")


def test_a_builder_goes_from_home_to_a_new_agents_draft(stack, approving, provider, browser):
    page, broken = arrive(browser, approving, provider, "priya")  # who owns two agents
    walk = Journey(page, "builder")
    assert ("Your roles: The team that runs a5s · Owner of the assistant · Owner of the watcher."
            in page.inner_text("#your-roles"))
    assert sidebar(page)["Build"] == ["Agents", "New agent", "Map"]
    stages = page.locator("#build .journey li")  # the way from a new agent to one at work
    assert stages.count() == 6 and "Start it" in stages.nth(0).inner_text()
    reads_well(page, broken, marked="Home")
    accessible(page)

    walk.click("#start-agent")
    page.wait_for_selector(".template >> text=assistant", timeout=30000)
    assert page.inner_text("#pages a[aria-current=page]").strip() == "New agent"
    reads_well(page, broken, marked="New agent")
    page.fill("#agent-name", "expenses-helper")  # typing counts as no click
    walk.click(".template:has-text('assistant') >> nth=0")
    walk.click("#make")
    page.wait_for_selector("#journey [aria-current=step]", timeout=30000)
    assert page.evaluate("location.pathname").startswith("/studio/drafts/")
    # on its workbench, the sidebar shrunk to its icons, each named, still marks where they are:
    # a new agent's draft, New agent
    page.wait_for_selector(".wb-rail nav a[aria-current=page]", timeout=30000)
    assert page.get_attribute(".wb-rail nav a[aria-current=page]", "aria-label") == "New agent"
    assert (walk.clicks, walk.loads) == (3, 0)

    walk.click(".wb-rail nav a[aria-label='Home']")  # and Home keeps the draft, to come back to
    page.wait_for_selector("#my-drafts >> text=expenses-helper", timeout=30000)
    reads_well(page, broken, marked="Home")


def test_an_administrator_finds_what_waits_on_them_and_who_holds_what(stack, approving,
                                                                      provider, browser):
    asked(stack)  # Ben asks for a change, which waits for Ana's decision
    assert len(held(stack)) == 1
    page, broken = arrive(browser, approving, provider, "ana")  # an instance approver
    walk = Journey(page, "administrator")
    assert ("Your roles: Instance approver · Owner of billing · Owner of "
            "assistant-finance.") in page.inner_text("#your-roles")  # what she runs (C2)
    assert sidebar(page) == {"Work": ["Home", "Chat", "Tasks", "Notebook"], "Build": ["Agents", "Map"],
                             "Decide": ["Decisions", "Settings"], "Oversee": ["Administration", "Spending"]}
    page.wait_for_selector("#waiting a:has-text('waits for your decision')", timeout=30000)
    reads_well(page, broken, marked="Home")
    accessible(page)

    walk.click("#pages a:has-text('Administration')")  # who holds each role, and by what
    page.wait_for_selector("#shown", timeout=30000)
    assert "Ana Ortiz (the directory)" in page.inner_text("#roles tr:has-text('Instance approver')")
    reads_well(page, broken, marked="Administration")
    walk.click("#pages a:has-text('Settings')")
    page.wait_for_selector("main h1:text-is('Settings')", timeout=30000)
    reads_well(page, broken, marked="Settings")
    walk.click("#pages a:has-text('Home')")  # building agents is someone else's, and Home says whose
    page.wait_for_selector("#build", timeout=30000)
    assert "an agent's owner or someone in the team that runs a5s, and you're neither" in page.inner_text("#build")
    assert "New agent" not in sidebar(page)["Build"]
    assert (walk.clicks, walk.loads) == (3, 0)



def test_an_administrator_reads_an_instance_and_one_of_its_runs(stack, approving, provider,
                                                                browser):
    listed_runs(stack)  # enough people served for its runs to show one by one
    asked(stack)  # one run, of Ben's asking
    page, broken = arrive(browser, approving, provider, "ana")
    walk = Journey(page, "an instance and a run")
    walk.click("#pages a:has-text('Agents')")
    walk.click(".agent-card a.agent-name:text-is('assistant')")
    walk.click("table.grid-table a:has-text('assistant-finance')")  # the agent at work
    page.wait_for_selector(".runs-chart .day", timeout=30000)
    assert "One agent at work" in page.inner_text(".page-head .about")
    reads_well(page, broken, marked="Agents")
    walk.click("table.runs-table a:has-text('Open') >> nth=0")  # its latest run
    page.wait_for_selector(".agent-map .flow-state", timeout=30000)
    assert "One run of an agent, from what started it to how it ended" in page.inner_text(
        ".page-head .about")
    reads_well(page, broken, marked="Agents")
    accessible(page)
    assert (walk.clicks, walk.loads) == (4, 0)

# Everyone in the sample: the roles the sidebar's foot names, with the instances they run, and
# every page their sidebar offers, in its order: no more, so nothing in it turns them away, and
# no less, so nothing they may use is hidden, as no administrator's mode would show more (round
# 17, C5). The team that runs a5s may start new agents and read the models' health, as a release
# counts its engineers (C3); running an instance is named beside the roles (C2).
EVERYDAY = ["home", "chat", "tasks"]
EVERYONE = [
    ("chen", [], EVERYDAY + ["agents", "map"]),
    ("ben", ["Deputy for assistant-finance"], EVERYDAY + ["notebook", "agents", "map",
                                                        "spending"]),
    ("priya", ["The team that runs a5s", "Owner of the assistant", "Owner of the watcher"],
     EVERYDAY + ["notebook", "agents", "new", "map", "settings", "status", "admin", "spending",
                 "health"]),
    ("tomas", ["The team that runs a5s"],
     EVERYDAY + ["agents", "new", "map", "status", "admin", "health"]),
    ("ana", ["Instance approver", "Owner of billing", "Owner of assistant-finance"],
     EVERYDAY + ["notebook", "agents", "map", "decide", "settings", "admin", "spending"]),
    ("omar", ["Owner of orders"], EVERYDAY + ["agents", "map", "decide", "settings", "admin",
                                              "spending"]),
    ("dana", ["Grader"], EVERYDAY + ["agents", "map", "grade"]),
    ("rosa", ["Release approver"], EVERYDAY + ["agents", "map", "admin", "health"]),
    ("kofi", ["Assurance"], EVERYDAY + ["agents", "map", "settings", "audit", "admin"]),
    ("noor", ["Data protection officer"], EVERYDAY + ["agents", "map", "settings", "admin",
                                                      "officer"]),
]


@pytest.mark.parametrize(("person", "roles", "theirs"), EVERYONE, ids=[p for p, *_ in EVERYONE])
def test_everyone_is_told_their_roles_and_offered_their_pages(stack, approving, provider, person,
                                                             roles, theirs):
    token = provider.id_token(person=person)
    shell = httpx.get(f"{approving}/shell/api", timeout=30,
                      headers={"Authorization": f"Bearer {token}"}).json()
    assert shell["roles"] == roles
    assert [place["page"] for place in shell["pages"]] == sorted(
        theirs, key=[key for key, *_ in shell_api.PAGES].index)
