"""People's commonest journeys through the studio, counted: the clicks each takes and the pages
the browser loads, from where the person starts to what they came to do. Each has a budget, and
a change that makes a journey longer fails here, so the studio only gets quicker to use.

A fresh sign-in for an act that counts is a page load of its own, to the identity provider and
back: the budgets count it, since a person waits for it. Keys count as nothing, so the palette's
way, Ctrl-K, the name, Enter, is the shortest there is."""

import pytest

from test_approvals import CHEN_TOO, proposed, serves
from test_proposals import asked, decide, held, sweep
from test_task_runs import ASKED, a_task

# What each journey may take at most: (clicks, page loads), counted once the person is on the
# page they start from, signed in
BUDGETS = {
    "decide a change from the home": (2, 1),
    "approve a version from its card": (1, 1),
    "grade a sample from the home": (3, 1),
    "cancel a task from the sidebar": (3, 0),
    "open an instance by name": (0, 0),
    "suspend an instance by name": (1, 1),  # in its zone, signed in afresh: no dialog besides
}

pytestmark = pytest.mark.usefixtures("approving")


class Journey:
    """A person's way through the studio: each click they make, and each page the browser loads,
    from the moment they start."""

    def __init__(self, page, name: str):
        self.page, self.name = page, name
        self.clicks = self.loads = 0
        page.on("load", lambda _: self.loaded())

    def loaded(self) -> None:
        self.loads += 1

    def click(self, selector: str) -> None:
        self.clicks += 1
        self.page.click(selector)

    def keys(self, *pressed: str) -> None:
        for key in pressed:
            self.page.keyboard.press(key)

    def type(self, words: str) -> None:
        self.page.keyboard.type(words)

    def done(self) -> None:
        """It took no more than its budget."""
        clicks, loads = BUDGETS[self.name]
        assert self.clicks <= clicks and self.loads <= loads, (
            f"{self.name} took {self.clicks} clicks and {self.loads} page loads, over its budget of "
            f"{clicks} and {loads}")


def start(browser, url: str, provider, person: str, path: str, ready: str, name: str) -> Journey:
    """The person, signed in, on the page they start from: the journey counts from here."""
    provider.person = person
    page = browser.new_page()
    page.goto(f"{url}{path}")
    page.wait_for_selector(ready, timeout=30000)
    return Journey(page, name)


def test_deciding_a_change_from_the_home(stack, approving, provider, browser):
    asked(stack)
    [p] = held(stack)
    walk = start(browser, approving, provider, "ana", "/studio/",
                 "#waiting a:has-text('waits for your decision')", "decide a change from the home")
    walk.click("#waiting a:has-text('waits for your decision')")
    walk.click(".approval button >> text=Approve")  # signed in afresh, for this decision alone
    walk.page.wait_for_selector("#status >> text=You approved P-1", timeout=30000)
    walk.done()
    assert held(stack)[0]["id"] == p["id"]


def test_approving_a_version_from_its_card(stack, approving, provider, browser):
    asked_for = proposed(stack, serves=CHEN_TOO)
    walk = start(browser, approving, provider, "ana", asked_for["link"].removeprefix(approving),
                 "#approve", "approve a version from its card")
    walk.click("#approve")
    walk.page.wait_for_selector(f"#status >> text=You approved version {asked_for['serial']}", timeout=30000)
    walk.done()
    stack.scheduler().apply_approved()
    assert serves(stack) == CHEN_TOO


def test_grading_a_sample_from_the_home(stack, approving, provider, browser):
    asked(stack)
    [p] = held(stack)
    decide(approving, provider, [p["digest"]])
    sweep(stack)
    walk = start(browser, approving, provider, "dana", "/studio/",
                 "#waiting a:has-text('waits for your grade')", "grade a sample from the home")
    walk.click("#waiting a:has-text('waits for your grade')")
    walk.page.wait_for_selector("[data-sample]", timeout=30000)
    walk.click("[data-sample] button:text-is('Right')")
    walk.click("#send")  # signed in afresh, for exactly this grade
    walk.page.wait_for_selector("#status >> text=Graded right", timeout=30000)
    walk.done()


def test_cancelling_a_task_from_the_sidebar(stack, approving, provider, browser):
    a_task(stack)
    walk = start(browser, approving, provider, "ana", "/studio/", "#pages a:has-text('Tasks')",
                 "cancel a task from the sidebar")
    walk.click("#pages a:has-text('Tasks')")
    walk.page.wait_for_selector(f"#tasks >> text={ASKED}", timeout=30000)
    walk.click("#tasks button:text-is('Cancel')")
    walk.click("dialog[open] button:has-text('Cancel it')")  # asked first, as what can't be undone
    walk.page.wait_for_selector("#status >> text=Cancelled", timeout=30000)
    walk.done()


def test_opening_an_instance_by_name(stack, approving, provider, browser):
    walk = start(browser, approving, provider, "ana", "/studio/", "#find-anything", "open an instance by name")
    walk.keys("Control+k")
    walk.page.wait_for_selector("[role=option] >> text=assistant-finance", timeout=30000)
    walk.type("assistant-finance")
    walk.keys("Enter")
    walk.page.wait_for_selector(".page-head h1 >> text=assistant-finance", timeout=30000)
    assert walk.page.evaluate("location.pathname") == "/studio/instances/assistant-finance"
    walk.done()


def test_suspending_an_instance_by_name(stack, approving, provider, browser):
    walk = start(browser, approving, provider, "ana", "/studio/", "#find-anything", "suspend an instance by name")
    walk.keys("Control+k")
    walk.page.wait_for_selector("[role=option] >> text=assistant-finance", timeout=30000)
    walk.type("assistant-finance")
    walk.keys("Enter")
    walk.click("#suspend")  # in its zone, below the head: signed in afresh, for this alone
    walk.page.wait_for_selector("#asked", timeout=30000)
    walk.done()
