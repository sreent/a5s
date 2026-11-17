"""Telling others of a version of the settings that only narrows what agents may do in some
parts (docs/administration.md): once it's in force, however it was applied, where its approvers
work or from the signed file with `a5s apply`, whoever would have approved it, had it widened
anything, hears in their digest what it changed and who approved it (round 14)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from a5s import db
from a5s.contract import Settings
from a5s.core import approvals, digests, languages, ledger, memberships, registry, words
from a5s.definitions import Definition

NARROWED = ("{names} approved version {serial} of the settings alone, since it only narrows "
            "what agents may do in {parts}: {said}")


def told(conn: db.Connection, scenario: Any, definitions: dict[str, Definition],
         settings: Settings, before: Settings | None, signers: list[str],
         now: datetime) -> list[str]:
    """Tell, in their digest, whoever would have approved a version that only narrows what
    agents may do in some parts, had it widened anything, once it's in force, in the caller's
    transaction: what it changes, in their language where a5s has the words, and who approved
    it. Whom it told: nobody, for any other version, which they approved themselves."""
    if before is None or (parts := registry.narrowed(settings, before)) is None:
        return []
    changed = [c["text"] for c in approvals.changes(before, settings, definitions,
                                                     scenario.person)]
    names = approvals.names_of([p.name if (p := scenario.person(s)) else s for s in signers])
    whom = []
    for person in registry.told(settings, scenario.holders, before,
                                memberships.rooted(scenario).holders):
        spoken = languages.of(conn, person)
        text = words.say(spoken, NARROWED, names=names, serial=settings.serial,
                         parts=approvals.names_of(sorted(parts)),
                         said=" ".join(words.translated(spoken, c) for c in changed))
        digests.keep(conn, person.id, None, None, None, text, now)
        ledger.append(conn, {"kind": "notice", "action": "narrowed", "run": None,
                             "instance": None, "acts_for": [], "decision": "record",
                             "args": {"settings": settings.version, "to": person.id,
                                      "parts": sorted(parts)}})
        whom.append(person.id)
    return whom
