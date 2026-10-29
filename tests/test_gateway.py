from dataclasses import replace

import httpx
import psycopg
import pytest

from a5s import db
from a5s.config import Config, load_models
from a5s.core import ledger
from a5s.core.gateway import Gateway, create_app, sanitize
from a5s.core.policy import PolicyEngine
from conftest import PROVIDER_KEY, SERVICE_TOKEN, free_port, serve


def test_only_the_scheduler_opens_runs(stack):
    with httpx.Client(base_url=stack.url) as c:
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {"sender": "ana"}})
    assert r.status_code == 401


def test_a_run_token_is_needed_and_dies_with_the_run(stack):
    run, token = stack.open_run()
    with stack.client("not-a-token") as c:
        assert c.get("/run").status_code == 401
    with stack.client() as c:
        c.post(f"/runs/{run}/close", json={"outcome": "done"}).raise_for_status()
    with stack.client(token) as c:
        assert c.get("/run").status_code == 401


def test_runs_open_only_for_people_the_instance_serves(stack):
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello", "chen")}})
    assert r.status_code == 409
    assert stack.ledger()[-1]["decision"] == "deny"


def test_a_tool_call_is_decided_and_recorded(stack):
    run, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/run/tools/search_records", json={"args": {"query": "invoice"}})
    assert r.status_code == 200
    assert r.json()["result"][0]["key"] == "Q-1001"
    decided, done = stack.ledger(run)[-2:]
    assert decided["decision"] == "allow"
    assert decided["reasons"] == ["active-instances-use-their-grant"]
    assert decided["acts_for"] == ["ana"] and decided["args"] == {"query": "invoice"}
    assert done["of"] == decided["seq"] and done["outcome"]["status"] == "ok"


def test_a_tool_outside_the_grant_is_denied_and_recorded(stack):
    run, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/run/tools/delete_everything", json={"args": {}})
    assert r.status_code == 403
    assert stack.ledger(run)[-1]["decision"] == "deny"


def test_a_tool_whose_schema_changed_is_refused(stack, monkeypatch):
    _, token = stack.open_run()
    tools = stack.gateway.scenario.tools()
    changed = replace(tools["search_records"], description="Search records, and something new.")
    monkeypatch.setattr(stack.gateway.scenario, "tools", lambda: {**tools, "search_records": changed})
    with stack.client(token) as c:
        r = c.post("/run/tools/search_records", json={"args": {"query": "invoice"}})
    assert r.status_code == 403 and r.json()["reasons"] == ["tools-match-the-release"]


def test_the_model_gateway_uses_the_providers_key_and_records_no_prompt(stack):
    stack.model.reply("Hello")
    run, token = stack.open_run()
    secret = "a sentence that must stay out of the ledger"
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions",
                   json={"model": "fake", "messages": [{"role": "user", "content": secret}]})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "Hello"
    sent = stack.model.requests[0]
    assert sent["headers"]["authorization"] == f"Bearer {PROVIDER_KEY}"
    assert sent["body"]["model"] == "fake-1" and token not in str(sent)
    entries = stack.ledger(run)
    assert secret not in str(entries)
    assert entries[-2]["args"]["prompt_sha256"] and entries[-1]["outcome"]["status"] == 200


def test_a_model_not_on_the_approved_list_is_denied(stack):
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions", json={"model": "something-else", "messages": []})
    assert r.status_code == 403 and not stack.model.requests


def test_suspending_an_instance_denies_its_next_call_in_a_running_run(stack):
    _, token = stack.open_run()
    stack.suspend()
    with stack.client(token) as c:
        tool = c.post("/run/tools/search_records", json={"args": {"query": "invoice"}})
        model = c.post("/v1/chat/completions", json={"model": "fake", "messages": []})
    assert tool.status_code == 403 and "only-active-instances-act" in tool.json()["reasons"]
    assert model.status_code == 403 and not stack.model.requests


def test_messages_keep_only_the_scenarios_record_links(stack):
    _, token = stack.open_run()
    text = ("See https://sample.a5s.dev/records/Q-1001 and https://evil.example/x?d=secret "
            "![p](https://evil.example/pixel.png)")
    with stack.client(token) as c:
        r = c.post("/run/messages", json={"to": "ana", "text": text})
    assert r.status_code == 200 and r.json()["links_removed"] == 2
    assert "https://sample.a5s.dev/records/Q-1001" in r.json()["text"]
    assert "evil.example" not in r.json()["text"]


def test_messages_go_only_to_the_audience(stack):
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/run/messages", json={"to": "mallory", "text": "hi"})
    assert r.status_code == 403


def test_when_the_database_is_down_calls_are_denied(stack):
    port = free_port()
    cfg = Config(database_url=f"postgresql://a5s@127.0.0.1:{free_port()}/postgres",
                 gateway_url=f"http://127.0.0.1:{port}", service_token=SERVICE_TOKEN,
                 root=stack.cfg.root)
    broken = Gateway(cfg, stack.gateway.scenario, PolicyEngine(),
                     load_models(cfg.models_file), stack.gateway.definitions, httpx.Client())
    with serve(create_app(broken), port) as url:
        r = httpx.post(f"{url}/run/tools/search_records", json={"args": {"query": "x"}},
                       headers={"Authorization": "Bearer anything"})
    assert r.status_code == 503 and "denied" in r.json()["error"]


def test_sanitize_drops_lookalike_links():
    text, removed = sanitize("https://sample.a5s.dev.evil.example/x", ("https://sample.a5s.dev/",))
    assert removed == 1 and "evil" not in text


def test_a_denied_call_says_why_in_words_and_never_runs(stack):
    stack.settle(level=0)  # signed by Ana, an instance approver
    run, token = stack.open_run()
    with stack.client(token) as c:
        denied = c.post("/run/tools/create_draft", json={"args": {"title": "t", "body": "b"}})
        unknown = c.post("/run/tools/delete_everything", json={"args": {}})
    assert denied.status_code == unknown.status_code == 403
    assert denied.json()["reasons"] == ["level-0-only-observes"]
    assert denied.json()["explanations"] == [
        "at level 0 the agent only observes, so it can't use a tool that writes"]
    assert unknown.json()["explanations"] == [
        "nothing permits it, such as a tool outside the instance's grant"]
    recorded = [(e["action"], e["decision"]) for e in stack.ledger(run) if e["kind"] == "tool"]
    assert recorded == [("create_draft", "deny"), ("delete_everything", "deny")]


def test_a_granted_tool_the_scenario_no_longer_has_is_refused(stack, monkeypatch):
    _, token = stack.open_run()
    tools = stack.gateway.scenario.tools()
    monkeypatch.setattr(stack.gateway.scenario, "tools",
                        lambda: {n: t for n, t in tools.items() if n != "create_draft"})
    with stack.client(token) as c:
        r = c.post("/run/tools/create_draft", json={"args": {"title": "x", "body": "y"}})
    assert r.status_code == 403 and r.json()["reasons"] == []


@pytest.mark.parametrize("text", [
    "[x](HTTPS://evil.example/?d=1)", "[x](//evil.example/a)", "[x](https:/\\evil.example/a)",
    '<img src="//evil.example/p.png?d=1">', "HTTPS://EVIL.example/x", "see //evil.example/y",
    "www.evil.example", "<https://evil.example/auto>", "[1]: https://evil.example/ref",
    "![p](https://evil.example/pixel.png)",
])
def test_no_link_survives_in_any_form(text):
    cleaned, removed = sanitize(text, ("https://sample.a5s.dev/",))
    assert removed >= 1 and "evil" not in cleaned.lower()


def test_plain_text_and_record_links_survive():
    text = ("a < b and c > d, 3/4 of them, at 10:30. "
            "See [Q-1001](https://sample.a5s.dev/records/Q-1001) and https://sample.a5s.dev/records/Q-1003.")
    assert sanitize(text, ("https://sample.a5s.dev/",)) == (text, 0)


def test_drafts_keep_only_text_and_record_links(stack):
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/run/tools/create_draft", json={"args": {
            "title": "Re: Q-1001", "body": "Pay at https://evil.example/pay"}})
    assert r.status_code == 200
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select body from sample.drafts").fetchone()["body"] == (
            "Pay at [link removed]")
    allowed = [e for e in stack.ledger() if e["kind"] == "tool" and e["decision"] == "allow"]
    assert [e["links_removed"] for e in allowed] == [1]


def test_a_tool_that_changes_its_risk_needs_a_new_release(stack, monkeypatch):
    _, token = stack.open_run()
    tools = stack.gateway.scenario.tools()
    quiet = replace(tools["create_draft"], writes=False)  # it claims it no longer writes
    monkeypatch.setattr(stack.gateway.scenario, "tools", lambda: {**tools, "create_draft": quiet})
    with stack.client(token) as c:
        r = c.post("/run/tools/create_draft", json={"args": {"title": "x", "body": "y"}})
    assert r.status_code == 403 and r.json()["reasons"] == ["tools-match-the-release"]


def test_providers_get_only_known_fields_and_never_their_own_tools(stack):
    stack.model.reply("Hello")
    run, token = stack.open_run()
    say = [{"role": "user", "content": "Hi"}]
    with stack.client(token) as c:
        searching = c.post("/v1/chat/completions", json={
            "model": "fake", "messages": say, "tools": [{"type": "web_search"}]})
        anthropic = c.post("/v1/messages", json={"model": "fake", "max_tokens": 10, "messages": say,
                                                 "tools": [{"type": "web_search_20250305",
                                                            "name": "web_search"}]})
        quiet = c.post("/v1/chat/completions", json={
            "model": "fake", "messages": say, "enable_search": True, "temperature": 0})
    assert searching.status_code == 403 and anthropic.status_code == 403
    assert quiet.status_code == 200 and len(stack.model.requests) == 1
    sent = stack.model.requests[0]["body"]
    assert "enable_search" not in sent and sent["temperature"] == 0
    decided = [e for e in stack.ledger(run) if e["kind"] == "model" and e["decision"] != "record"]
    assert [e["reasons"] for e in decided[:2]] == [["agents-use-their-own-tools"]] * 2
    assert decided[2]["args"]["left_out"] == ["enable_search"]
    assert decided[2]["args"]["params"] == {"temperature": 0}


@pytest.mark.parametrize("reports", ["fake-2", ""], ids=["another model", "no model"])
def test_a_response_must_report_the_approved_version(stack, reports):
    stack.model.reply("Hello")
    stack.model.reports = reports
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/v1/chat/completions", json={"model": "fake", "messages": []})
    assert r.status_code == 502 and r.json()["error"]["code"] == "model_mismatch"


def test_an_undated_model_must_say_what_its_provider_reports(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text("models:\n  latest:\n    provider: p\n    api: openai\n"
                    "    base_url: https://p.test\n    model: something-latest\n    key_env: K\n")
    with pytest.raises(ValueError, match="isn't a dated version"):
        load_models(path)


def test_a_call_that_ran_but_couldnt_be_recorded_isnt_called_denied(stack, monkeypatch):
    _, token = stack.open_run()
    append = ledger.append

    def outcomes_fail(conn, entry):
        if entry.get("decision") == "record":
            raise psycopg.OperationalError("the database went away")
        return append(conn, entry)

    monkeypatch.setattr(ledger, "append", outcomes_fail)
    with stack.client(token) as c:
        r = c.post("/run/tools/search_records", json={"args": {"query": "invoice"}})
    assert r.status_code == 200 and r.json()["recorded"] is False and r.json()["result"]
