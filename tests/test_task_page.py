"""People's own page for their tasks (core/tasking.py, core/inbox.py): each person sees every
long task they asked an agent for, how it stands, what it waits on and what it has spent, and
cancels one there. They see nobody else's, and a task whose words name a record they may no
longer see shows how it stands alone."""

from datetime import timedelta

import httpx

from a5s import db
from a5s.core.tasks import TaskService, TaskSpec
from test_task_runs import ASKED, a_task, tasks_of


def signed_in(url: str, provider):
    def api(path: str, person: str = "ana", method: str = "GET") -> httpx.Response:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        return httpx.request(method, f"{url}{path}", headers=headers, timeout=30)
    return api


def test_each_person_sees_and_cancels_their_own_tasks(stack, approving, provider):
    mine, bens = a_task(stack), a_task(stack, owner="ben")
    api = signed_in(approving, provider)
    seen = api("/tasks/api").json()
    assert seen["you"] == "Ana Ortiz"
    [shown] = seen["tasks"]  # hers alone
    assert (shown["task"], shown["agent"], shown["status"], shown["what"], shown["progress"]) == (
        f"T-{mine['number']}", "assistant", "queued", ASKED, 0)
    assert shown["spent"] == "0 of 400,000 tokens" and not shown["ended"] and shown["has until"]
    assert api(f"/tasks/api/T-{bens['number']}/cancel", method="POST").status_code == 404
    assert api(f"/tasks/api/T-{mine['number']}/cancel", method="POST").json() == {
        "cancelled": f"T-{mine['number']}"}
    assert [t["status"] for t in tasks_of(stack)] == ["cancelled", "queued"]  # Ben's goes on
    [cancel] = [e for e in stack.ledger() if e["kind"] == "task" and e["action"] == "cancel"]
    assert cancel["acts_for"] == ["ana"] and cancel["args"]["by"]["chars"] == 3  # by hash
    again = api(f"/tasks/api/T-{mine['number']}/cancel", method="POST")
    assert again.status_code == 409 and "can't be cancelled" in again.json()["detail"]
    assert api("/tasks/api").json()["tasks"][0]["ended"] is True
    assert api("/tasks/api/T-x/cancel", method="POST").status_code == 404
    assert httpx.get(f"{approving}/tasks/api", timeout=30).status_code == 401
    assert api("/tasks/api", person="nobody").status_code in (401, 403)


def test_a_task_naming_a_record_they_may_no_longer_see_shows_how_it_stands_alone(
        stack, approving, provider):
    tasks = TaskService(stack.admin)
    tasks.clock = stack.gateway.clock
    tasks.create(TaskSpec(instance="assistant-finance", owner="ana", task="Chase Q-1003 for me",
                          token_budget=40_000,
                          deadline=stack.gateway.clock() + timedelta(days=1)))
    [shown] = signed_in(approving, provider)("/tasks/api").json()["tasks"]
    assert shown["withheld"] is True and "what" not in shown and "plan" not in shown
    assert shown["status"] == "queued"  # how it stands, and nothing of its words


def test_an_offer_they_never_said_yes_to_shows_as_lapsed(stack, approving, provider):
    stack.model.reply(None, ("offer_task", {"task": ASKED}))
    stack.model.reply("I can take that on as a task: shall I start it?")
    stack.say("Could you go through all my open questions and say what each waits on?")
    api = signed_in(approving, provider)
    assert api("/tasks/api").json()["tasks"][0]["status"] == "offered"
    with db.transaction(stack.admin) as conn:  # offered two days before the core's now
        conn.execute("update tasks set asked_at = %s",
                     (stack.gateway.clock() - timedelta(days=2),))
    assert api("/tasks/api").json()["tasks"][0]["status"] == "offered, and lapsed"


def test_someone_sees_and_cancels_a_task_in_the_browser(stack, approving, provider, browser):
    a_task(stack)
    served = httpx.get(f"{approving}/tasks/", timeout=30)
    assert "script-src 'self'" in served.headers["Content-Security-Policy"]
    provider.person = "ana"
    page = browser.new_page()
    page.goto(f"{approving}/tasks/")
    page.wait_for_selector(f"#tasks >> text={ASKED}", timeout=30000)
    assert page.inner_text("#who") == "Ana Ortiz"
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    assert "with the assistant: queued, 0% done" in page.inner_text("#tasks")
    page.click("#tasks button:has-text('Cancel')")
    page.wait_for_selector("#status >> text=Cancelled", timeout=30000)
    assert "cancelled" in page.inner_text("#tasks") and page.locator("#tasks button").count() == 0
    assert tasks_of(stack)[0]["status"] == "cancelled"
