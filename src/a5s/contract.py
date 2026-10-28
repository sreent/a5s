"""The scenario contract: what a scenario gives a5s.

Phase 1 covers the directory, settings, tools and the policy pack. Records,
the governed process and the decision surface follow in later steps.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from a5s.core.ledger import canonical


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    team: str
    in_audience: bool = True  # whether agents may message them at all


@dataclass(frozen=True)
class ToolCall:
    """What a tool sees: its arguments, and who the run acts for."""

    args: dict[str, Any]
    instance: str
    run: str
    acts_for: tuple[str, ...]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[ToolCall], Any]
    reads: bool = True
    writes: bool = False
    destructive: bool = False
    sends_outside: bool = False

    @property
    def risk(self) -> dict[str, bool]:
        return {
            "reads": self.reads,
            "writes": self.writes,
            "destructive": self.destructive,
            "sends_outside": self.sends_outside,
        }

    @property
    def schema_hash(self) -> str:
        """Pinned in releases, so a changed tool needs a new release."""
        payload = {"name": self.name, "description": self.description, "schema": self.schema}
        return hashlib.sha256(canonical(payload).encode()).hexdigest()

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "schema": self.schema,
            "risk": self.risk,
            "schema_hash": self.schema_hash,
        }


@dataclass(frozen=True)
class InstanceSettings:
    id: str
    definition: str
    serves: tuple[str, ...]
    level: int | None = None  # the release's starting level, if the settings set none


@dataclass(frozen=True)
class Settings:
    version: str
    instances: tuple[InstanceSettings, ...] = field(default_factory=tuple)


class Scenario(Protocol):
    name: str
    record_links: tuple[str, ...]  # the only link prefixes agents' messages may carry

    def person(self, person_id: str) -> Person | None: ...

    def tools(self) -> dict[str, Tool]: ...

    def settings(self) -> Settings: ...

    def policy_pack(self) -> str | None: ...
