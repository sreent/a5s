"""What an agent may do in a part, by name: it reads only, it asks first, or it acts on its own.
Settings and agent definitions take the names, and the numbers as before; every file a5s ships,
everything its code and policies say, and the studio's words name them, never a number; and the pilot's assistant, as it ships, asks first at most, whatever the settings
give it."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from a5s import levels
from a5s.contract import SettingsError, parse_settings
from a5s.core import publishing, registry, words
from a5s.definitions import Autonomy, load

ROOT = Path(__file__).resolve().parents[1]
# a level by its number, as people no longer read it: "level 2", "Level {level}", "level-1-"
NUMBERED = re.compile(r"\blevels?[\s_-]*(?:[0-2](?!\d)|\{)", re.IGNORECASE)


def version(level: object = "asks first", part: object = None, action: object = None) -> bytes:
    """The sample's assistant in billing, at `level`, and in billing at `part`, with
    change-due-date at `action`, as YAML says them."""
    entry: dict = {}
    if part is not None:
        entry["level"] = part
    if action is not None:
        entry["actions"] = {"change-due-date": action}
    return yaml.safe_dump({"serial": 1, "data_class": "synthetic", "instances": {
        "assistant-finance": {"definition": "assistant", "serves": ["ana"], "owner": "ana",
                              "level": level, "parts": {"billing": entry or None}}}}).encode()


@pytest.mark.parametrize(("said", "level"), [
    ("reads only", 0), ("asks first", 1), ("acts on its own", 2), ("Asks First", 1),
    ("acts-on-its-own", 2), ("reads_only", 0), ("  asks   first ", 1), (0, 0), (1, 1), (2, 2)])
def test_settings_take_a_level_by_name_or_as_before_by_number(said, level):
    [inst] = parse_settings(version(said, part=said, action=said)).instances
    assert (inst.level, inst.parts, inst.actions) == (
        level, {"billing": level}, {"billing": {"change-due-date": level}})


@pytest.mark.parametrize("said", ["level 2", "two", "acts alone", "1", "", 3, -1, 1.5, True])
def test_a_level_by_any_other_name_or_number_is_refused(said):
    for given in (version(said), version(part=said), version(action=said)):
        with pytest.raises(SettingsError) as refused:
            parse_settings(given)
        if isinstance(said, str):  # what it may be, by name
            assert "a level is reads only, asks first or acts on its own" in str(refused.value)


def test_agent_definitions_take_their_levels_by_name_or_as_before_by_number():
    named = Autonomy.model_validate({"start": "reads only", "max": "acts on its own"})
    assert (named.start, named.max) == (levels.READS_ONLY, levels.ACTS)
    assert Autonomy.model_validate({"start": 1, "max": 2}).max == levels.ACTS
    assert Autonomy().start == Autonomy().max == levels.ASKS_FIRST  # unless it says otherwise
    with pytest.raises(ValueError, match="acting on its own only ever comes from the settings"):
        Autonomy.model_validate({"start": "acts on its own", "max": "acts on its own"})
    with pytest.raises(ValueError, match="a level is reads only, asks first or acts on its own"):
        Autonomy.model_validate({"start": "asks first", "max": "level 2"})


def shipped() -> list[Path]:
    """Every agent definition and version of the settings a5s ships, and its tests' own."""
    return sorted([*ROOT.glob("agents/*/agent.yaml"), *ROOT.glob("scenarios/*/agents/*/agent.yaml"),
                   *ROOT.glob("src/a5s/templates/*/agent.yaml"), *ROOT.glob("scenarios/*/settings.yaml"),
                   *ROOT.glob("tests/helpdesk/agents/*/agent.yaml"), ROOT / "tests/helpdesk/settings.yaml"])


def test_every_file_a5s_ships_names_each_level():
    files = shipped()
    assert len(files) >= 12
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:level|start|max):\s*\d", text, re.MULTILINE), path
        assert not re.search(r"actions:\s*\{[^}]*:\s*\d", text), path  # nor a type of change's
        assert not NUMBERED.search(text), path  # nor what its comments say
    for path in ROOT.glob("scenarios/*/settings.yaml"):  # and each still reads as a5s reads it
        parse_settings(path.read_bytes())
    for path in [p for p in files if p.name == "agent.yaml"]:
        load(path.parent)
    # what each agent reads, which it may say again: its instructions, skills and knowledge; and
    # what an administrator reads of each scenario, beside its settings
    told = [p for pattern in ("agents/**/*.md", "scenarios/*/agents/**/*.md",
                              "src/a5s/templates/**/*.md", "scenarios/*/knowledge/**/*.md",
                              "scenarios/*/README.md", "scenarios/*/mcp.yaml", "scenarios/*.md")
            for p in ROOT.glob(pattern)]
    assert len(told) >= 10 and not [p for p in told if NUMBERED.search(p.read_text(encoding="utf-8"))]


def test_the_pilots_assistant_asks_first_at_most_whatever_the_settings_give_it():
    assistant = load(ROOT / "agents" / "assistant")
    assert (assistant.autonomy.start, assistant.autonomy.max) == (levels.ASKS_FIRST,
                                                                  levels.ASKS_FIRST)
    [inst] = parse_settings(version("asks first", part="asks first",
                                    action="acts on its own")).instances
    assert registry.levels(inst, assistant) == (levels.ASKS_FIRST, {"billing": levels.ASKS_FIRST})
    assert registry.action_levels(inst, assistant) == {
        "billing": {"change-due-date": levels.ASKS_FIRST}}  # it asks first all the same


@pytest.mark.parametrize(("most", "told"), [
    ("acts on its own", "- It may act on its own, making a type of change itself"),
    (2, "- It may act on its own, making a type of change itself"),
    ("asks first", "- It asks first: it drafts changes"), (1, "- It asks first: it drafts changes"),
    ("reads only", "- It reads only: it observes and reports")])
def test_a_drafts_pull_request_reads_how_far_it_may_act_by_name_or_number(most, told):
    lines = publishing.may_do({"agent.yaml": yaml.safe_dump(
        {"autonomy": {"start": "reads only", "max": most}})})
    assert told in "\n".join(lines), lines


def said(tree: ast.AST) -> list[tuple[int, str]]:
    """Every string the code holds that it could say to someone: docstrings aside, and each
    f-string with a {} where what it says is put in."""
    docs = {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found.append((node.lineno, "".join(
                v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            found.append((node.lineno, node.value))
    return found


def test_what_a5s_says_names_each_level_never_its_number():
    code = [*(ROOT / "src" / "a5s").rglob("*.py"), *ROOT.glob("scenarios/**/*.py")]
    numbered = [f"{path.relative_to(ROOT)}:{line}: {text}" for path in code
                for line, text in said(ast.parse(path.read_text(encoding="utf-8"))) if NUMBERED.search(text)]
    assert numbered == []
    assert [words.level("en", n) for n in (0, 1, 2, None)] == [
        "reads only", "asks first", "acts on its own", "none"]


def test_the_policies_reasons_and_names_never_number_a_level():
    packs = [*(ROOT / "src" / "a5s" / "core" / "policies").glob("*.cedar"),
             *ROOT.glob("scenarios/*/*.cedar")]
    assert len(packs) >= 2
    for pack in packs:  # the agent and people read each reason, and the pages show each name
        for annotation in re.findall(r'@(?:id|reason)\("([^"]*)"\)', pack.read_text(encoding="utf-8")):
            assert not NUMBERED.search(annotation), (pack.name, annotation)


def test_the_studio_names_each_level():
    source = list((ROOT / "studio" / "src").rglob("*.ts*"))
    keys = {key for path in source
            for key in re.findall(r'\bt\(\s*"((?:[^"\\]|\\.)*)"', path.read_text(encoding="utf-8"))}
    assert keys and not [k for k in keys if NUMBERED.search(k)]
