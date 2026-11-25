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
    assert shell(approving, provider, "ana")["roles"] == ["Instance approver", "Owner of billing"]
    assert shell(approving, provider, "ben")["roles"] == []  # none: Ben works with the agents
    # Priya is on the team that runs a5s, and owns two agents; Tomas is on it, with no role
    assert shell(approving, provider, "priya")["roles"] == [
        "The team that runs a5s", "Owner of the assistant", "Owner of the watcher"]
    assert shell(approving, provider, "tomas")["roles"] == ["The team that runs a5s"]


def test_new_agent_is_in_the_sidebar_of_whoever_may_start_one(stack, approving, provider):
    def pages(person: str) -> list[str]:
        return [place["page"] for place in shell(approving, provider, person)["pages"]]

    assert pages("priya")[:7] == ["home", "chat", "tasks", "notebook", "agents", "new", "map"]
    # an instance approver, and someone on the team that runs a5s who is no engineer, may not
    assert "new" not in pages("ana") and "new" not in pages("tomas")
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
    assert "A new agent is started by an agent's owner or an engineer, and you're neither." in said
    assert page.locator("#start-agent").count() == 0
    assert page.locator("#pages a:has-text('New agent')").count() == 0
    page.wait_for_selector("#your-roles", timeout=30000)
    assert "You hold none of a5s's roles" in page.inner_text("#your-roles")
    assert page.locator("#me .me-roles").inner_text() == "No roles: you work with agents"
    accessible(page)


def test_an_agents_pages_mark_agents_and_the_foot_leads_to_what_you_may_do(stack, approving,
                                                                           provider, browser):
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/agents")
    page.wait_for_selector("#who-builds", timeout=30000)  # where the button would be, who may
    assert "an agent's owner or an engineer" in page.inner_text("#who-builds")
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
