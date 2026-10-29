import httpx

from a5s import db
from a5s.config import Config, load_models
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


def test_a_tool_whose_schema_changed_is_refused(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("""update instances set pins = jsonb_set(pins, '{search_records}', '"0000"')""")
    _, token = stack.open_run()
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


def test_explain_says_why_in_words_and_records_only_denials(stack):
    run, token = stack.open_run()
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set level = 0")
    with stack.client(token) as c:
        allowed = c.post("/run/explain", json={"action": "call_tool", "name": "search_records"})
        denied = c.post("/run/explain", json={"action": "call_tool", "name": "create_draft"})
        unknown = c.post("/run/explain", json={"action": "call_tool", "name": "delete_everything"})
    assert allowed.json()["decision"] == "allow"
    assert denied.json()["reasons"] == ["level-0-only-observes"]
    assert denied.json()["explanations"] == [
        "at level 0 the agent only observes, so it can't use a tool that writes"]
    assert unknown.json()["explanations"] == [
        "nothing permits it, such as a tool outside the instance's grant"]
    recorded = [(e["kind"], e["action"]) for e in stack.ledger(run) if e["kind"] == "explain"]
    assert recorded == [("explain", "create_draft"), ("explain", "delete_everything")]


def test_a_granted_tool_the_scenario_no_longer_has_is_refused(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set grants = array_append(grants, 'retired_tool')")
    _, token = stack.open_run()
    with stack.client(token) as c:
        r = c.post("/run/tools/retired_tool", json={"args": {}})
    assert r.status_code == 403 and r.json()["reasons"] == []
