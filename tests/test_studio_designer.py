"""The designer (docs/studio.md#the-designer): an agent built by hand on its canvas, on the draft's
workbench. It adopts n8n's canvas, as Ocean draws it, and extends it where an agent and a5s's
governance need more: each tool in the colour of what it does, a5s's checks on the canvas, and,
for whatever is chosen, what follows from it, by the settings in force and the directory: who
decides its changes, part by part, who signs its release, and its limits. Each change is made to
agent.yaml, keeping its comments, and checked as the forms' and the text's are. The canvas works
from the keyboard, and the same comes as a list, which a phone starts with."""

from __future__ import annotations

import yaml
from playwright.sync_api import expect

from a5s import db
from a5s.core import studio
from conftest import accessible
from test_r11_drafters import as_
from test_studio_authoring import kept


def drafted(browser, approving, provider, agent: str | None = None, width: int = 1440, height: int = 900):
    """A draft on its workbench, as priya, who owns both agents: of a new agent from the
    assistant's template, or of a change to `agent`."""
    provider.person = "priya"
    page = browser.new_page(viewport={"width": width, "height": height})
    refused: list[str] = []
    page.on("console", lambda m: refused.append(m.text) if "Content Security Policy" in m.text else None)
    if agent:
        page.goto(f"{approving}/studio/agents/{agent}")
        page.click("#draft-change")
    else:
        page.goto(f"{approving}/studio/new")
        page.wait_for_selector(".template >> text=assistant", timeout=30000)
        page.fill("#agent-name", "finance-helper")
        page.click(".template:has-text('assistant') >> nth=0")
        page.click("#make")
    page.wait_for_selector("#kept >> text=Kept", timeout=30000)
    return page, refused


def definition(stack, page) -> str:
    """The draft's agent.yaml, as a5s keeps it."""
    draft = page.evaluate("location.pathname").rsplit("/", 1)[-1]
    with db.transaction(stack.admin) as conn:
        return conn.execute("select files from agent_drafts where id = %s",
                            (draft,)).fetchone()["files"]["agent.yaml"]


def test_the_designer_is_offered_who_decides_each_part_and_the_limits(stack, approving, provider):
    found = as_(approving, provider, "priya")("GET", "/studio/api/tools").json()
    parts = {p["name"]: p for p in found["parts"]}
    assert parts["billing"]["deciders"] == ["Ana Ortiz"] and parts["billing"]["threshold"] == 0.98
    assert parts["orders"]["deciders"] == ["Omar Haddad"] and parts["orders"]["threshold"] == 0.95
    assert found["no_part"] == ["Ana Ortiz"]  # who approves instances decides for no part
    assert found["limits"]["change-due-date"] == {"per_run": 5, "per_person_30_days": 20}
    assert studio.rules(stack.gateway.scenario, None) == {"parts": [], "no_part": [], "limits": {}}


def test_each_tool_says_who_decides_its_changes_and_what_limits_them(stack, approving, provider, browser):
    page, refused = drafted(browser, approving, provider)
    page.wait_for_selector("#decides >> text=Ana Ortiz", timeout=30000)  # the draft as a whole
    assert "billing: Ana Ortiz" in page.inner_text("#decides")
    assert "orders: Omar Haddad" in page.inner_text("#decides")
    page.click("[data-step='tool:change_due_date']")
    follows = page.inner_text(".wb-inspector .follows")
    assert "a decider of its record's part: Ana Ortiz in billing; Omar Haddad in orders" in follows
    assert "The settings allow 5 in a run and 20 for each person in 30 days" in follows
    assert "98% in billing and 95% in orders" in follows
    expect(page.locator("[data-step='tool:change_due_date']")).to_have_attribute("aria-pressed", "true")
    page.click("text=The draft as a whole")
    page.wait_for_selector("#journey", timeout=30000)
    assert refused == []


def test_a_tool_dragged_onto_the_canvas_says_what_follows_and_who_must_sign(stack, approving, provider,
                                                                          browser):
    page, refused = drafted(browser, approving, provider, agent="watcher")  # it reads, at level 0
    assert "Nobody: it changes no records" in page.inner_text("#decides")
    # a tool dragged from the picker, as people do, onto the canvas
    page.locator(".picker [data-tool=change_due_date]").drag_to(page.locator(".flow-canvas .react-flow__pane"))
    page.wait_for_selector("#what-changed >> text=Added change_due_date", timeout=30000)
    kept(page)
    assert "Its release keeps it at level 0, which only observes, so a5s refuses every change" in page.inner_text(
        ".wb-inspector .follows")
    page.wait_for_selector("#what-changed >> text=must sign its release", timeout=30000)  # once it's kept
    assert "change_due_date" in yaml.safe_load(definition(stack, page))["tools"]["changes"]
    page.click("[data-step=agent]")
    page.select_option("#level-max", "1")  # a person decides each one, then
    kept(page)
    page.click("[data-step='tool:change_due_date']")
    assert "Its release goes no higher than level 1, so every one waits for its decider" in page.inner_text(
        ".wb-inspector .follows")
    assert refused == []


def test_the_canvas_works_from_the_keyboard(stack, approving, provider, browser):
    page, refused = drafted(browser, approving, provider)
    page.wait_for_selector("[data-step=agent]", timeout=30000)
    page.focus("[data-step=agent]")
    for key, to in (("ArrowDown", "model"), ("ArrowRight", "checks"), ("ArrowUp", "agent"),
                    ("ArrowRight", "reply"), ("ArrowLeft", "agent"), ("ArrowLeft", "messages")):
        page.keyboard.press(key)
        expect(page.locator(f"[data-step={to}]")).to_be_focused()
    page.keyboard.press("Enter")  # opens it, the inspector taking the keyboard's focus
    expect(page.locator("#inspector-title")).to_be_focused()
    assert page.inner_text("#inspector-title") == "A message"
    page.focus("[data-step='tool:get_messages']")
    page.keyboard.press("Delete")  # taken away, as n8n takes a step away
    page.wait_for_selector("[data-step='tool:get_messages']", state="detached", timeout=30000)
    assert "Took get_messages away" in page.inner_text("#what-changed")
    kept(page)
    text = definition(stack, page)
    assert "get_messages" not in text and "scope: none # it changes no part's data" in text
    assert refused == []


def test_a_schedule_added_and_set_by_hand_is_kept_as_a5s_reads_it(stack, approving, provider, browser):
    page, refused = drafted(browser, approving, provider)
    page.click("#add-schedule")
    expect(page.locator("#inspector-title")).to_be_focused()
    assert "a5s starts a run at 09:00, on weekdays" in page.inner_text("#what-changed")
    page.fill("#schedule-at", "08:30, 13:30")
    page.uncheck("label.day:has-text('fri') input")
    kept(page)
    page.wait_for_selector("#problem-count >> text=No problems", timeout=30000)  # a5s reads it
    [schedule] = yaml.safe_load(definition(stack, page))["schedules"]
    assert schedule == {"name": "morning", "at": ["08:30", "13:30"], "days": ["mon", "tue", "wed", "thu"],
                        "task": "Look through the open records."}
    assert 'at: ["08:30", "13:30"]' in definition(stack, page)  # times in quotes, as YAML needs them
    assert "a5s starts a run at 08:30 and 13:30, on Mondays, Tuesdays, Wednesdays and Thursdays" in page.inner_text(
        ".wb-inspector .follows")
    page.click("#take-away")
    kept(page)
    assert yaml.safe_load(definition(stack, page))["schedules"] == []
    assert refused == []


def test_axe_finds_nothing_amiss_on_the_workbench_nor_its_list_on_a_phone(stack, approving, provider, browser):
    from test_ui_pages import shot

    page, refused = drafted(browser, approving, provider, agent="watcher")
    page.click("[data-step='tool:search_records']")
    accessible(page)  # as wide as a desktop, and as a phone, light and dark
    shot(page, "studio-designer")
    phone, _ = drafted(browser, approving, provider, agent="watcher", width=390, height=844)
    phone.wait_for_selector(".design-list", timeout=30000)  # a phone starts with the list
    phone.click(".design-row-button:has-text('search_records')")
    assert "It reads" in phone.inner_text(".design-inline")
    phone.click("#list-adding")
    phone.click(".design-inline [data-tool=change_due_date]")
    phone.wait_for_selector(".design-row-button:has-text('change_due_date')", timeout=30000)
    accessible(phone)
    assert refused == []
