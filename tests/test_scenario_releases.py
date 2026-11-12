"""Each scenario a5s ships can be deployed. The core runs only a release the deployment's
people approved, so a scenario's directory must name who its first release needs: the
release approver, from outside the team that runs a5s and its line of managers; assurance;
an engineer of that team; and each agent's owner. Their made-up keys sign it here, and the
core accepts it, as `a5s release sign` and `a5s release approve` would on a deployment. And
the image holds each scenario, without the private keys."""

from __future__ import annotations

import importlib

import pytest
import yaml

from a5s.contract import Signature
from a5s.core import releases, signing
from conftest import ROOT

# Each scenario, its adapter, and who signs its first release: the release approver,
# assurance, an engineer of the team that runs a5s, and the owner of its agents
SCENARIOS = {
    "sample": ("a5s.sample:SampleScenario", ("rosa", "kofi", "tomas", "priya")),
    "master-data": ("a5s.master_data:MasterDataScenario", ("rhea", "ken", "tao", "ines")),
    "software-delivery": ("a5s.software_delivery:SoftwareDeliveryScenario",
                          ("rue", "ash", "ugo", "pam")),
    "service-desk": ("a5s.service_desk:ServiceDeskScenario", ("ren", "zia", "max", "dev")),
}


def scenario(folder: str):
    module, name = SCENARIOS[folder][0].split(":")
    return getattr(importlib.import_module(module), name)(ROOT / "scenarios" / folder, None)


def first_release(folder: str) -> tuple[bytes, list[releases.Need]]:
    here = ROOT / "scenarios" / folder
    agents = here / "agents" if (here / "agents").is_dir() else ROOT / "agents"
    raw = releases.manifest(ROOT, here, agents_dir=agents)
    return raw, releases.needs(yaml.safe_load(raw), None)


def signed(folder: str, raw: bytes, *people: str) -> list[Signature]:
    keys = ROOT / "scenarios" / folder / "keys"
    return [Signature(p, signing.sign((keys / f"{p}.key").read_text().strip(), raw,
                                      signing.RELEASE)) for p in people]


def test_every_scenario_a5s_ships_is_here():
    shipped = {p.parent.name for p in (ROOT / "scenarios").glob("*/data.yaml")}
    assert shipped == set(SCENARIOS)


@pytest.mark.parametrize("folder", SCENARIOS)
def test_a_scenarios_own_people_approve_its_first_release(folder):
    raw, need = first_release(folder)
    found = scenario(folder)
    assert {n.role for n in need} >= {releases.RELEASE_APPROVER, releases.ASSURANCE,
                                      releases.ENGINEER}
    verdict = releases.judge(need, raw, signed(folder, raw, *SCENARIOS[folder][1]), found,
                             "platform")
    assert verdict.ok, verdict.missing


@pytest.mark.parametrize("folder", SCENARIOS)
def test_nobody_in_a_scenarios_team_that_runs_a5s_or_above_it_approves_its_releases(folder):
    raw, need = first_release(folder)
    found = scenario(folder)
    approver = SCENARIOS[folder][1][0]
    assert releases.RELEASE_APPROVER in found.person(approver).roles
    team = found.team("platform")
    line = {boss for member in team for boss in releases._line(found, member)}
    assert approver not in {p.id for p in team} | line
    others = [p for p in SCENARIOS[folder][1] if p != approver]
    without = releases.judge(need, raw, signed(folder, raw, *others), found, "platform")
    assert not without.ok and any("release approver" in m for m in without.missing)


@pytest.mark.parametrize("folder", SCENARIOS)
def test_each_keyed_person_has_the_pair_and_no_private_key_ships(folder):
    keys = ROOT / "scenarios" / folder / "keys"
    found = scenario(folder)
    for pub in keys.glob("*.pub"):
        person = found.person(pub.stem)
        assert person is not None and person.public_key == pub.read_text().strip()
        assert (keys / f"{pub.stem}.key").exists()
    raw, _ = first_release(folder)
    assert not [p for p in yaml.safe_load(raw)["parts"]["scenario"] if p.endswith(".key")]


def test_the_image_holds_every_scenario_and_no_private_key():
    copied = [line.split()[1] for line in (ROOT / "Dockerfile").read_text().splitlines()
              if line.startswith("COPY ") and "scenarios" in line]
    assert copied == ["scenarios"], copied  # each scenario, chosen with A5S_SCENARIO
    assert "**/*.key" in (ROOT / ".dockerignore").read_text().splitlines()
