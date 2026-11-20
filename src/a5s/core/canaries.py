"""The drift canaries (docs/model-execution.md): a fixed, versioned set of cases every
approved model must answer exactly, asked of the providers directly and scored into the
ledger, so a model that changes behind its name shows here first. Each canary is one
conversation with one exact expected answer, compared case-insensitively, word for word."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from a5s import db
from a5s.config import ModelConfig
from a5s.core import models

CANARIES = Path(__file__).resolve().parents[3] / "config" / "canaries.yaml"


def load(path: Path = CANARIES) -> list[dict[str, Any]]:
    """The fixed set, checked strictly: each a name, messages and an exact expected answer."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for canary in data.get("canaries") or []:
        if not isinstance(canary, dict) or not canary.get("name") or not (
                canary.get("expect") or canary.get("not")):
            raise ValueError(f"a canary needs a name and an expect: {canary}")
        if not canary.get("messages"):
            raise ValueError(f"canary {canary.get('name')} has no messages")
        out.append(canary)
    return out


def ask(found: ModelConfig, canary: dict[str, Any],
        http: httpx.Client) -> tuple[bool, str, float]:
    """One canary's one call: whether it answered exactly, what it said, and how long it took."""
    body = {"model": found.alias, "messages": canary["messages"]}
    if canary.get("system"):
        body["system"] = canary["system"]
    start = time.perf_counter()
    status, data = models.forward(found, body, http)
    seconds = time.perf_counter() - start
    if status >= 400:
        return False, f"{status}: {str(data)[:200]}", seconds
    if found.api == "openai":
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    else:  # anthropic's messages style
        answer = "".join(block.get("text", "") for block in data.get("content", []))
    wanted = str(canary.get("expect", "")).strip().casefold()
    if canary.get("not"):  # the answer must not contain this, such as a made-up key
        passed = re.search(canary["not"], answer) is None
    elif canary.get("contains"):  # the value, in whatever words: such as a sum
        passed = wanted in answer.strip().casefold()
    else:
        passed = answer.strip().casefold() == wanted
    return passed, answer, seconds


def run(database: str, scenario: str, approved: dict[str, ModelConfig],
        canaries: list[dict[str, Any]] | None = None,
        http: httpx.Client | None = None) -> int:
    """Every canary, on each model it names (or every approved one it doesn't), recorded into
    canary_scores, which only ever grows: the scores are the drift's record. Returns how many
    failed, so a caller can fail a job on them."""
    canaries = canaries if canaries is not None else load()
    failed = 0
    with (http or httpx.Client(timeout=180)) as client, db.transaction(database) as conn:
        for canary in canaries:
            aliases = [canary["model"]] if canary.get("model") else sorted(approved)
            for alias in aliases:
                found = approved.get(alias)
                if found is None:
                    continue
                if found.key_env and not found.api_key:  # its key isn't set: can't ask
                    continue
                try:
                    passed, answer, seconds = ask(found, canary, client)
                except models.ModelUnavailable as exc:  # the provider stalled: a failure
                    passed, answer, seconds = False, str(exc)[:200], 0.0
                failed += 0 if passed else 1
                conn.execute(
                    "insert into canary_scores (scenario, canary, model, passed, answered, "
                    "seconds) values (%s, %s, %s, %s, %s, %s)",
                    (scenario, canary["name"], alias, passed, answer[:4000],
                     round(seconds, 3)))
    return failed


def scorecard(database: str, scenario: str, days: int = 1) -> list[dict[str, Any]]:
    """The latest day's scores, newest first, for a page or a report."""
    with db.connect(database) as conn:
        rows = conn.execute(
            "select canary, model, passed, seconds, at from canary_scores where scenario = %s "
            "and at > now() - make_interval(days => %s) order by at desc", (scenario, days),
        ).fetchall()
    return [dict(row) for row in rows]
