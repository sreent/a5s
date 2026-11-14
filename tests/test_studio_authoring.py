"""Making an agent in the studio, in a browser (docs/studio.md, step 2): an agent's owner starts
one from a template, picks its tools, edits what it's for, and sees what would stop its release
and its map as they go; the definition keeps its comments; the draft is kept as it's edited,
and is there again after a reload; and they draft a change to an agent they own, then drop it."""

from __future__ import annotations

import yaml

from a5s import db


def kept(page) -> None:
    """Once the page has kept the latest change."""
    page.wait_for_selector("#kept >> text=kept", timeout=30000)


def test_an_agents_owner_makes_an_agent_in_the_studio(stack, approving, provider, browser):
    from test_ui_pages import shot

    provider.person = "priya"  # who owns the assistant and the watcher
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    refused = []
    page.on("console", lambda m: refused.append(m.text) if "Content Security Policy" in m.text else None)
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"{approving}/studio/agents")
    page.click("a:has-text('New agent')")
    page.wait_for_selector(".template >> text=assistant", timeout=30000)
    page.fill("#agent-name", "finance-helper")
    page.click(".template:has-text('assistant') >> nth=0")
    page.click("#make")

    page.wait_for_selector("#problems >> text=Nothing would stop its release", timeout=30000)
    assert page.evaluate("location.pathname").startswith("/studio/drafts/")
    assert "the finance-helper is new" in page.inner_text("#signers")  # who'd sign, before anything
    page.wait_for_selector(".agent-map .map-node >> text=close_question", timeout=30000)
    assert "no sandbox here" in page.inner_text("#try")  # where there's none, it says so
    page.click("[role=tab]:has-text('Tools')")  # one tool fewer, and its map shows it
    page.uncheck("input[aria-label=close_question]")
    kept(page)
    page.wait_for_selector(".agent-map .map-node >> text=close_question", state="detached", timeout=30000)
    page.click("[role=tab]:has-text('Basics')")
    page.fill("#works-for", "The finance team")
    kept(page)
    page.click("[role=tab]:has-text('Files')")
    definition = page.input_value("#file-text")
    assert "works_for: The finance team" in definition and "close_question" not in definition
    assert "scope: none # it changes no part's data" in definition  # its comments kept
    page.fill("#file-text", definition.replace("documents: [create_draft]",
                                               "documents: [create_draft, shred_it]"))
    page.wait_for_selector("#problems >> text=the scenario hasn't got shred_it", timeout=30000)
    page.wait_for_selector(".agent-map .map-node.denied >> text=shred_it", timeout=30000)
    shot(page, "studio-draft")

    page.reload()  # it was kept, as it was left
    page.wait_for_selector("#problems >> text=shred_it", timeout=30000)
    page.click("[role=tab]:has-text('Basics')")
    assert page.input_value("#works-for") == "The finance team"

    page.click("nav.crumbs a:has-text('Agents')")  # their drafts, among the agents
    page.wait_for_selector("#drafts >> text=finance-helper", timeout=30000)
    page.click(".agent-card a.agent-name:text-is('assistant')")
    page.click("#draft-change")  # a change to the assistant, from its folder as released
    page.wait_for_selector("#problems >> text=Nothing would stop its release", timeout=30000)
    page.click("button:has-text('Drop the draft')")
    page.wait_for_selector("#drafts >> text=finance-helper", timeout=30000)
    assert page.locator("#drafts li").count() == 1  # the change dropped, the new one kept
    assert refused == []


def test_an_agents_owner_tries_their_draft_in_the_sandbox(stack, with_sandbox, approving, provider,
                                                          browser):
    from test_ui_pages import shot

    provider.person = "priya"
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    refused = []
    page.on("console", lambda m: refused.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto(f"{approving}/studio/new")
    page.wait_for_selector(".template >> text=assistant", timeout=30000)
    page.fill("#agent-name", "finance-helper")
    page.click(".template:has-text('assistant') >> nth=0")
    page.click("#make")
    page.wait_for_selector("#problems >> text=Nothing would stop its release", timeout=30000)
    page.wait_for_selector("#try-as", timeout=30000)
    page.select_option("#try-as", "ben")  # one of the sandbox's made-up people
    page.fill("#try-text", "Which questions mention an invoice?")
    page.click("#try button:has-text('Say it')")
    page.wait_for_selector(".try-answer >> text=I looked it up and found Q-1001", timeout=60000)
    assert "Ben Okafor said" in page.inner_text(".try-said")
    steps = page.inner_text(".try-answer .steps")
    assert "search_records" in steps and "allow" in steps
    page.click("details.sent summary")  # what the model was sent, whole: it's all made up
    page.wait_for_selector(".said-to.role-system", timeout=30000)
    assert page.inner_text(".try-answer .faint >> nth=0") == "finance-helper answered"
    assert page.locator(".said-to.role-system").count() == 1  # the second call shows what's new
    shot(page, "studio-try")
    page.fill("#try-text", "And which mention a refund?")  # a second turn, as the same person
    page.click("#try button:has-text('Say it')")
    page.wait_for_selector(".try-turns > li:nth-child(2) .try-answer", timeout=60000)
    assert "since what the stand-in used isn't the agent's choice" in page.inner_text(".try-keep")
    page.fill("#case-name", "finds questions by what they mention")
    page.click("#keep-case")
    page.wait_for_selector("#case-kept >> text=Kept as finds questions by what they mention", timeout=30000)
    page.wait_for_selector("#kept >> text=kept", timeout=30000)
    draft = page.evaluate("location.pathname").rsplit("/", 1)[-1]
    with db.transaction(stack.admin) as conn:
        files = conn.execute("select files from agent_drafts where id = %s", (draft,)).fetchone()["files"]
    [case] = yaml.safe_load(files["tests/tried.yaml"])  # as the agent's suite runs it
    assert case == {"name": "finds questions by what they mention", "as": "ben", "steps": [
        {"say": "Which questions mention an invoice?"}, {"say": "And which mention a refund?"}]}
    assert files["tests/tried.yaml"].startswith("# Test cases kept from the sandbox's test pane")
    page.fill("#case-name", "finds questions by what they mention")  # the same name again
    page.click("#keep-case")
    page.wait_for_selector(".try-keep .problem >> text=it has a test case called", timeout=30000)
    # Its test cases, the template's and the one just kept, run as its suite runs them: those
    # that need what the suite alone does say so, and on the stand-in, one fails, and says why
    page.wait_for_selector(".case >> text=finds questions by what they mention", timeout=30000)
    page.click("#run-cases")
    page.wait_for_selector("#cases-summary >> text=3 of 4 passed", timeout=120000)
    failed = page.locator(""".case:has-text("says when it can't find a record")""").inner_text()
    assert "failed" in failed and "step 1: said none of" in failed
    alone = page.locator(".case:has-text('offers a reminder, and keeps it on the yes')").inner_text()
    assert "its suite alone" in alone and "It needs then" in alone
    shot(page, "studio-cases")
    # Nothing set up to publish with here: its author opens the pull request, on whichever git
    # host, with its folder and the words a5s gives for it, which say who must sign
    assert page.locator("#publish").count() == 0
    assert page.inner_text("#pull-folder") == "agents/finance-helper/"
    assert page.input_value("#pull-title") == "Add finance-helper"
    assert "## Who must sign its release" in page.input_value("#pull-body")
    assert refused == []
