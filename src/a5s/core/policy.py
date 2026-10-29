"""Policy: Cedar decides allow or deny, outside the agent, and denies by default.

If the policy can't be evaluated for any reason, the answer is deny.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import cedarpy

_DEFAULT_DENY = "nothing permits it, such as a tool outside the instance's grant"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reasons: tuple[str, ...]  # the names of the policies that decided
    errors: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()  # the same, in words, for the agent and for people

    @property
    def label(self) -> str:
        return "allow" if self.allowed else "deny"

    def as_dict(self, explain: bool = False) -> dict[str, Any]:
        out = {"decision": self.label, "reasons": list(self.reasons), "errors": list(self.errors)}
        return {**out, "explanations": list(self.explanations)} if explain else out


def base_pack() -> str:
    return files("a5s.core").joinpath("policies/base.cedar").read_text()


def schema() -> str:
    return files("a5s.core").joinpath("policies/schema.cedarschema").read_text()


def _statements(text: str) -> dict[str, dict]:
    return json.loads(cedarpy.policies_to_json_str(text))["staticPolicies"]


class PolicyEngine:
    """a5s's base pack, plus any scenario packs, which may only add restrictions."""

    def __init__(self, base: str | None = None, packs: tuple[str, ...] = ()):
        for pack in packs:
            permits = [p for p in _statements(pack).values() if p["effect"] == "permit"]
            if permits:
                raise ValueError("a scenario's policy pack can only add restrictions (forbid)")
        self.text = "\n".join([base if base is not None else base_pack(), *packs])
        checked = cedarpy.validate_policies(self.text, schema())
        if not checked.validation_passed:
            problems = "; ".join(str(e) for e in checked.errors)
            raise ValueError(f"the policies don't match a5s's schema: {problems}")
        self._schema = cedarpy.Schema.from_str(schema())
        self.version = hashlib.sha256(self.text.encode()).hexdigest()[:16]
        statements = _statements(self.text)
        self._names = {pid: p.get("annotations", {}).get("id", pid) for pid, p in statements.items()}
        self._words = {pid: p.get("annotations", {}).get("reason") for pid, p in statements.items()}
        self._policies = cedarpy.PolicySet.from_str(self.text)

    def decide(
        self,
        *,
        principal: dict[str, str],
        action: str,
        resource: dict[str, str],
        context: dict[str, Any],
        entities: list[dict[str, Any]],
    ) -> Decision:
        request = {
            "principal": principal,
            "action": {"type": "Action", "id": action},
            "resource": resource,
            "context": context,
        }
        try:
            result = cedarpy.is_authorized(request, self._policies, entities, schema=self._schema)
        except Exception as exc:  # noqa: BLE001 - anything unexpected fails closed
            return Decision(False, (), (f"policy could not run: {exc}",),
                            ("a5s couldn't check the call, so it's denied",))
        pids = result.diagnostics.reasons
        reasons = tuple(self._names.get(pid, pid) for pid in pids)
        words = tuple(self._words.get(pid) or self._names.get(pid, pid) for pid in pids)
        errors = tuple(str(e) for e in result.diagnostics.errors)
        if errors:
            return Decision(False, reasons, errors, ("a5s couldn't check the call, so it's denied",))
        allowed = bool(result.allowed)
        return Decision(allowed, reasons, (), words or (() if allowed else (_DEFAULT_DENY,)))
