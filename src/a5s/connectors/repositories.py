"""Scenario-declared, read-only repository tools and their record permissions."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from a5s.connectors.github import GitHubRepository
from a5s.connectors.rest import RestClient
from a5s.contract import Tool, ToolCall

FILE = "repositories.yaml"
NAME = re.compile(r"[a-z][a-z0-9_]{0,30}")
PART = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
NAMES = {
    "search_records": "search_{name}",
    "get_record": "get_{name}",
    "get_comments": "get_{name}_comments",
    "read_repository_file": "read_{name}_file",
    "get_pr_diff": "get_{name}_diff",
}


def _local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _address(given: str) -> str:
    found = httpx.URL(given)
    if (found.scheme not in ("http", "https") or not found.host or found.userinfo
            or found.query or found.fragment):
        raise ValueError("a repository address is an HTTP(S) origin or path, without credentials, "
                         "query or fragment")
    if found.scheme == "http" and not _local(found.host):
        raise ValueError("a remote repository address needs HTTPS")
    return given.rstrip("/")


class Repository(BaseModel):
    """One repository, in one scenario part, read with a token of its own in the gateway."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["github", "forgejo"] = "github"
    repository: str
    url: str
    site: str
    part: str

    @field_validator("repository")
    @classmethod
    def _repository(cls, given: str) -> str:
        owner, separator, name = given.partition("/")
        if not separator or not owner or not name or "/" in name or given != given.strip():
            raise ValueError("a repository is owner/name")
        return given

    @field_validator("url", "site")
    @classmethod
    def _url(cls, given: str) -> str:
        return _address(given)

    @field_validator("part")
    @classmethod
    def _part(cls, given: str) -> str:
        if not PART.fullmatch(given):
            raise ValueError("a repository's part is lower-case letters, digits and hyphens")
        return given


class Declaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repositories: dict[str, Repository]

    @field_validator("repositories")
    @classmethod
    def _names(cls, given: dict[str, Repository]) -> dict[str, Repository]:
        for name in given:
            if not NAME.fullmatch(name):
                raise ValueError(f"{name!r} isn't a repository tool name: use lower-case letters, "
                                 "digits and underscores")
        return given


def declared(folder: Path) -> Declaration | None:
    path = folder / FILE
    if not path.exists():
        return None
    return Declaration.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


@dataclass(frozen=True)
class RepositoryTool(Tool):
    """A tool whose pin also covers its repository, endpoint, site and part."""

    declared: str = ""

    @property
    def schema_hash(self) -> str:
        import hashlib
        return hashlib.sha256((super().schema_hash + self.declared).encode()).hexdigest()


def tools(declaration: Declaration, scenario: Any, *, sandboxed: bool = False,
          http: httpx.Client | None = None) -> dict[str, Tool]:
    made: dict[str, Tool] = {}
    for name, config in declaration.repositories.items():
        def allowed(call: ToolCall, part=config.part) -> bool:
            sees = getattr(scenario, "sees_part", None)
            return bool(call.acts_for) and callable(sees) and all(
                sees(person, part) for person in call.acts_for)

        token_env = f"A5S_REPOSITORY_{name.upper()}_TOKEN"
        repository = GitHubRepository(
            config.repository, authorize=allowed,
            client=RestClient(config.url, token_env=token_env, http=http))
        pinned = json.dumps(config.model_dump(), sort_keys=True, separators=(",", ":"))
        for original, tool in repository.tools().items():
            named = NAMES[original].format(name=name)
            description = f"{tool.description} This is the {config.repository} repository."
            repo_tool = RepositoryTool(**{**tool.__dict__, "name": named, "description": description,
                                          "declared": pinned})
            if sandboxed:
                def unavailable(call: ToolCall) -> dict:
                    return {"error": "repository tools don't call the real service in the sandbox"}
                repo_tool = replace(repo_tool, run=unavailable)
            made[named] = repo_tool
    return made


class ServingRepositories:
    """A scenario with declared repository tools and their records' parts and visibility."""

    _a5s_repository_tools: dict[str, Tool]
    _a5s_repositories: dict[str, Repository]
    record_pattern: str | None
    record_links: tuple[str, ...]

    def tools(self) -> dict[str, Tool]:
        return {**super().tools(), **self._a5s_repository_tools}  # type: ignore[misc]

    def part_of(self, record: str) -> str | None:
        for config in self._a5s_repositories.values():
            prefix = config.repository + "#"
            if record.startswith(prefix) and record[len(prefix):].isdigit():
                return config.part
        return super().part_of(record)  # type: ignore[misc]

    def sees(self, person: str, record: str) -> bool:
        for config in self._a5s_repositories.values():
            prefix = config.repository + "#"
            if record.startswith(prefix) and record[len(prefix):].isdigit():
                sees = getattr(super(), "sees_part", None)
                return callable(sees) and bool(sees(person, config.part))
        return super().sees(person, record)  # type: ignore[misc]


def served(scenario: Any, folder: Path, *, sandboxed: bool = False,
           reserved: frozenset[str] = frozenset(), http: httpx.Client | None = None) -> Any:
    """Mix a folder's declared repository tools into its scenario, fail closed on a name clash."""
    declaration = declared(folder)
    if declaration is None:
        return scenario
    own = {name for name in scenario.tools()
           if not isinstance(scenario, ServingRepositories) or name not in scenario._a5s_repository_tools}
    made = tools(declaration, scenario, sandboxed=sandboxed, http=http)
    if clash := sorted(set(made) & (own | set(reserved))):
        raise ValueError(f"{folder / FILE} gives {', '.join(clash)}, which the scenario or a5s "
                         "has already: a repository's tools take names of their own")
    if not isinstance(scenario, ServingRepositories):
        cls = type(scenario)
        scenario.__class__ = type(cls.__name__, (ServingRepositories, cls),
                                  {"__module__": cls.__module__, "__qualname__": cls.__qualname__})
    scenario._a5s_repository_tools = made
    scenario._a5s_repositories = declaration.repositories
    patterns = [rf"\b{re.escape(config.repository)}#\d+\b"
                for config in declaration.repositories.values()]
    if scenario.record_pattern:
        patterns.insert(0, f"(?:{scenario.record_pattern})")
    scenario.record_pattern = "|".join(patterns)
    sites = tuple(config.site + "/" for config in declaration.repositories.values())
    scenario.record_links = tuple(dict.fromkeys((*scenario.record_links, *sites)))
    return scenario


__all__ = ["Declaration", "Repository", "declared", "served", "tools"]
