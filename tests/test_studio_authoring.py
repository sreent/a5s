"""Making an agent in the studio, in a browser (docs/studio.md, step 2): an agent's owner starts
one from a template, picks its tools, edits what it's for, and sees what would stop its release
and its map as they go; the definition keeps its comments; the draft is kept as it's edited,
and is there again after a reload; and they draft a change to an agent they own, then drop it."""

from __future__ import annotations


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
    page.goto(f"{approving}/studio/")
    page.click("a:has-text('New agent')")
    page.wait_for_selector(".template >> text=assistant", timeout=30000)
    page.fill("#agent-name", "finance-helper")
    page.click(".template:has-text('assistant') >> nth=0")
    page.click("#make")

    page.wait_for_selector("#problems >> text=Nothing would stop its release", timeout=30000)
    assert page.evaluate("location.pathname").startswith("/studio/drafts/")
    assert "the finance-helper is new" in page.inner_text("#signers")  # who'd sign, before anything
    page.wait_for_selector(".agent-map .map-node >> text=close_question", timeout=30000)
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
