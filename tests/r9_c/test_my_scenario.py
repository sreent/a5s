"""Round 9, reviewer C: a scratch helpdesk of my own (tests/r9_c/helpdesk_scenario.py), written
against the contract alone and plugged in as tests/test_master_data.py plugs in master data.

Its tickets are numbered in plain digits, as Zendesk's are, so its record_pattern is \\b\\d{6}\\b.
The contract says the pattern is for "its records' keys", which a5s finds in what people and
tools say. The studio also runs it over a5s's own JSON, each ledger entry's time included,
whose microseconds are six digits: so every run's page names "records" that don't exist, which
nobody may see, and the studio refuses every run's page to everyone, the part's own owner too."""

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
    from a5s.core import studio
    named = studio._named(help_desk.gateway.scenario, run["trigger"], help_desk.ledger(run["run"]))
    print(page.status_code, page.text[:120], sorted(named))
    assert named - {"104233"} and not any(help_desk.gateway.scenario.sees("olu", k)
                                          for k in named - {"104233"})  # tickets that aren't
    # FAILS: 404 "there's no such run that you may see", since the ledger's times hold six
    # digits, which the studio takes for tickets that don't exist
    assert page.status_code == 200, page.text


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
