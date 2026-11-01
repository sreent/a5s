"""Parts: the pieces of the business each instance works in, with a level in each.

The scenario says which part each record is in, and the directory what each person may see.
An instance works only on records in its parts, or in none, and only on those everyone its
run acts for may see. A call about records works at the lowest level the instance has in
their parts, and one about no record in particular at its own level, the lowest of all its
parts'. Each part's owner approves the instances that work in it, and how far
(core/registry.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from a5s.contract import PART_OWNER, Scenario

UNSEEN = "there's no such record, or the people this run is for may not see it"


def about(scenario: Scenario, run: dict, records: list[str], action: str | None = None,
          approved: Iterable[str] = (), caps: dict[tuple[str, str], int] | None = None
          ) -> dict[str, Any]:
    """What policy weighs of the records a call is about: the level it works at, whether
    they're all in the instance's parts, and whether everyone the run acts for may see them.

    A change, a call with a type of action, works at the level the settings set for that type
    in each record's part, or else at most at level 1. Level 2 counts only while someone who
    approved the settings in force still owns the part, and only up to a5s's cap for the
    release, part and type, which is 1 until graded samples raise it. A change about no record,
    or in a run that has read content from outside, works at level 1 at most."""
    parts = run.get("parts") or {}
    touched = {scenario.part_of(r) for r in records}
    levels = [_level(scenario, run, p, action, set(approved), caps or {})
              for p in touched if p in parts]
    level = min(levels) if levels else run["level"]
    if action and (not levels or None in touched or run.get("read_outside")):
        level = min(level, 1)  # level 2 is for a type set in a record's part, and nothing else
    return {"level": level,
            "in_scope": all(p is None or p in parts for p in touched),
            "visible": all(scenario.sees(who, r) for r in records for who in run["acts_for"])}


def _level(scenario: Scenario, run: dict, part: str, action: str | None, approved: set[str],
           caps: dict[tuple[str, str], int]) -> int:
    level = (run.get("parts") or {})[part]
    if not action:
        return level
    chosen = ((run.get("actions") or {}).get(part) or {}).get(action)
    level = min(level, 1) if chosen is None else chosen
    if level >= 2:
        role = f"{PART_OWNER}:{part}"
        if not any(role in who.roles for a in approved if (who := scenario.person(a))):
            return 1  # nobody who approved it owns the part now: until the new owner does
        level = min(level, caps.get((part, action), 1))
    return level


def workable(scenario: Scenario, run: dict, record: str) -> bool:
    """Whether a run may work on a record."""
    found = about(scenario, run, [record])
    return found["in_scope"] and found["visible"]


def kept(scenario: Scenario, run: dict, field: str | None, result: Any) -> tuple[Any, int]:
    """What a tool returned, less the records in it the run may not work on, at any depth, by
    the field that names each, and how many it left out. A record whose key isn't a string
    is left out too, since nothing can say whose it is."""
    withheld = 0

    def fits(item: dict) -> bool:
        key = item.get(field)
        return isinstance(key, str) and bool(key) and workable(scenario, run, key)

    def walk(value: Any) -> Any:
        nonlocal withheld
        if isinstance(value, list):
            found = []
            for item in value:
                if isinstance(item, dict) and field in item and not fits(item):
                    withheld += 1
                else:
                    found.append(walk(item))
            return found
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    if not field:
        return result, 0
    if isinstance(result, dict) and field in result and not fits(result):
        return {"error": UNSEEN}, 1
    found = walk(result)
    if isinstance(result, dict) and field in result and withheld:  # a record holding records
        return {"error": UNSEEN}, withheld + 1
    return found, withheld


def within(scenario: Scenario, instance: dict, people: list[str], records: list[Any]) -> list[Any]:
    """The records, of those given, that an instance may work on for these people, by each
    one's key, such as for a report."""
    run = {"parts": instance.get("parts") or {}, "level": instance["level"], "acts_for": people}
    return [r for r in records if workable(scenario, run, r.key)]
