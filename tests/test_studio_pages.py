"""The studio's pages and the people's API behind them, in the channels app: each person sees
the instances they may watch, how each is doing, and the runs whose every record they may see
(docs/studio.md). The channels app reads what those figures count, never what was said."""

import re

import httpx
import psycopg
import pytest
import yaml

from a5s import db
from a5s.core import inbox
from conftest import QUIET

OPS = {"definition": "assistant", "serves": ["chen"], "parts": ["orders"], "level": 1,
       "owner": "omar"}


def with_ops(stack) -> None:
    """A second assistant, in orders, which Omar owns and runs, serving Chen."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    assert not stack.settle(instances={**settings["instances"], "assistant-ops": OPS},
                            signers=("ana", "omar")).refused


def signed_in(url: str, provider):
    def api(path: str, person: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {provider.id_token(person=person)}"}
        return httpx.get(f"{url}{path}", headers=headers, timeout=30)
    return api


def instances(found: dict) -> set[str]:
    return {i["id"] for a in found["agents"] for i in a["instances"]}


def test_each_person_watches_what_they_run_own_or_decide_for(stack, approving, provider):
    with_ops(stack)
    api = signed_in(approving, provider)
    ana = api("/studio/api", "ana").json()
    assert ana["you"] == "Ana Ortiz"
    assert instances(ana) == {"assistant-finance", "assistant-ops"}  # she approves instances
    assert instances(api("/studio/api", "ben").json()) == {"assistant-finance"}  # its deputy
    assert instances(api("/studio/api", "omar").json()) == {"assistant-ops"}  # he runs it
    assert api("/studio/api", "chen").status_code == 403  # it serves her, but she runs nothing
    assert api("/studio/api/instances/assistant-ops", "ben").status_code == 404
    assert api("/studio/api/agents/watcher", "ben").status_code == 404
    assert api("/studio/api/agents/assistant", "ben").json()["instructions"]
    assert api("/studio/api/instances/assistant-finance?zone=Mars/Olympus", "ben").status_code == 400
    assert httpx.get(f"{approving}/studio/api", timeout=30).status_code == 401


def test_a_run_shows_only_to_those_who_may_see_its_records(stack, approving, provider):
    with_ops(stack)
    stack.model.reply(None, ("get_record", {"key": "Q-1003"}))
    stack.model.reply("Q-1003 is waiting on the warehouse.")
    stack.say("Where's Q-1003?", person="chen")
    api = signed_in(approving, provider)
    [ran] = api("/studio/api/instances/assistant-ops/runs", "omar").json()["runs"]
    shown = api(f"/studio/api/runs/{ran['run']}", "omar").json()
    assert shown["records"] == ["Q-1003"]
    assert (shown["acts_for"], shown["people"]) == ([], 1)  # named once the officer agrees
    assert "entries" not in shown and shown["started_by"] == {"kind": "message"}
    ana = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    assert (ana["runs"], ana["hidden"]) == ([], 1)  # she approves it, but may not see Q-1003
    assert api(f"/studio/api/runs/{ran['run']}", "ana").status_code == 404
    assert api(f"/studio/api/runs/{ran['run']}", "ben").status_code == 404
    figures = api("/studio/api/instances/assistant-ops", "ana").json()
    assert [r["runs"] for r in figures["runs"]] == [1]  # counted, and never named
    agent = api("/studio/api/agents/assistant/measures", "omar").json()
    assert agent["instances"] == ["assistant-ops"]  # of the instances he may watch alone


def test_watchers_see_whom_a_run_acted_for_once_the_officer_agrees(stack, provider):
    from dataclasses import replace

    from conftest import deciding
    stack.cfg = replace(stack.cfg, studio_names=True)  # A5S_STUDIO_NAMES, in the channels app
    stack.model.reply("Nothing's open for you.")
    stack.say("What's open?", person="ana")
    with deciding(stack, provider) as url:
        api = signed_in(url, provider)
        [ran] = api("/studio/api/instances/assistant-finance/runs", "ben").json()["runs"]
        shown = api(f"/studio/api/runs/{ran['run']}", "ben").json()
    assert ran["acts_for"] == shown["acts_for"] == [{"id": "ana", "name": "Ana Ortiz"}]
    assert shown["started_by"]["kind"] == "message" and "entries" not in shown


@pytest.mark.parametrize("column", ["reminders.about", "obligations.title", "obligations.person",
                                    "questions.text", "questions.answer", "runs.token_hash",
                                    "run_reads.text", "report_fires.records", "instances.pins"])
def test_the_channels_app_reads_what_figures_count_never_what_was_said(stack, column):
    table, name = column.split(".")
    with (pytest.raises(psycopg.errors.InsufficientPrivilege),
          db.transaction(db.as_role(stack.admin, "channels")) as conn):
        conn.execute(f"select {name} from {table} limit 1")


def test_someone_watches_an_instance_in_the_browser(stack, approving, provider, browser):
    from test_ui_pages import shot

    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("What's open?", person="ana")
    with db.transaction(stack.admin) as conn:  # on the core's day, which the tests keep apart
        conn.execute("update runs set opened_at = opened_at - (now() - %(quiet)s), "
                     "closed_at = closed_at - (now() - %(quiet)s)", {"quiet": QUIET})
    served = httpx.get(f"{approving}/studio/", timeout=30)
    assert "script-src 'self'" in served.headers["Content-Security-Policy"]
    provider.person = "ben"  # the assistant's deputy signs in at the provider
    page = browser.new_page(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Singapore")
    refused = []  # anything the page's policy stopped, such as an inline script or style
    page.on("console", lambda m: refused.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto(f"{approving}/studio/")
    page.wait_for_selector(".agent-card >> text=assistant", timeout=30000)
    assert page.inner_text("#me").endswith("Ben Okafor")
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    card = page.inner_text(".agent-card")
    assert "2 change" in card and "assistant-finance" in card
    shot(page, "studio-agents")

    page.click(".agent-card a.agent-name")  # the agent: its map, and its tools by what they do
    page.wait_for_selector(".agent-map .map-node >> text=change_due_date", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/agents/assistant"
    assert "Changes records" in page.locator(".tool-group").first.text_content()
    shot(page, "studio-agent")

    page.click("table.grid-table a:has-text('assistant-finance')")  # its instance
    page.wait_for_selector(".tile >> text=Runs", timeout=30000)
    assert "done" in page.inner_text("section.card:has(h3:text-is('How runs ended')) table")
    # Its runs by day, on his own days: today's, as it says on hover and on focus
    today = page.locator(".runs-chart .day[tabindex='0']")
    assert today.get_attribute("aria-label").endswith(": 1 run, 1 done")
    assert "Days in Asia/Singapore" in page.text_content(".runs-chart .as-table")
    today.focus()
    assert page.locator(".runs-chart .tip").is_visible()
    shot(page, "studio-instance")
    today.blur()

    page.click("table.runs-table a:has-text('Open')")  # a run, and what it did
    page.wait_for_selector(".step >> text=search_records", timeout=30000)
    # its path on its agent's map: what started it, and the tool it called, once; the rest faded
    page.wait_for_selector(".agent-map .map-node >> text=search_records", timeout=30000)
    called = page.locator(".agent-map .map-node", has_text="search_records")
    assert called.locator(".map-count").inner_text() == "×1"
    assert "dim" not in page.locator(".agent-map .map-node", has_text="A message").get_attribute("class")
    assert "dim" in page.locator(".agent-map .map-node", has_text="change_due_date").get_attribute("class")
    assert "allow" in page.inner_text(".steps") and "Q-1001" in page.inner_text(".chips")
    assert "1 person" in page.inner_text(".tiles")  # named once the officer agrees
    assert page.locator("#entries").count() == 0  # what was said isn't shown at all
    shot(page, "studio-run")

    page.go_back()  # the browser's own back goes to the instance, signed in still
    page.wait_for_selector(".tile >> text=Runs", timeout=30000)
    page.reload()  # and an address in the studio opens where it was, once signed in again
    page.wait_for_selector(".tile >> text=Runs", timeout=30000)
    assert page.evaluate("location.pathname") == "/studio/instances/assistant-finance"
    assert refused == []


def test_a_runs_path_shows_what_a5s_refused_it(stack, approving, provider, browser):
    run, token = stack.open_run(sender="ben")
    with stack.client(token) as c:  # a tool it hasn't got, and then one it has
        assert c.post("/run/tools/delete_everything", json={"args": {}}).status_code == 403
        assert c.post("/run/tools/search_records", json={"args": {"query": "invoice"}}).status_code == 200
    provider.person = "ben"
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{approving}/studio/runs/{run}")
    page.wait_for_selector(".agent-map .map-node >> text=delete_everything", timeout=30000)
    refused = page.locator(".agent-map .map-node", has_text="delete_everything").inner_text()
    assert "not among its tools" in refused and "1 of 1 refused" in refused
    assert page.locator(".agent-map .map-node", has_text="search_records").locator(".map-count").inner_text() == "×1"
    assert "2 calls, 1 refused" in page.inner_text(".agent-map .map-node.checks")
    assert page.locator(".agent-map .react-flow__edge.refused").count() == 1


def test_the_studio_serves_its_one_page_and_its_own_files_alone(approving, monkeypatch, tmp_path):
    policy = "default-src 'none'; script-src 'self'"
    for path in ("/studio/", "/studio/agents/assistant", "/studio/instances/assistant-finance",
                 "/studio/runs/7c1e9a52-0d4b-4bb4-9a0e-1f3c5d7e9b21"):
        shown = httpx.get(f"{approving}{path}", timeout=30)
        assert shown.status_code == 200 and '<div id="root">' in shown.text
        assert shown.headers["content-security-policy"].startswith(policy)
    # Its script and stylesheet, by the names its build gave them, which never change, so a
    # browser keeps them; and nothing else, under the studio's address or beside it
    page = httpx.get(f"{approving}/studio/", timeout=30).text
    files = re.findall(r'"(/studio/assets/[\w-]+\.(?:js|css))"', page)
    assert {f.rsplit(".", 1)[1] for f in files} == {"js", "css"}
    for name in files:
        kept = httpx.get(f"{approving}{name}", timeout=30)
        assert kept.status_code == 200 and "immutable" in kept.headers["cache-control"]
        assert kept.headers["content-security-policy"].startswith(policy)
    for path in ("/studio/assets/index.html", "/studio/assets/..%2Findex.html", "/studio/assets/x.js",
                 "/studio/other/assistant", "/studio/api/nothing"):
        assert httpx.get(f"{approving}{path}", timeout=30).status_code == 404, path
    # Unbuilt, as in a checkout before `npm run build`, it says how to build it
    monkeypatch.setattr(inbox, "STUDIO", tmp_path)
    unbuilt = httpx.get(f"{approving}/studio/agents/assistant", timeout=30)
    assert unbuilt.status_code == 503 and "npm run build" in unbuilt.text


def test_the_channels_apps_openapi_document_describes_the_peoples_api(approving):
    paths = set(httpx.get(f"{approving}/openapi.json", timeout=30).json()["paths"])
    assert {"/studio/api", "/studio/api/agents/{agent}", "/studio/api/agents/{agent}/measures",
            "/studio/api/instances/{instance}", "/studio/api/instances/{instance}/runs",
            "/studio/api/runs/{run_id}"} <= paths


def test_a_chase_shows_only_to_those_who_may_see_the_record_it_chases(stack, approving, provider):
    with_ops(stack)
    stack.at("2026-10-30T02:00:00+00:00")  # 10:00 in Singapore: half Q-1003's time has passed
    stack.model.reply("Chen, Q-1003 is due on Monday.")
    assert stack.scheduler().work_due() == 1
    api = signed_in(approving, provider)
    [chase] = api("/studio/api/instances/assistant-ops/runs", "omar").json()["runs"]
    assert chase["trigger"] == "obligation"
    assert api(f"/studio/api/runs/{chase['run']}", "omar").json()["records"] == ["Q-1003"]
    ana = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    assert (ana["runs"], ana["hidden"]) == ([], 1)  # it chases Q-1003, which she may not see
    assert api(f"/studio/api/runs/{chase['run']}", "ana").status_code == 404
