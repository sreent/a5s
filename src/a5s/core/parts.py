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
from a5s.core import groups

UNSEEN = "there's no such record, or the people this run is for may not see it"
NOWHERE = "there's no such record, or this run may not work on it"  # for a run for nobody
# Policy's two rules on the records a run may work on (core/policies/base.cedar): what the run
# hears when either refuses a call is the same as for a record there isn't, so it tells nobody
# that a record is there, nor in which part (round 15, A14)
RULES = frozenset({"instances-work-only-in-their-parts", "people-see-only-what-they-may"})
REFUSED = "runs-work-only-on-records-they-may-see"  # the one reason the run hears for both


def about(scenario: Scenario, run: dict, records: list[str], action: str | None = None,
          approved: Iterable[str] = (), caps: dict[tuple[str, str], int] | None = None,
          standing: dict[str, dict | None] | None = None) -> dict[str, Any]:
    """What policy weighs of the records a call is about: the level it works at, whether
    they're all in the instance's parts, whether everyone the run acts for may see them, and
    whether they're all the own of the one person it acts for, as the scenario says whose each
    record is, such as their own account: what a scenario's pack may hold a change to, such as
    self-service only for the person asking.

    A change, a call with a type of action, works at the level the settings set for that type
    in each record's part, or else at most at level 1. Level 2 counts only while someone who
    approved the settings in force still owns the part, and only up to a5s's cap for the
    release, part and type, which is 1 until graded samples raise it. A change about no record,
    or in a run that has read content from outside, works at level 1 at most.

    A run for nobody that a mailbox's new mail started sees only what every reader of the
    mailbox may see, since its draft waits where they all read it (`audience`, round 15)."""
    parts = run.get("parts") or {}
    touched = {scenario.part_of(r) for r in records}
    levels = [_level(scenario, run, p, action, set(approved), caps or {})
              for p in touched if p in parts]
    level = min(levels) if levels else run["level"]
    if action and (not levels or None in touched or run.get("read_outside")
                   or run.get("steered")):  # nor for a run a team's words steered (round 15)
        level = min(level, 1)  # level 2 is for a type set in a record's part, and nothing else
    reaching = audience(scenario, run)
    whom = list(run["acts_for"]) if reaching is None else reaching
    return {"level": level,
            "in_scope": all(p is None or p in parts for p in touched),
            "visible": all(scenario.sees(who, r) for r in records for who in whom) and not (
                reaching == [] and records),  # a mailbox nobody reads: none, failing closed
            "for_self": bool(action) and for_self(run, records, standing or {})}


def audience(scenario: Scenario, run: dict) -> list[str] | None:
    """Whom a run's work reaches, for a run for nobody that a mailbox's new mail started:
    everyone who reads the mailbox, as the directory says now, where its draft waits for them
    all (connectors/mailboxes.py); None for any other run, whose work reaches whom it acts
    for."""
    trigger = run.get("trigger") or {}
    readers = getattr(scenario, "mail_readers", None)
    if run["acts_for"] or trigger.get("kind") != "event" or not callable(readers):
        return None
    found = readers(trigger.get("source"))
    if not isinstance(found, tuple):
        return None
    from a5s.core import registry  # who's in a team or holds a role, now

    return registry.served(scenario, found)


def for_self(run: dict, records: list[str], standing: dict[str, dict | None]) -> bool:
    """Whether a change is the one person's own, at their own word: a run that answers their
    own message, one to one, and has read nothing from outside, about records each of them
    theirs, as the scenario said whose each was when the call read them (`standing`). Never a
    chase, a report, a reminder, a task's slice or another agent's question, which act for one
    person who asked for nothing, nor a group chat. If the records couldn't be read, it isn't,
    so a pack's restriction holds: it fails closed."""
    trigger, acts_for = run.get("trigger") or {}, list(run["acts_for"])
    if (trigger.get("kind") != "message" or groups.of(trigger.get("conversation"))
            or len(acts_for) != 1 or run.get("read_outside") or run.get("steered")
            or not records):
        return False
    return all((kept := standing.get(r)) is not None and kept.get("person") == acts_for[0]
               for r in records)


def _level(scenario: Scenario, run: dict, part: str, action: str | None, approved: set[str],
           caps: dict[tuple[str, str], int]) -> int:
    level = (run.get("parts") or {})[part]
    if not action:
        return level
    chosen = ((run.get("actions") or {}).get(part) or {}).get(action)
    level = min(level, 1) if chosen is None else chosen
    if level >= 2:
        if not owned(scenario, part, approved):
            return 1  # nobody who approved it owns the part now: until the new owner does
        level = min(level, caps.get((part, action), 1))
    return level


def owned(scenario: Scenario, part: str, approved: Iterable[str]) -> bool:
    """Whether someone who approved the settings in force owns a part now, so level 2 there
    counts."""
    role = f"{PART_OWNER}:{part}"
    return any(role in who.roles for a in approved if (who := scenario.person(a)))


def workable(scenario: Scenario, run: dict, record: str) -> bool:
    """Whether a run may work on a record."""
    found = about(scenario, run, [record])
    return found["in_scope"] and found["visible"]


def unseen(reasons: Iterable[str]) -> bool:
    """Whether policy refused a call, by its reasons, for a record the run may not work on, or
    for one there isn't: one in a part its instance doesn't work in, or one someone it acts for
    may not see, as the directory says of a record there isn't."""
    return not RULES.isdisjoint(reasons)


def told(scenario: Scenario, run: dict) -> str:
    """What a run hears of a record it may not work on, whichever rule refused it, and of a
    record there isn't: the same words for each, which only the run decides, never the record,
    so they tell nobody that a record is there, nor in which part (round 15, A14). Whoever it
    acts for is pointed to someone who runs its assistant, the instance's owner or else its
    deputy, never a part's owner, whom the part would give away. The ledger keeps the rules
    that refused it, as a run's page shows them."""
    whom = list(run.get("acts_for") or [])
    if not whom:
        return NOWHERE
    ask = next((who for pid in (run.get("owner"), run.get("deputy"))
                if pid and pid not in whom and (who := scenario.person(pid))), None)
    return UNSEEN + (f". If they think they should, they can ask {ask.name}, who runs this "
                     "assistant" if ask else "")


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
        if isinstance(value, dict):  # as an object's value, as MCP tools answer
            kept = {}
            for k, v in value.items():
                if isinstance(v, dict) and field in v and not fits(v):
                    withheld += 1
                else:
                    kept[k] = walk(v)
            return kept
        return value

    if not field:
        return result, 0
    if isinstance(result, dict) and field in result and not fits(result):
        return {"error": told(scenario, run)}, 1
    found = walk(result)
    if isinstance(result, dict) and field in result and withheld:  # a record holding records
        return {"error": told(scenario, run)}, withheld + 1
    return found, withheld


def within(scenario: Scenario, instance: dict, people: list[str], records: list[Any]) -> list[Any]:
    """The records, of those given, that an instance may work on for these people, by each
    one's key, such as for a report."""
    run = {"parts": instance.get("parts") or {}, "level": instance["level"], "acts_for": people}
    return [r for r in records if workable(scenario, run, r.key)]
