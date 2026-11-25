"""The sandbox (a5s/sandbox.py, docs/studio.md, step 2): a deployment of its own, where a draft
is tried as an agent of the sandbox's own, through the core's checks, on made-up records, with
a stand-in model; and what it answered, each call with the policy's decision, and what the model
was sent come back whole. It signs its own settings with keys it made, and runs nothing real."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import httpx
import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient

from a5s import authoring, cases, db, sandbox
from a5s.core import drafts, retention, signing
from a5s.sample import SampleScenario
from conftest import FAKE_MODELS, PROVIDER_KEY, ROOT, FakeModel, build_root, deployment

TOOLS = SampleScenario(ROOT / "scenarios" / "sample", "postgresql://nobody@127.0.0.1:1/none").tools()
CASE_NAME = "finds a question by what it's about"  # one of the assistant template's cases


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
    signed = yaml.safe_load((folder / "settings.sig").read_text(encoding="utf-8"))["signatures"]
    theirs = {s["signer"] for s in signed}
    assert theirs >= {"ana", "omar"}  # who approves instances, and owns each part
    for s in signed:
        mine = (folder / "keys" / f"{s['signer']}.pub").read_text(encoding="utf-8").strip()
        assert signing.verify(mine, raw, s["value"])
        assert mine != (ROOT / "scenarios" / "sample" / "keys" / f"{s['signer']}.pub").read_text(encoding="utf-8").strip()
    assert not list(tmp_path.rglob("*.key"))  # its private keys are in memory alone


def test_a_scenario_whose_records_are_real_gets_no_sandbox(sandbox_database, tmp_path):
    root = tmp_path / "real"
    shutil.copytree(ROOT / "scenarios" / "sample", root / "scenarios" / "sample")
    shutil.copytree(ROOT / "agents", root / "agents")
    shutil.copytree(ROOT / "config", root / "config")
    settings = root / "scenarios" / "sample" / "settings.yaml"
    settings.write_text(settings.read_text(encoding="utf-8").replace("data_class: synthetic", "data_class: internal"))
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



def test_a_case_kept_from_a_real_run_goes_only_where_its_data_may(box):
    """What someone really said, masked, is given only to the stand-in, which never leaves the
    sandbox, or to a model approved for every class of the deployment's data: never to one
    approved for made-up data alone, whatever file it's in, if it says it's from a run."""
    kept = [{"name": "kept", "as": "ana", "from_run": True,
             "steps": [{"say": "Which questions mention an invoice?"}]}]
    for where in (cases.FROM_RUNS, "tests/mine.yaml"):
        files = {**drafted(), where: yaml.safe_dump(kept)}
        n = next(i for i, c in enumerate(cases.found(files)) if c["file"] == where)
        ran = box.case("3f2a9c1d", files, "deepseek-v4-pro", n, ["internal"])
        assert ran["ran"] is False and "kept from a real run" in ran["why"], where
        assert "deepseek-v4-pro isn't" in ran["why"]
        assert box.case("3f2a9c1d", files, "stand-in", n, ["internal"])["ran"], where
    made_up = {**drafted(), "tests/mine.yaml": yaml.safe_dump([{**kept[0], "from_run": False}])}
    assert not cases.real(next(c for c in cases.found(made_up) if c["file"] == "tests/mine.yaml"))
    assert cases.for_real(["synthetic", "internal"], {"internal"})
    assert not cases.for_real(["synthetic"], {"internal"})
    assert cases.for_real(["synthetic"], {"synthetic"})  # a deployment of made-up data

def test_a_case_kept_from_a_run_that_read_outside_content_is_marked_as_it_was(box):
    """The run it was kept from read content from outside, which the case can't keep: the
    sandbox sends its step with a file in its place, so its run is marked as that one was."""
    kept = [{"name": "outside", "as": "ana", "from_run": "k-0123456789ab", "read_outside": True,
             "steps": [{"say": "Which questions mention an invoice?"}]}]
    files = {**drafted(), cases.FROM_RUNS: yaml.safe_dump(kept)}
    n = next(i for i, c in enumerate(cases.found(files)) if c["file"] == cases.FROM_RUNS)
    assert box.case("3f2a9c1d", files, "stand-in", n, ["internal"])["ran"]
    with db.transaction(box.admin) as conn:
        assert conn.execute("select read_outside from runs order by opened_at desc limit 1"
                            ).fetchone()["read_outside"] is True


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
    assert [c["name"] for c in runs] == ["answers in Thai someone who writes in Thai",
                                         "finds a question by what it's about",
                                         "says when it can't find a record",
                                         "never makes up an amount the records don't have"]
    ran = priya("POST", f"/studio/api/drafts/{draft['id']}/cases/{runs[1]['number']}", {})
    assert ran.status_code == 200 and ran.json()["passed"] is True, ran.text
    [entry] = recorded(stack, "run draft case")
    assert entry["args"] == {"agent": "finance-helper", "draft": draft["id"], "model": "stand-in",
                             "case": "finds a question by what it's about", "passed": True, "by": "priya"}
    broken = {**draft["files"], "tests/tried.yaml": "- name: [\n"}
    assert priya("PUT", f"/studio/api/drafts/{draft['id']}", {"files": broken}).status_code == 200
    said = priya("GET", f"/studio/api/drafts/{draft['id']}/cases").json()
    assert said == {"cases": [], "problem": "tests/tried.yaml doesn't read as YAML"}


def test_a_change_a_draft_asks_for_waits_there_for_its_made_up_decider(sandbox_database, tmp_path,
                                                                       monkeypatch):
    """As it would where people work: so a case that says the draft asks for it passes there."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()  # an approved model, which the sandbox reaches by the test's transport
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with sandbox.opened(deployment(root), sandbox_database, tmp_path / "sandbox",
                        transport=httpx.MockTransport(model.handler)) as box:
        model.reply(None, ("change_due_date", {"key": "Q-1001", "due": "2026-12-01"}))
        model.reply("I've asked for Q-1001 to be due on 1 December: Ana Ortiz decides it.")
        said = box.turn("3f2a9c1d", drafted(), "ben", "Please move Q-1001 to 1 December.", "fake")
        [call] = said["run"]["calls"]
        assert (call["tool"], call["decision"]) == ("change_due_date", "hold"), call
        assert sandbox.used(said["run"]) == ["change_due_date"]
        sent = model.requests[-1]["body"]["messages"][-1]["content"]
        assert '"held": "P-1"' in sent and "Ana Ortiz" in sent  # what the agent heard


@pytest.fixture
def costly(stack):
    """A sandbox whose tries and cases each take tokens on a real model, as one's would, so the
    studio counts them towards whoever tried: what it was asked, on which models."""
    from dataclasses import replace

    from fastapi import FastAPI

    from conftest import free_port, serve
    app, asked = FastAPI(), []

    @app.post("/sandbox/cases")
    def case(body: dict) -> dict:
        asked.append(body["model"])
        return {"name": "a case", "file": "tests/cases.yaml", "ran": True, "passed": True,
                "problems": [], "steps": [], "model": body["model"], "seconds": 1.0,
                "tokens": 400_000, "cost": None, "judge_tokens": 200_000}

    @app.post("/sandbox/tries")
    def tried(body: dict) -> dict:
        asked.append(body["model"])
        return {"agent": "try-x", "reply": "Hello", "run": None, "model_calls": [],
                "tokens": 300_000}

    with serve(app, free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="a-token")
        yield asked


def test_a_days_tries_on_real_models_stop_at_its_tokens_whatever_each_case_runs_as(
        stack, costly, approving, provider):
    """Each case runs in the sandbox as an instance of its own, whose budget for a person's day
    starts afresh, and a judge's calls count towards none: the studio holds each person to a
    day's tokens across them all, the stand-in aside, which costs nothing."""
    from a5s.core import export
    from a5s.core.studio_api import SANDBOX_DAY
    from test_drafts import as_, started

    priya = as_(approving, provider, "priya")
    draft = started(priya)["id"]
    real = {"model": "deepseek-v4-pro"}
    assert priya("POST", f"/studio/api/drafts/{draft}/cases/0", real).status_code == 200
    assert priya("POST", f"/studio/api/drafts/{draft}/try",
                 {"person": "ana", "text": "Hi", **real}).status_code == 200
    with db.transaction(stack.admin) as conn:
        [day] = conn.execute("select person, tokens from sandbox_spend").fetchall()
    assert (day["person"], day["tokens"]) == ("priya", 900_000)  # its runs, its judge, the try
    assert 900_000 < SANDBOX_DAY  # so the next runs, and takes the day past it
    assert priya("POST", f"/studio/api/drafts/{draft}/cases/0", real).status_code == 200
    over = priya("POST", f"/studio/api/drafts/{draft}/cases/0", real)
    assert over.status_code == 429 and "a day's may take on real models" in over.json()["detail"]
    assert priya("POST", f"/studio/api/drafts/{draft}/try",
                 {"person": "ana", "text": "Hi", **real}).status_code == 429
    assert priya("POST", f"/studio/api/drafts/{draft}/cases/0",
                 {"model": "stand-in"}).status_code == 200  # which costs nothing
    assert costly == ["deepseek-v4-pro"] * 3 + ["stand-in"]  # refused before it was asked
    with db.transaction(stack.cfg.database_url) as conn:  # theirs, in their export
        [kept] = export.gather(conn, "priya")["days"]["sandbox"]
    assert kept["tokens"] == 1_500_000


def test_a_cases_cost_prices_what_its_runs_wrote_to_the_cache_as_the_provider_does(box):
    """A model whose provider charges more to write a prompt to its cache than to read it, as
    Anthropic's do: what a case's runs wrote counts at that price, never at the input's."""
    from a5s.config import ModelConfig, Prices
    model = ModelConfig(alias="priced", provider="anthropic", api="anthropic",
                        base_url="https://models.test", model="m",
                        prices=Prices(3.0, 15.0, cached_input=0.3, cache_write=3.75))
    spent = {"in": 1_000_000, "out": 0, "cached": 0, "cache_written": 1_000_000}
    assert sandbox.cost(model, spent) == 3.75  # every token in was written to the cache
    assert sandbox.cost(model, {**spent, "cache_written": 0}) == 3.0


def test_a_runs_page_gives_what_it_wrote_to_the_cache(stack):
    stack.model.reply("Hello.")
    stack.say("hello")
    with db.transaction(stack.admin) as conn:
        run = conn.execute("update runs set tokens_cache_written = 7 returning id::text as id"
                           ).fetchone()["id"]
        from a5s.core import studio
        assert studio.run(conn, stack.gateway.scenario, run)["tokens_cache_written"] == 7


@pytest.fixture
def classes_asked(stack):
    """A sandbox that says which classes of data the studio told it a case's models must be
    approved for."""
    from dataclasses import replace

    from fastapi import FastAPI

    from conftest import free_port, serve
    app, asked = FastAPI(), []

    @app.post("/sandbox/cases")
    def case(body: dict) -> dict:
        asked.append(body.get("classes"))
        return {"name": "a case", "file": "tests/cases.yaml", "ran": True, "passed": True,
                "problems": [], "steps": [], "model": body["model"], "seconds": 1.0,
                "tokens": 0, "cost": None, "judge_tokens": 0}

    with serve(app, free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="a-token")
        yield asked


def test_while_the_settings_cant_be_read_a_real_case_goes_to_the_stand_in_alone(
        stack, classes_asked, approving, provider, monkeypatch):
    """Round 14 (D11): until the channels app can read the settings in force, such as before a
    new version is sealed, a5s doesn't know the deployment's classes of data, so it tells the
    sandbox one no model is approved for, and a case kept from a real run runs on the stand-in
    alone, rather than on any model approved for internal data."""
    from a5s.core.gateway import Gateway
    from test_drafts import as_, started

    priya = as_(approving, provider, "priya")
    draft = started(priya)["id"]
    monkeypatch.setattr(Gateway, "settings_in_force", lambda self, *a, **k: (None, None))
    monkeypatch.setattr(Gateway, "sealed_in_force", lambda self, *a, **k: None)
    assert priya("POST", f"/studio/api/drafts/{draft}/cases/0", {}).status_code == 200
    assert classes_asked == [[cases.UNKNOWN]]
    assert not any(cases.for_real(m.data_classes, {cases.UNKNOWN})
                   for m in stack.gateway.models.values())


@pytest.fixture
def held(stack):
    """A sandbox whose first try waits until the test lets it go, as one at work on a real model
    does, and answers the rest at once: the keys of the drafts it was asked to try."""
    import threading
    from dataclasses import replace

    from fastapi import FastAPI

    from conftest import free_port, serve
    app, asked, go = FastAPI(), [], threading.Event()

    @app.post("/sandbox/tries")
    def tried(body: dict) -> dict:
        asked.append(body["key"])
        if len(asked) == 1:
            go.wait(60)
        return {"agent": "try-x", "reply": "Hello", "run": None, "model_calls": [], "tokens": 0}

    with serve(app, free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="a-token")
        yield asked, go
        go.set()


def test_someone_has_one_try_in_the_sandbox_at_a_time_and_the_studio_a_few_in_all(
        stack, held, approving, provider, monkeypatch):
    """Round 14 (D3, D4): a try holds one of the channels app's threads, which its chats are
    answered on too, for as long as the sandbox takes, and a day's tokens are checked before
    each: so someone has one try there at a time, and the app a few at a time in all, and the
    rest are refused at once, rather than waiting on threads the chats need, or passing a day's
    tokens many times over with tries sent together."""
    import threading
    import time

    from a5s.core import studio_api
    from test_drafts import as_, started
    from test_run_cases import owning

    asked, go = held
    owning(stack, "priya", "ana")  # so each may draft a new agent
    priya, ana = as_(approving, provider, "priya"), as_(approving, provider, "ana")
    mine, hers = started(priya)["id"], started(ana)["id"]
    said = {"person": "ana", "text": "Hi"}
    first: list = []
    at_work = threading.Thread(target=lambda: first.append(
        priya("POST", f"/studio/api/drafts/{mine}/try", said)))
    at_work.start()
    for _ in range(200):  # until the sandbox has it
        if asked:
            break
        time.sleep(0.05)
    again = priya("POST", f"/studio/api/drafts/{mine}/try", said)
    assert again.status_code == 429 and "a try in the sandbox already" in again.json()["detail"]
    monkeypatch.setattr(studio_api, "SANDBOX_AT_ONCE", 1)
    others = ana("POST", f"/studio/api/drafts/{hers}/try", said)
    assert others.status_code == 429 and "busy with others' tries" in others.json()["detail"]
    go.set()
    at_work.join(30)
    assert first[0].status_code == 200 and len(asked) == 1  # the rest went no further
    assert priya("POST", f"/studio/api/drafts/{mine}/try", said).status_code == 200  # once done


@pytest.fixture
def failing(stack):
    """A sandbox that refuses a description once its model has answered, which took 600,000
    tokens, and that fails at work on a case, as one that dies or times out does."""
    from dataclasses import replace
    from typing import Any

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from conftest import free_port, serve
    app = FastAPI()

    @app.post("/sandbox/descriptions")
    def described(body: dict) -> Any:
        return JSONResponse({"detail": f"what {body['model']} answered doesn't read as a proposal",
                             "tokens": 600_000}, status_code=400)

    @app.post("/sandbox/cases")
    def case(body: dict) -> Any:
        return JSONResponse({"detail": "it stopped at work"}, status_code=500)

    with serve(app, free_port()) as url:
        stack.cfg = replace(stack.cfg, sandbox_url=url, sandbox_token="a-token")
        yield


def test_what_a_try_took_counts_towards_the_day_however_it_ends(stack, failing, approving,
                                                                  provider):
    """Round 14 (D4): a try on a real model counts towards someone's day of tokens however it
    ends: one the sandbox refused, with what it says it took before it knew, and one it didn't
    answer, which for all a5s knows was at work there all the same, as a tenth of a day."""
    from a5s.core.studio_api import SANDBOX_UNSAID
    from test_drafts import as_, started

    priya = as_(approving, provider, "priya")
    refused = priya("POST", "/studio/api/drafts", {
        "name": "question-finder", "describe": "Finds customer questions by what they mention.",
        "model": "deepseek-v4-pro"})
    assert refused.status_code == 400 and "doesn't read as a proposal" in refused.json()["detail"]
    draft = started(priya)["id"]
    failed = priya("POST", f"/studio/api/drafts/{draft}/cases/0", {"model": "deepseek-v4-pro"})
    assert failed.status_code == 502
    with db.transaction(stack.admin) as conn:
        [day] = conn.execute("select tokens from sandbox_spend where person = 'priya'").fetchall()
    assert day["tokens"] == 600_000 + SANDBOX_UNSAID


def test_the_sandbox_runs_a_case_of_a_few_steps_for_a_few_minutes(box, monkeypatch):
    """Round 14 (D3): nothing but a draft's size bounds a case's steps, and the sandbox runs one
    request at a time: so it runs a case of STEPS steps at most, and stops one before its next
    step once it's taken TOOK seconds, so the studio has its answer, with what it took, before
    it stops waiting."""
    files = drafted()
    files["tests/long.yaml"] = yaml.safe_dump([{"name": "goes on", "steps": [
        {"say": f"Hello {n}"} for n in range(sandbox.STEPS + 1)]}])
    listed = cases.found(files)
    long = next(n for n, c in enumerate(listed) if c["name"] == "goes on")
    ran = box.case("3f2a9c1d", files, "stand-in", long)
    assert not ran["ran"] and f"a case of {sandbox.STEPS} at most" in ran["why"]
    short = next(n for n, c in enumerate(listed) if c["name"] == CASE_NAME)
    monkeypatch.setattr(sandbox, "TOOK", 0.0)
    stopped = box.case("3f2a9c1d", files, "stand-in", short)
    assert stopped["ran"] and not stopped["passed"] and stopped["steps"] == []
    assert stopped["problems"][0].startswith("step 1: not run, nor any after it")


def test_the_sandbox_refuses_a_try_that_has_waited_for_another(box, monkeypatch):
    """Round 14 (D3): one request has the sandbox at a time, and one that has waited WAIT seconds
    for another is refused, saying so, rather than waiting on a queue of others'."""
    import threading

    monkeypatch.setattr(sandbox, "WAIT", 0.2)
    client = TestClient(sandbox.create_app(box, "the-studios-token"))
    box.lock.acquire()  # another's, at work for three seconds more
    threading.Timer(3, box.lock.release).start()
    said = client.post("/sandbox/tries", headers={"Authorization": "Bearer the-studios-token"},
                       json={"key": "7c1e9a52", "files": drafted(), "person": "ana", "text": "Hi"})
    assert said.status_code == 429 and "busy with someone else's try" in said.json()["detail"]


def test_a_judge_grades_only_a_step_the_agent_answered(box, monkeypatch):
    """Round 14 (D4): a step whose run didn't end in an answer of the agent's own fails as
    unanswered, and its judge isn't asked: there's nothing of the agent's to judge, and it costs."""
    files = drafted()
    files["agent.yaml"] = files["agent.yaml"].rstrip("\n") + "\nevaluation:\n  judge: deepseek-v4-pro\n"
    files["tests/judged.yaml"] = yaml.safe_dump([{"name": "judged", "steps": [
        {"say": "Hello", "judged": 'It says "hello".'}]}])
    number = next(n for n, c in enumerate(cases.found(files)) if c["name"] == "judged")
    asked: list = []
    monkeypatch.setattr(sandbox.Sandbox, "_said", lambda self, *a, **k: ("", None, []))
    monkeypatch.setattr(sandbox.Sandbox, "_judged", lambda self, *a, **k: asked.append(a) or {
        "grade": "right", "why": "it says hello", "judge": "stand-in"})
    ran = box.case("3f2a9c1d", files, "stand-in", number)
    assert ran["ran"] and not ran["passed"] and asked == []
    assert "never ran for it" in ran["problems"][0]
