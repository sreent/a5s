"""Idempotent scenario effects, including retries by fresh workers of a task."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock

from a5s import db
from a5s.contract import ToolCall
from a5s.effects import draft_once
from test_task_runs import a_task


def test_an_in_memory_draft_is_created_once_under_concurrent_retries():
    rows, lock = [], Lock()
    call = ToolCall(args={"title": "A readiness note", "body": "Review first", "record": "PR-21"},
                    instance="dev-team", run="run", acts_for=("raj",), key="one effect")

    def create(_):
        return draft_once(call, rows, "https://code.dev.test/", lock)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(create, range(24)))
    assert len(rows) == 1 and {r["draft"] for r in results} == {1}
    assert sum(r.get("replayed", False) for r in results) == 23


def test_a_draft_a_fresh_task_slice_repeats_is_created_once_but_a_new_draft_is_new(stack):
    task = a_task(stack)
    trigger = {"kind": "task", "task": str(task["id"])}
    args = {"title": "Q-1001 readiness", "body": "Review before release", "record": "Q-1001"}
    with stack.client() as client:
        first = client.post("/runs", json={"instance": "assistant-finance", "trigger": trigger})
        assert first.status_code == 200, first.text
        with stack.client(first.json()["token"]) as worker:
            made = worker.post("/run/tools/create_draft", json={"args": args})
        assert made.status_code == 200, made.text
        client.post(f"/runs/{first.json()['run']}/close", json={"outcome": "done"}).raise_for_status()
        stack.at((stack.gateway.clock() + timedelta(minutes=5)).isoformat())
        second = client.post("/runs", json={"instance": "assistant-finance", "trigger": trigger})
        assert second.status_code == 200, second.text
        with stack.client(second.json()["token"]) as worker:
            repeated = worker.post("/run/tools/create_draft", json={"args": args})
            different = worker.post("/run/tools/create_draft", json={"args": {
                **args, "body": "A different readiness note"}})
    assert repeated.status_code == 200, repeated.text
    assert different.status_code == 200, different.text
    assert repeated.json()["result"]["draft"] == made.json()["result"]["draft"]
    assert repeated.json()["result"]["replayed"] is True
    assert different.json()["result"]["draft"] != repeated.json()["result"]["draft"]
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from sample.drafts").fetchone()["n"] == 2


def test_the_sample_database_returns_one_draft_under_concurrent_retries(stack):
    tool = stack.gateway.scenario.tools()["create_draft"]
    call = ToolCall(args={"title": "A note", "body": "A body", "record": "Q-1001"},
                    instance="assistant-finance", run="run", acts_for=("ana",), key="one effect")

    def create(_):
        return tool.run(call)

    with db.transaction(stack.admin) as conn:
        before = conn.execute("select count(*) as n from sample.drafts").fetchone()["n"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create, range(16)))
    assert len({r["draft"] for r in results}) == 1
    assert sum(r.get("replayed", False) for r in results) == 15
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from sample.drafts").fetchone()["n"] == before + 1
