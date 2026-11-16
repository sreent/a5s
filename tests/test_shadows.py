"""Shadow runs (core/shadows.py, docs/agent-model.md#shadow-runs): a new version of an agent,
released as an agent of its own, answers what people ask an instance, beside it, as an instance
whose settings name the one it shadows, once the data protection officer chooses to let it. It
reads what that instance's run was given, offered only what reads, and sends and changes
nothing; graders from outside the team that built it compare its answers with those sent, and
its judge does too, apart."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db, definitions
from a5s.contract import parse_settings
from a5s.core import approvals, erasure, export, retention, shadows
from a5s.core.policy import PolicyEngine
from a5s.sample import SampleScenario
from conftest import FAKE_MODELS, PROVIDER_KEY, FakeModel, Stack, accessible, build_root, running

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
    spec.write_text(spec.read_text().replace("id: assistant\n", "id: assistant-next\n")
                    + "evaluation:\n  judge: fake\n  rubric: It says when a record falls due.\n")
    (candidate / "AGENTS.md").write_text((candidate / "AGENTS.md").read_text() + f"\n\n{NEXT}\n")
    tools = SampleScenario(root / "scenarios" / "sample", database).tools()
    definitions.pin(candidate, {n: t.schema_hash for n, t in tools.items()})
    with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                 model) as s:
        yield s


def shadowed(stack: Stack, lets: bool = True, **more) -> object:
    """A version with the assistant's next version shadowing assistant-finance, which Ana,
    billing's owner, and Noor, the officer, sign."""
    settings = yaml.safe_load((stack.cfg.scenario_dir / "settings.yaml").read_text())
    return stack.settle(instances={**settings["instances"], "assistant-next-finance": {
        "definition": "assistant-next", "serves": ["ana", "ben"], "parts": ["billing"],
        "level": 1, "owner": "ana", "deputy": "ben", "shadows": "assistant-finance", **more}},
        data_protection={"shadow_runs": lets}, signers=("ana", "noor"))


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
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
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
    accessible(page)
    page.click("#pairs button:has-text('As good')")
    page.wait_for_selector("#nothing", timeout=30000)
    page.wait_for_selector("#figures [data-shadow='assistant-next-finance']", timeout=30000)
    assert "1 better" not in page.inner_text("#figures") and "1 as good" in page.inner_text("#figures")
    accessible(page)
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select grade, graded_by from shadow_answers").fetchone() == {
            "grade": "same", "graded_by": "dana"}
