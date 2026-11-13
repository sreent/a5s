"""Round 9 of the critique: Graphify's CLI runs from the trusted core, so it's given none of the
gateway's secrets, its path is settled as a5s starts, and a question is never an option to it
(a5s/graphify.py; docs/critique.md, round 9)."""

import json
import os
import stat
import subprocess
import sys

from a5s.contract import ToolCall
from a5s.graphify import Graphify


def call(question: str) -> ToolCall:
    return ToolCall(args={"question": question}, instance="dev-team", run="r", acts_for=("raj",))


def test_the_graphify_cli_runs_without_the_cores_secrets(tmp_path, monkeypatch):
    seen = tmp_path / "seen.json"
    cli = tmp_path / "bin" / "graphify"  # any binary of that name, as a deployment installs it
    cli.parent.mkdir()
    payload = (f"import json, os\n"
               f"json.dump(sorted(k for k in os.environ if k.startswith('A5S_')), open({str(seen)!r}, 'w'))\n"
               "print('NODE Client [src=app.py]')\n")
    if os.name == "nt":
        runner = tmp_path / "graphify_fake.py"
        runner.write_text(payload)
        cli = cli.with_suffix(".cmd")  # the command shim an installed CLI has on Windows
        cli.write_text(f'@"{sys.executable}" "{runner}"\n')
    else:
        cli.write_text(f"#!{sys.executable}\n" + payload)
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{cli.parent}{os.pathsep}{os.environ['PATH']}")
    for name, value in (("A5S_SEAL_KEYS", "synthetic-seal-key"),  # as the chart gives the
                        ("A5S_SERVICE_TOKEN", "synthetic-service-token"),  # gateway, and
                        ("A5S_DATABASE_URL", "postgresql://a5s_gateway:synthetic@db/a5s")):
        monkeypatch.setenv(name, value)  # only the gateway
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    tool = Graphify(graph)
    # Windows preserves neither the extension's case nor POSIX's path case rules.
    assert os.path.normcase(tool.command) == os.path.normcase(str(cli))
    answer = tool.tools()["query_code"].run(call("authentication"))
    assert answer["answer"].startswith("NODE")
    assert json.loads(seen.read_text()) == []  # none of the core's secrets, nor anything a5s's


def test_a_question_that_starts_with_a_dash_is_a_question_not_an_option(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: commands.append(cmd) or
                        subprocess.CompletedProcess(cmd, 0, "ok", ""))
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    question = "--graph=/srv/other-repo/graphify-out/graph.json"
    Graphify(graph).tools()["query_code"].run(call(question))
    assert commands[0][-2:] == ["--", question], commands[0]  # after every option of a5s's
