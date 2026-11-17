"""The map of what depends on what (core/dependencies.py): the parts the settings name, the
instances at work in them, the agents they run, the tools each may call, the systems those come
from and the models, each as far as someone may see it, and what a change to any of them
reaches."""

import httpx
from playwright.sync_api import expect

from a5s import db
from a5s.connectors.libraries import Shelved
from a5s.connectors.mcp import Served
from a5s.core import dependencies, samples
from a5s.definitions import Evaluation
from conftest import accessible, raise_cap
from test_languages import reads
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
    assert said[("instance:assistant-finance", "part:billing")] == "{from} works in {to}, at level 1"
    assert said[("instance:assistant-finance", "agent:assistant")].startswith(
        "{from} runs {to}'s version ")  # whole, with each end where the page names it
    assert said[("instance:assistant-finance", "model:fake")] == "{from} calls {to}"
    assert said[("agent:assistant", "tool:change_due_date")] == "{from} may call {to}"
    assert said[("tool:change_due_date", "system:sample")] == "{from} comes from {to}"
    assert said[("agent:assistant", "model:fake")] == "{from}'s release names {to}"
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
    assert edges(ana)[("instance:assistant-ops", "instance:assistant-finance")] == "{from} may ask {to}"
    assert dependencies.reaching(ana, "part:billing")["depended_on_by"] == [
        "instance:assistant-finance", "instance:assistant-ops"]  # what billing's change reaches
    omar = mapped(approving, provider, "omar")
    assert "instance:assistant-ops" in keys(omar) and "part:orders" in keys(omar)
    assert "instance:assistant-finance" not in keys(omar) and "part:billing" not in keys(omar)
    assert not [e for e in omar["edges"] if e["says"] == "{from} may ask {to}"]


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
        "assistant may call change_due_date", "change_due_date comes from sample"]
    assert page.locator(".flow-step.dim[data-key='model:fake']").count() == 1  # beyond its reach
    assert page.locator(".flow-step.dim[data-key='part:billing']").count() == 0  # within it
    assert "at=tool%3Achange_due_date" in page.url  # so it can be linked to
    accessible(page)
    page.click("#depended-on-by [data-pick='agent:assistant']")
    page.wait_for_selector("#chosen h2 >> text=assistant", timeout=30000)
    for _ in range(3):  # the arrow keys move down a column; the map drawn again as what's
        page.focus(".flow [data-step='tool:change_due_date']")  # chosen changes can take the
        page.keyboard.press("ArrowDown")  # focus from it first, on a slow runner
        if page.locator(".flow [data-step='tool:close_question']:focus").count():
            break
        page.wait_for_timeout(500)
    assert page.evaluate("document.activeElement.dataset.step") == "tool:close_question"
    page.goto(f"{approving}/studio/map?at=part:billing")  # the address chooses it again
    page.wait_for_selector("#chosen h2 >> text=billing", timeout=30000)
    assert page.locator("#depended-on-by [data-pick]").all_inner_texts() == ["assistant-finance"]
    page.goto(f"{approving}/studio/agents/assistant")  # an agent's page leads to it there
    page.click("#on-the-map")
    page.wait_for_selector("#chosen h2 >> text=assistant", timeout=30000)


def drawn(stack, person: str = "ana", extra: dict | None = None, **changed) -> dict:
    """The map as someone may see it, of the assistant as `changed` makes it, with the tools the
    scenario has and those in `extra`."""
    definitions = dict(stack.gateway.definitions)
    if changed:
        definitions["assistant"] = definitions["assistant"].model_copy(update=changed)
    with db.transaction(stack.admin) as conn:
        return dependencies.drawn(conn, stack.gateway.scenario, definitions,
                                  {**stack.gateway.scenario.tools(), **(extra or {})},
                                  stack.gateway.models, stack.gateway.scenario.person(person),
                                  approved=stack.gateway.approvers_in_force(conn),
                                  caps_of=lambda release: samples.shown_caps(
                                      conn, stack.gateway.cfg.seal_keys, release))


def test_a_librarys_tools_come_from_it_and_one_acting_as_the_person_says_so(stack):
    def nothing(call):
        return {}
    library = Shelved(name="search_handbook", description="Searches the handbook",
                      schema={"type": "object"}, run=nothing, library="handbook",
                      title="The staff handbook", as_person="sharepoint")
    served = Served(name="find_ticket", description="Finds a ticket", schema={"type": "object"},
                    run=nothing, server="itsm", as_person="servicenow")
    assistant = stack.gateway.definitions["assistant"]
    found = drawn(stack, extra={"search_handbook": library, "find_ticket": served},
                  tools={**assistant.tools, "documents": ["search_handbook", "find_ticket"]})
    said = edges(found)
    about = {n["key"]: n["about"] for n in found["nodes"]}
    # A library's documents come from it, never from the scenario's records
    assert said[("tool:search_handbook", "system:The staff handbook")] == "{from} comes from {to}"
    assert ("tool:search_handbook", "system:sample") not in said
    assert about["system:The staff handbook"] == "a library of documents"
    assert said[("tool:find_ticket", "system:itsm")] == "{from} comes from {to}"
    for tool, system in (("search_handbook", "sharepoint"), ("find_ticket", "servicenow")):
        assert said[(f"tool:{tool}", f"system:{system}")] == (
            "{from} acts in {to} as the person it acts for, with their own permissions")
    assert dependencies.reaching(found, "system:servicenow")["depended_on_by"][:2] == [
        "tool:find_ticket", "agent:assistant"]  # what a change to the system it acts in reaches


def test_a_judge_a_model_it_lacks_level_two_and_a_shadow_are_on_the_map(stack):
    found = drawn(stack, evaluation=Evaluation(judge="fake-judge"), model="gone-model")
    said, about = edges(found), {n["key"]: n["about"] for n in found["nodes"]}
    assert said[("agent:assistant", "model:fake-judge")] == "{to} judges {from}'s work"
    assert said[("agent:assistant", "model:gone-model")] == "{from}'s release names {to}"
    assert about["model:gone-model"] == about["model:fake-judge"] == "not in models.yaml"
    with db.transaction(stack.admin) as conn:  # a type of change at level 2 in billing
        conn.execute("update instances set actions = '{\"billing\": {\"change-due-date\": 2}}' "
                     "where id = 'assistant-finance'")
    said = edges(drawn(stack))  # as a5s's cap, which no graded samples raised, holds it
    assert said[("instance:assistant-finance", "part:billing")] == (
        "{from} works in {to}, at level 1; the settings set level 2 for change-due-date, which "
        "a5s's cap holds at level 1 until graded samples show it's accurate enough")
    with db.transaction(stack.admin) as conn:  # an instance answering beside it, as a shadow
        conn.execute("insert into instances (id, definition, release, level, parts, actions, "
                     "grants, model, serves, owner, status, shadows) select 'assistant-next', "
                     "definition, release, level, parts, '{}', grants, model, serves, owner, "
                     "'shadow', 'assistant-finance' from instances where id = 'assistant-finance'")
    found = drawn(stack)
    assert edges(found)[("instance:assistant-next", "instance:assistant-finance")] == (
        "{from} answers beside {to}, and sends nothing")
    assert {n["key"]: n["about"] for n in found["nodes"]}["instance:assistant-next"] == (
        "a shadow: it answers beside another, and sends nothing")


def test_the_map_reads_in_the_language_someone_reads(stack, approving, provider):
    reads(stack, "ana", "th")
    found = mapped(approving, provider, "ana")
    said = edges(found)
    assert said[("agent:assistant", "tool:change_due_date")] == "{from} เรียกใช้ {to} ได้"
    assert {n["key"]: n["about"] for n in found["nodes"]}["instance:assistant-finance"] == (
        "กำลังทำงาน")


def test_whom_an_instance_may_hand_conversations_to_is_on_the_map(stack):
    """Round 14 (C16): the teams an instance may hand conversations to are on the map, as whom
    it may ask is."""
    assert not stack.settle(hands_to=["operations"]).refused
    found = drawn(stack)
    shown = {n["key"]: n for n in found["nodes"]}
    assert shown["team:operations"]["kind"] == "team"
    assert edges(found)[("instance:assistant-finance", "team:operations")] == (
        "{from} may hand a conversation to {to}, whose people answer it")


def test_the_map_says_where_level_two_counts_and_where_it_doesnt_yet(stack):
    """Round 14 (C16): level 2 the settings set counts on the map only as policy weighs it: once
    a5s's cap for the release lets it, and while someone who approved the settings in force owns
    the part, and the map says which holds it back."""
    from test_levels import levelled
    levelled(stack, cap=0)  # Ana, who owns billing, signs level 2 for changing due dates there
    edge = ("instance:assistant-finance", "part:billing")
    assert edges(drawn(stack))[edge] == (
        "{from} works in {to}, at level 1; the settings set level 2 for change-due-date, which "
        "a5s's cap holds at level 1 until graded samples show it's accurate enough")
    raise_cap(stack, cap=2)  # as graded samples raise it
    assert edges(drawn(stack))[edge] == (
        "{from} works in {to}, at level 1, and at level 2 for change-due-date")
    with db.transaction(stack.admin) as conn:  # had nobody who approved it owned billing now
        found = dependencies.drawn(conn, stack.gateway.scenario, stack.gateway.definitions,
                                   stack.gateway.scenario.tools(), stack.gateway.models,
                                   stack.gateway.scenario.person("ana"), approved=["ben"],
                                   caps_of=lambda release: samples.shown_caps(
                                       conn, stack.gateway.cfg.seal_keys, release))
    assert edges(found)[edge] == (
        "{from} works in {to}, at level 1; the settings set level 2 for change-due-date, which "
        "counts only once an owner of {to} approves the settings in force")


def test_on_a_phone_the_map_is_a_list_of_what_it_holds(stack, approving, provider, browser):
    """Round 14 (E-L8): on a phone the map is a list of what's on it, by kind, each a button,
    rather than a canvas too small to read or tap; choosing one says what it reaches, and takes
    the keyboard there. The canvas is a choice away."""
    from conftest import PHONE
    provider.person = "ana"
    page = browser.new_page(viewport=PHONE)
    page.goto(f"{approving}/studio/map")
    page.wait_for_selector("#things [data-pick='tool:change_due_date']", timeout=30000)
    assert page.locator(".flow-canvas").count() == 0
    assert page.inner_text("#things [data-kind=tool] h2") == "Tools"
    accessible(page)
    page.click("#things [data-pick='tool:change_due_date']")
    page.wait_for_selector("#chosen h2 >> text=change_due_date", timeout=30000)
    expect(page.locator("#chosen h2")).to_be_focused(timeout=10000)
    assert page.locator("#depended-on-by [data-pick]").all_inner_texts() == [
        "assistant-finance", "assistant"]
    page.click(".modes button:has-text('Map')")
    page.wait_for_selector(".flow-canvas", timeout=30000)
