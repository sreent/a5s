"""Round 9, reviewer A: a scenario's tools run in the gateway, the trusted core, and Graphify's
query_code runs whatever `graphify` is first on the PATH (a5s/graphify.py), unpinned, with the
gateway's whole environment: its seal keys, service token and database URL among it."""

import json
import os
import stat
import sys

from a5s.contract import ToolCall
from a5s.graphify import Graphify


def test_the_graphify_cli_runs_with_the_cores_secrets(tmp_path, monkeypatch):
    seen = tmp_path / "seen.json"
    cli = tmp_path / "bin" / "graphify"  # any binary of that name, as a deployment installs it
    cli.parent.mkdir()
    cli.write_text(f"#!{sys.executable}\nimport json, os\n"
                   f"json.dump(sorted(k for k in os.environ if k.startswith('A5S_')), open({str(seen)!r}, 'w'))\n"
                   "print('NODE Client [src=app.py]')\n")
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{cli.parent}{os.pathsep}{os.environ['PATH']}")
    for name, value in (("A5S_SEAL_KEYS", "synthetic-seal-key"),  # as the chart gives the
                        ("A5S_SERVICE_TOKEN", "synthetic-service-token"),  # gateway, and
                        ("A5S_DATABASE_URL", "postgresql://a5s_gateway:synthetic@db/a5s")):
        monkeypatch.setenv(name, value)  # only the gateway
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    answer = Graphify(graph).tools()["query_code"].run(ToolCall(
        args={"question": "authentication"}, instance="dev-team", run="r", acts_for=("raj",)))
    assert answer["answer"].startswith("NODE")
    got = json.loads(seen.read_text())
    # FAILS NOW: the external CLI was handed the core's seal key, token and database password
    assert not {"A5S_SEAL_KEYS", "A5S_SERVICE_TOKEN", "A5S_DATABASE_URL"} & set(got), got


def test_a_question_that_starts_with_a_dash_reaches_the_cli_as_an_option(tmp_path, monkeypatch):
    """Without "--" before it, a question such as "--graph=/elsewhere/graph.json" is an option
    to the CLI, not a question; what that does depends on Graphify's own parser."""
    import subprocess
    commands = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: commands.append(cmd) or
                        subprocess.CompletedProcess(cmd, 0, "ok", ""))
    graph = tmp_path / "graph.json"
    graph.write_text("{}")
    Graphify(graph).tools()["query_code"].run(ToolCall(
        args={"question": "--graph=/srv/other-repo/graphify-out/graph.json"}, instance="dev-team",
        run="r", acts_for=("raj",)))
    # FAILS NOW: ['graphify', 'query', '--graph=/srv/other-repo/...', '--graph', ...]
    assert "--" in commands[0][:3] or not commands[0][2].startswith("-"), commands[0]


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
