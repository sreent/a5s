"""The settings app: the people who approve instances review the whole version in force, in
words and as written, and ask for a new one. Asking changes nothing by itself: the gateway
proposes it to everyone it needs, and they approve it on its own page."""

import httpx
import yaml
from playwright.sync_api import expect

from a5s.contract import DataProtection
from a5s.core import approvals
from conftest import accessible
from test_approvals import in_force_serial
from test_ui_pages import shot

ASSISTANT = ("assistant-finance: the assistant, working in billing at level 1, serving Ana Ortiz "
             "and Ben Okafor, run by Ana Ortiz with Ben Okafor as deputy.")


def api(url: str, provider, path: str, person: str = "ana", **body) -> httpx.Response:
    headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
    if body:
        return httpx.post(f"{url}{path}", json=body, headers=headers, timeout=30)
    return httpx.get(f"{url}{path}", headers=headers, timeout=30)


def with_orders(url: str, provider) -> str:
    """The version in force, as written, with the assistant working in orders too."""
    edited = yaml.safe_load(api(url, provider, "/settings/api").json()["in_force"]["text"])
    edited["instances"]["assistant-finance"]["parts"] = ["billing", "orders"]
    return yaml.safe_dump(edited)


def test_an_approver_sees_the_whole_version_in_force(stack, approving, provider):
    now = api(approving, provider, "/settings/api")
    assert now.status_code == 200
    body = now.json()
    assert body["you"] == "Ana Ortiz" and body["in_force"]["serial"] == in_force_serial(stack)
    assert body["in_force"]["whole"] == [
        "The scenario's data is synthetic.", ASSISTANT,
        "Limit for change-due-date: 5 in one run and 20 for one person in 30 days.",
        "Limit for close-question: 5 in one run and 20 for one person in 30 days.",
        "An agent earns level 2 in billing once graded samples show it's 98% accurate.",
        "An agent earns level 2 in orders once graded samples show it's 95% accurate.",
        *approvals.protection(DataProtection())]  # the officer's choices, as a5s starts them
    written = yaml.safe_load(body["in_force"]["text"])
    assert written["instances"]["assistant-finance"]["parts"] == ["billing"]
    assert body["waiting"] == [] and body["requests"] == []
    # What the page's forms change, and what they offer: the people the settings name, the
    # types of change the tools make, and what each release starts at and allows
    assert body["in_force"]["data"] == written
    assert body["names"] == {"ana": "Ana Ortiz", "ben": "Ben Okafor"}
    assert body["actions"] == ["change-due-date", "close-question"]
    assert body["releases"]["assistant"] == {"starts": 1, "most": 2,
                                             "actions": ["change-due-date", "close-question"]}
    assert body["releases"]["watcher"] == {"starts": 0, "most": 0, "actions": []}


def test_only_people_who_approve_instances_use_it(stack, approving, provider):
    assert api(approving, provider, "/settings/api", person="ben").status_code == 403
    assert httpx.get(f"{approving}/settings/api", timeout=30).status_code == 401


def test_a_change_is_reviewed_in_words_before_anyone_asks_for_it(stack, approving, provider):
    found = api(approving, provider, "/settings/api/review", text=with_orders(approving, provider))
    body = found.json()
    assert body["serial"] == in_force_serial(stack) + 1 and body["problems"] == []
    assert body["changes"] == [
        {"text": "assistant-finance works in orders as well, at level 1.", "widens": True}]
    assert body["approvers"] == ["Ana Ortiz", "Omar Haddad"]
    assert "working in billing at level 1 and orders at level 1" in body["whole"][1]
    broken = api(approving, provider, "/settings/api/review", text="instances: [").json()
    assert broken["problems"][0].startswith("a5s can't read it as settings")
    unknown = yaml.safe_dump({"instances": {"x": {"definition": "nobody", "serves": []}}})
    assert api(approving, provider, "/settings/api/review", text=unknown).json()["problems"] == [
        "x names nobody, which no release here has"]


def test_asking_for_a_version_has_the_gateway_propose_it_to_everyone_it_needs(stack, approving,
                                                                               provider):
    asked = api(approving, provider, "/settings/api/requests", text=with_orders(approving, provider))
    assert asked.status_code == 202
    serial = asked.json()["serial"]
    assert stack.inbox("omar") == []  # not yet: the gateway proposes it, on its next sweep
    stack.scheduler().apply_approved()
    [told] = stack.inbox("omar")  # he owns orders, and has never written to a5s
    assert told["text"].startswith(f"Version {serial} of a5s's settings waits for its instance "
                                   "approvers")
    assert len(stack.inbox("ana")) == 1
    now = api(approving, provider, "/settings/api").json()
    [waiting] = now["waiting"]
    assert waiting["serial"] == serial and waiting["approved_by"] == []
    assert waiting["needs"] == ["the owner of billing hasn't approved it",
                                "the owner of orders hasn't approved it"]
    assert now["requests"][0]["outcome"] == "proposed"
    by = {e["action"]: e["args"].get("by") for e in stack.ledger() if e["kind"] == "admin"}
    assert by["request"] == "ana" and by["propose"] == "ana"
    stack.scheduler().apply_approved()
    assert len(stack.inbox("omar")) == 0  # asked once


def test_an_approver_asks_for_a_change_in_the_browser(stack, approving, provider, browser):
    page = browser.new_page()
    page.goto(f"{approving}/settings/")  # to the provider, and straight back
    page.wait_for_selector("#in-force-title >> text=In force", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/settings"  # in the studio, now
    assert page.inner_text("#me").endswith("Ana Ortiz")
    assert page.locator("#whole li").all_inner_texts()[1] == ASSISTANT
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    page.click("#by-text")  # the whole version, as written
    edited = yaml.safe_load(page.input_value("#text"))
    edited["instances"]["assistant-finance"]["serves"].append("chen")
    page.fill("#text", yaml.safe_dump(edited))
    page.click("#review")
    page.wait_for_selector("#reviewed-changes >> text=Chen Wei", timeout=30000)
    assert page.inner_text("#reviewed-approvers") == "It needs the approval of Ana Ortiz."
    page.click("#send")
    page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    page.wait_for_selector("#requests li", timeout=30000)
    assert "waiting for a5s to ask its approvers" in page.inner_text("#requests")


FORMS_CHANGES = [
    ("The limit for change-due-date becomes 3 in one run and 20 for one person in 30 days, "
     "instead of 5 in one run and 20 for one person in 30 days."),
    "assistant-finance serves Chen Wei as well. widens what agents do",
    ("assistant-finance's level for change-due-date in billing goes from 1 to 2, where it acts "
     "and reports, once samples show it's accurate enough. widens what agents do")]


def test_an_approver_changes_the_settings_in_forms_in_the_browser(stack, approving, provider,
                                                                  browser):
    page = browser.new_page()
    page.goto(f"{approving}/settings/")
    page.wait_for_selector("#forms fieldset", timeout=30000)
    assert page.get_attribute("#by-forms", "aria-pressed") == "true" and page.is_hidden("#as-text")
    assistant = page.locator("fieldset", has_text="assistant-finance, the assistant")
    assert assistant.get_by_label("level 1, asks").is_checked()
    # Chen, by their id; due dates in billing on its own, at level 2; three in one run at most
    assistant.get_by_label("Someone else assistant-finance serves").fill("chen")
    page.keyboard.press("Enter")
    assert assistant.get_by_label("chen", exact=True).is_checked()
    assistant.get_by_label("change-due-date in billing").check()
    page.get_by_label("change-due-date, in one run").fill("3")
    accessible(page)
    shot(page, "settings-forms")
    page.click("#review")
    page.wait_for_selector("#reviewed-changes >> text=Chen Wei", timeout=30000)
    assert page.locator("#reviewed-changes li").all_inner_texts() == FORMS_CHANGES
    assert page.inner_text("#reviewed-approvers") == "It needs the approval of Ana Ortiz."
    # A change after the review needs a review of its own: what's asked for is what was reviewed
    page.get_by_label("change-due-date, in one run").fill("4")
    assert page.is_hidden("#reviewed")
    page.get_by_label("change-due-date, in one run").fill("3")
    page.click("#review")
    page.wait_for_selector("#send", state="visible", timeout=30000)
    page.click("#send")
    page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    # What it asked for is the version in force with those changes and nothing else
    stack.scheduler().apply_approved()
    [waiting] = api(approving, provider, "/settings/api").json()["waiting"]
    widens = " widens what agents do"  # as the page marks what the API marks
    assert [c["text"] + (widens if c["widens"] else "") for c in waiting["changes"]] == FORMS_CHANGES
    # Its approvers' page says who asked for it, and what it changes in the same words
    page.goto(f"{approving}{waiting['link']}")  # to the provider, afresh, and straight back
    page.wait_for_selector("#asker >> text=Ana Ortiz asked for it", timeout=30000)
    assert page.locator("#changes li").all_inner_texts() == FORMS_CHANGES


def test_an_agent_is_put_to_work_from_its_page_in_the_studio(stack, approving, provider, browser):
    # Its owner, on the page of an agent no instance runs, follows the way to put it to work
    provider.person = "priya"
    page = browser.new_page()
    page.goto(f"{approving}/studio/agents/watcher")
    page.wait_for_selector("#put-to-work >> text=No instance runs it yet", timeout=30000)
    shot(page, "studio-put-to-work")
    page.click("#put-it-to-work")  # to the settings app, signing in, with the watcher chosen
    page.wait_for_selector("#add-instance", timeout=30000)
    expect(page.locator("#add-agent")).to_be_focused()
    assert page.input_value("#add-agent") == "watcher"
    # Its release allows level 0 alone, so it starts there, serving whoever adds it, run by them
    levels = page.locator("input[name=add-level]")
    assert levels.nth(0).is_checked() and levels.nth(1).is_disabled()
    page.select_option("#add-part", "billing")
    assert page.input_value("#add-id") == "watcher-billing"
    accessible(page)
    shot(page, "settings-add")
    page.click("#add-it")
    expect(page.locator("fieldset[data-instance=watcher-billing]")).to_be_focused()
    # Reviewed as any change: billing's owner approves it, and its owner asks them to
    page.click("#review")
    page.wait_for_selector("#reviewed-changes li", timeout=30000)
    assert page.locator("#reviewed-changes li").all_inner_texts() == [(
        "Adds watcher-billing: the watcher, working in billing at level 0, serving Priya Nair, run by "
        "Priya Nair. widens what agents do")]
    assert page.inner_text("#reviewed-approvers") == "It needs the approval of Ana Ortiz."
    page.click("#send")
    page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    # a5s proposes it to billing's owner, who approves it on its own page, seeing who asked
    stack.scheduler().apply_approved()
    [waiting] = api(approving, provider, "/settings/api", person="ana").json()["waiting"]
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}{waiting['link']}")  # signing in afresh, for this version alone
    page.wait_for_selector("#asker >> text=Priya Nair asked for it", timeout=30000)
    page.click("#approve")
    page.wait_for_selector("#status >> text=You approved version", timeout=30000)
    stack.scheduler().apply_approved()  # in force
    # And it's at work: its page shows where it runs, and no longer offers to put it to work
    provider.person = "priya"
    page = browser.new_page()
    page.goto(f"{approving}/studio/agents/watcher")
    page.wait_for_selector("table >> text=watcher-billing", timeout=30000)
    assert page.locator("#put-to-work").count() == 0
    assert page.get_attribute("#draft-change", "class") == "primary"  # its one thing to do again
