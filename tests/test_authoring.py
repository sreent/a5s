"""Making agents, studio step 2's first piece (docs/studio.md): a new agent's folder from a
template, with its own id, a first release and its tools pinned; and the checks that say what
stops an agent's folder from being released here, which the command line runs, as the studio
will as people type."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

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


def test_a_blank_start_fits_every_scenario_and_runs_on_the_deployments_own_model(tmp_path):
    found = authoring.templates(ROOT)
    assert next(iter(found)) == authoring.BLANK  # offered first
    assert authoring.lacks(found[authoring.BLANK], {}) == []  # it needs no tool of anyone's
    model = next(iter(MODELS))
    folder = authoring.new(found[authoring.BLANK], "desk-helper", tmp_path, TOOLS, model=model)
    blank = definitions.load(folder)
    assert (blank.id, blank.model, blank.tool_names) == ("desk-helper", model, [])
    assert (blank.autonomy.start, blank.autonomy.max) == (0, 0)  # it only observes, till changed
    assert authoring.check(folder, TOOLS, MODELS) == []


def test_a_new_agent_is_its_templates_copy_with_its_own_id_release_and_pins(tmp_path):
    folder = made(tmp_path)
    assert folder == tmp_path / "finance-helper"
    theirs, ours = (ASSISTANT / "agent.yaml").read_text(encoding="utf-8"), (folder / "agent.yaml").read_text(encoding="utf-8")
    assert ours.splitlines()[:2] == ["id: finance-helper", "release: 0.1.0"]
    assert ours.splitlines()[2:] == theirs.splitlines()[2:]  # the rest as it was, comments too
    assert (folder / "AGENTS.md").read_text(encoding="utf-8") == (ASSISTANT / "AGENTS.md").read_text(encoding="utf-8")
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
    spec.write_text(re.sub(rf"(?m)^{field}:.*$", f"{field}: {value}", spec.read_text(encoding="utf-8"), count=1))


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
    pins = yaml.safe_load(lock.read_text(encoding="utf-8"))
    lock.write_text(yaml.safe_dump({**pins, "get_record": "0" * 64, "close_enough": "1" * 64}), encoding="utf-8")
    again = "pin its tools again, with `a5s pin finance-helper`"
    assert authoring.check(folder, TOOLS, MODELS) == [
        f"get_record isn't pinned as the scenario has it now: {again}",
        f"its tools.lock pins close_enough, which it doesn't use: {again}"]
    definitions.pin(folder, {n: t.schema_hash for n, t in TOOLS.items()})
    assert authoring.check(folder, TOOLS, MODELS) == []
    spec = folder / "agent.yaml"
    spec.write_text(spec.read_text(encoding="utf-8").replace("documents: [create_draft]", "documents: [shred_it]"))
    problems = authoring.check(folder, TOOLS, MODELS)
    assert "the scenario hasn't got shred_it" in problems


def test_the_checks_say_why_a_definition_doesnt_load(tmp_path):
    folder = made(tmp_path)
    spec = folder / "agent.yaml"
    good = spec.read_text(encoding="utf-8")
    spec.write_text(good.replace("  per_run: 200000", "  per_run: 1000"), encoding="utf-8")
    [problem] = authoring.check(folder, TOOLS, MODELS)
    assert problem.startswith("budget.per_run must fit 6 model calls")
    spec.write_text(good + "colour: blue\n", encoding="utf-8")
    assert authoring.check(folder, TOOLS, MODELS) == ["colour: Extra inputs are not permitted"]
    spec.write_text("id: [finance-helper\n", encoding="utf-8")
    assert authoring.check(folder, TOOLS, MODELS)[0].startswith("its YAML doesn't read")
    spec.write_text(good, encoding="utf-8")
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


# Skills: a new one, and one published elsewhere, brought in as its text alone (docs/manual/skills.md)

ABOUT = "How to answer a question about a refund: when it's paid, step by step."
PUBLISHED = """---
name: refunds
description: How to answer a question about a refund, step by step.
license: MIT
---

# Refunds

Check the refund's record first, then say when it's paid, as `reference.md` and `scripts/paid_by.py` say.
"""


def published(where: Path, remote: str | None = None) -> Path:
    """A skill as another organisation publishes it, with a script, a picture and a licence, in
    a git checkout of theirs if it has a `remote`."""
    skill = where / "skills" / "refunds"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(PUBLISHED, encoding="utf-8")
    (skill / "reference.md").write_text("# When refunds are paid\n", encoding="utf-8")
    (skill / "scripts" / "paid_by.py").write_text("print('2026-11-11')\n", encoding="utf-8")
    (skill / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (skill / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    if remote:
        for argv in (["init", "-q"], ["add", "."], ["-c", "user.name=Them", "-c", "user.email=them@example.com",
                                                    "commit", "-q", "-m", "Refunds"],
                     ["remote", "add", "origin", remote]):
            subprocess.run(["git", "-C", str(where), *argv], check=True, capture_output=True)
    return skill


def test_a_new_skill_is_a_folder_a5s_loads_saying_what_its_for(tmp_path):
    folder = made(tmp_path)
    authoring.new_skill(folder, "refunds", ABOUT)
    loaded = definitions.skills_of(folder / "skills")
    meta, body = definitions.front_matter(loaded["/skills/refunds/SKILL.md"])
    assert meta == {"name": "refunds", "description": ABOUT}  # its colon read as written
    assert body.startswith("# Refunds\n")
    for name, about, says in [("Refunds", ABOUT, "as Agent Skills names a skill"),
                              ("refunds", ABOUT, "has a skill refunds already"),
                              ("payments", " \n ", "say what the skill is for"),
                              ("payments", "x" * 1025, "1,024 characters at most")]:
        with pytest.raises(ValueError, match=says):
            authoring.new_skill(folder, name, about)
    with pytest.raises(ValueError, match="isn't an agent's folder"):
        authoring.new_skill(tmp_path, "payments", ABOUT)


def test_a_skill_from_elsewhere_comes_in_as_its_text_alone_saying_where_from(tmp_path):
    skill = published(tmp_path / "theirs", "https://someone:not-a-real-token@example.com/org/skills.git")
    folder = made(tmp_path / "ours")
    added = authoring.add_skill(folder, skill)
    assert added.left_out == ["logo.png", "scripts/paid_by.py"]  # nothing a run can't read
    assert added.source == "https://example.com/org/skills.git skills/refunds"  # nobody's credentials
    assert added.commit and len(added.commit) == 40
    loaded = definitions.skills_of(folder / "skills")
    assert set(loaded) == {"/skills/refunds/SKILL.md", "/skills/refunds/reference.md",
                           "/skills/refunds/LICENSE.txt"}  # its terms, kept as text
    meta, body = definitions.front_matter(loaded["/skills/refunds/SKILL.md"])
    assert meta and meta["license"] == "MIT" and meta["metadata"] == {"source": added.source,
                                                                     "commit": added.commit}
    assert body == PUBLISHED.split("---\n", 2)[2].lstrip("\n")  # what it says, as it says it
    assert "\n---\n\n# Refunds\n" in loaded["/skills/refunds/SKILL.md"]  # a line between, as it had
    assert "someone" not in str(loaded) and "not-a-real-token" not in str(loaded)
    with pytest.raises(ValueError, match="has a skill refunds already"):
        authoring.add_skill(folder, skill)


def test_a_skill_from_elsewhere_must_be_one_a5s_loads(tmp_path):
    folder = made(tmp_path / "ours")
    skill = published(tmp_path / "theirs")
    assert authoring.add_skill(folder, skill).source is None  # no checkout to say where from
    for text, says in [("# Refunds\n", "front matter naming it refunds"),
                       (PUBLISHED.replace("name: refunds", "name: payments"), "naming it refunds")]:
        other = published(tmp_path / f"theirs-{len(text)}")
        (other / "SKILL.md").write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=says):
            authoring.add_skill(made(tmp_path / f"ours-{len(text)}"), other)
    long = published(tmp_path / "theirs-long")
    (long / "SKILL.md").write_text(PUBLISHED.replace("step by step.", "x" * 1100), encoding="utf-8")
    target = made(tmp_path / "ours-long")
    with pytest.raises(ValueError, match="1,024 characters"):
        authoring.add_skill(target, long)
    assert not (target / "skills" / "refunds").exists()  # nothing left half brought in


def test_the_command_line_gives_an_agent_a_skill(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("A5S_ROOT", str(ROOT))
    monkeypatch.setenv("A5S_AGENTS_DIR", str(tmp_path / "agents"))
    made(tmp_path / "agents")
    cli.main(["skill", "new", "finance-helper", "refunds", "--about", ABOUT])
    said = capsys.readouterr().out
    assert "skills/refunds/SKILL.md" in said and "its owner and an engineer sign it" in said
    with pytest.raises(SystemExit, match="has a skill refunds already"):
        cli.main(["skill", "new", "finance-helper", "refunds", "--about", ABOUT])
    other = published(tmp_path / "theirs")
    (other.parent / "chargebacks").mkdir()
    (other.parent / "chargebacks" / "SKILL.md").write_text(
        PUBLISHED.replace("name: refunds", "name: chargebacks"), encoding="utf-8")
    cli.main(["skill", "add", "finance-helper", str(other.parent / "chargebacks")])
    said = capsys.readouterr().out
    assert "Say in its pull request where it came from" in said
    cli.main(["agent", "check"])
    assert capsys.readouterr().out == "finance-helper: ready to release\n"
