"""Agent definitions: a folder in git, and each release a tested version of it."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Autonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(1, ge=0, le=1)  # level 2 only ever comes from the settings
    max: int = Field(1, ge=0, le=2)


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    release: str
    works_for: str
    does: str
    owner: str | None = None
    deputy: str | None = None
    scope: str = "none"
    model: str
    autonomy: Autonomy = Autonomy()
    tools: dict[str, list[str]] = {}
    triggers: list[dict[str, Any]] = []
    obligations: list[dict[str, Any]] = []
    reminders: bool = False
    preferences: list[str] = []
    channels: list[str] = ["teams"]
    context: dict[str, Any] = {}
    budget: dict[str, Any] = {}

    # Filled in from the folder, not from agent.yaml.
    instructions: str = ""
    pins: dict[str, str] = {}
    digest: str = ""

    @property
    def tool_names(self) -> list[str]:
        return [name for names in self.tools.values() for name in names]

    @property
    def release_id(self) -> str:
        return f"{self.release}+{self.digest[:12]}"


def _folder_digest(folder: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        sha.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes() + b"\0")
    return sha.hexdigest()


def load(folder: Path) -> Definition:
    spec = yaml.safe_load((folder / "agent.yaml").read_text())
    lock = folder / "tools.lock"
    return Definition(
        **spec,
        instructions=(folder / "AGENTS.md").read_text(),
        pins=yaml.safe_load(lock.read_text()) or {} if lock.exists() else {},
        digest=_folder_digest(folder),
    )


def load_all(agents_dir: Path) -> dict[str, Definition]:
    found = [load(f) for f in sorted(agents_dir.iterdir()) if (f / "agent.yaml").exists()]
    return {d.id: d for d in found}


def pin(folder: Path, schema_hashes: dict[str, str]) -> Path:
    """Record the schema of every tool the definition uses, as part of its release."""
    definition = load(folder)
    missing = [t for t in definition.tool_names if t not in schema_hashes]
    if missing:
        raise ValueError(f"the scenario doesn't provide: {', '.join(missing)}")
    lock = folder / "tools.lock"
    pins = {t: schema_hashes[t] for t in definition.tool_names}
    lock.write_text(
        "# Written by `a5s pin`. A tool whose schema no longer matches is refused.\n"
        + yaml.safe_dump(pins, sort_keys=True)
    )
    return lock
