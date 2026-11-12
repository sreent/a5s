"""Roles from the identity provider's groups (docs/administration.md, step 3).

The settings in force map groups, by the ids their sign-ins show them by, to a5s's roles: those
people use by signing in, such as part-owner:billing, an auditor's or a grader's. The roles a
release needs, which people use by signing with keys of their own, stay the directory's. So an
organisation manages who holds a role in its identity provider, with its access reviews and
time-bound elevation, and a5s's settings say what each group may do.

- A sign-in shows someone's groups. a5s keeps those the settings name, as theirs until a later
  sign-in shows otherwise, so a role someone loses stops working at their next sign-in, and
  what they approved stops counting then, as when the directory takes a role away. What they do
  with a sign-in counts by the groups that sign-in shows.
- Giving a group a role needs the role's owner, as the directory names them: a part's owner for
  its part's roles, else an instance approver. Nobody who holds a role through a group gives it
  to another, so every grant goes back to someone the release names.
- A version's own map gives nothing towards its approval: the one in force before it does, and
  only for the grants the directory's owners approved.
- Groups give a5s's powers alone: what someone may see stays the directory's, by their team.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import psycopg

from a5s import db
from a5s.contract import INSTANCE_APPROVER, PART_OWNER, Person, Settings

log = logging.getLogger(__name__)

EVERY = 10.0  # seconds a part keeps everyone's groups and the settings' map before reading again
Mapping = dict[str, tuple[str, ...]]


def shown(claims: dict[str, Any], claim: str | None) -> tuple[str, ...]:
    """The groups a sign-in shows, by their ids. None where the deployment names no claim for
    them, and none where the sign-in had too many to list, as Entra ID does past 200, so a5s
    gives nothing for groups it can't see."""
    if not claim:
        return ()
    value = claims.get(claim)
    if value is None and claim in (claims.get("_claim_names") or {}):
        log.warning("a sign-in had too many groups to show them, so it gives no role: have the "
                    "identity provider send only the groups assigned to a5s's app")
    if isinstance(value, str):
        value = [value]
    return tuple(sorted({g for g in value or () if isinstance(g, str) and g}))


def granted(mapping: Mapping, groups: Iterable[str]) -> tuple[str, ...]:
    """The roles a person's groups give them, as a map says."""
    return tuple(sorted({role for g in groups for role in mapping.get(g, ())}))


def holding(person: Person | None, roles: Iterable[str]) -> Person | None:
    """Someone, with the roles their groups give them besides the directory's."""
    if person is None:
        return None
    more = tuple(r for r in roles if r not in person.roles)
    return replace(person, roles=(*person.roles, *more)) if more else person


def grants(settings: Settings, before: Settings | None) -> list[tuple[str, str]]:
    """Each group a version gives a role that the version before it didn't."""
    had = before.groups if before else {}
    return [(g, role) for g, roles in sorted(settings.groups.items()) for role in roles
            if role not in had.get(g, ())]


def owner_of(role: str) -> str:
    """Whose role gives a group this one: a part's owner, for its part's roles; else an
    instance approver's."""
    part = role.partition(":")[2]
    return f"{PART_OWNER}:{part}" if part else INSTANCE_APPROVER


def stored(conn: psycopg.Connection, person: str | None = None) -> dict[str, tuple[str, ...]]:
    """The groups each person's latest sign-in showed, of those the settings name."""
    rows = conn.execute("select person, groups from sign_in_groups "
                        "where %(p)s::text is null or person = %(p)s", {"p": person}).fetchall()
    return {r["person"]: tuple(r["groups"]) for r in rows}


def keep(conn: psycopg.Connection, person: str, groups: tuple[str, ...], at: datetime) -> None:
    """Keep the groups a sign-in made at `at` showed, unless a later sign-in's are kept."""
    conn.execute(
        "insert into sign_in_groups (person, groups, seen_at) values (%s, %s, %s) "
        "on conflict (person) do update set groups = excluded.groups, seen_at = excluded.seen_at "
        "where sign_in_groups.seen_at <= excluded.seen_at", (person, list(groups), at))


def rooted(scenario: Any) -> Any:
    """A scenario's own directory, without the roles groups give."""
    return Own(scenario) if isinstance(scenario, Grouped) else scenario


def under(scenario: Any, conn: psycopg.Connection, mapping: Mapping) -> Callable[[str], Person | None]:
    """Who someone is, with the roles their latest sign-in's groups give them under `mapping`,
    read afresh, for checking a version of the settings: never what a part kept."""
    inner = rooted(scenario)

    def person(pid: str) -> Person | None:
        found = inner.person(pid)
        if found is None or not mapping:
            return found
        return holding(found, granted(mapping, stored(conn, pid).get(pid, ())))
    return person


@dataclass
class _State:
    url: str
    mapped: Callable[[psycopg.Connection], Mapping]
    every: float = EVERY
    clock: Callable[[], float] = time.monotonic
    mapping: Mapping = field(default_factory=dict)
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    read: float = float("-inf")
    reading: bool = False


class Grouped:
    """A scenario's directory, with the roles its people hold through their groups, as the
    settings in force map them. `grouped` mixes it into a scenario's own class, so the scenario
    is the same object, whatever else it does."""

    _a5s_roles: _State

    def fresh(self, conn: psycopg.Connection | None = None) -> None:
        """Read the map and everyone's groups again, if they're older than its `every`. Asked
        again while it reads, as reading the settings may, what it read last stands."""
        state = self._a5s_roles
        if state.reading or state.clock() - state.read < state.every:
            return
        state.reading = True
        try:
            if conn is None:
                with db.transaction(state.url) as own:
                    state.mapping, state.groups = state.mapped(own), stored(own)
            else:
                state.mapping, state.groups = state.mapped(conn), stored(conn)
            state.read = state.clock()
        except psycopg.Error as exc:  # what it read last stands, a while longer
            log.warning("couldn't read the roles groups give, so the last read stands: %s", exc)
        finally:
            state.reading = False

    def forget(self) -> None:
        """Read the map and everyone's groups afresh at the next look."""
        self._a5s_roles.read = float("-inf")

    def _of(self, person: Person | None) -> Person | None:
        if person is None:
            return None
        self.fresh()
        state = self._a5s_roles
        return holding(person, granted(state.mapping, state.groups.get(person.id, ())))

    def person(self, person_id: str) -> Person | None:
        return self._of(super().person(person_id))  # type: ignore[misc]

    def find(self, identity: str) -> Person | None:
        return self._of(super().find(identity))  # type: ignore[misc]

    def team(self, name: str) -> list[Person]:
        return [p for p in (self._of(p) for p in super().team(name)) if p]  # type: ignore[misc]

    def holders(self, role: str) -> list[Person]:
        """Who holds a role: the directory's holders, and those whose groups give it them."""
        self.fresh()
        state = self._a5s_roles
        found = {p.id: p for p in (self._of(p) for p in super().holders(role)) if p}  # type: ignore[misc]
        for pid, groups in sorted(state.groups.items()):
            if (pid not in found and role in granted(state.mapping, groups)
                    and (person := self.person(pid)) is not None):
                found[pid] = person
        return list(found.values())

    def signed_in(self, person: Person, claims: dict[str, Any], claim: str | None) -> Person:
        """Someone who just signed in, with the roles this sign-in's groups give them, and
        those groups kept, of the ones the settings name, for when they aren't signed in.
        `claim` is the one their groups are in."""
        self.fresh()
        state = self._a5s_roles
        groups = tuple(g for g in shown(claims, claim) if g in state.mapping)
        if groups != state.groups.get(person.id, ()):
            at = datetime.fromtimestamp(claims.get("iat") or time.time(), UTC)
            with db.transaction(state.url) as conn:
                keep(conn, person.id, groups, at)
            state.groups[person.id] = groups
        base = Own(self).person(person.id) or person
        return holding(base, granted(state.mapping, groups))


class Own:
    """A grouped scenario's own directory, as its release has it, without the roles groups
    give: for what only the directory decides, such as who may give a group a role."""

    def __init__(self, scenario: Grouped):
        self.scenario = scenario

    def person(self, person_id: str) -> Person | None:
        return super(Grouped, self.scenario).person(person_id)  # type: ignore[misc]

    def find(self, identity: str) -> Person | None:
        return super(Grouped, self.scenario).find(identity)  # type: ignore[misc]

    def team(self, name: str) -> list[Person]:
        return super(Grouped, self.scenario).team(name)  # type: ignore[misc]

    def holders(self, role: str) -> list[Person]:
        return super(Grouped, self.scenario).holders(role)  # type: ignore[misc]


def grouped(scenario: Any, url: str, mapped: Callable[[psycopg.Connection], Mapping], *,
            every: float = EVERY, clock: Callable[[], float] = time.monotonic) -> Any:
    """A scenario, with the roles its people's groups give them mixed into its own class: the
    same object, so all it does, and all that's set on it, stays as it was."""
    if not isinstance(scenario, Grouped):
        cls = type(scenario)
        scenario.__class__ = type(cls.__name__, (Grouped, cls),
                                  {"__module__": cls.__module__, "__qualname__": cls.__qualname__})
    scenario._a5s_roles = _State(url, mapped, every, clock)
    return scenario
