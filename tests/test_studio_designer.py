"""The designer (docs/studio.md#the-designer): an agent built by hand on its canvas, on the draft's
workbench. It adopts n8n's canvas, as Ocean draws it, and extends it where an agent and a5s's
governance need more: each tool in the colour of what it does, a5s's checks on the canvas, and,
for whatever is chosen, what follows from it, by the settings in force and the directory: who
decides its changes, part by part, who signs its release, and its limits. Each change is made to
agent.yaml, keeping its comments, and checked as the forms' and the text's are. The canvas works
from the keyboard, and the same comes as a list, which a phone starts with."""

from __future__ import annotations

import re

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
    page.locator(".fd-palette [data-tool=change_due_date]").drag_to(page.locator(".flow-canvas .react-flow__pane"))
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
    page.uncheck(".wb-inspector label.choice:has-text('fri') input")
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
    phone.wait_for_selector(".flow-listing", timeout=30000)  # a phone starts with the list
    row = phone.locator("button.flow-row:has-text('search_records')")
    row.click()
    assert "It reads" in phone.inner_text(".flow-inline")
    phone.locator(".flow-inline").first.press("Escape")  # its settings close, the keyboard on its row
    expect(phone.locator(".flow-inline")).to_have_count(0)
    expect(row).to_be_focused()
    expect(row).to_have_attribute("aria-expanded", "false")
    phone.click("#list-adding")
    phone.click(".flow-inline [data-tool=change_due_date]")
    phone.wait_for_selector("button.flow-row:has-text('change_due_date')", timeout=30000)
    phone.click(".flow-listing .modes button:has-text('Canvas')")  # its canvas, a choice of views away
    phone.wait_for_selector(".flow-canvas [data-step='tool:change_due_date']", timeout=30000)
    accessible(phone)
    assert refused == []


# Its first instance, as its authors plan it: never in force, and only what they may name

def test_a_drafts_plan_is_kept_checked_and_said_in_its_pull_request_without_names(stack, approving,
                                                                                  provider):
    from a5s.core import erasure, export
    from test_studio_spaces import coauthor

    stack.with_watcher()  # two instances at work, which priya may see, owning both agents
    priya = as_(approving, provider, "priya")
    offer = priya("GET", "/studio/api/tools").json()  # those the settings name, and her
    assert {s["id"] for s in offer["servable"]} == {"ana", "ben", "priya"}
    assert {a["id"] for a in offer["askable"]} == {"assistant-finance", "watcher-finance"}
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    plan = {"parts": ["billing"], "serves": ["ana", "ben"], "asks": ["watcher-finance"]}
    kept = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": draft["files"], "plan": plan})
    assert kept.status_code == 200, kept.text
    assert kept.json()["plan"] == plan
    for wrong, said in (({"parts": ["nowhere"]}, "nowhere isn't a part the settings know"),
                        ({"serves": ["kofi"]}, "kofi isn't one the settings name, nor you"),
                        ({"asks": ["helper-elsewhere"]}, "helper-elsewhere isn't an instance you may see at work")):
        refused = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": draft["files"], "plan": {**plan, **wrong}})
        assert refused.status_code == 400 and said in refused.json()["detail"]
    files_alone = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": draft["files"]})
    assert files_alone.json()["plan"] == plan  # kept, as the files change
    body = priya("GET", f"/studio/api/drafts/{draft['id']}/pull-request").json()["body"]
    planned = body.split("## Its first instance, as planned")[1]
    assert "in billing, serving 2 people, asking watcher-finance" in planned
    assert "Ana" not in planned and "Ben" not in planned  # a pull request names nobody served

    coauthor(stack)  # a co-author's copy keeps it
    copy = as_(approving, provider, "omar")("POST", "/studio/api/drafts", {"copy_of": draft["id"]}).json()
    assert copy["plan"] == plan
    with db.transaction(stack.cfg.database_url) as conn:  # the core's export of Ben
        found = export.gather(conn, "ben")
    assert [d["agent"] for d in found["planned_for"]] == ["assistant", "assistant"]
    with db.transaction(stack.cfg.database_url) as conn:  # the core erases Ben, as asked
        gone, _ = erasure.erase(conn, "ben", stack.gateway.clock(), here=True)
    assert gone.get("planned_for") == 2  # and goes from them
    assert priya("GET", f"/studio/api/drafts/{draft['id']}").json()["plan"]["serves"] == ["ana"]


def test_its_first_instance_is_planned_on_the_canvas_and_goes_to_work_with_it(stack, approving,
                                                                             provider, browser):
    page, refused = drafted(browser, approving, provider, agent="watcher")
    page.click("[data-step=agent]")
    page.check("#plan-title ~ fieldset label:has-text('billing') input")
    page.wait_for_selector("#what-changed >> text=Ana Ortiz would decide its changes there", timeout=30000)
    page.check("#plan-title ~ fieldset label:has-text('Ben Okafor') input")
    page.check("#plan-title ~ fieldset label:has-text('assistant-finance') input")  # its release must let it
    page.wait_for_selector("#what-changed >> text=Its release now lets it ask other agents", timeout=30000)
    kept(page)
    expect(page.locator("[data-step=agent]")).to_have_attribute("aria-label", re.compile(r"in billing$"))
    assert "from Ben Okafor" in page.get_attribute("[data-step=messages]", "aria-label")
    asked = page.locator(".flow-step.agent-tone[data-key='ask:assistant-finance']")
    expect(asked).to_have_count(1)
    assert yaml.safe_load(definition(stack, page))["context"]["agents"] is True
    page.wait_for_selector("#what-changed >> text=must sign its release", timeout=30000)
    page.click("text=The draft as a whole")
    assert "Ana Ortiz, for billing" in page.inner_text("#to-work")
    assert "serving Ben Okafor, and asking assistant-finance" in page.inner_text("#to-work")
    assert "billing: Ana Ortiz" in page.inner_text("#decides") or "Nobody" in page.inner_text("#decides")

    page.reload()  # kept, and once released, it's what putting it to work starts from
    page.wait_for_selector("[data-step=agent]", timeout=30000)
    expect(page.locator("[data-step=agent]")).to_have_attribute("aria-label", re.compile(r"in billing$"))

    def released(route) -> None:
        route.fulfill(json={**route.fetch().json(), "released": True, "at_work": False})

    page.route("**/studio/api/drafts/*", released)
    page.reload()
    page.wait_for_selector("#put-to-work", timeout=30000)
    assert page.get_attribute("#put-to-work", "href") == (
        "/settings/?add=watcher&parts=billing&serves=ben&asks=assistant-finance")
    assert refused == []


def test_the_settings_app_starts_from_a_drafts_plan(stack, approving, provider, browser):
    provider.person = "ana"  # billing's owner, who approves versions of the settings
    page = browser.new_page()
    page.goto(f"{approving}/settings/?add=watcher&parts=billing&serves=ben,nobody%3Cb%3E&asks=assistant-finance")
    page.wait_for_selector("#add-instance", timeout=30000)
    assert page.input_value("#add-agent") == "watcher" and page.input_value("#add-part") == "billing"
    served = page.locator("input[name=add-serves]")
    assert [served.nth(i).is_checked() for i in range(served.count())].count(True) == 1  # Ben alone
    assert "It may ask assistant-finance" in page.inner_text("#add-instance")
    page.click("#add-it")
    page.click("#review")
    page.wait_for_selector("#reviewed-changes li", timeout=30000)
    added = page.locator("#reviewed-changes li").first.inner_text()
    assert "watcher-billing" in added and "serving Ben Okafor" in added


# Each step's name on the canvas, where it stands, and where its step does
NAMES = """() => [...document.querySelectorAll('.flow-canvas .flow-step')].flatMap(step => {
  const name = step.querySelector(':scope > .flow-name');
  if (!name) return [];
  const s = step.getBoundingClientRect(), n = name.getBoundingClientRect();
  return [{step: step.dataset.key, html: name.innerHTML, left: n.left, right: n.right, top: n.top,
           bottom: n.bottom, from: s.left, to: s.right}];
})"""


def test_each_steps_name_stays_within_it_and_clear_of_the_others(stack, approving, provider, browser):
    """A tool's long name, such as change_due_date, wraps within its step, after an underscore,
    and stands clear of the names of the steps beside it, as Ocean's FlowNode keeps them, so
    nothing on the canvas runs into anything else (the long-label overlap)."""
    page, refused = drafted(browser, approving, provider)
    page.wait_for_selector("[data-step='tool:change_due_date']", timeout=30000)
    names = page.evaluate(NAMES)
    assert len(names) >= 8, names  # what starts it, its reply, its model, checks and six tools
    for name in names:
        assert name["from"] - 0.5 <= name["left"] and name["right"] <= name["to"] + 0.5, name  # within it
    for i, one in enumerate(names):
        for other in names[i + 1:]:
            assert (one["right"] <= other["left"] or other["right"] <= one["left"]
                    or one["bottom"] <= other["top"] or other["bottom"] <= one["top"]), (one, other)
    [due] = [n for n in names if n["step"] == "tool:change_due_date"]
    assert due["html"] == "change_<wbr>due_<wbr>date", due  # it may break after each underscore
    assert refused == []
