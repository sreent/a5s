"""Installing a5s and its first day (docs/first-day.md).

Before installing: deploy/reach-check.py, run where a5s will run, says whether it reaches the
database, the identity provider and whatever else a5s calls, and what to fix where it doesn't.
The chart's examples, one for each cloud and one for the organisation's own cluster, name only
values the chart has, and render. deploy/chat-apps.py makes each agent's Teams package and Slack
manifest from what a5s takes, so nobody works out scopes and addresses by hand. And once it's
installed, `a5s release status` names whom the directory gives each role the release needs."""

from __future__ import annotations

import importlib.util
import json
import socket
import struct
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import psycopg.conninfo
import pytest
import yaml

from a5s import cli, config
from a5s.core import slack, teams
from conftest import ROOT
from test_configuration import containers, rendered
from test_release import deployed  # noqa: F401 - the fixture, as test_release has it
from test_routers import described

DEPLOY = ROOT / "deploy"
EXAMPLES = sorted((DEPLOY / "helm" / "examples").glob("*.yaml"))


def script(name: str) -> ModuleType:
    """One of deploy's scripts, which have no package of their own, as a module."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), DEPLOY / f"{name}.py")
    assert spec and spec.loader
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


def reach(*args: str) -> subprocess.CompletedProcess[str]:
    """The reach check, as someone runs it where a5s will run: Python alone, nothing of a5s's."""
    return subprocess.run([sys.executable, "-I", str(DEPLOY / "reach-check.py"), *args],
                          capture_output=True, text=True, timeout=120, check=False)


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# Before installing: what a5s will reach from where it runs

def test_the_reach_check_says_what_answers_and_what_to_fix(database_url, provider):
    given = psycopg.conninfo.conninfo_to_dict(database_url)
    db = f"{given.get('host') or '127.0.0.1'}:{given.get('port') or 5432}"
    closed = f"127.0.0.1:{closed_port()}"
    found = reach("--postgres", db, "--postgres", closed, "--issuer", provider.url)
    lines = found.stdout.splitlines()
    assert found.returncode == 1, found.stdout + found.stderr
    assert lines[0] == f"ok   Postgres: Postgres at {db} takes connections."
    assert lines[1].startswith(f"fix  Postgres: nothing takes connections at {closed}")
    assert lines[2] == (f"ok   Signing in: the identity provider at {provider.url} answers, and "
                        f"its keys at {provider.url}/certs do.")
    assert lines[3] == "1 can't be reached from here: fix it before installing a5s."
    everything = reach("--postgres", db, "--issuer", provider.url)
    assert everything.returncode == 0 and everything.stdout.endswith("Everything answered.\n")


def test_an_issuer_set_otherwise_than_the_provider_names_both(provider):
    found = reach("--issuer", provider.url + "/")
    assert found.returncode == 1
    assert (f"the provider names its issuer '{provider.url}', and you gave '{provider.url}/': "
            "set people.oidcIssuer to its own, to the last slash") in found.stdout


def test_the_reach_check_tries_what_a5s_itself_calls_for_each_chat():
    """--plan says what it would try, and tries nothing: for Teams and Slack, what a5s's own
    adapters call, so the list can't drift from them."""
    found = reach("--plan", "--teams", "--slack", "--matrix", "https://matrix.example.org/")
    assert found.returncode == 0
    tried = [line.split(": ", 1) for line in found.stdout.splitlines()]
    assert ["Teams", teams.METADATA] in tried
    hosts = {Path(url.split("://", 1)[1]).parts[0] for _, url in tried}
    assert set(config.TEAMS_SERVICE_HOSTS.default) <= hosts  # where Teams takes replies
    assert ["Slack", f"{slack.API}/api.test"] in tried and slack.FILE_HOSTS <= hosts
    assert ["Matrix", "https://matrix.example.org/_matrix/client/versions"] in tried
    assert reach().returncode == 2  # nothing named: it says what to name


# The chart's examples, one for each cloud and one for the organisation's own cluster

@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_each_example_names_only_values_the_chart_has(example):
    chart = yaml.safe_load((DEPLOY / "helm" / "a5s" / "values.yaml").read_text(encoding="utf-8"))
    free = {"annotations", "podLabels", "expires"}  # the deployment's own names

    def unknown(given: dict, known: dict, at: str) -> list[str]:
        found = []
        for key, value in given.items():
            if key not in known:
                found.append(f"{at}{key}")
            elif isinstance(value, dict) and known[key] and isinstance(known[key], dict) \
                    and key not in free:  # an empty default, such as a selector, takes any
                found += unknown(value, known[key], f"{at}{key}.")
        return found

    given = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert unknown(given, chart, "") == []
    assert {"image", "people", "anchor", "networkPolicies", "ingress"} <= set(given)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_each_example_renders_and_gives_the_core_its_sign_in(example):
    docs = rendered(f"examples/{example.name}")
    issuer = yaml.safe_load(example.read_text(encoding="utf-8"))["people"]["oidcIssuer"]
    core = {env["name"]: env.get("value") for doc in docs if doc["metadata"]["name"] == "a5s-gateway"
            for container in containers(doc) for env in container.get("env") or []}
    assert core["A5S_OIDC_ISSUER"] == issuer


# Each agent's app in Teams and in Slack

def test_the_slack_manifest_sends_events_and_buttons_where_the_channels_take_them(approving):
    apps = script("chat-apps")
    manifest = yaml.safe_load(apps.slack("assistant", "a5s.example.org", "Assistant", "Helps."))
    served = described(approving)
    for url in (manifest["settings"]["event_subscriptions"]["request_url"],
                manifest["settings"]["interactivity"]["request_url"]):
        assert url.startswith("https://a5s.example.org/") and url[len("https://a5s.example.org"):] in served
    assert apps.TEAMS_ENDPOINT in served
    settings = manifest["settings"]
    assert settings["socket_mode_enabled"] is False and settings["token_rotation_enabled"] is False
    readme = (ROOT / "README.md").read_text(encoding="utf-8")  # as the README says Slack needs
    assert all(f"`{scope}`" in readme for scope in manifest["oauth_config"]["scopes"]["bot"])
    assert all(f"`{event}`" in readme for event in settings["event_subscriptions"]["bot_events"])


def test_the_teams_package_holds_its_manifest_and_icons(tmp_path):
    out = tmp_path / "assistant.zip"
    app_id = "00000000-0000-0000-0000-000000000001"
    made = subprocess.run([sys.executable, "-I", str(DEPLOY / "chat-apps.py"), "teams",
                           "--agent", "assistant", "--app-id", app_id, "--host",
                           "https://a5s.example.org/", "--developer", "Example Ltd", "--out",
                           str(out)], capture_output=True, text=True, timeout=60, check=False)
    assert made.returncode == 0, made.stderr
    assert "https://a5s.example.org/channels/teams/messages" in made.stdout
    with zipfile.ZipFile(out) as package:
        assert sorted(package.namelist()) == ["color.png", "manifest.json", "outline.png"]
        manifest = json.loads(package.read("manifest.json"))
        sizes = {name: struct.unpack(">II", package.read(name)[16:24])
                 for name in ("color.png", "outline.png")}
    assert sizes == {"color.png": (192, 192), "outline.png": (32, 32)}  # as Teams asks
    [bot] = manifest["bots"]
    assert manifest["id"] == bot["botId"] == app_id
    assert bot["scopes"] == ["personal", "groupChat"]  # never a team's, which a5s turns away
    assert bot["supportsFiles"] is True  # so people can send it files one to one
    assert manifest["validDomains"] == ["a5s.example.org"]


# Once it's installed: whom the release needs

def test_release_status_names_whom_the_directory_gives_each_role(deployed, tmp_path, monkeypatch,  # noqa: F811
                                                                 capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("A5S_ROOT", str(deployed.cfg.root))
    monkeypatch.setenv("A5S_DATABASE_URL", deployed.admin)
    with pytest.raises(SystemExit):
        cli.main(["release", "status"])
    said = capsys.readouterr().out
    assert ("- It needs the release approver, from outside the team that runs a5s, because "
            "the trusted core changed: Rosa Mendes (rosa).") in said, said
    assert ("- It needs an engineer from the team that runs a5s, because the services changed: "
            "Priya Nair (priya), Tomas Berg (tomas).") in said
    assert "because the trusted core changed: Kofi Mensah (kofi)." in said  # assurance
    assert "a5s release sign --as <them> --key <their key>" in said
