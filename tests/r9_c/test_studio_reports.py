"""Round 9, reviewer C: the studio shows a watcher "the runs whose every record they may see"
(docs/data-protection.md, docs/studio.md). It counts the records a run read with its tools and
those its trigger and ledger entries name, but not the records a5s itself gave the run: a
report's facts, worked out by code from the person's records. So every report run reaches
every watcher of the instance, by name and time, whatever records it told of."""

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
        for_pia = [r for r in page["runs"] if [p["id"] for p in r["acts_for"]] == ["pia"]]
        assert for_pia, page  # the report run exists, and Una sees it
        run = api(url, provider, f"/studio/api/runs/{for_pia[0]['run']}", "una").json()
    told = [e for e in mdg.ledger(for_pia[0]["run"]) if e.get("kind") == "run"]
    print(run["records"], run["started_by"], told[0]["args"])
    # FAILS: Una, who owns supplier general data, sees Pia's report run, by name, and when it
    # ran, though it told of Pia's bank data's quality, which she may not see: the records
    # a5s gives a run in its task count for nothing in the studio's check.
    assert for_pia == [], "Una sees a report run about records she may not see"


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
