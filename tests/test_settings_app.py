"""The settings app: the people who approve instances review the whole version in force, in
words and as written, and ask for a new one. Asking changes nothing by itself: the gateway
proposes it to everyone it needs, and they approve it on its own page."""

import httpx
import yaml

from test_approvals import in_force_serial

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
        "An agent earns level 2 in orders once graded samples show it's 95% accurate."]
    written = yaml.safe_load(body["in_force"]["text"])
    assert written["instances"]["assistant-finance"]["parts"] == ["billing"]
    assert body["waiting"] == [] and body["requests"] == []


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
    assert told["text"].startswith(f"Serial {serial} of a5s's settings waits for its instance "
                                   "approvers")
    assert len(stack.inbox("ana")) == 1
    now = api(approving, provider, "/settings/api").json()
    [waiting] = now["waiting"]
    assert waiting["serial"] == serial and waiting["approved_by"] == []
    assert waiting["needs"] == ["nobody who approves instances has approved it"]
    assert now["requests"][0]["outcome"] == "proposed"
    by = {e["action"]: e["args"].get("by") for e in stack.ledger() if e["kind"] == "admin"}
    assert by["request"] == "ana" and by["propose"] == "ana"
    stack.scheduler().apply_approved()
    assert len(stack.inbox("omar")) == 0  # asked once


def test_an_approver_asks_for_a_change_in_the_browser(stack, approving, provider, browser):
    page = browser.new_page()
    page.goto(f"{approving}/settings/")  # to the provider, and straight back
    page.wait_for_selector("#in-force-title >> text=In force", timeout=30000)
    assert page.inner_text("#who") == "Ana Ortiz"
    assert page.locator("#whole li").all_inner_texts()[1] == ASSISTANT
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    edited = yaml.safe_load(page.input_value("#text"))
    edited["instances"]["assistant-finance"]["serves"].append("chen")
    page.fill("#text", yaml.safe_dump(edited))
    page.click("#review")
    page.wait_for_selector("#reviewed-changes >> text=Chen Wei", timeout=30000)
    assert page.inner_text("#reviewed-approvers") == "It needs the approval of Ana Ortiz."
    page.click("#send")
    page.wait_for_selector("#status >> text=You asked for serial", timeout=30000)
    page.wait_for_selector("#requests li", timeout=30000)
    assert "waiting for a5s to ask its approvers" in page.inner_text("#requests")
