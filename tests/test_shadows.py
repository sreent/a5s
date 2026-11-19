"""Shadow runs (core/shadows.py, docs/agent-model.md#shadow-runs): a new version of an agent,
released as an agent of its own, answers what people ask an instance, beside it, as an instance
whose settings name the one it shadows, once the data protection officer chooses to let it. It
reads what that instance's run was given, offered only what reads, and sends and changes
nothing; graders from outside the team that built it compare its answers with those sent, and
its judge does too, apart."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
import yaml
from playwright.sync_api import expect
from psycopg.types.json import Jsonb

from a5s import db, definitions
from a5s.contract import parse_settings
from a5s.core import approvals, erasure, export, registry, retention, shadows
from a5s.core.policy import PolicyEngine
from a5s.sample import SampleScenario
from a5s.services.scheduler import Scheduler
from conftest import (
    FAKE_MODELS,
    PROVIDER_KEY,
    FakeModel,
    Stack,
    accessible,
    build_root,
    running,
    signed,
)

ASKED = "When is Q-1002 due?"
SENT = "It's still open: I'll keep an eye on it for you."
SHADOWED = "Still open, and nothing's changed: ask me if it should move."
NEXT = "You're the assistant's next version: say less, and more plainly."


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The sample, with the assistant's next version beside it, as an agent of its own, with a
    judge."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    candidate = root / "agents" / "assistant-next"
    shutil.copytree(root / "agents" / "assistant", candidate)
    spec = candidate / "agent.yaml"
    spec.write_text(spec.read_text(encoding="utf-8").replace("id: assistant\n", "id: assistant-next\n")
                    + "evaluation:\n  judge: fake\n  rubric: It says when a record falls due.\n")
    (candidate / "AGENTS.md").write_text((candidate / "AGENTS.md").read_text(encoding="utf-8") + f"\n\n{NEXT}\n")
    tools = SampleScenario(root / "scenarios" / "sample", database).tools()
    definitions.pin(candidate, {n: t.schema_hash for n, t in tools.items()})
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def shadowed(stack: Stack, lets: bool = True, names: bool = True, **more) -> object:
    """A version with the assistant's next version shadowing assistant-finance, which Ana,
    billing's owner, and Noor, the officer, sign: with names in the studio, unless not
    `names`, so graders read the pairs of an instance serving two people."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text(encoding="utf-8"))
    return stack.settle(instances={**settings["instances"], "assistant-next-finance": {
        "definition": "assistant-next", "serves": ["ana", "ben"], "parts": ["billing"],
        "level": 1, "owner": "ana", "deputy": "ben", "shadows": "assistant-finance", **more}},
        data_protection={"shadow_runs": lets, "studio_names": names}, signers=("ana", "noor"))


def as_person(stack: Stack, approving: str, provider, person: str, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
    return httpx.request(method, f"{approving}{path}", json=body, timeout=30,
                         headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})


def answered(stack: Stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from shadow_answers order by id").fetchall()


def test_a_shadow_answers_beside_the_instance_it_shadows_sending_and_changing_nothing(stack):
    assert not shadowed(stack).refused
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select status from instances where id = 'assistant-next-finance'"
                            ).fetchone()["status"] == "shadow"
    stack.model.reply(SENT)  # the assistant, at work
    stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": "2026-12-20"}))
    stack.model.reply(SHADOWED)  # its next version, beside it, which can't make the change
    assert stack.say(ASKED, person="ben") == SENT  # what Ben hears: the answer sent, alone
    live, first, _ = (r["body"] for r in stack.model.requests)
    assert NEXT in json.dumps(first) and NEXT not in json.dumps(live)  # its own instructions
    assert ASKED in json.dumps(first)  # given the conversation as the assistant's run was
    offered = {t["function"]["name"] for t in first.get("tools", [])}
    assert offered and not offered & {"change_due_date", "close_question", "create_draft",
                                      "offer_reminder", "ask_agent", "offer_task"}
    assert "search_records" in offered  # what reads alone
    [pair] = answered(stack)
    assert (pair["asked"], pair["sent"], pair["answer"]) == (ASKED, SENT, SHADOWED)
    assert pair["records"] == ["Q-1002"] and pair["acts_for"] == ["ben"]
    assert (pair["instance_id"], pair["shadows"], pair["definition"]) == (
        "assistant-next-finance", "assistant-finance", "assistant-next")
    with db.transaction(stack.admin) as conn:
        assert [r["text"] for r in conn.execute("select text from outbox order by id")] == [SENT]
        assert conn.execute("select count(*) as n from proposals").fetchone()["n"] == 0
        said = [r["content"] for r in conn.execute("select content from turns order by id")]
        assert SHADOWED not in said  # never in Ben's conversation
    entries = stack.ledger()
    [kept] = [e for e in entries if e.get("action") == "shadow answer"]
    assert kept["instance"] == "assistant-next-finance" and SHADOWED not in json.dumps(entries)
    opened = [e for e in entries if e["kind"] == "run" and e["action"] == "open"
              and e["instance"] == "assistant-next-finance"]
    assert opened and opened[0]["args"]["trigger"] == shadows.KIND
    # Once a message, beside each run that answered it
    with stack.client() as c:
        again = c.post("/runs", json={"instance": "assistant-next-finance", "trigger": {
            "kind": shadows.KIND, "live": str(pair["live_run_id"])}})
    assert again.status_code == 409 and "answered beside that run already" in again.text


def test_the_core_lets_a_shadow_read_and_keep_its_answer_and_nothing_else(stack):
    assert not shadowed(stack).refused
    with stack.client() as c:  # while it's suspended, the assistant answers alone
        assert c.post("/instances/assistant-next-finance/suspend", json={"by": "ana"}).status_code == 200
    stack.model.reply(SENT)
    assert stack.say(ASKED, person="ben") == SENT and answered(stack) == []
    with stack.client() as c:
        assert c.post("/instances/assistant-next-finance/resume", json={"by": "ana"}).status_code == 200
    with db.transaction(stack.admin) as conn:
        live = conn.execute("select id::text from runs where instance_id = 'assistant-finance' "
                            "order by opened_at desc limit 1").fetchone()["id"]
    with stack.client() as c:
        opened = c.post("/runs", json={"instance": "assistant-next-finance",
                                       "trigger": {"kind": shadows.KIND, "live": live}})
        assert opened.status_code == 200, opened.text
        wrong = c.post("/runs", json={"instance": "assistant-finance",
                                      "trigger": {"kind": shadows.KIND, "live": live}})
        assert wrong.status_code == 409 and "isn't a shadow" in wrong.text
    token = opened.json()["token"]
    with stack.client(token) as run:
        changed = run.post("/run/tools/change_due_date", json={"args": {
            "key": "Q-1002", "due": "2026-12-20"}})
        assert changed.status_code == 403 and changed.json()["reasons"] == ["shadows-change-nothing"]
        offered = run.post("/run/tools/offer_reminder", json={"args": {}})
        assert offered.status_code == 403  # a5s's own that write, too
        assert run.post("/run/tools/search_records", json={"args": {"query": "refund"}}
                        ).status_code == 200  # what reads
        sent = run.post("/run/messages", json={"to": "ben", "text": "Hello from a shadow"})
        assert sent.status_code == 403 and "shadows-send-nothing" in sent.json()["reasons"]
        assert run.post("/run/shadow", json={"text": SHADOWED}).json()["kept"]
        assert run.post("/run/shadow", json={"text": SHADOWED}).status_code == 409  # once
    with stack.client() as c:
        assert c.post("/run/shadow", json={"text": "x"}).status_code in (401, 403)
    [refused] = [e for e in stack.ledger() if e["kind"] == "tool" and e["action"] == "change_due_date"]
    assert refused["decision"] == "deny" and refused["reasons"] == ["shadows-change-nothing"]
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from outbox where text like 'Hello from%'"
                            ).fetchone()["n"] == 0



def test_nothing_a_shadow_does_reaches_whom_it_was_beside(stack, monkeypatch):
    """Once they have their answer, a shadow that can't answer, even for a database away as
    the scheduler looks for it, tells them nothing more."""
    assert not shadowed(stack).refused

    def away(*_args, **_kwargs):
        raise psycopg.OperationalError("the database is away")

    monkeypatch.setattr(Scheduler, "_shadow", away)
    stack.model.reply(SENT)
    assert stack.say(ASKED, person="ben") == SENT  # their answer, alone
    with db.transaction(stack.admin) as conn:
        assert [r["text"] for r in conn.execute("select text from outbox order by id")] == [SENT]

def test_a_shadow_answers_only_while_the_officer_lets_it(stack, approving, provider):
    assert not shadowed(stack, lets=False).refused  # signed, but the core's checks say no
    folder = stack.cfg.scenario_dir
    refused = stack.gateway.unusable(parse_settings((folder / "settings.yaml").read_bytes()), None)
    assert any("data protection officer hasn't chosen to let shadows answer" in p for p in refused)
    stack.model.reply(SENT)
    assert stack.say(ASKED, person="ben") == SENT
    assert answered(stack) == [] and len(stack.model.requests) == 1  # the shadow never ran
    [denied] = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"
                and e["instance"] == "assistant-next-finance"]
    assert denied["decision"] == "deny" and "officer" in denied["reasons"][0]


def test_approvers_read_what_a_shadow_is_and_the_core_checks_it(stack):
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    before = parse_settings((folder / "settings.yaml").read_bytes())
    settings["serial"] += 1
    settings["data_protection"] = {"shadow_runs": True}
    settings["instances"]["assistant-next-finance"] = {
        "definition": "assistant-next", "serves": ["ana", "ben"], "parts": ["billing"],
        "owner": "ana", "shadows": "assistant-finance"}
    after = parse_settings(yaml.safe_dump(settings).encode())
    words = approvals.changes(before, after, stack.gateway.definitions,
                              stack.gateway.scenario.person)
    [added] = [w for w in words if w["text"].startswith("Adds assistant-next-finance")]
    assert "It's a shadow: it answers what assistant-finance is asked, beside it" in added["text"]
    [choice] = [w for w in words if w["text"].startswith("A shadow may answer")]
    assert choice["widens"] and "graders read what it answered" in choice["text"]
    assert stack.gateway.unusable(after, None) == []
    for wrong, said in (({"serves": ["ana", "ben", "chen"]}, "whom assistant-finance"),
                        ({"parts": ["billing", "orders"]}, "works in orders"),
                        ({"shadows": "nobody-here"}, "which the settings don't have"),
                        ({"asks": ["assistant-finance"]}, "asks no agent")):
        changed = {**settings, "instances": {**settings["instances"], "assistant-next-finance": {
            **settings["instances"]["assistant-next-finance"], **wrong}}}
        found = stack.gateway.unusable(parse_settings(yaml.safe_dump(changed).encode()), None)
        assert any(said in p for p in found), (wrong, found)


def test_a_shadow_has_no_work_of_its_own_and_resumes_as_one(stack):
    assert not shadowed(stack).refused
    told = stack.say("Hello, next version?", person="ben", agent="assistant-next")
    assert "assistant-next" in told and len(stack.model.requests) == 0  # no run of its own
    with stack.client() as c:
        for act in ("suspend", "resume"):
            assert c.post(f"/instances/assistant-next-finance/{act}", json={"by": "ana"}
                          ).status_code == 200
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select status from instances where id = 'assistant-next-finance'"
                            ).fetchone()["status"] == "shadow"
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    assert stack.say(ASKED, person="ben") == SENT
    assert [p["answer"] for p in answered(stack)] == [SHADOWED]  # its record checks out


def test_graders_compare_its_answers_and_its_judge_does_too_apart(stack, approving, provider):
    assert not shadowed(stack).refused
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    [pair] = as_person(stack, approving, provider, "dana", "GET", "/studio/api/shadows").json()["pairs"]
    assert (pair["asked"], pair["sent"], pair["answer"]) == (ASKED, SENT, SHADOWED)
    assert "ben" not in json.dumps(pair).lower()  # never whose it was
    for nobody in ("chen", "ben", "ana"):  # not graders, or built it, or it answered them
        assert as_person(stack, approving, provider, nobody, "GET",
                         "/studio/api/shadows").json()["pairs"] == []
    [mine] = as_person(stack, approving, provider, "ana", "GET", "/studio/api/shadows").json()["shadows"]
    assert mine["instance"] == "assistant-next-finance" and mine["answered"] == 1  # its owner
    path = f"/studio/api/shadows/{pair['id']}/grade"
    assert as_person(stack, approving, provider, "chen", "POST", path,
                     {"grade": "worse"}).status_code == 404
    assert as_person(stack, approving, provider, "dana", "POST", path,
                     {"grade": "fine"}).status_code == 409
    assert as_person(stack, approving, provider, "dana", "POST", path,
                     {"grade": "worse"}).json() == {"graded": True}
    again = as_person(stack, approving, provider, "dana", "POST", path, {"grade": "better"})
    assert again.status_code == 404 or "graded already" in again.text
    stack.model.answering = lambda body: (json.dumps({"grade": "same", "why": "Both say when."})
                                          if "You compare two answers" in json.dumps(body)
                                          else None)
    with stack.client() as c:
        swept = c.post("/shadows/sweep").json()
    assert swept["noted"] == 1 and swept["judged"] == [{"answer": pair["id"], "verdict": "same"}]
    [figures] = as_person(stack, approving, provider, "dana", "GET", "/studio/api/shadows").json()["shadows"]
    assert figures["graded"]["worse"] == 1 and figures["judged"]["same"] == 1
    [noted] = [e for e in stack.ledger() if e.get("action") == "shadow-grade"]
    assert noted["args"] == {"answer": pair["id"], "grade": "worse", "by": "dana"}
    home = as_person(stack, approving, provider, "dana", "GET", "/studio/api/home").json()["waiting"]
    assert not any(w["kind"] == "shadow" for w in home)  # nothing left to compare



def test_graders_see_a_pair_only_if_they_may_see_every_record_its_runs_handled(
        stack, approving, provider):
    """Either answer may say what a record holds without naming it, so a grader who may not see
    a record either run handled doesn't see the pair, as the studio wouldn't show them the run."""
    assert not shadowed(stack).refused
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    scenario = stack.gateway.scenario
    hidden = next(r.key for r in scenario.watched() if not scenario.sees("dana", r.key))
    [pair] = answered(stack)
    for run in (pair["live_run_id"], pair["run_id"]):
        with db.transaction(stack.admin) as conn:
            conn.execute("insert into run_records (run_id, record) values (%s, %s)", (run, hidden))
        assert as_person(stack, approving, provider, "dana", "GET",
                         "/studio/api/shadows").json()["pairs"] == [], run
        assert as_person(stack, approving, provider, "dana", "POST",
                         f"/studio/api/shadows/{pair['id']}/grade",
                         {"grade": "same"}).status_code == 404, run
        with db.transaction(stack.admin) as conn:
            conn.execute("delete from run_records where record = %s", (hidden,))
    assert [p["id"] for p in as_person(stack, approving, provider, "dana", "GET",
                                       "/studio/api/shadows").json()["pairs"]] == [pair["id"]]


def test_a_judge_reads_no_pair_with_data_of_a_class_it_isnt_approved_for(stack):
    """Either answer may say what any field of a record holds, so a judge not approved for every
    class the settings give a field judges nothing, as for samples."""
    assert not shadowed(stack).refused
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    folder = stack.cfg.scenario_dir
    signed(folder, {**yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8")),
                    "classified": {"customer": "personal"}})
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert not registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name).refused
    stack.model.answering = lambda body: (json.dumps({"grade": "same", "why": "Both say when."})
                                          if "You compare two answers" in json.dumps(body)
                                          else None)
    asked = len(stack.model.requests)
    with stack.client() as c:
        assert c.post("/shadows/sweep").json()["judged"] == []
    assert len(stack.model.requests) == asked  # never asked
    fake = stack.gateway.models["fake"]
    stack.gateway.models["fake"] = replace(fake, data_classes=(*fake.data_classes, "personal"))
    with stack.client() as c:
        assert [j["verdict"] for j in c.post("/shadows/sweep").json()["judged"]] == ["same"]

def test_what_a_shadow_answered_is_kept_as_the_conversation_is(stack, approving, provider):
    assert not shadowed(stack).refused
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    home = as_person(stack, approving, provider, "dana", "GET", "/studio/api/home").json()["waiting"]
    assert any(w["kind"] == "shadow" and w["go"] == "/studio/shadows" for w in home)
    shell = as_person(stack, approving, provider, "dana", "GET", "/shell/api").json()["pages"]
    assert any(p["page"] == "shadows" for p in shell)
    [pair] = answered(stack)
    as_person(stack, approving, provider, "dana", "POST", f"/studio/api/shadows/{pair['id']}/grade",
              {"grade": "same"})
    with db.transaction(stack.admin) as conn:
        [kept] = export.gather(conn, "ben")["shadow_answers"]
        assert kept["answer"] == SHADOWED and kept["grade"] == "same"
        assert export.gather(conn, "dana")["shadow_grades"] == 1
        gone, _ = erasure.erase(conn, "dana", datetime.now(UTC), here=True)
        assert gone["shadow_grades"] == 1  # the grade stays, without whose it was
        gone, _ = erasure.erase(conn, "ben", datetime.now(UTC), here=True)
        assert gone["shadow_answers"] == 1
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ana")
    with db.transaction(stack.admin) as conn:  # and goes when the conversation's time is up
        conn.execute("update shadow_answers set at = now() - interval '13 months'")
        assert retention.sweep(conn, datetime.now(UTC), stack.gateway.scenario.name)["shadows"] == 1


def test_the_policy_lets_a_shadow_read_and_nothing_else():
    engine = PolicyEngine()

    def instance(status: str) -> dict:
        return {"uid": {"type": "Instance", "id": "assistant-next-finance"},
                "attrs": {"status": status, "level": 1, "model": "fake", "serves": ["ana"],
                          "grants": ["search_records", "change_due_date", "create_draft"]},
                "parents": []}

    def tool(name: str, writes: bool = False, action: str = "") -> dict:
        return {"uid": {"type": "Tool", "id": name},
                "attrs": {"name": name, "known": True, "pinned": True, "reads": True,
                          "writes": writes or bool(action), "destructive": False,
                          "sends_outside": False, "action": action}, "parents": []}

    context = {"level": 1, "read_outside": False, "acts_for": ["ana"], "in_scope": True,
               "visible": True, "for_self": False, "over_limit": False}

    def decide(status: str, resource: dict) -> object:
        return engine.decide(principal=instance(status)["uid"], action="call_tool",
                             resource=resource["uid"], context=context,
                             entities=[instance(status), resource])

    read = decide("shadow", tool("search_records"))
    assert read.allowed and read.reasons == ("shadows-only-read",)
    for resource in (tool("change_due_date", action="change-due-date"),
                     tool("create_draft", writes=True)):
        d = decide("shadow", resource)
        assert not d.allowed and "shadows-change-nothing" in d.reasons
    sent = engine.decide(principal=instance("shadow")["uid"], action="send_message",
                         resource={"type": "Person", "id": "ana"},
                         context={**context},
                         entities=[instance("shadow"), {"uid": {"type": "Person", "id": "ana"},
                                                        "attrs": {"in_audience": True},
                                                        "parents": []}])
    assert not sent.allowed  # no permit lets a shadow send
    assert decide("active", tool("search_records")).reasons == ("active-instances-use-their-grant",)


def test_graders_compare_answers_in_the_studio(stack, approving, provider, browser):
    assert not shadowed(stack).refused
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    provider.person = "dana"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{approving}/studio/shadows")
    page.wait_for_selector("#pairs [data-pair]", timeout=30000)
    shown = page.inner_text("#pairs")
    assert SHADOWED in shown and SENT in shown and ASKED in shown
    room = page.eval_on_selector("#pairs [data-pair] [role=group]", """el => [getComputedStyle(el).columnGap,
        el.getBoundingClientRect().top - el.previousElementSibling.getBoundingClientRect().bottom]""")
    assert room[0] != "normal" and room[1] > 4  # its buttons apart, and apart from the answers
    accessible(page)
    page.click("#pairs button:has-text('As good')")
    page.wait_for_selector("#nothing", timeout=30000)
    expect(page.locator("#nothing")).to_be_focused(timeout=10000)  # never lost
    page.wait_for_selector("#figures [data-shadow='assistant-next-finance']", timeout=30000)
    assert "1 better" not in page.inner_text("#figures") and "1 as good" in page.inner_text("#figures")
    accessible(page)
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select grade, graded_by from shadow_answers").fetchone() == {
            "grade": "same", "graded_by": "dana"}


# Round 14

def test_until_names_are_agreed_graders_read_no_pair_of_a_small_instance_and_others_masked(
        stack, approving, provider):
    """C4: graders read what someone said as well as both answers, as owners read answers said
    to be wrong: until the officer agrees to names, none of an instance serving fewer than the
    officer chose, and the rest with names, emails, links and long numbers masked by code."""
    assert not shadowed(stack, names=False).refused
    stack.model.reply("Hello, Ben: Q-1002 is still open.")
    stack.model.reply("Hi Ben, it's still open.")
    stack.say("Hello, I'm Ben Okafor: is Q-1002 still open?", person="ben")
    page = as_person(stack, approving, provider, "dana", "GET", "/studio/api/shadows").json()
    assert page["pairs"] == []  # assistant-finance serves two, fewer than the officer's five
    dana = stack.gateway.scenario.person("dana")
    with db.transaction(stack.admin) as conn:
        [pair] = shadows.gradeable(conn, stack.gateway.scenario, dana, names=False)
    assert pair["asked"] == "Hello, I'm [someone] [someone]: is Q-1002 still open?"
    assert (pair["sent"], pair["answer"]) == ("Hello, [someone]: Q-1002 is still open.",
                                             "Hi [someone], it's still open.")


def test_once_shadows_may_not_answer_graders_read_none_they_answered(stack, approving, provider):
    """C's question: the officer's choice in force decides whether graders read pairs at all,
    not only whether shadows answer: pairs already kept go unread once it's taken back."""
    assert not shadowed(stack).refused
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text(encoding="utf-8"))
    assert not stack.settle(instances=settings["instances"], data_protection={
        "shadow_runs": False, "studio_names": True}, signers=("ana", "noor")).refused
    page = as_person(stack, approving, provider, "dana", "GET", "/studio/api/shadows")
    assert page.json()["pairs"] == []
    with db.transaction(stack.admin) as conn:
        pair = conn.execute("select id from shadow_answers").fetchone()["id"]
    assert as_person(stack, approving, provider, "dana", "POST", f"/studio/api/shadows/{pair}/grade",
                     {"grade": "same"}).status_code == 404


def test_a_grader_reads_how_a_shadow_did_only_with_a_pair_of_it_to_grade(stack, approving,
                                                                         provider):
    """C5: Dana grades, and may not know the assistant or its next version exist: the shadows
    page names a shadow to her only once it offers her a pair of its to grade."""
    assert not shadowed(stack).refused
    assert as_person(stack, approving, provider, "dana", "GET",
                     "/studio/api/agents/assistant-next").status_code == 404
    page = as_person(stack, approving, provider, "dana", "GET", "/studio/api/shadows").json()
    assert page["shadows"] == []
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    stack.say(ASKED, person="ben")
    page = as_person(stack, approving, provider, "dana", "GET", "/studio/api/shadows").json()
    assert [s["instance"] for s in page["shadows"]] == ["assistant-next-finance"]


def test_older_pairs_a_grader_may_not_grade_hide_none_they_may(stack):
    """C8: graders read pairs a page at a time, so 500 older ones Dana may not grade, of orders'
    records, don't keep her from a newer one she may."""
    assert not shadowed(stack).refused
    dana = stack.gateway.scenario.person("dana")

    def pair(conn, records: list[str]) -> None:
        runs = []
        for instance in ("assistant-next-finance", "assistant-finance"):
            run = str(uuid.uuid4())
            conn.execute("insert into runs (id, instance_id, token_hash, trigger, acts_for) "
                         "values (%s, %s, %s, %s, %s)", (run, instance, uuid.uuid4().bytes,
                                                         Jsonb({"kind": "message"}), ["ben"]))
            runs.append(run)
        conn.execute(
            "insert into shadow_answers (run_id, live_run_id, instance_id, shadows, definition, "
            "person, agent, acts_for, asked, sent, answer, records) values (%s, %s, "
            "'assistant-next-finance', 'assistant-finance', 'assistant-next', 'ben', "
            "'assistant', %s, 'asked', 'sent', 'answer', %s)", (*runs, ["ben"], records))

    with db.transaction(stack.admin) as conn:
        for _ in range(shadows.SCAN):
            pair(conn, ["Q-1003"])  # orders', which quality may not see
        pair(conn, [])
        assert len(shadows.gradeable(conn, stack.gateway.scenario, dana)) == 1


def test_their_next_message_waits_on_no_shadow(stack):
    """Round 14 (C3): shadows answer beside a run once its conversation is let go, so the
    person's next message, or a group's, is taken at once, never after each shadow's run."""
    assert not shadowed(stack).refused
    seen = {}

    def during(n: int) -> None:
        if n != 2:  # the shadow's model call, once the live answer has gone
            return
        with db.transaction(stack.admin) as conn:
            seen["leases"] = [r["key"] for r in conn.execute("select key from leases")]
        httpx.post(f"{stack.channels_url}/channels/local/messages", timeout=30,
                   json={"person": "ben", "agent": "assistant", "text": "And Q-1001?"})
        seen["claimed"] = stack.scheduler()._claim()  # another scheduler, at that moment

    stack.model.on_request = during
    stack.model.reply(SENT)
    stack.model.reply(SHADOWED)
    assert stack.say("When is Q-1002 due?", person="ben") == SENT
    assert "ben/assistant/general" not in seen["leases"]
    assert seen["claimed"] is not None and seen["claimed"]["person"] == "ben"


def test_a_group_chats_pairs_are_counted_in_exports_and_kept_under_a_leavers_archive(stack):
    """Round 14 (C13): what a shadow answered in a group chat holds others' words too, so each
    member's export counts it, and gives only their own chats' pairs; and someone who leaves is
    under their archive's name in it, as in the group's turns, and so is its grader."""
    from a5s.core import departures
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into shadow_answers (run_id, live_run_id, instance_id, shadows, definition, "
            "person, agent, acts_for, asked, sent, answer, graded_by) values (gen_random_uuid(), "
            "gen_random_uuid(), 'assistant-next-finance', 'assistant-finance', 'assistant-next', "
            "'group:room', 'assistant', '{ana,ben}', 'When is Q-1002 due, Ben?', 'Friday.', "
            "'On Friday.', 'dana')")
    with db.transaction(stack.cfg.database_url) as conn:
        found = export.gather(conn, "ana")
    assert found["shadow_answers"] == [] and found["shadow_answers_in_groups"] == 1
    with db.transaction(stack.cfg.database_url) as conn:
        ben = departures.rename(conn, "ben", stack.gateway.clock())
        dana = departures.rename(conn, "dana", stack.gateway.clock())
    with db.transaction(stack.admin) as conn:
        [pair] = conn.execute("select acts_for, graded_by from shadow_answers").fetchall()
    assert (pair["acts_for"], pair["graded_by"]) == (["ana", ben], dana)
