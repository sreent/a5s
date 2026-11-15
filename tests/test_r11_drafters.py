"""Round 11, reviewer E (E-4): a draft keeps who drafted it before whoever holds it now. A
handed-over draft read as its taker's own, on its page and in its pull request, which told its
reviewers and the release's signers that the taker drafted it: so its first author, the agent's
owner, could sign it as though someone else had written it. Now the draft keeps who drafted it
before, and when and how it went on, handed over or copied; its page says so, its pull request
names everyone who drafted it, and an export and an erasure find someone named there."""

from a5s import db
from a5s.core import erasure, export
from test_drafts import as_
from test_studio_spaces import coauthor

ADDED = "\nWhen asked about a record, also tell them its link and what they asked.\n"


def handed(stack, approving, provider) -> str:
    """Priya changes the assistant's instructions in a draft, and hands it over to Omar."""
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    files = {**draft["files"], "AGENTS.md": draft["files"]["AGENTS.md"] + ADDED}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).status_code == 200
    coauthor(stack)
    assert priya("POST", f"/studio/api/drafts/{draft['id']}/hand-over",
                 {"to": "omar"}).status_code == 200
    return draft["id"]


def test_a_handed_over_draft_names_who_drafted_it_before(stack, approving, provider):
    draft = handed(stack, approving, provider)
    omar = as_(approving, provider, "omar")
    his = omar("GET", f"/studio/api/drafts/{draft}").json()
    assert his["yours"] and [(d["name"], d["how"]) for d in his["drafted_before"]] == [
        ("Priya Nair", "handed")]
    pull = omar("GET", f"/studio/api/drafts/{draft}/pull-request").json()
    first = pull["body"].splitlines()[0]
    assert first.startswith("Drafted in the a5s studio by Omar Haddad (omar)")
    assert first.endswith("Before them, Priya Nair handed it over.")


def test_a_copy_names_who_drafted_what_it_copies(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    coauthor(stack)
    omar = as_(approving, provider, "omar")
    copy = omar("POST", "/studio/api/drafts", {"copy_of": draft["id"]}).json()
    assert [(d["name"], d["how"]) for d in copy["drafted_before"]] == [("Priya Nair", "copied")]
    pull = omar("GET", f"/studio/api/drafts/{copy['id']}/pull-request").json()
    assert "Before them, Priya Nair drafted what it copies." in pull["body"].splitlines()[0]


def test_an_export_and_an_erasure_find_someone_who_drafted_anothers_draft(stack, approving,
                                                                        provider):
    draft = handed(stack, approving, provider)
    with db.transaction(stack.cfg.database_url) as conn:  # the core's export of Priya
        found = export.gather(conn, "priya")
    assert [(d["agent"], d["how"]) for d in found["drafted_first"]] == [("assistant", "handed")]
    with db.transaction(stack.cfg.database_url) as conn:  # the core erases Priya, as asked
        gone, _ = erasure.erase(conn, "priya", stack.gateway.clock(), here=True)
    assert gone.get("drafted_first") == 1
    omar = as_(approving, provider, "omar")
    his = omar("GET", f"/studio/api/drafts/{draft}").json()
    assert [(d["name"], d["how"]) for d in his["drafted_before"]] == [
        ("someone a5s no longer names", "handed")]
    assert "Priya" not in str(his["drafted_before"])


def test_the_draft_page_says_who_handed_it_over(stack, approving, provider, browser):
    draft = handed(stack, approving, provider)
    provider.person = "omar"
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/studio/drafts/{draft}")
    page.wait_for_selector("#kept >> text=kept", timeout=30000)  # his, to change
    assert "Before you, Priya Nair handed it over" in page.inner_text("main")
