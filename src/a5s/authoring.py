"""Making agents (docs/studio.md, step 2): a new agent's folder from a template, and the checks
a definition must pass before it's released, which the command line runs, as the studio will
as people type.

A template is an agent a5s ships: a blank one, which does nothing yet and so fits every scenario,
the reference agents, in agents/, and each scenario's own, in its agents/. A new agent starts as a copy of one: its definition, with its own id and a first
release of its own, its instructions, its skills and its test cases, and its tools pinned
against the scenario's, as `a5s pin` pins them. It's then a folder like any agent's, which its
owner edits, checks and releases as any agent is: nothing about it is the studio's.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml
from pydantic import ValidationError

from a5s import cases, definitions
from a5s.config import ModelConfig
from a5s.connectors import libraries
from a5s.contract import Tool

NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")  # such as finance-assistant
LONGEST = 40
FIRST = "0.1.0"  # a new agent's first release
LEFT_OUT = ("tools.lock", "__pycache__", "*.pyc")  # pinned again for the new agent; a build's leftovers


BLANK = "blank"  # a5s's own start for a new agent, which does nothing yet: in a5s's code


def templates(root: Path) -> dict[str, Path]:
    """Each agent a new one may start from, by name: a blank one, the reference agents, such as
    assistant, and each scenario's own, such as master-data/mdg-assistant."""
    found = {BLANK: Path(__file__).parent / "templates" / BLANK}
    found |= {f.name: f for f in _agents(root / "agents")}
    scenarios = root / "scenarios"
    for scenario in sorted(p for p in scenarios.iterdir() if p.is_dir()) if scenarios.is_dir() else []:
        found |= {f"{scenario.name}/{f.name}": f for f in _agents(scenario / "agents")}
    return found


def _agents(folder: Path) -> list[Path]:
    return sorted(f for f in folder.iterdir() if (f / "agent.yaml").is_file()) if folder.is_dir() else []


def lacks(template: Path, tools: dict[str, Tool]) -> list[str]:
    """The tools a template uses that the scenario hasn't got: none, if it fits."""
    return [t for t in definitions.load(template).tool_names if t not in tools]


def new(template: Path, name: str, into: Path, tools: dict[str, Tool], model: str | None = None) -> Path:
    """A new agent's folder, `into`/`name`, from a template's, with its tools pinned against the
    scenario's `tools`, and on `model`, if given, such as the deployment's own for the blank one,
    which names none. Nothing is left behind if it can't be made."""
    if name in definitions.RESERVED:
        raise ValueError(f"an agent can't be called {name}: in a conversation, that's who the "
                         "other words are by")
    if len(name) > LONGEST or not NAME.fullmatch(name):
        raise ValueError(f"name it in lower case letters and digits, with single hyphens between, "
                         f"starting with a letter, in {LONGEST} characters or fewer, such as "
                         "finance-assistant")
    target = into / name
    if target.exists():
        raise ValueError(f"{target} is there already")
    if missing := lacks(template, tools):
        raise ValueError(f"{template.name} uses tools this scenario hasn't got: {', '.join(missing)}. "
                         "Start from one of this scenario's agents instead")
    shutil.copytree(template, target, ignore=shutil.ignore_patterns(*LEFT_OUT))
    try:
        spec = target / "agent.yaml"
        text = spec.read_text(encoding="utf-8")
        for field, value in (("id", name), ("release", FIRST), *((("model", model),) if model else ())):
            text, found = re.subn(rf"(?m)^{field}:[ \t]*\S+", f"{field}: {value}", text, count=1)
            if not found:
                raise ValueError(f"{template.name}'s agent.yaml has no {field} to set")
        spec.write_text(text, encoding="utf-8")
        definitions.pin(target, {n: t.schema_hash for n, t in tools.items()})
    except BaseException:
        shutil.rmtree(target)
        raise
    return target


def check(folder: Path, tools: dict[str, Tool], models: dict[str, ModelConfig]) -> list[str]:
    """What stops a definition's folder from being released here, in words: none if nothing.
    That it loads, as the core loads it, with its skills and budgets that fit; that it's named
    as its folder is; that the scenario has each of its tools, pinned as they are now; and that
    its model is one the deployment approves."""
    try:
        found = definitions.load(folder)
    except FileNotFoundError as e:
        return [f"it has no {Path(str(e.filename)).name}"]
    except yaml.YAMLError as e:
        return [f"its YAML doesn't read: {str(e).splitlines()[0]}"]
    except ValidationError as e:
        return [_said(error) for error in e.errors()]
    except (TypeError, ValueError) as e:
        return [str(e)]
    problems = []
    if found.id != folder.name:
        problems.append(f"its id, {found.id}, isn't its folder's name, {folder.name}")
    if missing := [t for t in found.tool_names if t not in tools]:
        problems.append(f"the scenario hasn't got {', '.join(missing)}")
    if stale := [t for t in found.tool_names if t in tools and found.pins.get(t) != tools[t].schema_hash]:
        problems.append(f"{', '.join(stale)} {'isn' if len(stale) == 1 else 'aren'}'t pinned as "
                        f"the scenario has {'it' if len(stale) == 1 else 'them'} now: pin its tools "
                        f"again, with `a5s pin {folder.name}`")
    if unused := sorted(set(found.pins) - set(found.tool_names)):
        problems.append(f"its tools.lock pins {', '.join(unused)}, which it doesn't use: pin its "
                        f"tools again, with `a5s pin {folder.name}`")
    if not found.context.documents and (read := [t for t in found.tool_names if t in tools
                                                 and isinstance(tools[t], libraries.Shelved)
                                                 and tools[t].outside]):
        problems.append(f"{', '.join(read)} {'reads' if len(read) == 1 else 'read'} a library "
                        "through a5s's reader alone, which it asks with ask_about: give it "
                        "context.documents")
    if found.model not in models:
        problems.append(f"its model, {found.model}, isn't one config/models.yaml approves")
    if found.evaluation and found.evaluation.judge not in models:
        problems.append(f"its judge, {found.evaluation.judge}, isn't one config/models.yaml "
                        "approves")
    try:  # a case that can't be read as a5s runs it checks nothing, so it stops a release
        listed = cases.found({p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8")
                              for p in sorted((folder / "tests").glob("*.y*ml"))})
    except cases.Unreadable as e:
        problems.append(f"its test cases don't read as a5s runs them: {e}")
        listed = []
    except (OSError, UnicodeDecodeError):
        problems.append("its test cases can't be read as text")
        listed = []
    if not found.evaluation and any(step.get("judged") for case in listed for step in case["steps"]):
        problems.append("its test cases ask its judge whether an answer is right, and it names "
                        "no judge: give it one, under evaluation")
    return problems


def _said(error: dict) -> str:
    """One of pydantic's errors, by where in agent.yaml it is."""
    where = ".".join(str(part) for part in error.get("loc", ()))
    said = str(error.get("msg", "isn't right")).removeprefix("Value error, ")
    return f"{where}: {said}" if where else said
