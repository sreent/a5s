"""Drafts of agents, which the studio keeps for the people who author them (docs/studio.md,
step 2): an agent's folder, file by file, until its author publishes it as a pull request or
drops it. A draft is never in force. No run uses it, nothing about it is signed, and it gives
nobody a right: publishing makes the pull request, and the release the people it needs sign.

Who may author: for an agent, its owners and the people the organisation names its authors,
by the identity provider's groups (agent-owner:<agent> and agent-author:<agent>); for a new
agent, anyone who owns an agent, or an engineer of the team that runs a5s. A draft is its
author's alone. Its tools are pinned as the scenario has them each time it's saved, as `a5s
pin` pins them, and the checks `a5s agent check` makes say what would stop its release.
"""

from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import psycopg
import yaml
from psycopg.types.json import Jsonb

from a5s import authoring, definitions
from a5s.config import ModelConfig
from a5s.contract import Person, Tool
from a5s.core.releases import ENGINEER, agent_owner

MOST_FILES = 64  # in one draft's folder
MOST_BYTES = 192 * 1024  # of all its files' text together: under what the channels app
#                          reads of a body, escaped as JSON; the biggest agent a5s ships is 12 KB
MOST_DRAFTS = 20  # one person keeps at once [TBC]
TEXT = (".md", ".yaml", ".yml", ".txt", ".csv", ".json", ".lock")  # what an agent's folder holds
SHOWN = "id::text as id, agent, based_on, created_at, updated_at"


class Refused(ValueError):
    """Why a draft can't be kept as asked, in words."""


def agent_author(agent: str) -> str:
    return f"agent-author:{agent}"


def may_author(person: Person, agent: str | None) -> bool:
    """Whether someone may draft a change to `agent`, or, with None, a new agent."""
    if agent is not None:
        return bool({agent_owner(agent), agent_author(agent)} & set(person.roles))
    return ENGINEER in person.roles or any(r.startswith("agent-owner:") for r in person.roles)


def authors(person: Person) -> bool:
    """Whether someone may author anything at all."""
    return may_author(person, None) or any(r.startswith("agent-author:") for r in person.roles)


def folder_files(folder: Path) -> dict[str, str]:
    """An agent's folder as a draft keeps it: each of its files' text, by its path in it."""
    return {p.relative_to(folder).as_posix(): p.read_text() for p in sorted(folder.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def shape(files: Any) -> list[str]:
    """What stops some files from being an agent's folder at all: too many, too much, or a
    name a folder couldn't hold."""
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                              for k, v in files.items()):
        return ["a draft is its files' text, each by its path in the agent's folder"]
    problems = []
    if len(files) > MOST_FILES:
        problems.append(f"an agent's folder holds {MOST_FILES} files at most")
    if sum(len(text.encode()) for text in files.values()) > MOST_BYTES:
        problems.append(f"an agent's folder holds {MOST_BYTES // 1024} KB of text at most")
    for path in sorted(files):
        pure = PurePosixPath(path)
        if (pure.is_absolute() or not pure.parts or ".." in pure.parts or "\\" in path
                or pure.as_posix() != path or pure.suffix.lower() not in TEXT
                or any(part.startswith(".") for part in pure.parts)):
            problems.append(f"{path[:80]!r} isn't a file an agent's folder holds: its files are "
                            + ", ".join(TEXT) + ", each by its path inside the folder")
    return problems


def _written(files: dict[str, str], folder: Path) -> None:
    for path, text in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def pinned(agent: str, files: dict[str, str], tools: dict[str, Tool]) -> dict[str, str]:
    """A draft's files with the tools it names that the scenario has pinned as they are now,
    as `a5s pin` pins them, if its definition loads: its author picks the tools, and a5s pins
    them. If it doesn't load as it is, or names a tool the scenario hasn't got, its checks
    say so."""
    with tempfile.TemporaryDirectory() as there:
        folder = Path(there) / agent
        _written(files, folder)
        try:
            names = definitions.load(folder).tool_names
        except (ValueError, TypeError, OSError, yaml.YAMLError):
            return files
    pins = {name: tools[name].schema_hash for name in names if name in tools}
    return {**files, "tools.lock": definitions.lock_text(pins)}


def check(agent: str, files: dict[str, str], tools: dict[str, Tool],
          models: dict[str, ModelConfig]) -> list[str]:
    """What would stop a draft from being released here: the checks `a5s agent check` makes,
    on its files, as a folder named for its agent."""
    if problems := shape(files):
        return problems
    with tempfile.TemporaryDirectory() as there:
        folder = Path(there) / agent
        _written(files, folder)
        return authoring.check(folder, tools, models)


# What a5s keeps of them

def mine(conn: psycopg.Connection, person: Person) -> list[dict]:
    return [dict(r) for r in conn.execute(
        f"select {SHOWN} from agent_drafts where person = %s order by updated_at desc",
        (person.id,))]


def get(conn: psycopg.Connection, person: Person, draft: str) -> dict | None:
    """One of someone's drafts, with its files; None if it isn't theirs, or isn't there."""
    try:
        found = conn.execute(f"select {SHOWN}, files from agent_drafts where id = %s::uuid "
                             "and person = %s", (draft, person.id)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        return None
    return dict(found) if found else None


def start(conn: psycopg.Connection, person: Person, agent: str, based_on: str,
          files: dict[str, str]) -> dict:
    """A new draft of someone's: their first of `agent`, among no more than MOST_DRAFTS."""
    held = conn.execute("select count(*) as n, bool_or(agent = %s) as already from agent_drafts "
                        "where person = %s", (agent, person.id)).fetchone()
    if held["already"]:
        raise Refused(f"you have a draft of {agent} already: carry on with it, or drop it first")
    if held["n"] >= MOST_DRAFTS:
        raise Refused(f"you keep {MOST_DRAFTS} drafts at most: publish or drop one first")
    return dict(conn.execute(
        "insert into agent_drafts (person, agent, based_on, files) values (%s, %s, %s, %s) "
        f"returning {SHOWN}, files", (person.id, agent, based_on, Jsonb(files))).fetchone())


def save(conn: psycopg.Connection, person: Person, draft: str, files: dict[str, str]) -> dict | None:
    """A draft of someone's, with these files now; None if it isn't theirs, or isn't there."""
    try:
        found = conn.execute(
            "update agent_drafts set files = %s, updated_at = now() where id = %s::uuid and "
            f"person = %s returning {SHOWN}, files", (Jsonb(files), draft, person.id)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        return None
    return dict(found) if found else None


def drop(conn: psycopg.Connection, person: Person, draft: str) -> dict | None:
    """Let one of someone's drafts go; what it was, or None if it isn't theirs, or isn't there."""
    try:
        found = conn.execute(f"delete from agent_drafts where id = %s::uuid and person = %s "
                             f"returning {SHOWN}", (draft, person.id)).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        return None
    return dict(found) if found else None
