"""The studio's first step, read only, through the core's API and the command line: the agents
of the release and where they run, how each agent and instance is doing, and what each run did
(docs/studio.md). The core's API is the team's that runs a5s, behind the service token."""

import json
import uuid

from a5s import db
from conftest import SERVICE_TOKEN
from test_watcher import THURSDAY


def get(stack, path: str, token: str = SERVICE_TOKEN):
    with stack.client(token) as c:
        return c.get(path)


def answered(stack, person: str = "ana") -> str:
    """Someone asks the assistant what's open, and it looks it up: what they're told."""
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 is open: the invoice went to the wrong address.")
    return stack.say("What's open?", person=person)


def test_the_catalogue_shows_each_agent_its_tools_and_where_it_runs(stack):
    found = {a["id"]: a for a in get(stack, "/studio/agents").json()["agents"]}
    assistant = found["assistant"]
    tools = {t["name"]: t for t in assistant["tools"]}
    assert tools["change_due_date"]["changes"] == "change-due-date"
    assert tools["change_due_date"]["writes"] and tools["change_due_date"]["pinned"]
    assert tools["search_records"]["reads"] and not tools["search_records"]["writes"]
    assert tools["get_messages"]["outside"]  # what customers wrote, through a5s's reader
    assert "offer_reminder" in assistant["a5s_tools"]
    [inst] = assistant["instances"]
    assert (inst["id"], inst["level"], list(inst["parts"]), inst["people"]) == (
        "assistant-finance", 1, ["billing"], 2)
    assert (inst["owner"], inst["deputy"], inst["current"]) == ("Ana Ortiz", "Ben Okafor", True)
    assert found["watcher"]["reports"] == ["records"]
    assert "instructions" not in assistant  # those are for one agent's page


def test_one_agent_shows_its_instructions_and_an_unknown_one_isnt_there(stack):
    shown = get(stack, "/studio/agents/assistant").json()
    assert shown["instructions"].startswith("# Assistant")
    assert get(stack, "/studio/agents/nobody").status_code == 404
    assert get(stack, "/studio/agents/nobody/measures").status_code == 404
    assert get(stack, "/studio/instances/nowhere/runs").status_code == 404


def test_an_instances_figures_are_the_measures_of_it_alone(stack):
    answered(stack)
    whole = get(stack, "/measures").json()
    one = get(stack, "/studio/instances/assistant-finance/measures").json()
    agent = get(stack, "/studio/agents/assistant/measures").json()
    assert one["runs"] == whole["runs"] == agent["runs"]  # only the assistant has run
    assert [r["runs"] for r in one["runs"]] == [1]
    assert one["ended"] == [{"kind": "message", "outcome": "done", "runs": 1}]
    assert one["instances"] == ["assistant-finance"] and one["denied"] == []


def test_an_instances_runs_fall_on_each_day_in_the_viewers_own_time_zone(stack):
    for _ in range(3):
        answered(stack)
    opened = ["2026-10-29T17:30:00+00:00",  # 01:30 on 30 October in Singapore
              "2026-10-29T15:00:00+00:00",  # 23:00 on 29 October there
              "2026-10-31T02:00:00+00:00"]
    with db.transaction(stack.admin) as conn:
        runs = [r["id"] for r in conn.execute("select id from runs order by opened_at")]
        for run, at in zip(runs, opened, strict=True):
            conn.execute("update runs set opened_at = %s where id = %s", (at, run))
        conn.execute("update runs set outcome = 'failed' where id = %s", (runs[1],))
    stack.at("2026-11-01T00:00:00+00:00")
    week = "/studio/instances/assistant-finance/measures?days=7"
    singapore = get(stack, f"{week}&zone=Asia/Singapore").json()
    days = {d["day"]: d for d in singapore["daily"]}
    assert singapore["zone"] == "Asia/Singapore"
    assert list(days) == [f"2026-10-{d}" for d in range(25, 32)] + ["2026-11-01"]  # quiet ones too
    assert days["2026-10-28"] == {"day": "2026-10-28", "runs": 0, "ended": {}}
    assert (days["2026-10-29"]["ended"], days["2026-10-30"]["ended"]) == ({"failed": 1}, {"done": 1})
    assert days["2026-10-31"] == {"day": "2026-10-31", "runs": 1, "ended": {"done": 1}}
    assert sum(d["runs"] for d in singapore["daily"]) == sum(e["runs"] for e in singapore["ended"])
    london = {d["day"]: d["runs"] for d in get(stack, f"{week}&zone=Europe/London").json()["daily"]}
    assert (london["2026-10-29"], london["2026-10-30"]) == (2, 0)  # both on the 29th there
    assert get(stack, week).json()["zone"] == "UTC"  # unless someone says
    for zone in ("Mars/Olympus", "../etc/passwd", "x" * 300):
        assert get(stack, f"{week}&zone={zone}").status_code == 400
    assert get(stack, "/studio/agents/assistant/measures?zone=Asia/Singapore").json()["daily"]


def test_each_instance_counts_its_own_runs_and_reports(stack):
    stack.with_watcher()
    stack.at(THURSDAY)
    stack.model.reply("Ana, Q-1001 is open.")
    stack.model.reply("Ben, Q-1002 is open.")
    assert stack.scheduler().work_due() == 2
    watcher = get(stack, "/studio/instances/watcher-finance/measures").json()
    assistant = get(stack, "/studio/instances/assistant-finance/measures").json()
    assert watcher["reports"] == [{"source": "records", "outcome": "run", "reports": 2}]
    assert [r["instance"] for r in watcher["runs"]] == ["watcher-finance"]
    assert assistant["reports"] == [] and assistant["runs"] == [] and assistant["ended"] == []


def test_what_was_denied_and_why_is_counted(stack):
    _, token = stack.open_run()
    with stack.client(token) as c:
        assert c.post("/run/tools/delete_everything", json={"args": {}}).status_code == 403
        for _ in range(2):
            assert c.post("/run/tools/search_records",
                          json={"args": {"query": 5}}).status_code == 403
    denied = get(stack, "/studio/instances/assistant-finance/measures").json()["denied"]
    assert denied == [
        {"kind": "tool", "action": "search_records", "reasons": ["arguments-fit-the-schema"],
         "times": 2},
        {"kind": "tool", "action": "delete_everything", "reasons": [], "times": 1}]


def test_an_instances_runs_and_what_each_did(stack):
    answered(stack)
    page = get(stack, "/studio/instances/assistant-finance/runs").json()
    [ran] = page["runs"]
    assert (ran["trigger"], ran["outcome"], page["hidden"]) == ("message", "done", 0)
    assert ran["acts_for"] == [{"id": "ana", "name": "Ana Ortiz"}]
    shown = get(stack, f"/studio/runs/{ran['run']}").json()
    assert (shown["agent"], shown["records"]) == ("assistant", ["Q-1001"])
    assert shown["started_by"]["kind"] == "message"
    [call] = shown["calls"]
    assert (call["tool"], call["decision"], call["outcome"]) == ("search_records", "allow", "ok")
    assert "invoice" not in json.dumps(shown["entries"])  # what was said, by its hash alone
    assert page["before"] is None  # the last page says so
    assert get(stack, "/studio/runs/not-a-run").status_code == 404
    assert get(stack, f"/studio/runs/{uuid.uuid4()}").status_code == 404


def test_the_studios_api_is_behind_the_service_token(stack):
    for path in ("/studio/agents", "/studio/agents/assistant",
                 "/studio/instances/assistant-finance/measures",
                 "/studio/instances/assistant-finance/runs"):
        assert get(stack, path, token="not-the-token").status_code == 401, path


def test_the_command_line_says_the_same(stack, monkeypatch, capsys):
    from a5s import cli
    answered(stack)
    monkeypatch.setenv("A5S_ROOT", str(stack.cfg.root))
    monkeypatch.setenv("A5S_GATEWAY_URL", stack.url)
    monkeypatch.setenv("A5S_SERVICE_TOKEN", SERVICE_TOKEN)
    cli.main(["agents"])
    said = capsys.readouterr().out
    assert ("assistant-finance: active, level 1, in billing, serving 2 people, run by Ana Ortiz "
            "and Ben Okafor") in said
    cli.main(["agents", "show", "assistant"])
    said = capsys.readouterr().out
    assert "changes: change_due_date (reads, writes, changes change-due-date)" in said
    assert "Instructions:" in said
    cli.main(["runs", "assistant-finance"])
    said = capsys.readouterr().out
    assert " message for Ana Ortiz: done" in said
    run = said.split()[1]
    cli.main(["runs", "show", run])
    assert "search_records: allow (" in capsys.readouterr().out
    cli.main(["measures", "--instance", "assistant-finance"])
    assert capsys.readouterr().out.strip()


def test_the_cores_openapi_document_describes_the_studios_api(stack):
    paths = set(get(stack, "/openapi.json").json()["paths"])
    assert {"/studio/agents", "/studio/agents/{agent}", "/studio/agents/{agent}/measures",
            "/studio/instances/{instance}/measures", "/studio/instances/{instance}/runs",
            "/studio/runs/{run_id}"} <= paths
