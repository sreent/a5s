"""Parts: the pieces of the business each instance works in, with a level in each.

The scenario says which part each record is in, and the directory what each person may see.
An instance works only on records in its parts, or in none, and only on those everyone its
run acts for may see. A call about records works at the lowest level the instance has in
their parts, and one about no record in particular at its own level, the lowest of all its
parts'. Each part's owner approves the instances that work in it, and how far
(core/registry.py).
"""

from __future__ import annotations

from typing import Any

from a5s.contract import Scenario

UNSEEN = "there's no such record, or the people this run is for may not see it"


def about(scenario: Scenario, run: dict, records: list[str]) -> dict[str, Any]:
    """What policy weighs of the records a call is about: the level it works at, whether
    they're all in the instance's parts, and whether everyone the run acts for may see them."""
    parts = run.get("parts") or {}
    touched = {scenario.part_of(r) for r in records}
    levels = [parts[p] for p in touched if p in parts]
    return {"level": min(levels) if levels else run["level"],
            "in_scope": all(p is None or p in parts for p in touched),
            "visible": all(scenario.sees(who, r) for r in records for who in run["acts_for"])}


def workable(scenario: Scenario, run: dict, record: str) -> bool:
    """Whether a run may work on a record."""
    found = about(scenario, run, [record])
    return found["in_scope"] and found["visible"]


def kept(scenario: Scenario, run: dict, field: str | None, result: Any) -> tuple[Any, int]:
    """What a tool returned, less the records in it the run may not work on, by the field
    that names each, and how many it left out."""
    def fits(item: Any) -> bool:
        key = item.get(field) if isinstance(item, dict) else None
        return not isinstance(key, str) or workable(scenario, run, key)

    if not field:
        return result, 0
    if isinstance(result, list):
        found = [item for item in result if fits(item)]
        return found, len(result) - len(found)
    return (result, 0) if fits(result) else ({"error": UNSEEN}, 1)


def within(scenario: Scenario, instance: dict, people: list[str], records: list[Any]) -> list[Any]:
    """The records, of those given, that an instance may work on for these people, by each
    one's key, such as for a report."""
    run = {"parts": instance.get("parts") or {}, "level": instance["level"], "acts_for": people}
    return [r for r in records if workable(scenario, run, r.key)]
