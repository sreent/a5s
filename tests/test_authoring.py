"""Making agents, studio step 2's first piece (docs/studio.md): a new agent's folder from a
template, with its own id, a first release and its tools pinned; and the checks that say what
stops an agent's folder from being released here, which the command line runs, as the studio
will as people type."""

from __future__ import annotations

import re
import shutil

import pytest
import yaml

from a5s import authoring, cli, definitions
from a5s.config import load_models
from a5s.sample import SampleScenario
from conftest import ROOT

TOOLS = SampleScenario(ROOT / "scenarios" / "sample", "postgresql://nobody@127.0.0.1:1/none").tools()
MODELS = load_models(ROOT / "config" / "models.yaml")
ASSISTANT = ROOT / "agents" / "assistant"


def made(tmp_path, name: str = "finance-helper"):
    return authoring.new(ASSISTANT, name, tmp_path, TOOLS)


def test_templates_are_the_reference_agents_and_each_scenarios_own():
    found = authoring.templates(ROOT)
    assert {"assistant", "watcher", "master-data/mdg-assistant", "service-desk/desk-assistant",
            "software-delivery/dev-assistant"} <= set(found)
    assert authoring.lacks(found["assistant"], TOOLS) == []
    assert "check_quality" in authoring.lacks(found["master-data/mdg-watcher"], TOOLS)


def test_a_new_agent_is_its_templates_copy_with_its_own_id_release_and_pins(tmp_path):
    folder = made(tmp_path)
    assert folder == tmp_path / "finance-helper"
    theirs, ours = (ASSISTANT / "agent.yaml").read_text(), (folder / "agent.yaml").read_text()
    assert ours.splitlines()[:2] == ["id: finance-helper", "release: 0.1.0"]
    assert ours.splitlines()[2:] == theirs.splitlines()[2:]  # the rest as it was, comments too
    assert (folder / "AGENTS.md").read_text() == (ASSISTANT / "AGENTS.md").read_text()
    assert sorted(p.name for p in (folder / "tests").iterdir()) == sorted(
        p.name for p in (ASSISTANT / "tests").iterdir())  # its test cases, to start from
    found = definitions.load(folder)
    assert (found.id, found.release) == ("finance-helper", "0.1.0")
    assert found.pins == {t: TOOLS[t].schema_hash for t in found.tool_names}
    assert authoring.check(folder, TOOLS, MODELS) == []


@pytest.mark.parametrize("name", ["Finance", "-helper", "finance--helper", "helper-", "9lives",
                                  "a" * 41, "finance helper", "../escape"])
def test_a_new_agent_needs_a_plain_name(tmp_path, name):
    with pytest.raises(ValueError, match="lower case letters"):
        made(tmp_path, name)
    assert list(tmp_path.iterdir()) == []


def test_a_new_agent_needs_a_free_folder_and_a_template_this_scenario_can_run(tmp_path):
    made(tmp_path)
    with pytest.raises(ValueError, match="is there already"):
        made(tmp_path)
    with pytest.raises(ValueError, match="uses tools this scenario hasn't got: .*check_quality"):
        authoring.new(authoring.templates(ROOT)["master-data/mdg-watcher"], "quality", tmp_path, TOOLS)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["finance-helper"]  # nothing left behind


def changed(folder, field: str, value: str) -> None:
    spec = folder / "agent.yaml"
    spec.write_text(re.sub(rf"(?m)^{field}:.*$", f"{field}: {value}", spec.read_text(), count=1))


def test_the_checks_say_what_stops_a_release(tmp_path):
    folder = made(tmp_path)
    changed(folder, "id", "someone-else")
    assert authoring.check(folder, TOOLS, MODELS) == [
        "its id, someone-else, isn't its folder's name, finance-helper"]
    changed(folder, "id", "finance-helper")
    changed(folder, "model", "a-model-nobody-approved")
    assert authoring.check(folder, TOOLS, MODELS) == [
        "its model, a-model-nobody-approved, isn't one config/models.yaml approves"]
    changed(folder, "model", "deepseek-v4-pro")
    lock = folder / "tools.lock"
    pins = yaml.safe_load(lock.read_text())
    lock.write_text(yaml.safe_dump({**pins, "get_record": "0" * 64, "close_enough": "1" * 64}))
    again = "pin its tools again, with `a5s pin finance-helper`"
    assert authoring.check(folder, TOOLS, MODELS) == [
        f"get_record isn't pinned as the scenario has it now: {again}",
        f"its tools.lock pins close_enough, which it doesn't use: {again}"]
    definitions.pin(folder, {n: t.schema_hash for n, t in TOOLS.items()})
    assert authoring.check(folder, TOOLS, MODELS) == []
    spec = folder / "agent.yaml"
    spec.write_text(spec.read_text().replace("documents: [create_draft]", "documents: [shred_it]"))
    problems = authoring.check(folder, TOOLS, MODELS)
    assert "the scenario hasn't got shred_it" in problems


def test_the_checks_say_why_a_definition_doesnt_load(tmp_path):
    folder = made(tmp_path)
    spec = folder / "agent.yaml"
    good = spec.read_text()
    spec.write_text(good.replace("  per_run: 200000", "  per_run: 1000"))
    [problem] = authoring.check(folder, TOOLS, MODELS)
    assert problem.startswith("budget.per_run must fit 6 model calls")
    spec.write_text(good + "colour: blue\n")
    assert authoring.check(folder, TOOLS, MODELS) == ["colour: Extra inputs are not permitted"]
    spec.write_text("id: [finance-helper\n")
    assert authoring.check(folder, TOOLS, MODELS)[0].startswith("its YAML doesn't read")
    spec.write_text(good)
    (folder / "AGENTS.md").unlink()
    assert authoring.check(folder, TOOLS, MODELS) == ["it has no AGENTS.md"]


def test_the_command_line_makes_and_checks_agents(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("A5S_ROOT", str(ROOT))
    monkeypatch.setenv("A5S_AGENTS_DIR", str(tmp_path))
    cli.main(["agent", "templates"])
    listed = capsys.readouterr().out
    assert "assistant: The people its instance is assigned to\n" in listed
    assert "master-data/mdg-watcher:" in listed and "this scenario hasn't got" in listed
    cli.main(["agent", "new", "finance-helper", "--from", "assistant"])
    assert "agent-owner:finance-helper" in capsys.readouterr().out
    cli.main(["agent", "check"])
    assert capsys.readouterr().out == "finance-helper: ready to release\n"
    changed(tmp_path / "finance-helper", "model", "nobody-approved")
    with pytest.raises(SystemExit) as stopped:
        cli.main(["agent", "check", str(tmp_path / "finance-helper")])
    assert stopped.value.code == 1
    assert capsys.readouterr().out.splitlines() == [
        "finance-helper: 1 to fix before its release",
        "- its model, nobody-approved, isn't one config/models.yaml approves"]
    for argv in (["agent", "new", "x-ray", "--from", "nowhere"],
                 ["agent", "new", "finance-helper", "--from", "assistant"]):
        with pytest.raises(SystemExit, match="no template nowhere|is there already"):
            cli.main(argv)
    shutil.rmtree(tmp_path / "finance-helper")
