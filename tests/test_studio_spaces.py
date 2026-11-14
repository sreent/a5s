"""Many people in one studio (docs/studio.md#people-roles-and-spaces): an agent's owners and
authors read each other's drafts of it, read only, copy one into a draft of their own, and hand
their own over to one another; and the agents someone's roles bring into their view, with why.
Nobody gets a right here that the directory and the signed settings don't give them."""

from __future__ import annotations

from dataclasses import replace

from test_drafts import as_, recorded, started


def coauthor(stack, who: str = "omar", agent: str = "assistant") -> None:
    """The organisation names someone an author of an agent, in its directory."""
    person = stack.gateway.scenario.person(who)
    stack.gateway.scenario._people[who] = replace(person, roles=(*person.roles, f"agent-author:{agent}"))


def test_an_agents_co_authors_read_each_others_drafts_of_it(stack, approving, provider):
    priya = as_(approving, provider, "priya")  # who owns the assistant
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    new = started(priya)  # and a new agent's, which nobody else may author yet
    coauthor(stack)
    omar = as_(approving, provider, "omar")
    listed = omar("GET", "/studio/api/drafts").json()
    assert listed["drafts"] == []
    assert [(d["agent"], d["author"]) for d in listed["theirs"]] == [("assistant", "Priya Nair")]
    seen = omar("GET", f"/studio/api/drafts/{draft['id']}").json()
    assert (seen["yours"], seen["author"], seen["files"]) == (False, "Priya Nair", draft["files"])
    for method, path, body in (("PUT", "", {"files": draft["files"]}), ("DELETE", "", None),
                               ("POST", "/try", {"person": "ana", "text": "Hello"}),
                               ("POST", "/publish", None), ("GET", "/folder", None),
                               ("GET", "/pull-request", None), ("GET", "/co-authors", None),
                               ("POST", "/hand-over", {"to": "omar"})):
        assert omar(method, f"/studio/api/drafts/{draft['id']}{path}", body).status_code == 404, path
    assert omar("GET", f"/studio/api/drafts/{new['id']}").status_code == 404
    assert as_(approving, provider, "chen")("GET", f"/studio/api/drafts/{draft['id']}").status_code == 403
    assert priya("GET", f"/studio/api/drafts/{draft['id']}").json()["yours"] is True


def test_a_co_author_copies_a_draft_into_one_of_their_own(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    files = {**draft["files"], "AGENTS.md": draft["files"]["AGENTS.md"] + "\nAsk before changing anything.\n"}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).status_code == 200
    coauthor(stack)
    omar = as_(approving, provider, "omar")
    copied = omar("POST", "/studio/api/drafts", {"copy": draft["id"]})
    assert copied.status_code == 200, copied.text
    mine = copied.json()
    assert (mine["agent"], mine["yours"], mine["based_on"]) == (
        "assistant", True, f"a co-author's draft, from {draft['based_on']}")
    assert mine["files"]["AGENTS.md"].endswith("Ask before changing anything.\n")
    again = omar("POST", "/studio/api/drafts", {"copy": draft["id"]})
    assert again.status_code == 409 and "already" in again.json()["detail"]
    assert priya("POST", "/studio/api/drafts", {"copy": draft["id"]}).status_code == 404  # her own
    [entry] = recorded(stack, "copy draft")
    assert (entry["args"]["copied"], entry["args"]["draft"], entry["args"]["by"]) == (
        draft["id"], mine["id"], "omar")


def test_its_author_hands_a_draft_over_to_a_co_author(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    coauthor(stack)
    people = priya("GET", f"/studio/api/drafts/{draft['id']}/co-authors").json()["people"]
    assert people == [{"id": "omar", "name": "Omar Haddad"}]  # who may author it too, with none
    refused = priya("POST", f"/studio/api/drafts/{draft['id']}/hand-over", {"to": "chen"})
    assert refused.status_code == 400 and "may not author the assistant" in refused.json()["detail"]
    handed = priya("POST", f"/studio/api/drafts/{draft['id']}/hand-over", {"to": "omar"})
    assert handed.json() == {"handed": draft["id"], "to": "Omar Haddad"}
    omar = as_(approving, provider, "omar")
    assert omar("GET", f"/studio/api/drafts/{draft['id']}").json()["yours"] is True  # his now
    hers = priya("GET", f"/studio/api/drafts/{draft['id']}").json()  # and hers to read, as its owner
    assert (hers["yours"], hers["author"]) == (False, "Omar Haddad")
    [entry] = recorded(stack, "hand over draft")
    assert (entry["args"]["to"], entry["args"]["by"]) == ("omar", "priya")
    other = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()  # a fresh one
    busy = priya("POST", f"/studio/api/drafts/{other['id']}/hand-over", {"to": "omar"})
    assert busy.status_code == 409 and "has a draft of the assistant already" in busy.json()["detail"]


def test_the_catalogue_says_why_each_agent_is_in_view(stack, approving, provider):
    coauthor(stack)
    def why(person: str) -> dict:
        return {a["id"]: a["why"] for a in as_(approving, provider, person)("GET", "/studio/api").json()["agents"]}
    assert why("priya")["assistant"][0] == "you own it"
    assert why("omar")["assistant"] == ["you author it"]  # authoring brings it in, without its runs
    assert "you run assistant-finance" in why("ben")["assistant"]  # its deputy
    assert "it works in billing, which you own" in why("ana")["assistant"]


def test_a_co_author_reads_a_draft_and_copies_it_in_the_studio(stack, approving, provider, browser):
    priya = as_(approving, provider, "priya")
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    coauthor(stack)
    provider.person = "omar"
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    refused = []
    page.on("console", lambda m: refused.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto(f"{approving}/studio/agents")
    page.wait_for_selector("#co-drafts >> text=Priya Nair's", timeout=30000)
    page.click("#co-drafts a.mono")
    page.wait_for_selector("#copy-draft", timeout=30000)
    assert "read only" in page.inner_text(".page-head, header, main")
    assert page.locator("#try").count() == 0 and page.locator("#publishing").count() == 0
    page.click("#copy-draft")
    page.wait_for_selector("#kept >> text=kept", timeout=30000)  # his own, to change
    assert page.evaluate("location.pathname") != f"/studio/drafts/{draft['id']}"
    assert refused == []
