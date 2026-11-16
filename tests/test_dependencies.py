"""The map of what depends on what (core/dependencies.py): the parts the settings name, the
instances at work in them, the agents they run, the tools each may call, the systems those come
from and the models, each as far as someone may see it, and what a change to any of them
reaches."""

import httpx

from a5s import db
from a5s.core import dependencies
from conftest import accessible
from test_r9_studio_need_to_know import with_ops


def mapped(approving: str, provider, person: str) -> dict:
    token = provider.id_token(person=person)
    answer = httpx.get(f"{approving}/studio/api/map", timeout=30,
                       headers={"Authorization": f"Bearer {token}"})
    assert answer.status_code == 200, answer.text
    return answer.json()


def keys(found: dict) -> list[str]:
    return [n["key"] for n in found["nodes"]]


def edges(found: dict) -> dict[tuple[str, str], str]:
    return {(e["from"], e["to"]): e["says"] for e in found["edges"]}


def test_the_map_joins_each_part_instance_agent_tool_system_and_model(stack, approving, provider):
    found = mapped(approving, provider, "ana")
    assert keys(found)[:3] == ["part:billing", "instance:assistant-finance", "agent:assistant"]
    assert keys(found)[-2:] == ["system:sample", "model:fake"]  # in its columns' order
    said = edges(found)
    assert said[("instance:assistant-finance", "part:billing")] == "works in it, at level 1"
    assert said[("instance:assistant-finance", "agent:assistant")].startswith("runs its version ")
    assert said[("instance:assistant-finance", "model:fake")] == "calls it"
    assert said[("agent:assistant", "tool:change_due_date")] == "may call it"
    assert said[("tool:change_due_date", "system:sample")] == "comes from it"
    shown = {n["key"]: n for n in found["nodes"]}
    assert (shown["tool:change_due_date"]["tone"], shown["tool:search_records"]["tone"]) == (
        "changes", "reads")  # as the studio colours what a tool does
    assert shown["agent:assistant"]["at"] == "/studio/agents/assistant"
    assert shown["instance:assistant-finance"]["at"] == "/studio/instances/assistant-finance"
    assert shown["instance:assistant-finance"]["about"] == "at work"


def test_what_a_change_to_a_tool_reaches_and_what_an_instance_rests_on(stack, approving, provider):
    found = mapped(approving, provider, "ana")
    assert dependencies.reaching(found, "tool:change_due_date") == {
        "depends_on": ["system:sample"],
        "depended_on_by": ["agent:assistant", "instance:assistant-finance"]}  # nearest first
    rests = dependencies.reaching(found, "instance:assistant-finance")
    assert rests["depended_on_by"] == []
    assert {"part:billing", "agent:assistant", "model:fake", "tool:change_due_date",
            "system:sample"} <= set(rests["depends_on"])


def test_each_sees_only_what_the_studio_shows_them(stack, approving, provider):
    assert mapped(approving, provider, "chen") == {"nodes": [], "edges": []}  # nothing theirs
    assert "agent:watcher" in keys(mapped(approving, provider, "priya"))  # its owner, unserved
    assert "agent:watcher" not in keys(mapped(approving, provider, "ana"))  # at work nowhere
    kofi = keys(mapped(approving, provider, "kofi"))  # assurance: how agents are built, not
    assert "tool:change_due_date" in kofi  # where they work, nor for whom
    assert not [k for k in kofi if k.startswith(("instance:", "part:"))]


def test_an_agent_listed_for_everyone_shows_alone_to_someone_it_doesnt_serve(stack, approving,
                                                                              provider):
    found = stack.gateway.definitions["assistant"]
    stack.gateway.definitions["assistant"] = found.model_copy(update={"listed": True})
    chen = mapped(approving, provider, "chen")  # that it exists, not what it may do
    assert keys(chen) == ["agent:assistant"] and chen["edges"] == []


def test_whom_an_instance_may_ask_shows_only_among_those_someone_may_watch(stack, approving,
                                                                           provider):
    with_ops(stack)  # Omar runs assistant-ops, in orders, and may not watch assistant-finance
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set asks = '{assistant-finance}' where id = 'assistant-ops'")
    ana = mapped(approving, provider, "ana")  # who approves instances watches both
    assert edges(ana)[("instance:assistant-ops", "instance:assistant-finance")] == "may ask it"
    assert dependencies.reaching(ana, "part:billing")["depended_on_by"] == [
        "instance:assistant-finance", "instance:assistant-ops"]  # what billing's change reaches
    omar = mapped(approving, provider, "omar")
    assert "instance:assistant-ops" in keys(omar) and "part:orders" in keys(omar)
    assert "instance:assistant-finance" not in keys(omar) and "part:billing" not in keys(omar)
    assert not [e for e in omar["edges"] if e["says"] == "may ask it"]


def test_choosing_on_the_map_says_what_a_change_reaches(stack, approving, provider, browser):
    provider.person = "ana"
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(f"{approving}/studio/map")
    page.wait_for_selector(".flow [data-step='tool:change_due_date']", timeout=30000)
    assert page.title() == "Map · a5s studio"
    accessible(page)
    page.click(".flow [data-step='tool:change_due_date']")
    page.wait_for_selector("#chosen h2 >> text=change_due_date", timeout=30000)
    assert page.locator("#depended-on-by [data-pick]").all_inner_texts() == [
        "assistant-finance", "assistant"]
    assert page.locator("#parts-reached [data-pick]").all_inner_texts() == ["billing"]
    assert page.locator("#depends-on [data-pick]").all_inner_texts() == ["sample"]
    assert page.locator("#says li").all_inner_texts() == [
        "assistant may call change_due_date.", "It comes from sample."]
    assert page.locator(".flow-step.dim[data-key='model:fake']").count() == 1  # beyond its reach
    assert page.locator(".flow-step.dim[data-key='part:billing']").count() == 0  # within it
    assert "at=tool%3Achange_due_date" in page.url  # so it can be linked to
    accessible(page)
    page.click("#depended-on-by [data-pick='agent:assistant']")
    page.wait_for_selector("#chosen h2 >> text=assistant", timeout=30000)
    page.focus(".flow [data-step='tool:change_due_date']")  # the arrow keys move down a column
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.dataset.step") == "tool:close_question"
    page.goto(f"{approving}/studio/map?at=part:billing")  # the address chooses it again
    page.wait_for_selector("#chosen h2 >> text=billing", timeout=30000)
    assert page.locator("#depended-on-by [data-pick]").all_inner_texts() == ["assistant-finance"]
    page.goto(f"{approving}/studio/agents/assistant")  # an agent's page leads to it there
    page.click("#on-the-map")
    page.wait_for_selector("#chosen h2 >> text=assistant", timeout=30000)
