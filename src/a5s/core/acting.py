"""Whose power a page that changes things uses, for the line across its top (Ocean's ActingAs;
docs/design.md#risk-and-the-friction-it-earns): the roles its acts count as, worked out by the
rules that let someone do them, named as What you may do names roles, and what that lets them do
there.

A page says it only while it holds an act of theirs that a role gives them: deciding held
changes, grading samples or a new version's answers, approving a version of the settings,
suspending or resuming an instance, undoing a change as one of its deciders, the data protection
officer's requests, answering a conversation handed to their team, and taking a note out of a
notebook they keep. A page that only shows has none; nor has one whose acts are someone's own,
such as their tasks or undoing a change made for them, or one that only asks, such as for a
version of the settings, which its approvers approve on its own page, with the line. So the line
means, wherever it is, that a role's power is in use, and which.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from a5s.contract import (
    AGENT_OWNER,
    ASSURANCE,
    DATA_PROTECTION,
    INSTANCE_APPROVER,
    PART_DELEGATE,
    PART_OWNER,
    RELEASE_APPROVER,
    Person,
)
from a5s.core import groups, languages, proposals, samples, words

# What each power lets someone do on its page, after the role it's theirs by
DECIDES = "what you approve here, the agent that asked for it does in its records"
GRADES = "your grades count towards whether an agent may act on its own, or must ask first"
SHADOWS = ("your grades say how a new version answers beside the one at work, for its owners "
           "to decide whether to put it to work")
APPROVES = ("your approval counts towards this version, which changes what agents may do once "
            "every approval it needs is in")
SUSPENDS = "suspending it stops it answering anyone, and working on its own, until it's resumed"
RESUMES = "resuming it lets it answer people, and work on its own, again"
UNDOES = "undoing it has a5s reverse the change in its record, as the change's tool says how"
OFFICER = "what you ask here, a5s exports, or erases for good, about one person"
ANSWERS = "what you write here goes to {person} in their chat, with your name"
KEEPS = "a note you take out here, its agent no longer reads"

TEAM = "one of the team that runs a5s"
OWNS_IT = "Owner of this instance"
DEPUTY_IT = "Deputy for this instance"
SUSPENDED_IT = "the one who suspended it"


def line(roles: Iterable[str], lets: str, language: str = languages.ENGLISH,
         **given: object) -> dict | None:
    """The line a page shows: the roles its acts count as, each once, in words, and what they
    let someone do there; or none, where no role's power is in use."""
    named = list(dict.fromkeys(roles))
    if not named:
        return None
    return {"role": groups.listed(named, most=len(named)), "lets": words.say(language, lets, **given)}


def shown(found: dict | None) -> dict:
    """The line as a page's answer carries it: there, or not at all."""
    return {"acting": found} if found else {}


def named(roles: Iterable[str], language: str = languages.ENGLISH) -> list[str]:
    """Roles in words, as What you may do names them."""
    from a5s.core import administration  # which reaches undoing, whose page has the line

    return [administration.named(role, language) for role in roles]


def deciding(person: Person, parts: Iterable[Iterable[str]],
             language: str = languages.ENGLISH) -> dict | None:
    """Deciding the held changes waiting for someone, each in the parts given: the roles each
    is theirs to decide by, as core/proposals.py gives deciders them, a part's owner or delegate,
    or the instance approver, for a change in no part."""
    held = set(person.roles)
    roles = [role for touched in parts for part in (sorted(touched) or [None])
             for role in proposals.roles(part) if role in held]
    return line(named(roles, language), DECIDES, language)


def grading(person: Person, shadows: bool = False,
            language: str = languages.ENGLISH) -> dict | None:
    """Grading agents' work, or what a new version answered beside it: the grader's."""
    if samples.GRADER not in person.roles:
        return None
    return line(named([samples.GRADER], language), SHADOWS if shadows else GRADES, language)


APPROVING = (INSTANCE_APPROVER, DATA_PROTECTION, ASSURANCE)


def approving(person: Person, needed: Iterable[str],
              language: str = languages.ENGLISH) -> dict | None:
    """Approving a version of the settings: the roles of theirs it needs, as core/registry.py's
    `needed` says, or, where it needs none of theirs in particular, those they approve
    versions by (registry.approves)."""
    held = list(person.roles)
    roles = [role for role in dict.fromkeys(needed) if role in held] or [
        role for role in held
        if role in APPROVING or role.startswith((f"{PART_OWNER}:", f"{AGENT_OWNER}:"))]
    return line(named(roles, language), APPROVES, language)


def suspending(person: Person, inst: dict, action: str, team: str | None,
               language: str = languages.ENGLISH) -> dict | None:
    """Suspending or resuming an instance, which core/suspension.py's `may` lets them: why it's
    theirs to do, by the same rules."""
    if action == "resume":
        if inst.get("suspended_by") == person.id:
            return line([words.say(language, SUSPENDED_IT)], RESUMES, language)
        if RELEASE_APPROVER in person.roles:
            return line(named([RELEASE_APPROVER], language), RESUMES, language)
        return None
    roles = [words.say(language, OWNS_IT)] if person.id == inst.get("owner") else []
    roles += [words.say(language, DEPUTY_IT)] if person.id == inst.get("deputy") else []
    roles += named([role for role in (f"{AGENT_OWNER}:{inst['definition']}",
                                      *(f"{kind}:{part}" for part in sorted(inst.get("parts") or {})
                                        for kind in (PART_OWNER, PART_DELEGATE)))
                    if role in person.roles], language)
    roles += [words.say(language, TEAM)] if team is not None and person.team == team else []
    return line(roles, SUSPENDS, language)


def undoing(person: Person, part: str | None, language: str = languages.ENGLISH) -> dict | None:
    """Undoing a change as one of the deciders of its record's part, not as whoever it was for,
    whose own it is: core/undoing.py's `may` lets both."""
    held = set(person.roles)
    return line(named([role for role in proposals.roles(part) if role in held], language),
                UNDOES, language)


def officer(person: Person, language: str = languages.ENGLISH) -> dict | None:
    """The data protection officer's requests for someone's data."""
    if DATA_PROTECTION not in person.roles:
        return None
    return line(named([DATA_PROTECTION], language), OFFICER, language)


def answering(team: str, whom: str, language: str = languages.ENGLISH) -> dict | None:
    """Answering a conversation handed to someone's team, as one of it."""
    return line([words.say(language, "one of the {team} team", team=team)], ANSWERS, language,
                person=whom)


def keeping(person: Person, instances: Iterable[dict], name: Any,
            language: str = languages.ENGLISH) -> dict | None:
    """Taking notes out of the notebooks someone keeps (core/notebook.py's `keeps`): as the
    owner of an instance's agent, or as an instance's owner or deputy, each named."""
    roles: list[str] = []
    for inst in instances:
        if f"{AGENT_OWNER}:{inst['definition']}" in person.roles:
            roles += named([f"{AGENT_OWNER}:{inst['definition']}"], language)
        if person.id == inst["owner"]:
            roles.append(words.say(language, "Owner of {instance}", instance=name(inst)))
        if person.id == inst["deputy"]:
            roles.append(words.say(language, "Deputy for {instance}", instance=name(inst)))
    return line(roles, KEEPS, language)
