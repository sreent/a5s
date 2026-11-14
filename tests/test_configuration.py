"""a5s's configuration (a5s/config.py, docs/configuration.md): every setting a deployment gives
it, in one list, with what each takes and its default, which is written there alone; read
through that list alone, never as a module is imported; checked as each part starts, so a
value it can't use, or an A5S_ name that isn't a setting, stops it there with what to change;
and shown, secrets masked, by `a5s config`, each part's first log line and the core's status."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from a5s import cli, config
from a5s.core import status
from conftest import ROOT

SRC = ROOT / "src" / "a5s"


def bare_env(**given: str) -> dict[str, str]:
    """The test's environment without its A5S_ settings, and with these."""
    return {**{k: v for k, v in os.environ.items() if not k.startswith("A5S_")}, **given}


def test_every_setting_is_listed_once_with_what_it_takes_and_a_default_it_would_take():
    names = [v.name for v in config.VARS]
    assert len(names) == len(set(names)) and all(n.startswith("A5S_") for n in names)
    for var in config.VARS:
        assert var.means and var.takes and var.area in config.AREAS, var.name
        assert var.read({}) == var.default, var.name  # unset, it's its default
        if var.default not in (None, "", (), {}, frozenset()) and not var.secret:
            shown, _ = config.shown(var, {})
            assert var.read({var.name: shown}) == var.default, (  # in its own bounds
                f"{var.name}'s default, {shown}, isn't one it would take")


def test_a_part_reads_no_setting_but_through_the_list():
    """No module reads an A5S_ variable from the environment itself, by name: so every
    setting is listed, checked as a part starts, and shown, and none is read at import."""
    def names_a_setting(node: ast.AST) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.startswith("A5S_")
        if isinstance(node, ast.JoinedStr) and node.values:
            first = node.values[0]
            return isinstance(first, ast.Constant) and str(first.value).startswith("A5S_")
        return False

    def environ(node: ast.AST) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == "environ" or (
            isinstance(node, ast.Name) and node.id == "environ")

    found = []
    for path in sorted(SRC.rglob("*.py")):
        if path == SRC / "config.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            key = None
            if isinstance(node, ast.Subscript) and environ(node.value):
                key = node.slice
            elif (isinstance(node, ast.Call) and node.args and isinstance(node.func, ast.Attribute)
                  and (node.func.attr in ("get", "pop", "setdefault") and environ(node.func.value)
                       or node.func.attr == "getenv")):
                key = node.args[0]
            if key is not None and names_a_setting(key):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert found == [], f"read through a5s/config.py instead: {found}"


def test_every_A5S_name_anywhere_is_a_setting_a_family_or_said_not_to_be_one():
    """Compose, the chart, the scripts, the docs and the tests name no A5S_ variable that a5s
    doesn't list: a name in one of them that isn't a setting would be set and do nothing."""
    unknown = {}
    for path in sorted(ROOT.rglob("*")):
        if (not path.is_file() or path == Path(__file__)  # which misspells some, as people do
                or any(p in path.parts for p in (".git", ".venv", ".a5s", "node_modules"))
                or path.suffix not in (".py", ".yaml", ".yml", ".tpl", ".sh", ".md", ".toml",
                                       ".txt", "") or path.name.startswith(".")):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for name in set(re.findall(r"\bA5S_[A-Z0-9_]*[A-Z0-9]\b", text)):
            if not (config.known(name) or name in config.MOVED
                    or any(f.pattern.partition("<")[0].rstrip("_") == name
                           for f in config.FAMILIES)):
                unknown.setdefault(name, str(path.relative_to(ROOT)))
    assert unknown == {}, f"list these in a5s/config.py, or say they aren't settings: {unknown}"


def test_a_value_a_part_cant_use_stops_it_as_it_starts_saying_which_and_what_it_takes():
    run = subprocess.run(
        [sys.executable, "-m", "a5s.cli", "scheduler"], capture_output=True, text=True,
        timeout=120, check=False, env=bare_env(A5S_DB_POOL_SIZE="ten", A5S_DB_POOLSIZE="20",
                                  A5S_DEVELOPMENT="ture", A5S_TEAMS_APP_ID="app",
                                  A5S_SERVICE_TOKEN="a secret"))
    assert run.returncode == 1, run.stderr
    said = run.stderr
    assert "a5s scheduler can't start, as its settings need changing:" in said
    assert "A5S_DB_POOL_SIZE is 'ten': it takes a whole number from 1 to 200" in said
    assert "A5S_DEVELOPMENT is 'ture': it takes true or false" in said
    assert ("Teams needs A5S_TEAMS_APP_SECRET and A5S_TEAMS_TENANT_ID as well as "
            "A5S_TEAMS_APP_ID") in said
    assert "A5S_DB_POOLSIZE isn't one of a5s's settings: did you mean A5S_DB_POOL_SIZE?" in said
    assert "a secret" not in said  # nor any secret's value


def test_a_value_it_cant_use_never_breaks_an_import():
    """Each is read as it's needed, so a module imports whatever its environment holds, and
    the part that starts says what's wrong, rather than a traceback from deep in an import."""
    bad = {v.name: "?" for v in config.VARS}
    imported = ("import a5s.cli, a5s.core.gateway, a5s.core.inbox, a5s.db, a5s.worker, "
                "a5s.services.scheduler, a5s.core.models, a5s.core.teams, a5s.core.identity, "
                "a5s.core.matrix, a5s.client, a5s.sandbox")
    run = subprocess.run([sys.executable, "-c", imported], capture_output=True, text=True,
                         timeout=120, env=bare_env(**bad), check=False)
    assert run.returncode == 0, run.stderr


def test_the_command_line_is_only_told_of_a_name_that_isnt_a_setting():
    env = {"A5S_DB_POOLSIZE": "20", "A5S_TEST_ANYTHING": "1", "A5S_IMAGE": "a5s:dev"}
    problems, warnings = config.check(env, serving=False)
    assert problems == [] and warnings == [
        "A5S_DB_POOLSIZE isn't one of a5s's settings: did you mean A5S_DB_POOL_SIZE?"]
    assert config.check(env, serving=True) == (warnings, [])


def test_a_bot_whose_secret_isnt_set_stops_teams_as_it_starts():
    bots = json.dumps([{"agent": "watcher", "app_id": "2",
                        "secret_env": "A5S_TEAMS_SECRET_WATCHER"}])
    problems, _ = config.check({"A5S_TEAMS_BOTS": bots, "A5S_TEAMS_TENANT_ID": "t"})
    assert problems == [("A5S_TEAMS_BOTS gives the watcher agent's bot its secret in "
                         "A5S_TEAMS_SECRET_WATCHER, which isn't set")]
    assert config.check({"A5S_TEAMS_BOTS": bots, "A5S_TEAMS_TENANT_ID": "t",
                         "A5S_TEAMS_SECRET_WATCHER": "s"}) == ([], [])


def test_what_a_part_runs_with_is_shown_with_its_secrets_masked(monkeypatch, capsys, tmp_path):
    env = {"A5S_DATABASE_URL": "postgresql://a5s_gateway:hunter2@db:5432/a5s",
           "A5S_SERVICE_TOKEN": "s3cret", "A5S_DB_POOL_SIZE": "20",
           "A5S_OIDC_ISSUER": "https://login.example/tenant/", "A5S_OIDC_GROUPS_CLAIM": ""}
    assert config.set_here(env) == {
        "A5S_SERVICE_TOKEN": "•••", "A5S_DATABASE_URL": "postgresql://a5s_gateway:•••@db:5432/a5s",
        "A5S_DB_POOL_SIZE": "20", "A5S_OIDC_ISSUER": "https://login.example/tenant/",
        "A5S_OIDC_GROUPS_CLAIM": "set empty"}  # the issuer exactly as its tokens name it
    for name in list(os.environ):
        if name.startswith("A5S_"):
            monkeypatch.delenv(name)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)  # where `a5s up` has kept no token of its own
    cli.main(["config"])
    said = capsys.readouterr().out
    assert said.startswith(f"5 of a5s's {len(config.VARS)} settings are set here")
    assert "  A5S_DB_POOL_SIZE = 20  (set)" in said and "  A5S_DB_CONNECT_TIMEOUT = 2  (a5s default)" in said
    assert "hunter2" not in said and "s3cret" not in said
    cli.main(["config", "--json"])
    listed = {s["name"]: s for s in json.loads(capsys.readouterr().out)["settings"]}
    assert listed["A5S_SERVICE_TOKEN"]["value"] == "•••" and len(listed) == len(config.VARS)
    monkeypatch.setenv("A5S_WORKER_SLOTS", "assistant=many")
    with pytest.raises(SystemExit) as stopped:  # as a check before deploying, too
        cli.main(["config", "--set"])
    assert stopped.value.code == 1
    assert ("A5S_WORKER_SLOTS is 'assistant=many': it takes agent=number pairs, by commas"
            in capsys.readouterr().out)


def test_the_core_says_what_it_runs_with_in_its_status(stack, monkeypatch):
    monkeypatch.setenv("A5S_DB_POOL_SIZE", "12")
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["configuration"]["set"]["A5S_DB_POOL_SIZE"] == "12"
    assert now["configuration"]["defaults"] == len(config.VARS) - len(now["configuration"]["set"])
    assert "A5S_DB_POOL_SIZE=12" in status.told(now)


def test_the_docs_list_every_setting_as_the_code_does():
    doc = (ROOT / "docs" / "configuration.md").read_text()
    start, end = "<!-- a5s config --markdown -->", "<!-- end of a5s config --markdown -->"
    assert start in doc and end in doc
    listed = doc.split(start, 1)[1].split(end, 1)[0].strip()
    assert listed == config.markdown().strip(), (
        "the table is out of date: put `a5s config --markdown` in its place")


# Each default is written once, in a5s/config.py: compose and the chart set only what a
# deployment chooses, and pass everything else through unset

HELM = ("alpine/helm:3.16.3@sha256:"
        "ed9dfc49d43d034df3f9880eb777caf0183e5156508672478b80412c63f3db4f")


def repeated(name: str, value: str) -> bool:
    """Whether a value someone wrote for a setting is only its default again."""
    var = config.BY_NAME.get(name)
    if var is None or not value.strip() or var.secret:
        return False
    try:
        return var.read({name: value}) == var.default
    except config.ConfigError:
        return False


def test_compose_sets_no_setting_to_its_default():
    found = []
    for path in sorted((ROOT / "deploy").glob("compose*.yaml")):
        stack = yaml.safe_load(path.read_text())
        envs = [v for k, v in stack.items() if k.startswith("x-") and isinstance(v, dict)]
        envs += [s.get("environment") or {} for s in (stack.get("services") or {}).values()]
        for env in envs:
            pairs = (env.items() if isinstance(env, dict)
                     else (e.partition("=")[::2] for e in env if isinstance(e, str)))
            for name, value in pairs:
                if not str(name).startswith("A5S_") or value is None:
                    continue
                written = str(value)
                for interpolated in re.findall(r"\$\{(A5S_[A-Z0-9_]+):-([^}]*)\}", written):
                    if repeated(*interpolated):  # a fallback that's only the default
                        found.append(f"{path.name}: {interpolated[0]}:-{interpolated[1]}")
                if "${" not in written and repeated(str(name), written):
                    found.append(f"{path.name}: {name}={written}")
    assert found == [], f"leave these unset, so a5s's own default holds: {found}"


def rendered(*values: str, sandbox: bool = False) -> list[dict]:
    """The chart, as helm renders it with these values files, as a5s's release or the
    sandbox's."""
    charts = ROOT / "deploy" / "helm"
    args = ["template", "a5s", "/charts/a5s", *(a for v in values for a in ("-f", f"/charts/{v}")),
            *(["--set", "mode=sandbox"] if sandbox else [])]
    if shutil.which("helm"):
        command = ["helm", *[a.replace("/charts", str(charts)) for a in args]]
    elif shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True,
                                                   check=False).returncode == 0:
        command = ["docker", "run", "--rm", "-v", f"{charts}:/charts:ro", HELM, *args]
    else:
        pytest.skip("neither helm nor docker is here to render the chart")
    run = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    assert run.returncode == 0, run.stderr
    return [d for d in yaml.safe_load_all(run.stdout) if d]


def containers(doc: dict) -> list[dict]:
    spec = doc.get("spec") or {}
    spec = (spec.get("jobTemplate") or {}).get("spec", spec)
    pod = (spec.get("template") or {}).get("spec") or {}
    return [*(pod.get("initContainers") or []), *(pod.get("containers") or [])]


# What the chart states though they're a5s's defaults, as it sizes its pods' shutdown by them:
# held to the code's, so they can't drift from it
STATED = {"A5S_PROVIDER_TIMEOUT", "A5S_WORKER_WAIT"}


def test_the_chart_sets_no_setting_to_its_default_and_none_a5s_doesnt_know():
    found, strangers, stated = [], [], {}
    for doc in [*rendered("ci-values.yaml"), *rendered("ci-values.yaml", sandbox=True)]:
        for container in containers(doc):
            for env in container.get("env") or []:
                name = env["name"]
                if not name.startswith("A5S_"):
                    continue
                if not config.known(name):
                    strangers.append(name)
                if name in STATED:
                    stated.setdefault(name, set()).add(str(env.get("value")))
                elif "value" in env and repeated(name, str(env["value"])):
                    found.append(f"{doc['kind']}/{doc['metadata']['name']}: {name}={env['value']}")
    assert strangers == [], f"the chart sets what a5s doesn't read: {strangers}"
    assert found == [], f"leave these unset, so a5s's own default holds: {found}"
    assert set(stated) == STATED and all(repeated(n, v) for n, vs in stated.items() for v in vs), (
        f"the chart's timeouts aren't a5s's defaults: {stated}")


def test_the_copier_copies_every_hour_unless_its_told_otherwise(monkeypatch, tmp_path):
    every: list[int | None] = []
    monkeypatch.setattr(cli, "_anchor", lambda cfg, n: every.append(n))
    monkeypatch.chdir(tmp_path)
    for args in (["anchor", "--every"], ["anchor", "--every", "60"], ["anchor"]):
        cli.main(args)
    assert every == [cli.ANCHOR_EVERY, 60, None] and cli.ANCHOR_EVERY == 3600  # once, alone
