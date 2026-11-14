"""The sandbox (a5s/sandbox.py, docs/studio.md, step 2): a deployment of its own, where a draft
is tried as an agent of the sandbox's own, through the core's checks, on made-up records, with
a stand-in model; and what it answered, each call with the policy's decision, and what the model
was sent come back whole. It signs its own settings with keys it made, and runs nothing real."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient

from a5s import authoring, cases, sandbox
from a5s.core import drafts, retention, signing
from a5s.sample import SampleScenario
from conftest import ROOT, deployment

TOOLS = SampleScenario(ROOT / "scenarios" / "sample", "postgresql://nobody@127.0.0.1:1/none").tools()


def drafted(name: str = "finance-helper") -> dict[str, str]:
    """A new agent's files, as the studio keeps its draft."""
    with tempfile.TemporaryDirectory() as there:
        return drafts.folder_files(authoring.new(ROOT / "agents" / "assistant", name, Path(there), TOOLS))


def test_a_draft_is_tried_as_an_agent_of_the_sandboxs_own(box):
    said = box.turn("3f2a9c1d", drafted(), "ana", "Which questions mention an invoice?", "stand-in")
    assert said["agent"] == "try-3f2a9c1d"
    assert said["reply"] == "(A stand-in model.) I looked it up and found Q-1001."
    [call] = said["run"]["calls"]
    assert (call["tool"], call["decision"]) == ("search_records", "allow")
    first, then = said["model_calls"]  # what the model was sent, whole: it's all made up here
    assert first["sent"]["messages"][0]["role"] == "system"
    assert "search_records" in {t["function"]["name"] for t in first["sent"]["tools"]}
    assert first["came"]["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "search_records"
    assert then["sent"]["messages"][-1]["role"] == "tool" and "Q-1001" in then["sent"]["messages"][-1]["content"]
    again = box.turn("3f2a9c1d", drafted(), "ben", "And which mention a refund?", "stand-in")
    assert again["run"]["calls"][0]["decision"] == "allow"  # tried again, as someone else
    assert set(box.standing["instances"]["try-3f2a9c1d"]["serves"]) == {"ana", "ben"}


def test_the_sandbox_says_why_it_wont_try_a_draft(box):
    files = drafted()
    for key, person, model, why in (("3f2a9c1d", "nobody", "stand-in", "nobody called nobody"),
                                    ("NOT-A-KEY", "ana", "stand-in", "lower case letters"),
                                    ("3f2a9c1d", "ana", "a-model-it-hasnt", "can't call a-model-it-hasnt")):
        with pytest.raises(sandbox.Refused, match=why):
            box.turn(key, files, person, "Hello", model)
    shredding = {**files, "agent.yaml": files["agent.yaml"].replace("documents: [create_draft]",
                                                                   "documents: [create_draft, shred_it]")}
    with pytest.raises(sandbox.Refused, match="the scenario hasn't got shred_it"):
        box.turn("3f2a9c1d", shredding, "ana", "Hello", "stand-in")


def test_it_signs_its_own_settings_with_keys_it_made_and_keeps_none_on_disk(box, tmp_path):
    folder = box.cfg.scenario_dir
    raw = (folder / "settings.yaml").read_bytes()
    signed = yaml.safe_load((folder / "settings.sig").read_text())["signatures"]
    theirs = {s["signer"] for s in signed}
    assert theirs >= {"ana", "omar"}  # who approves instances, and owns each part
    for s in signed:
        mine = (folder / "keys" / f"{s['signer']}.pub").read_text().strip()
        assert signing.verify(mine, raw, s["value"])
        assert mine != (ROOT / "scenarios" / "sample" / "keys" / f"{s['signer']}.pub").read_text().strip()
    assert not list(tmp_path.rglob("*.key"))  # its private keys are in memory alone


def test_a_scenario_whose_records_are_real_gets_no_sandbox(sandbox_database, tmp_path):
    root = tmp_path / "real"
    shutil.copytree(ROOT / "scenarios" / "sample", root / "scenarios" / "sample")
    shutil.copytree(ROOT / "agents", root / "agents")
    shutil.copytree(ROOT / "config", root / "config")
    settings = root / "scenarios" / "sample" / "settings.yaml"
    settings.write_text(settings.read_text().replace("data_class: synthetic", "data_class: internal"))
    with (pytest.raises(sandbox.Refused, match="only a scenario whose records are all made up"),
          sandbox.opened(deployment(root), sandbox_database, tmp_path / "work")):
        pass


def test_its_api_answers_the_studio_it_shares_a_token_with_alone(box):
    client = TestClient(sandbox.create_app(box, "the-studios-token"))
    assert client.get("/sandbox").status_code == 401
    assert client.get("/sandbox", headers={"Authorization": "Bearer guessed"}).status_code == 401
    shown = client.get("/sandbox", headers={"Authorization": "Bearer the-studios-token"}).json()
    assert {"id": "ana", "name": "Ana Ortiz"} in shown["people"] and shown["models"][0] == "stand-in"
    tried = client.post("/sandbox/tries", headers={"Authorization": "Bearer the-studios-token"},
                        json={"key": "7c1e9a52", "files": drafted("orders-helper"), "person": "ana",
                              "text": "Which questions mention an invoice?"})
    assert tried.status_code == 200, tried.text
    assert tried.json()["run"]["calls"][0]["decision"] == "allow"
    refused = client.post("/sandbox/tries", headers={"Authorization": "Bearer the-studios-token"},
                          json={"key": "7c1e9a52", "files": {}, "person": "ana", "text": "Hi"})
    assert refused.status_code == 400


def test_it_wont_open_on_a_deployments_own_database(stack, tmp_path):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")  # the deployment's ledger, with what it did
    with (pytest.raises(sandbox.Refused, match="holds a deployment's ledger"),
          sandbox.opened(deployment(), stack.admin, tmp_path)):
        pass


def test_someone_tries_their_draft_in_the_sandbox_from_the_studio(stack, with_sandbox, approving,
                                                                   provider):
    from test_drafts import as_, recorded, started

    priya = as_(approving, provider, "priya")
    draft = started(priya)
    offered = priya("GET", "/studio/api/sandbox").json()
    assert offered["models"][0] == "stand-in" and {"id": "ana", "name": "Ana Ortiz"} in offered["people"]
    tried = priya("POST", f"/studio/api/drafts/{draft['id']}/try",
                  {"person": "ana", "text": "Which questions mention an invoice?"})
    assert tried.status_code == 200, tried.text
    assert tried.json()["reply"] == "(A stand-in model.) I looked it up and found Q-1001."
    assert tried.json()["run"]["calls"][0]["decision"] == "allow"
    [entry] = recorded(stack, "try draft")
    assert entry["args"] == {"agent": "finance-helper", "draft": draft["id"], "as": "ana",
                             "model": "stand-in", "by": "priya"}
    with psycopg.connect(stack.admin) as conn:  # it ran there, not here
        assert conn.execute("select count(*) from runs").fetchone()[0] == 0
    refused = priya("POST", f"/studio/api/drafts/{draft['id']}/try",
                    {"person": "nobody", "text": "Hello"})
    assert refused.status_code == 400 and "nobody called nobody" in refused.json()["detail"]
    ben = as_(approving, provider, "ben")
    assert ben("POST", f"/studio/api/drafts/{draft['id']}/try",
               {"person": "ana", "text": "Hello"}).status_code == 403


def test_with_no_sandbox_the_studio_says_so(stack, approving, provider):
    from test_drafts import as_, started

    priya = as_(approving, provider, "priya")
    draft = started(priya)
    r = priya("POST", f"/studio/api/drafts/{draft['id']}/try", {"person": "ana", "text": "Hello"})
    assert r.status_code == 503 and "there's no sandbox here" in r.json()["detail"]


def test_a_sandbox_started_again_carries_on_where_it_was(sandbox_database, tmp_path):
    for _ in range(2):  # as after a restart, on the same database, with new keys each time
        with sandbox.opened(deployment(), sandbox_database, tmp_path) as opened:
            said = opened.turn("3f2a9c1d", drafted(), "ana", "Which questions mention an invoice?",
                               "stand-in")
            assert said["run"]["calls"][0]["decision"] == "allow"


def test_what_was_said_in_the_sandbox_goes_an_hour_after_its_quiet(box):
    box.turn("3f2a9c1d", drafted(), "ana", "Which questions mention an invoice?", "stand-in")
    agent, words = "try-3f2a9c1d", ("turns", "inbound", "outbox")

    def said() -> dict[str, int]:
        with psycopg.connect(box.admin) as conn:
            return {table: conn.execute(f"select count(*) from {table} where agent = %s",
                                        (agent,)).fetchone()[0] for table in words}

    assert all(said().values())
    box.forget()
    assert all(said().values())  # a moment ago: the next turn of a try answers from it
    with psycopg.connect(box.admin) as conn:  # as if an hour and more had gone by
        for table, at in (("turns", "at"), ("inbound", "received_at"), ("outbox", "at")):
            conn.execute(f"update {table} set {at} = {at} - interval '61 minutes' where agent = %s",
                         (agent,))
    assert box.forget().get("messages")
    assert not any(said().values())
    again = box.turn("3f2a9c1d", drafted(), "ana", "Which mention a refund?", "stand-in")
    assert again["run"]["calls"][0]["decision"] == "allow"


def test_the_sweep_keeps_things_only_for_a_time_it_can_read():
    for kept in ("1 hour; drop table turns", "0 days", "forever", ""):
        with pytest.raises(ValueError, match="isn't a time to keep things for"):
            retention.sweep(None, None, "sample", kept=kept)


def test_a_drafts_test_cases_run_there_as_its_suite_runs_them(box):
    files = drafted()
    numbered = {case["name"]: n for n, case in enumerate(cases.found(files))}
    ran = box.case("3f2a9c1d", files, "stand-in", numbered["finds a question by what it's about"])
    assert (ran["ran"], ran["passed"], ran["problems"]) == (True, True, [])
    [step] = ran["steps"]
    assert step["called"] == ["search_records"] and "Q-1001" in step["reply"]
    ran = box.case("3f2a9c1d", files, "stand-in", numbered["says when it can't find a record"])
    assert ran["ran"] and not ran["passed"]  # what the stand-in says isn't what the agent would
    assert ran["problems"][0].startswith("step 1: said none of")
    ran = box.case("3f2a9c1d", files, "stand-in", numbered["offers a reminder, and keeps it on the yes"])
    assert (ran["ran"], ran["why"]) == (False, "it needs then, which the agent's suite alone runs")
    with psycopg.connect(box.admin) as conn:  # each case that ran, in a conversation of its own
        talked = conn.execute("select count(distinct agent) from turns where agent like 'case-%'").fetchone()[0]
    assert talked == 2
    assert [i for i in box.standing["instances"] if i.startswith("case-")] != []  # the last's alone
    assert len([i for i in box.standing["instances"] if i.startswith("case-")]) == 1


def test_the_sandbox_says_which_cases_it_cant_run(box):
    stranger = {**drafted(), "tests/stranger.yaml": "- name: as someone it hasn't got\n  as: zed\n"
                                                    "  steps: [{say: Hello}]\n"}
    found = cases.found(stranger)
    ran = box.case("3f2a9c1d", stranger, "stand-in",
                   next(n for n, c in enumerate(found) if c["file"] == "tests/stranger.yaml"))
    assert (ran["ran"], ran["why"]) == (False, "it's said as zed, and the sandbox has nobody called that")
    with pytest.raises(sandbox.Refused, match="tests/broken.yaml doesn't read as YAML"):
        box.case("3f2a9c1d", {**drafted(), "tests/broken.yaml": "- name: [\n"}, "stand-in", 0)
    with pytest.raises(sandbox.Refused, match="not a case 100"):
        box.case("3f2a9c1d", drafted(), "stand-in", 99)


def test_someone_runs_their_drafts_cases_from_the_studio(stack, with_sandbox, approving, provider):
    from test_drafts import as_, recorded, started

    priya = as_(approving, provider, "priya")
    draft = started(priya)
    listed = priya("GET", f"/studio/api/drafts/{draft['id']}/cases").json()["cases"]
    runs = [c for c in listed if not c["suite_alone"]]
    assert [c["name"] for c in runs] == ["finds a question by what it's about",
                                         "says when it can't find a record",
                                         "never makes up an amount the records don't have"]
    ran = priya("POST", f"/studio/api/drafts/{draft['id']}/cases/{runs[0]['number']}", {})
    assert ran.status_code == 200 and ran.json()["passed"] is True, ran.text
    [entry] = recorded(stack, "run draft case")
    assert entry["args"] == {"agent": "finance-helper", "draft": draft["id"], "model": "stand-in",
                             "case": "finds a question by what it's about", "passed": True, "by": "priya"}
    broken = {**draft["files"], "tests/tried.yaml": "- name: [\n"}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": broken}).status_code == 200
    said = priya("GET", f"/studio/api/drafts/{draft['id']}/cases").json()
    assert said == {"cases": [], "problem": "tests/tried.yaml doesn't read as YAML"}
