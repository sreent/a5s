"""The studio says where to go, how to build an agent, and what someone's roles let them do.

Home comes first in every sidebar, and under Build the agents, then New agent, for whoever may
start one, so how to build an agent is never only a button on another page. a5s has no
administrator's mode to be in or out of, only roles, so every sidebar's foot names the roles
someone holds, or that they hold none, and leads to What you may do. Home says the same, and
shows whoever may build an agent the way from a new one to one at work, and anyone else who may
start one and how to become one of them (deploy/compose.identity.yaml signs in each of them)."""

from __future__ import annotations

import httpx

from conftest import accessible


def shell(approving: str, provider, person: str) -> dict:
    token = provider.id_token(person=person)
    answer = httpx.get(f"{approving}/shell/api", timeout=30,
                       headers={"Authorization": f"Bearer {token}"})
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_every_sidebar_names_the_roles_someone_holds(stack, approving, provider):
    # and the instances someone runs, as its owner or deputy, which is what gives them its
    # notebook, its spending and suspending it: no role, but named beside them (round 17, C2)
    assert shell(approving, provider, "ana")["roles"] == [
        "Instance approver", "Owner of billing", "Owner of assistant-finance"]
    assert shell(approving, provider, "ben")["roles"] == ["Deputy for assistant-finance"]
    assert shell(approving, provider, "chen")["roles"] == []  # none: Chen works with agents
    # Priya is on the team that runs a5s, and owns two agents; Tomas is on it, with no role
    assert shell(approving, provider, "priya")["roles"] == [
        "The team that runs a5s", "Owner of the assistant", "Owner of the watcher"]
    assert shell(approving, provider, "tomas")["roles"] == ["The team that runs a5s"]


def test_new_agent_is_in_the_sidebar_of_whoever_may_start_one(stack, approving, provider):
    def pages(person: str) -> list[str]:
        return [place["page"] for place in shell(approving, provider, person)["pages"]]

    assert pages("priya")[:7] == ["home", "chat", "tasks", "notebook", "agents", "new", "map"]
    # an instance approver may not; anyone in the team that runs a5s may, as an engineer, as a
    # release counts its engineers, though the directory gives Tomas no role (round 17, C3)
    assert "new" not in pages("ana") and "new" in pages("tomas")
    assert pages("chen") == ["home", "chat", "tasks", "agents", "map"]  # everyone's
    places = {p["page"]: p for p in shell(approving, provider, "priya")["pages"]}
    assert (places["home"]["at"], places["agents"]["at"], places["new"]["at"]) == (
        "/studio/", "/studio/agents", "/studio/new")
    assert (places["new"]["name"], places["new"]["group"]) == ("New agent", "Build")


def test_home_shows_whoever_may_build_an_agent_the_way(stack, approving, provider, browser):
    provider.person = "priya"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#build #start-agent", timeout=30000)
    stages = [s.strip() for s in page.locator("#build .journey li").all_inner_texts()]
    assert len(stages) == 6 and stages[0].startswith("1") and "Start it" in stages[0]
    assert "Put it to work" in stages[4]
    page.wait_for_selector("#your-roles", timeout=30000)
    assert "Your roles: The team that runs a5s · Owner of the assistant · Owner of the watcher." \
        in page.inner_text("#your-roles")
    assert "no administrator's mode" in page.inner_text("#your-roles")
    assert page.locator("#pages a[aria-current=page]").inner_text().strip() == "Home"
    accessible(page)
    page.click("#start-agent")
    page.wait_for_url("**/studio/new", timeout=30000)
    page.wait_for_selector("#pages a[aria-current=page]:has-text('New agent')", timeout=30000)


def test_home_tells_anyone_else_who_may_build_one(stack, approving, provider, browser):
    provider.person = "ben"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#build", timeout=30000)
    said = page.inner_text("#build")
    assert ("A new agent is started by an agent's owner or someone in the team that runs a5s, "
            "and you're neither.") in said
    assert page.locator("#start-agent").count() == 0
    assert page.locator("#pages a:has-text('New agent')").count() == 0
    page.wait_for_selector("#your-roles", timeout=30000)
    assert "Deputy for assistant-finance" in page.inner_text("#your-roles")  # what he runs
    assert page.locator("#me .me-roles").inner_text() == "Deputy for assistant-finance"
    accessible(page)


def test_an_agents_pages_mark_agents_and_the_foot_leads_to_what_you_may_do(stack, approving,
                                                                           provider, browser):
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/agents")
    page.wait_for_selector("#who-builds", timeout=30000)  # where the button would be, who may
    assert "an agent's owner or someone in the team that runs a5s" in page.inner_text(
        "#who-builds")
    page.click(".agent-card a.agent-name:text-is('assistant')")
    page.wait_for_selector(".agent-map", timeout=30000)
    assert page.locator("#pages a[aria-current=page]").inner_text().strip() == "Agents"
    me = page.locator("#me a")
    assert "Instance approver · Owner of billing" in me.inner_text()
    me.click()
    page.wait_for_selector("h1:text-is('What you may do')", timeout=30000)
    assert "no administrator's mode" in page.inner_text(".page-head")
    page.locator("aside.sidebar a.brand").click()  # the mark leads home
    page.wait_for_selector("#waiting", timeout=30000)


def test_every_page_a_sidebar_lists_is_served_at_its_own_address(stack, approving):
    """Each page the sidebars list opens at its own address, as a reload or a plain link from
    the web chat's sidebar asks for it, with the band across its top as every page has it:
    the Status page did not (round 17, B6)."""
    from a5s.core.shell_api import PAGES

    for _, _, _, _, at in PAGES:
        found = httpx.get(f"{approving}{at}", timeout=30, follow_redirects=True)
        assert found.status_code == 200 and "text/html" in found.headers["content-type"], at


def test_the_team_that_runs_a5s_counts_as_engineers_wherever_the_studio_asks(stack, approving,
                                                                             provider):
    """A release counts anyone in the team that runs a5s as an engineer, and no directory or
    group gives the role, so the studio asks the same: Tomas starts a new agent, offers his
    draft to the team, and reads the models' health, which his sidebar lists; Ben, outside it,
    does none (round 17, C3)."""
    from test_agent_asks import send

    made = send(approving, provider, "tomas", "POST", "/studio/api/drafts",
                {"name": "night-helper", "template": "assistant"})
    assert made.status_code == 200, made.text
    co = send(approving, provider, "tomas", "GET",
              f"/studio/api/drafts/{made.json()['id']}/co-authors").json()["people"]
    assert "Priya Nair" in [p["name"] for p in co]  # who's in the team, and so may make it too
    assert send(approving, provider, "tomas", "GET", "/health/api").status_code == 200
    assert "health" in [p["page"] for p in shell(approving, provider, "tomas")["pages"]]
    refused = send(approving, provider, "ben", "GET", "/health/api")
    assert refused.status_code == 403 and "the team that runs a5s" in refused.json()["detail"]
    assert send(approving, provider, "ben", "POST", "/studio/api/drafts",
                {"name": "day-helper", "template": "assistant"}).status_code == 403


def test_the_administrators_page_names_whom_its_for_not_everyone_with_a_role(stack, approving,
                                                                           provider):
    """A grader holds a role, but the administrators' page isn't theirs, and its refusal says
    whose it is (round 17, C6)."""
    from test_agent_asks import send

    refused = send(approving, provider, "dana", "GET", "/admin/api")
    assert refused.status_code == 403
    assert refused.json()["detail"] == (
        "the administrators' page is for those who own, approve, decide or oversee in a5s, and "
        "the team that runs it: part owners and their delegates, agents' owners, instance and "
        "release approvers, assurance, auditors and the data protection officer")


def test_the_palette_finds_each_page_once_and_narrows_cleanly(stack, approving, provider,
                                                            browser):
    """The palette had Agents and New agent twice, by one id, so typing left rows behind and
    marked two chosen (round 17, C1): each is there once, and narrowing leaves one chosen."""
    provider.person = "priya"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#find-anything", timeout=30000)
    page.keyboard.press("Control+k")
    palette = page.locator("dialog.palette")
    page.keyboard.type("agent")
    palette.locator("[role=option]:has-text('New agent')").wait_for(timeout=30000)
    names = [n.strip() for n in palette.locator("[role=option]").all_inner_texts()]
    assert len(names) == len(set(names)), names
    assert sum(n.startswith("New agent") for n in names) == 1
    assert sum(n.startswith("Agents") for n in names) == 1
    assert palette.locator("[aria-selected=true]").count() == 1
    page.keyboard.press("Control+a")
    page.keyboard.type("tasks")
    palette.locator("[role=option]:has-text('New agent')").wait_for(state="detached",
                                                                    timeout=30000)
    left = [n.lower() for n in palette.locator("[role=option]").all_inner_texts()]
    assert left and all("task" in n for n in left), left  # no row left behind
    assert palette.locator("[aria-selected=true]").count() == 1
    chosen = palette.locator("[aria-selected=true]").get_attribute("id")
    assert page.locator("dialog.palette [role=combobox]").get_attribute(
        "aria-activedescendant") == chosen


def test_a_draft_marks_what_it_is_and_a_page_in_no_sidebar_marks_none(stack, approving, provider,
                                                                     browser):
    """A draft of an agent released here is the Agents page's, not New agent's; and What you may
    do is in no sidebar, so nothing is marked, as a screen reader heard Home (round 17, C8)."""
    from test_agent_asks import send

    change = send(approving, provider, "priya", "POST", "/studio/api/drafts",
                  {"agent": "assistant"}).json()
    assert change["changes"] is True
    provider.person = "priya"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/drafts/{change['id']}")
    page.wait_for_selector(".wb-rail nav a[aria-current=page]", timeout=30000)
    assert page.get_attribute(".wb-rail nav a[aria-current=page]", "aria-label") == "Agents"
    page.goto(f"{approving}/studio/you")
    page.wait_for_selector("#roles", timeout=30000)
    page.wait_for_selector("#pages a", timeout=30000)
    assert page.locator("#pages a[aria-current=page]").count() == 0
