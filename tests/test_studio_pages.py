"""The studio's pages and the people's API behind them, in the channels app: each person sees
the instances they may watch, how each is doing, and the runs whose every record they may see
(docs/studio.md). The channels app reads what those figures count, never what was said."""

import httpx
import psycopg
import pytest
import yaml

from a5s import db

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
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("What's open?", person="ana")
    served = httpx.get(f"{approving}/studio/", timeout=30)
    assert "script-src 'self'" in served.headers["Content-Security-Policy"]
    provider.person = "ben"  # the assistant's deputy signs in at the provider
    page = browser.new_page()
    page.goto(f"{approving}/studio/")
    page.wait_for_selector("#agents >> text=assistant, release", timeout=30000)
    assert page.inner_text("#who") == "Ben Okafor"
    assert page.evaluate("window.location.search") == ""  # the code doesn't linger
    assert "changes: change_due_date (reads, writes, changes change-due-date)" in page.inner_text(
        "#agents")
    page.click("#agents button:has-text('assistant-finance')")
    page.wait_for_selector("#figures >> text=How runs ended", timeout=30000)
    assert "message done: 1" in page.inner_text("#figures")
    page.click("#runs button")
    page.wait_for_selector("#calls >> text=search_records", timeout=30000)
    assert "allow" in page.inner_text("#calls") and "Q-1001" in page.inner_text("#run-facts")
    assert "for 1 person" in page.inner_text("#run-facts")  # named once the officer agrees
    assert page.locator("#entries").count() == 0  # what was said isn't shown at all
    page.click("#to-instance")
    assert page.is_visible("#instance") and not page.is_visible("#run")


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
