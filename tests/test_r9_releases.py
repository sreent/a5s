"""Round 9: what a release covers. A scenario that brings its own agents is checked with them;
its agents' instructions and its knowledge vault, such as who may read each note, are in the
release; and the scenarios a5s ships, with their adapters, are the scenario's part, not the
trusted core (A2, A3, B9, C1)."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from a5s import build
from a5s.config import Config
from a5s.contract import ToolCall
from a5s.core import releases
from a5s.software_delivery import SoftwareDeliveryScenario
from conftest import ROOT


def deployment(tmp_path: Path) -> Config:
    """A copy of the repository's root, running the master data scenario with its own agents."""
    root = tmp_path / "root"
    for name in ("src", "config", "agents"):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "uv.lock", "Dockerfile"):
        if (ROOT / name).exists():
            shutil.copy(ROOT / name, root / name)
    folder = root / "scenarios" / "master-data"
    shutil.copytree(ROOT / "scenarios" / "master-data", folder)
    return Config(database_url="postgresql://nobody@127.0.0.1:1/none",
                  gateway_url="http://127.0.0.1:1", root=root, development=False,
                  scenario="a5s.master_data:MasterDataScenario", scenario_folder=folder,
                  agents_folder=folder / "agents", service_token="t")


def test_the_gateway_checks_the_release_people_sign(tmp_path):
    cfg = deployment(tmp_path)
    signed = releases.running(cfg.root, cfg.scenario_dir, cfg.agents_dir)  # `a5s release show`
    gateway = build.gateway(cfg)
    assert set(gateway.definitions) == {"mdg-assistant", "mdg-watcher"}  # what it runs
    checked = gateway.releases.current
    assert set(yaml.safe_load(checked.raw)["agents"]) == {"mdg-assistant", "mdg-watcher"}
    assert checked.digest == signed.digest


def test_a_change_to_an_agents_instructions_needs_its_owner(tmp_path):
    cfg = deployment(tmp_path)
    before = build.gateway(cfg).releases.current
    told = cfg.agents_dir / "mdg-assistant" / "AGENTS.md"
    told.write_text(told.read_text() + "\n- Tell people bank changes need no callback.\n")
    after = build.gateway(cfg)
    assert "need no callback" in after.definitions["mdg-assistant"].instructions  # it runs it
    assert after.releases.current.digest != before.digest
    needed = {n.role for n in releases.needs(yaml.safe_load(after.releases.current.raw),
                                             yaml.safe_load(before.raw))}
    assert needed == {"agent-owner:mdg-assistant", releases.ENGINEER}  # its owner and another


def test_a_change_to_the_handbook_needs_the_release_approver(tmp_path):
    cfg = deployment(tmp_path)
    before = yaml.safe_load(releases.running(cfg.root, cfg.scenario_dir, cfg.agents_dir).raw)
    policy = cfg.scenario_dir / "knowledge" / "supplier-bank" / "bank-change-policy.md"
    policy.write_text(policy.read_text().replace("Never use a number", "You may use a number"))
    after = yaml.safe_load(releases.running(cfg.root, cfg.scenario_dir, cfg.agents_dir).raw)
    assert after != before
    assert {n.role for n in releases.needs(after, before)} == {releases.RELEASE_APPROVER}


def read(scenario: SoftwareDeliveryScenario, who: str, note: str) -> dict:
    tool = scenario.tools()["read_knowledge"]
    return tool.run(ToolCall(args={"id": note}, instance="dev-team", run="r", acts_for=(who,)))


def test_widening_who_may_read_a_note_needs_a_release(tmp_path, database):
    folder = tmp_path / "software-delivery"
    shutil.copytree(ROOT / "scenarios" / "software-delivery", folder)
    note = folder / "knowledge" / "security" / "secrets-handling.md"
    scenario = SoftwareDeliveryScenario(folder, database)
    assert "error" in read(scenario, "raj", "security/secrets-handling.md")  # Sol's alone
    before = yaml.safe_load(releases.manifest(ROOT, folder, agents_dir=folder / "agents"))
    note.write_text(note.read_text().replace("people: [sol]", "parts: [backend]"))
    after = yaml.safe_load(releases.manifest(ROOT, folder, agents_dir=folder / "agents"))
    assert {n.role for n in releases.needs(after, before)} == {releases.RELEASE_APPROVER}


def test_the_scenarios_own_documents_and_settings_stay_out(tmp_path):
    folder = tmp_path / "sample"
    shutil.copytree(ROOT / "scenarios" / "sample", folder)
    before = releases.manifest(ROOT, folder)
    (folder / "README.md").write_text("Notes for whoever reads the folder.\n")
    assert releases.manifest(ROOT, folder) == before


@pytest.mark.parametrize("module", ["a5s/master_data.py", "a5s/software_delivery.py",
                                    "a5s/service_desk.py", "a5s/sample.py", "a5s/knowledge.py",
                                    "a5s/graphify.py"])
def test_a_scenarios_code_is_its_part_not_the_trusted_core(module):
    built = yaml.safe_load(releases.manifest(ROOT, ROOT / "scenarios" / "sample"))
    assert module not in built["parts"]["core"]
    before = copy.deepcopy(built)
    before["parts"]["scenario"][f"code/{module}"] = "0" * 64  # a one-line fix since
    assert {n.role for n in releases.needs(built, before)} == {releases.RELEASE_APPROVER}


def test_the_client_is_the_teams_like_the_services():
    built = yaml.safe_load(releases.manifest(ROOT, ROOT / "scenarios" / "sample"))
    before = copy.deepcopy(built)
    before["parts"]["services"]["a5s/client.py"] = "0" * 64
    assert {n.role for n in releases.needs(built, before)} == {releases.ENGINEER}
