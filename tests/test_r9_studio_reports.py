"""Round 9 of the critique: a report run counts the records a5s itself gave it, its facts
worked out by code from someone's records, so it shows only to those who may see them all
(docs/critique.md, round 9)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, FakeModel, Stack, build_root, deciding
from scenario_stack import running_scenario

SCENARIO = "a5s.master_data:MasterDataScenario"


@pytest.fixture
def mdg(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "master-data",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def api(url: str, provider, path: str, person: str) -> httpx.Response:
    return httpx.get(f"{url}{path}", timeout=30,
                     headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})


def test_a_report_run_shows_only_to_those_who_may_see_what_it_reported(mdg, provider):
    mdg.at("2026-11-04T09:30:00+00:00")  # each owner's morning report
    for _ in range(8):
        mdg.model.reply("Here's how your data stands this morning.")
    mdg.scheduler().work_due()
    scenario = mdg.gateway.scenario
    assert not scenario.sees("una", "DQ-supplier-bank")  # Pia's data object, not Una's
    assert not scenario.sees("una", "CR0000102")  # nor the bank change that waits on Pia
    with deciding(mdg, provider) as url:
        page = api(url, provider, "/studio/api/instances/mdg-quality/runs", "una").json()
    with mdg.client() as c:  # the team sees whom each acted for, and the records it handled
        every = c.get("/studio/instances/mdg-quality/runs").json()["runs"]
        shown = [c.get(f"/studio/runs/{r['run']}").json() for r in page["runs"]]
    pias = [r for r in every if [p["id"] for p in r["acts_for"]] == ["pia"]]
    assert pias and page["hidden"] >= len(pias)  # Pia's reports, among those hidden from Una
    assert all(scenario.sees("una", k) for found in shown for k in found["records"])
    assert not {r["run"] for r in pias} & {r["run"] for r in page["runs"]}
