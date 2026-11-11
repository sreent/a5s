from __future__ import annotations

import subprocess

import pytest

from a5s.contract import ToolCall
from a5s.graphify import Graphify


def call(question: str = "authentication") -> ToolCall:
    return ToolCall(args={"question": question}, instance="code", run="run", acts_for=("ana",))


def test_a_graphify_query_is_local_read_only_and_bounded(tmp_path, monkeypatch):
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    commands = []

    def run(cmd, **kwargs):
        commands.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "NODE Client [src=httpx/_client.py]", "")

    monkeypatch.setattr(subprocess, "run", run)
    tool = Graphify(graph, command="graphify-test", budget=750).tools()["query_code"]
    found = tool.run(call())
    assert found == {"answer": "NODE Client [src=httpx/_client.py]", "truncated": False}
    [(command, given)] = commands
    assert command == ["graphify-test", "query", "--graph", str(graph.resolve()), "--budget",
                       "750", "--", "authentication"]
    assert {k: v for k, v in given.items() if k != "env"} == {
        "capture_output": True, "text": True, "check": False, "timeout": 60}
    assert not any(k.startswith("A5S_") for k in given["env"])  # none of the core's
    assert tool.risk == {"reads": True, "writes": False, "destructive": False,
                         "sends_outside": False}
    assert tool.definition()["schema_hash"] == tool.schema_hash


def test_a_graphify_query_reports_what_it_finds_without_calling_the_cli(tmp_path, monkeypatch):
    def unexpected(cmd, **kwargs):
        raise AssertionError("the CLI should not run")

    monkeypatch.setattr(subprocess, "run", unexpected)
    tool = Graphify(tmp_path / "missing.json").tools()["query_code"]
    assert "isn't available" in tool.run(call())["error"]
    assert "ask what" in Graphify(tmp_path / "graph.json").tools()["query_code"].run(call("  "))["error"]


@pytest.mark.parametrize("code, expected", [(3, "several"), (4, "no code concept"), (1, "couldn't")])
def test_graphify_query_results_have_useful_errors(tmp_path, monkeypatch, code, expected):
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs:
                        subprocess.CompletedProcess(cmd, code, "Graphify said", ""))
    found = Graphify(graph).tools()["query_code"].run(call())["error"]
    assert expected in found


def test_a_graphify_query_that_cant_run_says_so(tmp_path, monkeypatch):
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: (_ for _ in ()).throw(
        FileNotFoundError(cmd)))
    assert Graphify(graph).tools()["query_code"].run(call()) == {"error": "Graphify couldn't answer now"}


def test_graphify_tool_is_pinned_into_an_agent_release(tmp_path):
    import shutil

    import yaml

    from a5s import definitions
    from conftest import ROOT

    agent = tmp_path / "assistant"
    shutil.copytree(ROOT / "agents" / "assistant", agent)
    spec = yaml.safe_load((agent / "agent.yaml").read_text())
    spec["tools"]["knowledge"] = ["query_code"]
    (agent / "agent.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    tool = Graphify(tmp_path / "graph.json").tools()["query_code"]
    hashes = {name: f"pin-{name}" for name in definitions.load(agent).tool_names}
    hashes["query_code"] = tool.schema_hash
    definitions.pin(agent, hashes)
    assert yaml.safe_load((agent / "tools.lock").read_text())["query_code"] == tool.schema_hash
