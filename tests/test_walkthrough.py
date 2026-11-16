"""Phase 5's first walk-through (docs/phase-5.md), on the sample scenario: an agent goes from an
idea to work through a5s's own pages and its command line alone, as its people would take it.

Priya owns the team's agents, and builds a new one, due-dates, in the studio, and publishes it.
Rosa approves releases from outside the team that runs a5s, and signs the release that adds it,
with Priya, whom the directory names its owner. Ana owns billing: she approves putting it to
work there, and decides the changes it asks for. Ben is served by it. Kofi, assurance, reads
what happened in the audit trail.

The deployment isn't in development: it opens no run until its release has the signatures it
needs. Its guide, with a picture of each step:

    A5S_GUIDE=docs/guides uv run pytest tests/test_walkthrough.py
"""

from __future__ import annotations

from a5s.contract import record_of
from a5s.core import drafts
from conftest import (
    PROVIDER_KEY,
    build_root,
    deciding,
    free_port,
    running,
    serve,
)
from fake_github import FakeGitHub
from test_proposals import invented
from test_studio_authoring import kept
from walkthrough import (
    Walk,
    answering,
    confirms,
    decided_in_trail,
    deployed,
    merged,
    owned,
    released,
    says,
    signed_and_recorded,
    walking_on,
)

AGENT = "due-dates"
INSTANCE = f"{AGENT}-billing"
INSTRUCTIONS = """# due-dates

You keep the due dates of customers' questions in billing right. When someone asks you to move
one, find the question, say what its due date is now, and ask for the change at once, with the tool
that makes it: its decider in billing decides it, so you needn't ask them to confirm it first.
Never move a date you weren't asked to move.
"""


def built(walk: Walk, url: str, forge: FakeGitHub) -> tuple[str, dict]:
    """Priya builds due-dates in the studio and publishes it: its draft, and its pull request."""
    page = walk.as_("priya", f"{url}/studio/new")
    with walk.step("Priya, who owns the team's agents, starts a new one in the studio, due-dates, "
                   "from the assistant's template.", page):
        page.wait_for_selector(".template >> text=assistant", timeout=30000)
        page.fill("#agent-name", AGENT)
        page.click(".template:has-text('assistant') >> nth=0")
        page.click("#make")
        page.wait_for_selector(".flow-canvas [data-step='tool:change_due_date']", timeout=30000)
        kept(page)
    with walk.step("On its canvas, she keeps the tools that read records and the one that changes "
                   "a question's due date, and takes away the rest. What follows says who'd "
                   "decide each change it asks for, in billing and in orders.", page):
        for tool in ("close_question", "create_draft"):
            page.click(f"[data-step='tool:{tool}']")
            page.click("#take-away")
            page.wait_for_selector(f"[data-step='tool:{tool}']", state="detached", timeout=30000)
            kept(page)
        page.click("[data-step='tool:change_due_date']")
        follows = page.inner_text(".wb-inspector .follows")
        assert "a decider of its record's part: Ana Ortiz in billing; Omar Haddad in orders" in follows
    with walk.step("She plans its first instance: in billing, serving Ben Okafor. It's kept "
                   "with the draft, and in force nowhere until billing's owner approves it.", page):
        page.click("[data-step=agent]")
        page.check("#plan-title ~ fieldset label:has-text('billing') input")
        page.wait_for_selector("#what-changed >> text=Ana Ortiz would decide its changes there",
                               timeout=30000)
        page.check("#plan-title ~ fieldset label:has-text('Ben Okafor') input")
        kept(page)
    with walk.step("She tells it how to work, in its instructions.", page):
        page.click(".wb-bar .modes button:has-text('Instructions')")
        page.fill("#instructions", INSTRUCTIONS)
        kept(page)
    with walk.step("Before she publishes it, the draft says who must sign its release: Rosa, "
                   "the release approver, and the due-dates's owner, whom the directory doesn't "
                   "name yet.", page):
        page.click(".wb-bar .modes button:has-text('Design')")  # the draft as a whole, chosen nothing
        page.wait_for_selector("#signers li", timeout=30000)
        signers = page.inner_text("#signers")
        assert "the release approver, from outside the team that runs a5s: Rosa Mendes" in signers
        assert "Nobody holds that role in the directory yet" in page.inner_text(
            f"#signers [data-role='agent-owner:{AGENT}']")
        page.locator("#signers").scroll_into_view_if_needed()
    with walk.step("Nothing a5s checks stops its release, so she publishes it: a5s opens its pull "
                   "request on the team's repository, as her, once she says so at GitHub.", page):
        page.click("#to-publish")
        page.click("#publish")
        page.wait_for_selector("#user-code", timeout=30000)
        forge.grant(page.inner_text("#user-code"), "priya-gh")  # at GitHub, as herself
        page.wait_for_selector("#published >> text=its pull request", timeout=30000)
    [pull] = forge.pulls
    assert "Nobody holds that role in the directory yet" in pull["body"]
    return page.evaluate("location.pathname"), pull


def at_work(walk: Walk, stack, url: str, draft: str) -> None:
    """Priya puts it to work from its plan, and Ana, billing's owner, approves it."""
    page = walk.as_("priya", f"{url}{draft}")
    with walk.step("Back in the studio, its draft says its release is signed and deployed. Priya "
                   "follows its one next step: putting it to work, from its plan, in the studio's "
                   "settings.", page):
        page.wait_for_selector("#put-to-work", timeout=30000)
        page.click("#put-to-work")
        page.wait_for_selector("#add-instance", timeout=30000)
        assert page.input_value("#add-agent") == AGENT and page.input_value("#add-part") == "billing"
        assert page.input_value("#add-id") == INSTANCE
    with walk.step("The form is filled in from its plan: due-dates, in billing, serving Ben. "
                   "She reviews what it changes, in words, and asks for it.", page):
        page.click("#add-it")
        page.click("#review")
        page.wait_for_selector("#reviewed-changes li", timeout=30000)
        added = page.locator("#reviewed-changes li").first.inner_text()
        assert INSTANCE in added and "serving Ben Okafor" in added
        assert page.inner_text("#reviewed-approvers") == "It needs the approval of Ana Ortiz."
        page.click("#send")
        page.wait_for_selector("#status >> text=You asked for version", timeout=30000)
    stack.scheduler().apply_approved()  # a5s asks its approvers, as it does on its own
    page = walk.as_("ana", f"{url}/studio/")
    with walk.step("Ana, who owns billing, finds it waiting for her approval on her studio home.",
                   page):
        page.wait_for_selector("#waiting .wait >> text=waits for your approval", timeout=30000)
        page.click("#waiting a:has-text('waits for your approval')")
        page.wait_for_selector("#asker >> text=Priya Nair asked for it", timeout=30000)
    with walk.step("She reads what it changes, and approves it, signed in afresh for that version "
                   "alone.", page):
        page.click("#approve")
        page.wait_for_selector("#status >> text=You approved version", timeout=30000)
    stack.scheduler().apply_approved()  # in force


def asked_and_decided(walk: Walk, stack, url: str) -> str:
    """Ben asks it to move a due date, and Ana decides the change it asks for: the new date."""
    move, day = invented()
    stack.model.reply(None, move)
    stack.model.reply(f"Q-1002 is due on 2026-11-06. I've asked to move it to {day}: Ana Ortiz "
                      "decides it.")
    page = walk.as_("ben", f"{url}/chat/")
    with walk.step("Ben asks due-dates, in the chat, to move a question's due date. It asks for "
                   "the change, which waits for Ana, its decider in billing.", page):
        says(page, AGENT, f"Please move Q-1002 to {day}.", f"I've asked to move it to {day}")
        confirms(page, stack, AGENT)
    page = walk.as_("ana", f"{url}/studio/")
    with walk.step("Ana finds the change waiting for her decision, and opens its card: who asks, "
                   "for whom, and what it does, in code's words.", page):
        page.wait_for_selector("#waiting a:has-text('waits for your decision')", timeout=30000)
        page.click("#waiting a:has-text('waits for your decision')")
        page.wait_for_selector(".approval >> text=Q-1002", timeout=30000)
        assert "for Ben Okafor" in page.inner_text(".approval .who-about")
    with walk.step("She approves it, signed in afresh for this decision alone, and a5s makes the "
                   "change.", page):
        walk.signs_in("ana")
        page.click(".approval button >> text=Approve")
        page.wait_for_selector("#status >> text=You approved", timeout=30000)
    stack.scheduler().decided()  # a5s makes the change, as it does on its own
    assert record_of(stack.gateway.scenario, "Q-1002").fields["due date"] == day
    return day


def watched_and_audited(walk: Walk, url: str, day: str) -> None:
    """Priya watches its runs, and Kofi reads the change in the audit trail."""
    page = walk.as_("priya", f"{url}/studio/agents/{AGENT}")
    with walk.step("Priya watches it at work, on its instance's page: its figures for each day. "
                   "Its runs, one by one, stay hidden while it serves so few people, since each "
                   "would say what Ben did.", page):
        page.wait_for_selector(f"table >> text={INSTANCE}", timeout=30000)
        page.click(f"a:has-text('{INSTANCE}')")
        page.wait_for_selector(".tiles .tile", timeout=30000)
        page.wait_for_selector("text=It serves fewer than", timeout=30000)
    page = walk.as_("kofi", f"{url}/audit/")
    with walk.step("Kofi, of assurance, reads what due-dates did in the audit trail: who asked, "
                   "who decided, and what changed.", page):
        page.wait_for_selector("#find:not([hidden])", timeout=30000)
        page.fill("#instance", INSTANCE)
        page.click("#search")
        page.wait_for_selector("#entries li", timeout=30000)
        assert day in page.inner_text("#entries") or "change_due_date" in page.inner_text("#entries")
        decided_in_trail(page, "ana")


def test_an_agent_goes_from_an_idea_to_work_through_a5s_alone(database, tmp_path, provider, browser,
                                                              monkeypatch, capsys):
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    on = walking_on()
    model, http = on.model, on.http
    root = build_root(tmp_path, on.alias, on.models)
    walk = Walk("sample", "An agent, from an idea to work", browser, provider)
    forge = FakeGitHub({f"agents/{name}/{path}": text for name in ("assistant", "watcher")
                        for path, text in drafts.folder_files(root / "agents" / name).items()})
    with serve(forge.app(), free_port()) as forge_url:
        forge.url = forge_url
        # The deployment as it stands: its release approved by everyone it needs, at first
        with running(database, root, http, model) as stack:
            deployed(stack, forge)
            said = released(stack, tmp_path / "first", monkeypatch, capsys)
            said = signed_and_recorded(said, capsys, "priya", "tomas", "rosa", "kofi")
            assert said.rstrip().endswith("Approved here."), said
            with deciding(stack, provider) as url:
                draft, pull = built(walk, url, forge)

        with walk.step("The team reviews its pull request, and it's merged. Nobody holds the "
                       "due-dates's owner role yet, so the directory names Priya, as the identity "
                       "provider's administrator would."):
            merged(stack, forge.files(pull["head"]), AGENT)
            owned(stack.cfg.scenario_dir, "priya", AGENT)
        with running(database, root, http, model) as stack:  # deployed again, from main
            deployed(stack, forge)
            with walk.step("Deployed again, a5s runs nothing of the new release yet. "
                           "`a5s release status` says who must sign it, and why: Rosa, since the "
                           "directory changed and due-dates is new, and its owner, Priya."):
                said = released(stack, tmp_path / "second", monkeypatch, capsys)
                assert "It needs the release approver" in said and f"the {AGENT}'s owner" in said
                assert "Not approved here" in said
            with walk.step("Rosa and Priya sign it with `a5s release sign`, each on their own "
                           "machine, and the team records it with `a5s release approve`: it's "
                           "approved here, and a5s runs it."):
                said = signed_and_recorded(said, capsys, "rosa", "priya")
                assert said.rstrip().endswith("Approved here."), said
            with deciding(stack, provider) as url, answering(stack):
                at_work(walk, stack, url, draft)
                day = asked_and_decided(walk, stack, url)
                watched_and_audited(walk, url, day)
    walk.guide("A new agent, due-dates, taken from an idea to work in the sample scenario through "
               "a5s's own pages and its command line, by the people whose part each step is. "
               "tests/test_walkthrough.py takes these steps, and made these pictures.")
