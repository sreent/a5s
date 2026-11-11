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
    assert shown["records"] == ["Q-1003"] and shown["acts_for"][0]["name"] == "Chen Wei"
    ana = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    assert (ana["runs"], ana["hidden"]) == ([], 1)  # she approves it, but may not see Q-1003
    assert api(f"/studio/api/runs/{ran['run']}", "ana").status_code == 404
    assert api(f"/studio/api/runs/{ran['run']}", "ben").status_code == 404
    figures = api("/studio/api/instances/assistant-ops", "ana").json()
    assert [r["runs"] for r in figures["runs"]] == [1]  # counted, and never named
    agent = api("/studio/api/agents/assistant/measures", "omar").json()
    assert agent["instances"] == ["assistant-ops"]  # of the instances he may watch alone


@pytest.mark.parametrize("column", ["reminders.about", "obligations.title", "obligations.person",
                                    "questions.text", "questions.answer", "runs.token_hash",
                                    "run_reads.text", "report_fires.records", "instances.pins"])
def test_the_channels_app_reads_what_figures_count_never_what_was_said(stack, column):
    table, name = column.split(".")
    with (pytest.raises(psycopg.errors.InsufficientPrivilege),
          db.transaction(db.as_role(stack.admin, "channels")) as conn):
        conn.execute(f"select {name} from {table} limit 1")
