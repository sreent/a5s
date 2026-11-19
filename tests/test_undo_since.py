"""Undoing a change only as the change left it (round 14, B-U1, B-U2): an undo whose call is
made of the change's own arguments alone, such as taking a question off hold, still checks the
record holds what the change left in every field it altered, so it never puts back what someone
changed since; and undoing one of two changes a run made counts against that change alone."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db
from a5s.connectors import mcp
from conftest import FAKE_MODELS, PROVIDER_KEY, FakeModel, build_root, free_port, running, serve
from test_levels import levelled
from test_proposals import decide, held
from test_proposals import sweep as decided
from test_undo import undo

server_sdk = pytest.importorskip("mcp.server.mcpserver")
mcp_types = pytest.importorskip("mcp.types")
KEY = {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}


def holds(admin: str):
    """A system that puts a question on hold, and takes it off hold, in the sample's records."""
    server = server_sdk.MCPServer("holds")
    hints = mcp_types.ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False)

    def status(key: str, value: str) -> dict:
        with db.transaction(admin) as conn:
            conn.execute("insert into sample.changes (key, field, value, made_for) "
                         "values (%s, 'status', %s, 'holds')", (key, value))
        return {"key": key, "status": value}

    @server.tool(annotations=hints)
    def hold(key: str) -> dict:
        """Put a question on hold."""
        return status(key, "on hold")

    @server.tool(annotations=hints)
    def release(key: str) -> dict:
        """Take a question off hold."""
        return status(key, "open")

    return server.streamable_http_app()


def declared(url: str) -> dict:
    tool = {"server": "holds", "arguments": KEY, "returns": ["key", "status"], "writes": True,
            "idempotent": True, "record_arg": "key", "record_field": "key",
            "action": "close-question"}
    return {"servers": {"holds": {"url": url}}, "tools": {
        "hold_question": {**tool, "calls": "hold", "description": "Put a question on hold",
                          "undo": {"tool": "release_question", "args": {"key": "args.key"}}},
        "release_question": {**tool, "calls": "release",
                             "description": "Take a question off hold"}}}


@pytest.fixture
def stack(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with serve(holds(database), free_port()) as server:
        (root / "scenarios" / "sample" / mcp.FILE).write_text(yaml.safe_dump(declared(f"{server}/mcp")), encoding="utf-8")
        spec = root / "agents" / "assistant" / "agent.yaml"
        spec.write_text(re.sub(r"changes: \[change_due_date, close_question\]",
                               "changes: [change_due_date, close_question, hold_question, "
                               "release_question]", spec.read_text(encoding="utf-8")))
        with running(database, root, httpx.Client(transport=httpx.MockTransport(model.handler)),
                     model) as s:
            yield s


def status_of(stack, key: str = "Q-1002") -> str:
    from a5s.contract import record_of
    return record_of(stack.gateway.scenario, key).fields["status"]


def swept_undo(stack) -> dict:
    with stack.client() as c:
        answer = c.post("/undo/sweep")
    answer.raise_for_status()
    return answer.json()


def test_an_undo_of_the_changes_own_arguments_leaves_what_someone_changed_since(
        stack, approving, provider):
    stack.model.reply(None, ("hold_question", {"key": "Q-1002"}))
    stack.model.reply("It waits for Ana.")
    stack.say("Please put Q-1002 on hold.", person="ben")
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    decided(stack)
    assert status_of(stack) == "on hold"
    with db.transaction(stack.admin) as conn:
        [made] = conn.execute("select * from changes_made").fetchall()
    assert made["as_left"] == {"status": "on hold"}  # what it altered, as it left it
    with db.transaction(stack.admin) as conn:  # Chen closes it in the records system, since
        conn.execute("insert into sample.changes (key, field, value, made_for) "
                     "values ('Q-1002', 'status', 'closed', 'chen')")
    assert undo(approving, provider, made["id"], "ben").status_code == 200
    assert swept_undo(stack) == {"undone": 0, "refused": 1, "failed": 0}
    assert status_of(stack) == "closed"  # Chen's, as Chen left it


def test_undoing_one_of_two_changes_counts_against_that_change_alone(stack, approving, provider):
    levelled(stack)  # level 2 for due dates in billing
    stack.model.reply(None, ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"}),
                      ("change_due_date", {"key": "Q-1001", "due": "2026-11-20"}))
    stack.model.reply("Both moved.")
    stack.say("Please move Q-1002 to 2026-11-13 and Q-1001 to 2026-11-20.", person="ben")
    with db.transaction(stack.admin) as conn:
        changes = conn.execute("select id, record from changes_made order by id").fetchall()
        drawn = conn.execute("select id, records from samples order by id").fetchall()
    first = next(iter(drawn[0]["records"]))  # the run's first sample, whichever ran first
    other = next(c for c in changes if c["record"] != first)  # the change it isn't
    assert undo(approving, provider, other["id"], "ben").status_code == 200
    assert swept_undo(stack)["undone"] == 1
    with db.transaction(stack.admin) as conn:
        after = conn.execute("select records, grade from samples order by id").fetchall()
    assert [list(s["records"]) for s in after if s["grade"] == "wrong"] == [[other["record"]]]
