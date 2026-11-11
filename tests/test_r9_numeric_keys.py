"""Round 9 of the critique: a scenario whose keys are plain digits, as a help desk's tickets
are (tests/helpdesk_scenario.py, written against the contract alone). The studio hides a run
by the keys it handled, which a5s keeps with the run, never by a pattern run over a5s's own
JSON, whose times and ids hold digits too (docs/critique.md, round 9)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from a5s.core import signing
from conftest import FAKE_MODELS, FakeModel, Stack, build_root, deciding, signed
from scenario_stack import running_scenario

HERE = Path(__file__).parent / "helpdesk"


@pytest.fixture
def help_desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    folder = tmp_path / "helpdesk"
    shutil.copytree(HERE, folder)
    (folder / "keys").mkdir()
    for who in ("ida", "olu"):
        private, public = signing.keypair()
        (folder / "keys" / f"{who}.key").write_text(private + "\n")
        (folder / "keys" / f"{who}.pub").write_text(public + "\n")
    signed(folder, yaml.safe_load((folder / "settings.yaml").read_text()), ("olu", "ida"))
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, "helpdesk_scenario:HelpdeskScenario",
                          str(folder), httpx.Client(transport=httpx.MockTransport(model.handler))
                          ) as found:
        yield found


def test_the_parts_owner_opens_a_run_on_a_ticket_she_may_see(help_desk, provider):
    help_desk.model.reply(None, ("get_record", {"key": "104233"}))
    help_desk.model.reply("104233 is open: payroll has it.")
    assert "104233 is open" in help_desk.say("Where's 104233?", person="tim",
                                             agent="help-assistant")
    assert help_desk.gateway.scenario.sees("olu", "104233")  # payroll's own ticket
    with deciding(help_desk, provider) as url:
        def api(path: str) -> httpx.Response:
            return httpx.get(f"{url}{path}", timeout=30, headers={
                "Authorization": f"Bearer {provider.id_token(person='olu')}"})
        [run] = api("/studio/api/instances/help-payroll/runs").json()["runs"]  # on the list
        page = api(f"/studio/api/runs/{run['run']}")
    assert page.status_code == 200, page.text  # by the keys the run handled, not a pattern
    assert page.json()["records"] == ["104233"]  # over a5s's own times and ids

