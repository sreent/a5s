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

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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


# A new skill's SKILL.md: its name and what it's for, as Agent Skills begins one, what it's for
# quoted, so YAML reads it as written, colons and all, and where its steps go
SKILL_START = """---
name: {name}
description: {about}
---

# {title}

How to do this kind of work, step by step, naming the tools it uses.
"""


def new_skill(agent: Path, name: str, about: str) -> Path:
    """A new skill's folder in an agent's, with its SKILL.md, for its author to write its steps
    in (docs/manual/skills.md): refused if a5s wouldn't load it, or the agent has one so named."""
    if not (agent / "agent.yaml").is_file():
        raise ValueError(f"{agent} isn't an agent's folder: it has no agent.yaml")
    if not definitions.SKILL_NAME.fullmatch(name) or len(name) > 64:
        raise ValueError(f"name {name[:64]!r} as Agent Skills names a skill: in lower-case letters "
                         "and digits, with single hyphens between, 64 characters at most")
    about = " ".join(about.split())
    if not about or len(about) > 1024:
        raise ValueError("say what the skill is for, and when it's needed, in 1,024 characters at most")
    folder = agent / "skills" / name
    if folder.exists():
        raise ValueError(f"{agent.name} has a skill {name} already")
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(SKILL_START.format(
        name=name, about=json.dumps(about, ensure_ascii=False),
        title=name[0].upper() + name[1:].replace("-", " ")), encoding="utf-8")
    return folder


LICENCES = {"LICENSE", "LICENCE", "COPYING", "NOTICE"}  # a skill's terms, kept as .txt


@dataclass(frozen=True)
class Added:
    """A skill brought in from elsewhere: where it is now, what of it a5s left out, and where it
    came from, if a git checkout says."""
    folder: Path
    left_out: list[str]
    source: str | None = None
    commit: str | None = None


def add_skill(agent: Path, source: Path) -> Added:
    """A skill published elsewhere, brought into an agent's folder as its text alone
    (docs/manual/skills.md): its SKILL.md and each file beside it a run can read, never a
    script, a link or anything else, which it names as left out; and, where the folder is in a
    git checkout, the repository and commit it came from, in its SKILL.md's metadata, without
    anyone's credentials, so its release's signers can compare it with what was published.
    Nothing it brings is trusted: it's checked as a5s loads a skill, and read by its signers."""
    if not (agent / "agent.yaml").is_file():
        raise ValueError(f"{agent} isn't an agent's folder: it has no agent.yaml")
    told = source / "SKILL.md"
    if not told.is_file() or told.is_symlink():
        raise ValueError(f"{source} has no SKILL.md: a skill is a folder with one")
    name = source.resolve().name
    text = told.read_text(encoding="utf-8")
    meta, body = definitions.front_matter(text)
    if meta is None or meta.get("name") != name:
        raise ValueError(f"its SKILL.md must begin with front matter naming it {name}, as its "
                         "folder is named")
    target = agent / "skills" / name
    if target.exists():
        raise ValueError(f"{agent.name} has a skill {name} already")
    kept: dict[str, str] = {}
    left_out: list[str] = []
    for path in sorted(p for p in source.rglob("*") if p.is_file() or p.is_symlink()):
        inside = path.relative_to(source).as_posix()
        if any(part.startswith(".") for part in path.relative_to(source).parts):
            continue  # git's own, and the like: no part of the skill
        licence = not path.suffix and path.name.upper() in LICENCES  # kept, as text a run reads
        if path.is_symlink() or not (licence or path.suffix.lower() in definitions.SKILL_FILES):
            left_out.append(inside)
            continue
        try:
            kept[inside + (".txt" if licence else "")] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            left_out.append(inside)
    where, commit = _published(source)
    if where and commit:
        said = dict(meta.get("metadata") or {}) if isinstance(meta.get("metadata"), dict) else {}
        meta["metadata"] = {**{k: str(v) for k, v in said.items()}, "source": where, "commit": commit}
        kept["SKILL.md"] = ("---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
                            + "---\n\n" + body.lstrip("\n"))
    for inside, said in kept.items():
        (target / inside).parent.mkdir(parents=True, exist_ok=True)
        (target / inside).write_text(said, encoding="utf-8")
    try:
        definitions.skills_of(agent / "skills")  # as a5s will load it
    except ValueError:
        shutil.rmtree(target)
        raise
    return Added(target, left_out, where, commit)


def _published(source: Path) -> tuple[str | None, str | None]:
    """Where a skill's folder was published, if it's in a git checkout: its remote, without
    anyone's credentials, and the folder's path in it, and the commit checked out. Git runs no
    command the checkout's own settings name."""
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(source), *args],
                                  capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() or None if done.returncode == 0 else None
    commit, remote = git("rev-parse", "HEAD"), git("config", "--get", "remote.origin.url")
    if not commit or not remote:
        return None, None
    parts = urlsplit(remote)
    if parts.scheme and parts.hostname:  # https://someone:token@host/... names no one here
        remote = urlunsplit((parts.scheme, parts.hostname + (f":{parts.port}" if parts.port else ""),
                             parts.path, "", ""))
    inside = git("rev-parse", "--show-prefix") or ""
    return remote + (f" {inside.rstrip('/')}" if inside else ""), commit


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
