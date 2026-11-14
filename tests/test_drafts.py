"""Drafts of agents, which the studio keeps for their authors (core/drafts.py, docs/studio.md,
step 2): a new agent from a template, or a change to one of the release, its tools pinned as
the scenario has them each time it's saved, and the checks `a5s agent check` makes. A draft is
its author's alone, never in force, and goes with what a5s keeps of them."""

from __future__ import annotations

import re
from dataclasses import replace

import httpx
import pytest
import yaml
from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import Person
from a5s.core import drafts, ledger
from conftest import ROOT
from test_erase import erase
from test_export import export


def as_(url: str, provider, person: str):
    """The people's API, as someone signed in."""
    def call(method: str, path: str, body: dict | None = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        return httpx.request(method, f"{url}{path}", json=body, headers=headers, timeout=30)
    return call


def started(call) -> dict:
    r = call("POST", "/studio/api/drafts", {"name": "finance-helper", "template": "assistant"})
    assert r.status_code == 200, r.text
    return r.json()


def recorded(stack, action: str) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return [e for e in ledger.entries(conn, limit=1000) if e.get("action") == action]


def test_who_may_author_what():
    def who(*roles: str) -> Person:
        return Person(id="p", name="P", team="t", roles=roles)
    owner, author, engineer = who("agent-owner:assistant"), who("agent-author:assistant"), who("engineer")
    assert drafts.may_author(owner, "assistant") and drafts.may_author(author, "assistant")
    assert not drafts.may_author(owner, "watcher") and not drafts.may_author(engineer, "assistant")
    assert drafts.may_author(owner, None) and drafts.may_author(engineer, None)
    assert not drafts.may_author(author, None)  # named for one agent, not to start new ones
    assert drafts.authors(author) and not drafts.authors(who("part-owner:billing"))


def test_an_agents_owner_starts_a_new_one_from_a_template(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    assert (draft["agent"], draft["based_on"], draft["problems"]) == (
        "finance-helper", "template assistant", [])
    spec = yaml.safe_load(draft["files"]["agent.yaml"])
    assert (spec["id"], spec["release"]) == ("finance-helper", "0.1.0")
    assert draft["files"]["AGENTS.md"] == (ROOT / "agents" / "assistant" / "AGENTS.md").read_text()
    assert yaml.safe_load(draft["files"]["tools.lock"])["get_record"]  # its tools pinned
    assert [d["agent"] for d in priya("GET", "/studio/api/drafts").json()["drafts"]] == ["finance-helper"]
    [entry] = recorded(stack, "draft")
    assert entry["args"] == {"agent": "finance-helper", "draft": draft["id"],
                             "based_on": "template assistant", "by": "priya"}
    templates = {t["name"]: t for t in priya("GET", "/studio/api/templates").json()["templates"]}
    assert templates["assistant"]["lacks"] == [] and "get_record" in templates["assistant"]["tools"]


def test_a_change_to_an_agent_starts_from_its_folder_as_released(stack, approving, provider):
    r = as_(approving, provider, "priya")("POST", "/studio/api/drafts", {"agent": "assistant"})
    assert r.status_code == 200, r.text
    folder = stack.cfg.agents_dir / "assistant"  # as this deployment released it
    assert r.json()["files"]["agent.yaml"] == (folder / "agent.yaml").read_text()
    assert r.json()["based_on"].startswith("assistant 0.1.0+") and r.json()["problems"] == []
    ben = as_(approving, provider, "ben")  # its instance's deputy, who doesn't author it
    assert ben("POST", "/studio/api/drafts", {"agent": "assistant"}).status_code == 403
    assert ben("GET", "/studio/api/drafts").status_code == 403


def test_saving_pins_its_tools_and_says_what_would_stop_its_release(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    files = {**draft["files"], "tools.lock": "get_record: made-up\n"}  # a5s pins, not the page
    files["agent.yaml"] = files["agent.yaml"].replace("documents: [create_draft]",
                                                      "documents: [create_draft, shred_it]")
    saved = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).json()
    assert saved["problems"] == ["the scenario hasn't got shred_it"]
    assert "made-up" not in saved["files"]["tools.lock"]
    files["agent.yaml"] = re.sub(r"(?m)^model:.*$", "model: anything", draft["files"]["agent.yaml"])
    saved = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).json()
    assert saved["problems"] == ["its model, anything, isn't one config/models.yaml approves"]
    files["agent.yaml"] = draft["files"]["agent.yaml"]
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).json()["problems"] == []
    assert priya("GET", f"/studio/api/drafts/{draft['id']}").json()["files"]["agent.yaml"] == files["agent.yaml"]


@pytest.mark.parametrize("path", ["../escape.md", "/etc/passwd.md", "tools.py", ".git/config.yaml",
                                  "skills\\x.md", "a//b.md", ""])
def test_files_no_agents_folder_could_hold_are_refused(stack, approving, provider, path):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    r = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": {**draft["files"], path: "x"}})
    assert r.status_code == 400 and "isn't a file an agent's folder holds" in r.json()["detail"]


def test_a_draft_is_its_authors_alone(stack, approving, provider):
    draft = started(as_(approving, provider, "priya"))
    omar = stack.gateway.scenario.person("omar")  # whom the organisation names its author
    stack.gateway.scenario._people["omar"] = replace(omar, roles=(*omar.roles, "agent-author:assistant"))
    theirs = as_(approving, provider, "omar")
    assert theirs("GET", "/studio/api/drafts").json() == {"drafts": []}
    for method, body in (("GET", None), ("PUT", {"files": draft["files"]}), ("DELETE", None)):
        assert theirs(method, f"/studio/api/drafts/{draft['id']}", body).status_code == 404
    assert theirs("GET", "/studio/api/drafts/not-a-draft").status_code == 404
    assert theirs("POST", "/studio/api/drafts", {"name": "x-ray", "template": "assistant"}).status_code == 403


def test_a_new_agent_needs_a_new_name_and_a_template_that_fits(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    started(priya)
    for body, status, said in (
            ({"name": "finance-helper", "template": "assistant"}, 409, "already"),
            ({"name": "assistant", "template": "watcher"}, 409, "there's an agent assistant already"),
            ({"name": "Finance", "template": "assistant"}, 400, "lower case letters"),
            ({"name": "x-ray", "template": "nowhere"}, 404, "no template nowhere"),
            ({"name": "x-ray"}, 400, "name a new agent")):
        r = priya("POST", "/studio/api/drafts", body)
        assert (r.status_code, said in r.json()["detail"]) == (status, True), r.text


def test_a_dropped_draft_is_gone_and_the_ledger_says_so(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    assert priya("DELETE", f"/studio/api/drafts/{draft['id']}").json() == {"dropped": draft["id"]}
    assert priya("GET", f"/studio/api/drafts/{draft['id']}").status_code == 404
    assert [e["args"]["agent"] for e in recorded(stack, "drop draft")] == ["finance-helper"]


def test_drafts_show_in_their_authors_export_and_go_when_theirs_is_erased(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into agent_drafts (person, agent, based_on, files) values "
                     "('priya', 'finance-helper', 'template assistant', %s)",
                     (Jsonb({"AGENTS.md": "# Finance helper"}),))
    [kept] = export(stack, "priya").json()["drafts"]
    assert kept["agent"] == "finance-helper" and "AGENTS.md" in kept["files"]
    r = erase(stack, "priya")
    assert r.status_code == 200, r.text
    assert r.json()["gone"]["agent_drafts"] == 1
    assert export(stack, "priya").json()["drafts"] == []


def test_the_catalogue_says_what_someone_may_author_and_offers_the_scenarios_tools(stack, approving, provider):
    priya, ben = as_(approving, provider, "priya"), as_(approving, provider, "ben")
    assert priya("GET", "/studio/api").json()["authoring"] == {"new": True, "agents": ["assistant", "watcher"]}
    assert ben("GET", "/studio/api").json()["authoring"] == {"new": False, "agents": []}
    offered = priya("GET", "/studio/api/tools").json()
    tools = {t["name"]: t for t in offered["tools"]}
    assert tools["search_records"]["reads"] and not tools["search_records"]["writes"]
    assert tools["change_due_date"]["changes"] == "change-due-date"
    assert offered["models"] and ben("GET", "/studio/api/tools").status_code == 403


def test_a_draft_says_who_would_sign_its_release(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    new = started(priya)
    assert {(s["who"], s["why"]) for s in new["signers"]} == {
        ("the release approver, from outside the team that runs a5s", "the finance-helper is new"),
        ("the finance-helper's owner", "the finance-helper is new")}
    change = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    assert change["signers"] == []  # as released: it changes nothing yet
    files = {**change["files"], "AGENTS.md": change["files"]["AGENTS.md"] + "\nBe brief.\n"}
    worded = priya("PUT", f"/studio/api/drafts/{change['id']}", {"files": files}).json()
    assert [s["role"] for s in worded["signers"]] == ["agent-owner:assistant", "engineer"]
    files["agent.yaml"] = files["agent.yaml"].replace("documents: [create_draft]",
                                                      "documents: [create_draft, shred_it]")
    widened = priya("PUT", f"/studio/api/drafts/{change['id']}", {"files": files}).json()
    assert [s["role"] for s in widened["signers"]] == ["release-approver"]
    broken = priya("PUT", f"/studio/api/drafts/{change['id']}",
                   {"files": {**files, "agent.yaml": "id: [assistant\n"}}).json()
    assert broken["signers"] is None


def test_a_draft_that_loads_shows_as_the_catalogue_would(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    preview = draft["preview"]
    assert preview["id"] == "finance-helper" and preview["instances"] == []
    assert {t["name"] for t in preview["tools"]} >= {"search_records", "change_due_date"}
    assert preview["instructions"] == draft["files"]["AGENTS.md"]
    broken = {**draft["files"], "agent.yaml": "id: [finance-helper\n"}
    saved = priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": broken}).json()
    assert saved["preview"] is None and saved["problems"][0].startswith("its YAML doesn't read")
