"""Publishing a draft (core/publishing.py, docs/studio.md, step 2): a pull request to the
agents' repository, opened as the person publishing, once they let a5s's App act as them at
GitHub's own sign-in. a5s holds no token or secret for it: the token GitHub gives is used for
that one publish, and is nowhere afterwards. The pull request carries the draft's folder and
says who must sign its release; published again, the draft adds a commit to the same one."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from dataclasses import replace

import pytest
import yaml

from a5s import db
from a5s.core import drafts, ledger, publishing
from conftest import ROOT, free_port, serve
from fake_github import CLIENT, FakeGitHub
from test_drafts import as_, started


@pytest.fixture
def github(stack) -> Iterator[FakeGitHub]:
    """GitHub, with the agents as released on its main branch. Ask for it before the channels
    app, as `approving`, so the app knows where to publish."""
    fake = FakeGitHub({f"agents/{name}/{path}": text for name in ("assistant", "watcher")
                       for path, text in drafts.folder_files(ROOT / "agents" / name).items()})
    with serve(fake.app(), free_port()) as url:
        fake.url = url
        stack.cfg = replace(stack.cfg, github_client_id=CLIENT, github_repo=fake.repo,
                            github_url=url, github_api_url=url)
        yield fake


def published(call, github: FakeGitHub, draft: str, login: str) -> dict:
    """Publish a draft, as someone who lets a5s act as them at GitHub when it asks."""
    asked = call("POST", f"/studio/api/drafts/{draft}/publish")
    assert asked.status_code == 200, asked.text
    asked = asked.json()
    assert asked["status"] == "signing in" and asked["verify_at"] == "https://github.test/login/device"
    waiting = call("GET", f"/studio/api/publishes/{asked['id']}").json()
    assert waiting["status"] == "signing in"  # until they let it
    github.grant(asked["user_code"], login)
    done = call("GET", f"/studio/api/publishes/{asked['id']}").json()
    assert done["status"] == "opened", done
    return done


def everything(stack) -> str:
    """All a5s keeps, as text: its ledger and its drafts."""
    with db.transaction(stack.admin) as conn:
        entries = ledger.entries(conn, limit=10000)
        kept = [dict(r) for r in conn.execute("select * from agent_drafts")]
    return json.dumps([entries, kept], default=str)


def test_a_new_agent_is_published_as_a_pull_request_opened_as_its_author(stack, github, approving,
                                                                        provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    done = published(priya, github, draft["id"], login="priya-gh")
    [pull] = github.pulls
    assert done["pull"] == pull["html_url"] and pull["user"] == "priya-gh"  # as them, not a5s
    assert (pull["title"], pull["base"], pull["head"]) == (
        "Add finance-helper", "main", publishing.branch("finance-helper", draft["id"]))
    body = pull["body"]
    assert "Drafted in the a5s studio by Priya" in body and "from template assistant" in body
    for signer in draft["signers"]:  # who must sign its release, and why
        assert signer["who"] in body and signer["why"] in body
    files = github.files(pull["head"])
    assert {p.removeprefix("agents/finance-helper/"): t for p, t in files.items()
            if p.startswith("agents/finance-helper/")} == draft["files"]
    assert {p: t for p, t in files.items() if not p.startswith("agents/finance-helper/")} == \
        github.files("main")  # nothing else changes
    head = github.head(pull["head"])
    assert head["parents"] == [github.refs["heads/main"]] and head["author"] == "priya-gh"
    assert {who for _, _, who in github.calls} == {"priya-gh"}  # every call to the API as them
    [given] = github.tokens
    assert given not in everything(stack)  # used for that publish alone: kept nowhere
    entry = [e for e in ledger_of(stack) if e.get("action") == "publish draft"][-1]
    assert entry["args"] == {"agent": "finance-helper", "draft": draft["id"], "pull": pull["html_url"],
                             "by": "priya", "based_on": "template assistant"}
    assert priya("GET", f"/studio/api/drafts/{draft['id']}").json()["published"] == pull["html_url"]


def ledger_of(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return ledger.entries(conn, limit=10000)


def test_published_again_a_draft_adds_a_commit_to_its_pull_request(stack, github, approving,
                                                                    provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    first = published(priya, github, draft["id"], login="priya-gh")
    before = github.refs[f"heads/{first['branch']}"]
    files = {**draft["files"], "AGENTS.md": draft["files"]["AGENTS.md"] + "\nAsk before you change anything.\n"}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).status_code == 200
    again = published(priya, github, draft["id"], login="priya-gh")
    assert again["pull"] == first["pull"] and len(github.pulls) == 1  # the same pull request
    head = github.head(again["branch"])
    assert head["parents"] == [before]  # on from the last: never over anyone's commits
    assert github.files(again["branch"])["agents/finance-helper/AGENTS.md"].endswith(
        "Ask before you change anything.\n")


def test_a_change_to_an_agent_lets_go_of_the_files_its_draft_did(stack, github, approving, provider):
    priya = as_(approving, provider, "priya")  # who owns the assistant
    draft = priya("POST", "/studio/api/drafts", {"agent": "assistant"}).json()
    files = {p: t for p, t in draft["files"].items() if p != "tests/outside.yaml"}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": files}).status_code == 200
    done = published(priya, github, draft["id"], login="priya-gh")
    [pull] = github.pulls
    assert pull["title"] == "Change assistant"
    there = github.files(done["branch"])
    assert "agents/assistant/tests/outside.yaml" in github.files("main")
    assert "agents/assistant/tests/outside.yaml" not in there
    assert there["agents/assistant/agent.yaml"] == files["agent.yaml"]


def test_a_publish_says_why_it_didnt_open_a_pull_request(stack, github, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    for end, state, why in ((github.deny, "refused", "you didn't let a5s publish as you on GitHub"),
                            (github.lapse, "lapsed", "the sign-in to GitHub lapsed")):
        asked = priya("POST", f"/studio/api/drafts/{draft['id']}/publish").json()
        end(asked["user_code"])
        found = priya("GET", f"/studio/api/publishes/{asked['id']}").json()
        assert (found["status"], found["user_code"]) == (state, None) and why in found["problem"]
    github.cannot_push.add("ben-gh")  # someone who may read the repository, not push to it
    asked = priya("POST", f"/studio/api/drafts/{draft['id']}/publish").json()
    github.grant(asked["user_code"], "ben-gh")
    found = priya("GET", f"/studio/api/publishes/{asked['id']}").json()
    assert found["status"] == "refused"
    assert "GitHub won't let a5s publish to acme/agents as you (403" in found["problem"]
    assert github.pulls == [] and not any(p.startswith("heads/a5s/") for p in github.refs)
    assert not [e for e in ledger_of(stack) if e.get("action") == "publish draft"]


def test_only_a_drafts_author_publishes_it_and_only_once_nothing_stops_its_release(
        stack, github, approving, provider):
    priya, ben = as_(approving, provider, "priya"), as_(approving, provider, "ben")
    draft = started(priya)
    asked = priya("POST", f"/studio/api/drafts/{draft['id']}/publish").json()
    assert ben("GET", f"/studio/api/publishes/{asked['id']}").status_code in (403, 404)
    assert ben("POST", f"/studio/api/drafts/{draft['id']}/publish").status_code in (403, 404)
    broken = {**draft["files"], "agent.yaml": draft["files"]["agent.yaml"].replace(
        "search_records", "shred_everything")}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": broken}).status_code == 200
    refused = priya("POST", f"/studio/api/drafts/{draft['id']}/publish")
    assert refused.status_code == 409 and "would stop its release" in refused.json()["detail"]


def test_without_github_set_up_its_author_downloads_the_folder(stack, approving, provider):
    priya = as_(approving, provider, "priya")
    draft = started(priya)
    refused = priya("POST", f"/studio/api/drafts/{draft['id']}/publish")
    assert refused.status_code == 503 and "download its folder" in refused.json()["detail"]
    got = priya("GET", f"/studio/api/drafts/{draft['id']}/folder")
    assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
    assert 'filename="finance-helper.zip"' in got.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(got.content)) as folder:
        found = {name.removeprefix("finance-helper/"): folder.read(name).decode()
                 for name in folder.namelist()}
    assert found == draft["files"]
    assert yaml.safe_load(found["agent.yaml"])["id"] == "finance-helper"
    assert as_(approving, provider, "ben")("GET", f"/studio/api/drafts/{draft['id']}/folder").status_code in (403, 404)


def test_its_author_publishes_a_draft_from_its_page(stack, github, approving, provider, browser):
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
    page.click("#publish")
    page.wait_for_selector("#user-code", timeout=30000)
    assert page.get_attribute(".sign-in-code a", "href") == "https://github.test/login/device"
    shot(page, "studio-publish")
    github.grant(page.inner_text("#user-code"), "priya-gh")  # at GitHub, as themselves
    page.wait_for_selector("#published >> text=its pull request", timeout=30000)
    [pull] = github.pulls
    assert page.get_attribute("#published a", "href") == pull["html_url"]
    assert page.inner_text("#publish") == "Publish again"
    assert refused == []
