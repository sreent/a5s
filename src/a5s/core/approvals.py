"""Approving settings where people work: a card in their chat, and the decision on the
core's own page.

A version of the settings can be proposed to its instance approvers rather than signed
with their keys: the owner of each part its instances work in, and an instance approver for
any instance in no part. Each gets a card in the chat they last had with a5s, such as
Teams, or a message with a link elsewhere, saying what the version changes in words code
works out. The card only opens the core's page. Decisions are taken there, apart from the
conversation, and never by telling an agent.

On the page, the approver signs in afresh at the organisation's identity provider, with a
nonce that commits to approving exactly this version, so the provider's signature covers
the decision. The channels app checks the sign-in: that it's recent, for this version, and
from someone who approves instances. It records it once, with the sign-in itself, since a
signature works for one decision. The gateway checks the sign-in again, and seals the
approval with a key only the core holds, which the channels app never has (core/sealing.py).
The approval keeps counting after the provider rotates its keys, and nobody who can only edit
the database can make one. The core checks the seal again at every run, as it checks
signatures made with keys, and the approver must still hold their role. Once everyone a
version needs has approved it, the gateway applies it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from collections.abc import Callable, Iterable
from typing import Any

from a5s import db
from a5s.contract import DataProtection, InstanceSettings, Person, Settings, Spending
from a5s.core import memberships, registry, sealing
from a5s.core.identity import (
    IdentityError,
    UnknownPerson,
    Verifier,
    second_factor,
    whose,
    without_second_factor,
)
from a5s.core.languages import ENGLISH
from a5s.core.ledger import canonical
from a5s.core.words import say
from a5s.definitions import Definition

log = logging.getLogger(__name__)
FRESH = 600  # seconds: how recent the sign-in that approves a version must be
_SEALED = ("scenario", "digest", "person", "nonce", "salt", "issuer", "subject")
HASHED = "sha256:"  # how a sign-in is kept: by its hash, never as a token that still works

Directory = Callable[[str], Person | None]


class Refused(Exception):
    def __init__(self, status: int, reason: str, second_factor: str | None = None):
        super().__init__(reason)
        self.status, self.reason = status, reason
        self.second_factor = second_factor  # what was refused for want of one, to count it


# What approving an instance's `asks` lets through, its `hands_to` (core/handover.py) and its
# `shadows` (core/shadows.py), in words, as a new instance's and as a change: each sentence whole,
# so it reads whole in each language a5s has the words in (core/words.py)
ASKS = ("It may ask {asked} questions, for the people it acts for, which each answers from the "
        "records in its own parts that those people may see.")
ASKS_MORE = ("{id} may ask {asked} questions, for the people it acts for, which each answers from "
             "the records in its own parts that those people may see.")
HANDS = ("It may hand a conversation over, at its agent's word, to the people of {teams}, who "
         "read its brief and what the person said, and answer them in the same chat until they "
         "hand it back.")
HANDS_MORE = ("{id} may hand a conversation over, at its agent's word, to the people of {teams}, "
              "who read its brief and what the person said, and answer them in the same chat "
              "until they hand it back.")
SHADOWS = ("It's a shadow: it answers what {live} is asked, beside it, as the same people, "
           "sending and changing nothing: graders read its answers beside those sent.")
SHADOWS_NOW = ("{id} answers what {live} is asked, beside it, as the same people, sending and "
               "changing nothing: graders read its answers beside those sent, as a shadow.")


def _teams(teams: Iterable[str], language: str = ENGLISH) -> str:
    """Teams of the directory, in words: the finance team, or the finance and quality teams."""
    named = list(teams)
    if len(named) == 1:
        return say(language, "the {team} team", team=named[0])
    return say(language, "the {teams} and {last} teams", teams=", ".join(named[:-1]),
               last=named[-1])


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def nonce(version: str, salt: str) -> str:
    """What a sign-in to approve a version carries, so the provider's signature covers the
    decision. The page picks the salt, so each sign-in is different."""
    bound = hashlib.sha256(f"a5s approves settings {version} {salt}".encode()).digest()
    return base64.urlsafe_b64encode(bound).rstrip(b"=").decode()


# Sealing: what the core checked, it vouches for with a key only it holds

def seal(keys: tuple[str, ...], approval: dict) -> str:
    """The core's seal over an approval, with the first of its keys."""
    return _mac(keys[0], approval)


def sealed(keys: tuple[str, ...], approval: dict) -> bool:
    """Whether the core sealed this approval with any of its keys: the first seals, and any
    others are ones it's moving away from."""
    return any(hmac.compare_digest(_mac(key, approval), approval["seal"]) for key in keys)


def _mac(key: str, approval: dict) -> str:
    fields = {k: approval[k] for k in _SEALED}
    token = approval["token"]  # the sign-in, kept by its hash only once it's recorded
    fields["token"] = (token.removeprefix(HASHED) if token.startswith(HASHED)
                       else hashlib.sha256(token.encode()).hexdigest())
    if approval.get("groups") is not None:  # the groups its sign-in showed, once kept
        fields["groups"] = sorted(approval["groups"])
    return hmac.new(key.encode(), canonical(fields).encode(), hashlib.sha256).hexdigest()


def vouch(keys: tuple[str, ...], scenario: str, serial: int, raw: bytes) -> str:
    """The core's seal on a version of the settings it checked while it was in force."""
    return _vouching(keys[0], scenario, serial, raw)


def vouched(keys: tuple[str, ...], scenario: str, serial: int, raw: bytes,
            seal: str | None) -> bool:
    """Whether the core sealed this version, with any of its keys, while it was in force."""
    return bool(seal) and any(hmac.compare_digest(_vouching(key, scenario, serial, raw), seal)
                              for key in keys)


def _vouching(key: str, scenario: str, serial: int, raw: bytes) -> str:
    fields = {"scenario": scenario, "serial": serial, "raw": hashlib.sha256(raw).hexdigest()}
    return hmac.new(key.encode(), b"a5s settings in force\n" + canonical(fields).encode(),
                    hashlib.sha256).hexdigest()


# Proposing a version, and saying what it changes

def propose(conn: db.Connection, scenario: str, settings: Settings,
            base: int | None = None) -> tuple[dict, bool]:
    """Record a version for the instance approvers to approve, written against the version in
    force, `base`, by its serial: its record, and whether it's new."""
    version = digest(settings.raw)
    row = conn.execute(
        "insert into settings_proposals (scenario, digest, version, serial, raw, base) "
        "values (%s, %s, %s, %s, %s, %s) on conflict do nothing returning *",
        (scenario, version, settings.version, settings.serial, settings.raw, base)).fetchone()
    if row is not None:
        return row, True
    return conn.execute("select * from settings_proposals where scenario = %s and digest = %s",
                        (scenario, version)).fetchone(), False


def stale(row: dict, last: dict | None) -> bool:
    """Whether a proposed version was written against another version than the one in force:
    its approvers reviewed what it changes from that, so it never comes into force on this."""
    return (last["serial"] if last else None) != row.get("base")


def latest(conn: db.Connection, scenario: str) -> dict | None:
    """The version in force: the one applied last."""
    return conn.execute("select serial, version, raw from settings_versions where scenario = %s "
                        "order by serial desc limit 1", (scenario,)).fetchone()


class Words:
    """How code puts a version of the settings in words, from the releases and the directory,
    in the language someone reads, where a5s has the words (core/words.py): English otherwise."""

    def __init__(self, definitions: dict[str, Definition], directory: Directory,
                 language: str = ENGLISH):
        self.definitions, self.directory, self.language = definitions, directory, language

    def say(self, text: str, **given: object) -> str:
        return say(self.language, text, **given)

    def names(self, people: Any) -> str:
        return names_of([self.name(pid) for pid in sorted(people)], self.language)

    def name(self, entry: str) -> str:
        """Someone, by name, or a group, as the directory decides who is in it at the time."""
        if entry.startswith("team:"):
            return self.say("everyone in the {team} team", team=entry[5:])
        if entry.startswith("role:"):
            return self.say("everyone who holds the {role} role", role=entry[5:])
        return p.name if (p := self.directory(entry)) else entry

    def actions(self, instance: InstanceSettings) -> dict[tuple[str, str], int]:
        """Its level for each type of action in each part, within its release's maximum."""
        release = self.definitions.get(instance.definition)
        found = registry.action_levels(instance, release) if release else instance.actions
        return {(p, a): lv for p, acts in found.items() for a, lv in acts.items()}

    def limits(self, settings: Settings) -> dict[str, str]:
        """The scenario's limit for each type of action, in words."""
        said = {}
        for action, limit in sorted(settings.limits.items()):
            parts = ([self.say("{n} in one run", n=limit["per_run"])] if "per_run" in limit
                     else []) + ([self.say("{n} for one person in 30 days",
                                           n=limit["per_person_30_days"])]
                                 if "per_person_30_days" in limit else [])
            said[action] = names_of(parts, self.language) if parts else self.say("no limit")
        return said

    def levels(self, instance: InstanceSettings) -> tuple[int | None, dict[str, int | None]]:
        release = self.definitions.get(instance.definition)
        if release is None:
            return instance.level, {p: lv if lv is not None else instance.level
                                    for p, lv in instance.parts.items()}
        return registry.levels(instance, release)

    def where(self, instance: InstanceSettings) -> str:
        level, parts = self.levels(instance)
        if not parts:
            return self.say("in no part, at level {level}", level=level)
        return self.say("working in {parts}", parts=names_of(
            [self.say("{part} at level {level}", part=p, level=lv) for p, lv in parts.items()],
            self.language))

    def owner(self, instance: InstanceSettings, who: str) -> str | None:
        release = self.definitions.get(instance.definition)
        return getattr(instance, who) or (getattr(release, who) if release else None)

    def classes(self, settings: Settings) -> str:
        own = [self.say("{field} is {data_class}", field=field, data_class=cls)
               for field, cls in sorted(settings.classified.items())]
        return self.say("{data_class}, except that {own}", data_class=settings.data_class,
                        own=names_of(own, self.language)) if own else settings.data_class


def changes(before: Settings | None, after: Settings, definitions: dict[str, Definition],
            directory: Directory, language: str = ENGLISH) -> list[dict]:
    """What a version changes from the one in force, in words code works out, in the language
    someone reads, each with whether it widens what agents do. A change to the classes of data
    counts as widening, since a5s can't tell which classes are wider."""
    words = Words(definitions, directory, language)
    said = words.say
    was = {i.id: i for i in before.instances} if before else {}
    found: list[dict] = []
    if before is not None and words.classes(before) != words.classes(after):
        found.append({"text": said("The scenario's data becomes {now}, instead of {was}.",
                                   now=words.classes(after), was=words.classes(before)),
                      "widens": True})
    limits_was = words.limits(before) if before else {}
    limits_now = words.limits(after)
    for action, now in limits_now.items():
        if limits_was.get(action) != now:
            earlier = before.limits.get(action) if before else None
            found.append({"text": said("The limit for {action} becomes {now}, instead of {was}.",
                                       action=action, now=now, was=limits_was[action])
                          if action in limits_was else
                          said("The limit for {action} becomes {now}.", action=action, now=now),
                          "widens": _looser(earlier, after.limits[action])})
    for action in sorted(set(limits_was) - set(limits_now)):
        found.append({"text": said("{action} has no limit any more, instead of {was}.",
                                   action=action, was=limits_was[action]), "widens": True})
    thresholds_was = before.thresholds if before else {}
    for part in sorted(set(thresholds_was) | set(after.thresholds)):
        a, b = thresholds_was.get(part), after.thresholds.get(part)
        if a != b:
            share = _percent(b) if b else said("none, so none earns it")
            found.append({"text": said("The accuracy {part} needs before an agent earns level 2 "
                                       "there becomes {share}, instead of {was}.", part=part,
                                       share=share, was=_percent(a)) if a else
                          said("The accuracy {part} needs before an agent earns level 2 there "
                               "becomes {share}.", part=part, share=share),
                          "widens": b is not None and (a is None or b < a)})
    found += _spending(before.spending if before else Spending(), after.spending, language)
    asked = {i.id: i.definition for i in after.instances}
    for new in after.instances:
        old = was.pop(new.id, None)
        if old is None:
            given = {"id": new.id, "agent": new.definition, "where": words.where(new),
                     "whom": words.names(new.serves)}
            owner = words.owner(new, "owner")
            found.append({"text": " ".join([
                said("Adds {id}: the {agent}, {where}, serving {whom}, run by {owner}.",
                     owner=words.names([owner]), **given) if owner else
                said("Adds {id}: the {agent}, {where}, serving {whom}.", **given),
                *_reaches(words, new, asked)]), "widens": True})
            continue
        if new.shadows != old.shadows:
            found.append({"text": said(SHADOWS_NOW, id=new.id, live=new.shadows) if new.shadows
                          else said("{id} is no longer a shadow of {live}: it works for its "
                                    "people itself.", id=new.id, live=old.shadows),
                          "widens": True})
        if more := [t for t in new.hands_to if t not in old.hands_to]:
            found.append({"text": said(HANDS_MORE, id=new.id, teams=_teams(more, language)),
                          "widens": True})
        if fewer := [t for t in old.hands_to if t not in new.hands_to]:
            found.append({"text": said("{id} no longer hands conversations to {teams}.",
                                       id=new.id, teams=_teams(fewer, language)),
                          "widens": False})
        if more := [a for a in new.asks if a not in old.asks]:
            found.append({"text": said(ASKS_MORE, id=new.id,
                                       asked=_asked(more, asked, language)), "widens": True})
        if fewer := [a for a in old.asks if a not in new.asks]:
            found.append({"text": said("{id} no longer asks {asked}.", id=new.id,
                                       asked=_asked(fewer, asked, language)), "widens": False})
        if new.definition != old.definition:
            found.append({"text": said("{id} becomes the {agent}, instead of the {was}.",
                                       id=new.id, agent=new.definition, was=old.definition),
                          "widens": True})
        if more := set(new.serves) - set(old.serves):
            found.append({"text": said("{id} serves {whom} as well.", id=new.id,
                                       whom=words.names(more)), "widens": True})
        if fewer := set(old.serves) - set(new.serves):
            found.append({"text": said("{id} no longer serves {whom}.", id=new.id,
                                       whom=words.names(fewer)), "widens": False})
        (a, was_in), (b, now_in) = words.levels(old), words.levels(new)
        if not was_in and not now_in and a != b:
            found.append({"text": said("{id}'s level goes from {was} to {now}.", id=new.id,
                                       was=a, now=b), "widens": (b or 0) > (a or 0)})
        for part in sorted(set(now_in) - set(was_in)):
            found.append({"text": said("{id} works in {part} as well, at level {level}.",
                                       id=new.id, part=part, level=now_in[part]),
                          "widens": True})
        for part in sorted(set(was_in) - set(now_in)):
            found.append({"text": said("{id} no longer works in {part}.", id=new.id, part=part),
                          "widens": False})
        for part in sorted(set(was_in) & set(now_in)):
            if (a := was_in[part]) != (b := now_in[part]):
                found.append({"text": said("{id}'s level in {part} goes from {was} to {now}.",
                                           id=new.id, part=part, was=a, now=b),
                              "widens": (b or 0) > (a or 0)})
        acts_was, acts_now = words.actions(old), words.actions(new)
        for part, action in sorted(set(acts_was) | set(acts_now)):
            a = acts_was.get((part, action), min(was_in.get(part) or 0, 1) if part in was_in else None)
            b = acts_now.get((part, action), min(now_in.get(part) or 0, 1) if part in now_in else None)
            if a != b and b is not None:
                given = {"id": new.id, "action": action, "part": part, "now": b,
                         "was": a if a is not None else said("none")}
                found.append({"text": said("{id}'s level for {action} in {part} goes from {was} "
                                           "to {now}, where it acts and reports, once samples "
                                           "show it's accurate enough.", **given) if b >= 2 else
                              said("{id}'s level for {action} in {part} goes from {was} to "
                                   "{now}.", **given),
                              "widens": b > (a or 0)})
        for who in ("owner", "deputy"):
            if (a := words.owner(old, who)) != (b := words.owner(new, who)):
                given = {"id": new.id, "was": words.names([a]) if a else said("nobody"),
                         "now": words.names([b]) if b else said("nobody")}
                found.append({"text": said("{id}'s owner changes from {was} to {now}.", **given)
                              if who == "owner" else
                              said("{id}'s deputy changes from {was} to {now}.", **given),
                              "widens": False})
    for gone in was.values():
        found.append({"text": said("Retires {id}, which served {whom}.", id=gone.id,
                                   whom=words.names(gone.serves)), "widens": False})
    given_by = before.groups if before else {}  # the roles groups give, in the identity provider
    for group in sorted(set(given_by) | set(after.groups)):
        a, b = set(given_by.get(group, ())), set(after.groups.get(group, ()))
        if more := sorted(b - a):
            found.append({"text": said(HOLDS, group=group, roles=names_of(more, language)),
                          "widens": True})
        if fewer := sorted(a - b):
            found.append({"text": said("The group {group} no longer gives {roles}.", group=group,
                                       roles=names_of(fewer, language)), "widens": False})
    found += _protection(before.data_protection if before else DataProtection(),
                         after.data_protection, language)
    return found or [{"text": said("It changes nothing the agents do: only its number or its "
                                   "notes."), "widens": False}]


# A group's members holding a role, as a version that gives it says it, and a whole version does
HOLDS = "Everyone in the group {group} holds {roles}, as their sign-ins show they're in it."


# The data protection officer's choices that name people, in words: as each stands on, and off
# (contract.DataProtection), as a version that changes one says it, and a whole version does
NAMING = {
    "studio_names": ("The studio's pages name whom each run acted for.",
                     "The studio's pages say how many people each run acted for, never who."),
    "audit_names": ("The auditors' page names whom agents acted for, and exports the ledger.",
                    ("The auditors' page shows stand-ins for whom agents acted for, and exports "
                     "nothing.")),
    "flag_rubber_stamps": (("The status names the deciders whose approvals are graded wrong far "
                            "more often than others'."),
                           ("The status names no decider for how often their approvals are "
                            "graded wrong.")),
    "cases_from_runs": (("Those who author an agent may keep one of its runs as a test case, "
                         "where every one of them may see the run: what someone said to it, "
                         "masked by code and checked by whoever keeps it. Every author of the "
                         "agent reads it, and once it's released, so does everyone who reads the "
                         "agents' repository."),
                        ("No run of an agent's becomes a test case: its cases are made up.")),
    "shadow_runs": (("A shadow may answer what people ask the instance it shadows, beside it, "
                     "sending and changing nothing: it reads what they say and what their records "
                     "hold, and graders read what it answered beside what was sent, with "
                     "what they said, masked by code unless names are shown, as the studio shows "
                     "runs."),
                    ("No shadow answers what people ask: a new version is tried on test cases "
                     "alone.")),
}


def money(amount: float, currency: str | None = None) -> str:
    """An amount, whole or with its cents, which a budget is in, in the currency it names, or
    in the one models.yaml prices models in, which the words then say they're in."""
    said = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
    return f"{currency} {said}" if currency else said


def _in(currency: str | None, language: str = ENGLISH) -> str:
    return currency or say(language, "the currency models.yaml prices models in")


def _spending(was: Spending, now: Spending, language: str = ENGLISH) -> list[dict]:
    """What a version changes of what agents may cost a month, in words: none widens what
    agents do, since a budget stops no work."""
    found = []
    if was.currency != now.currency and (now.agents or was.agents):
        found.append({"text": say(language, "Budgets are in {now}, instead of {was}.",
                                  now=_in(now.currency, language), was=_in(was.currency, language)),
                      "widens": False})
    a, b = was.agents, now.agents
    for name in sorted(set(a) | set(b)):
        if a.get(name) == b.get(name) and was.currency == now.currency:
            continue
        if name not in b:
            text = say(language, "There's no budget for the {name} any more, instead of {was} a "
                       "month.", name=name, was=money(a[name], was.currency))
        elif name in a:
            text = say(language, "The budget for the {name} becomes {amount} a month, instead of "
                       "{was}: what its model calls may cost, which a5s shows spending against, "
                       "and which stops no work.", name=name, amount=money(b[name], now.currency),
                       was=money(a[name], was.currency))
        else:
            text = say(language, "The budget for the {name} becomes {amount} a month: what its "
                       "model calls may cost, which a5s shows spending against, and which stops "
                       "no work.", name=name, amount=money(b[name], now.currency))
        found.append({"text": text, "widens": False})
    return found


def _days(kept: str) -> float:
    """How long a kept_for is, in days, a month being a twelfth of a year."""
    n, unit = kept.split()
    return int(n) * (1 if unit.startswith("day") else 365.25 / 12)


def _period(kept: str, language: str = ENGLISH) -> str:
    """A kept_for, such as 90 days, as someone reads it: as written, in English."""
    if language == ENGLISH:
        return kept
    n, unit = kept.split()
    return say(language, "{n} days" if unit.startswith("day") else "{n} months", n=n)


def _protection(was: DataProtection, now: DataProtection, language: str = ENGLISH) -> list[dict]:
    """What a version changes of the data protection officer's choices, in words: each widens
    what a5s does with people's data if it keeps it longer, names people, or lets an instance's
    figures out when it serves fewer of them."""
    found = []
    if was.kept_for != now.kept_for:
        found.append({"text": say(language, "a5s keeps what's said for {kept} after a "
                                  "conversation's last message, and what goes with it, instead of "
                                  "{was}.", kept=_period(now.kept_for, language),
                                  was=_period(was.kept_for, language)),
                      "widens": _days(now.kept_for) > _days(was.kept_for)})
    if was.fewest_people != now.fewest_people:
        found.append({"text": say(language, "An instance's own figures go out to the team's "
                                  "dashboards once it serves {n} people, instead of {was}.",
                                  n=now.fewest_people, was=was.fewest_people),
                      "widens": now.fewest_people < was.fewest_people})
    for name, (on, off) in NAMING.items():
        if (turned := getattr(now, name)) != getattr(was, name):
            found.append({"text": say(language, on if turned else off), "widens": turned})
    return found


def protection(choices: DataProtection, language: str = ENGLISH) -> list[str]:
    """The data protection officer's choices, each in words, as a whole version says them."""
    return [say(language, "a5s keeps what's said for {kept} after a conversation's last message, "
                "and what goes with it.", kept=_period(choices.kept_for, language)),
            say(language, "An instance's own figures go out to the team's dashboards once it "
                "serves {n} people or more.", n=choices.fewest_people),
            *(say(language, on if getattr(choices, name) else off)
              for name, (on, off) in NAMING.items())]


def _asked(ids: list[str] | tuple[str, ...], definitions: dict[str, str],
           language: str = ENGLISH) -> str:
    """The instances an instance may ask, in words: the watcher (watcher-finance)."""
    return names_of([say(language, "the {agent} ({id})", agent=definitions[a], id=a)
                     if a in definitions else a for a in ids], language)


def _reaches(words: Words, instance: InstanceSettings, asked: dict[str, str]) -> list[str]:
    """Whom an instance may ask and hand conversations to, and which it shadows, in words, each a
    sentence of its own."""
    return ([words.say(ASKS, asked=_asked(instance.asks, asked, words.language))]
            if instance.asks else []) + (
        [words.say(HANDS, teams=_teams(instance.hands_to, words.language))]
        if instance.hands_to else []) + (
        [words.say(SHADOWS, live=instance.shadows)] if instance.shadows else [])


def _percent(share: float) -> str:
    return f"{share * 100:g}%"


def _looser(was: dict[str, int] | None, now: dict[str, int]) -> bool:
    """Whether a type of action's new limit lets more through than its old one: a limit that's
    new only narrows, and one that rises or goes widens."""
    return was is not None and any(k not in now or now[k] > v for k, v in was.items())


def described(settings: Settings, definitions: dict[str, Definition],
              directory: Directory, language: str = ENGLISH) -> list[str]:
    """A whole version of the settings in words, for reviewing all of it before approving it, in
    the language someone reads."""
    words = Words(definitions, directory, language)
    said = words.say
    told = [said("The scenario's data is {classes}.", classes=words.classes(settings))]
    asked = {j.id: j.definition for j in settings.instances}
    for i in settings.instances:
        given = {"id": i.id, "agent": i.definition, "where": words.where(i),
                 "whom": words.names(i.serves)}
        owner, deputy = words.owner(i, "owner"), words.owner(i, "deputy")
        if owner and deputy:
            first = said("{id}: the {agent}, {where}, serving {whom}, run by {owner} with "
                         "{deputy} as deputy.", owner=words.names([owner]),
                         deputy=words.names([deputy]), **given)
        elif owner:
            first = said("{id}: the {agent}, {where}, serving {whom}, run by {owner}.",
                         owner=words.names([owner]), **given)
        elif deputy:
            first = said("{id}: the {agent}, {where}, serving {whom}, with {deputy} as deputy.",
                         deputy=words.names([deputy]), **given)
        else:
            first = said("{id}: the {agent}, {where}, serving {whom}.", **given)
        told.append(" ".join([first, *_reaches(words, i, asked)]))
        told += [said("{id} works at level {level} for {action} in {part}, where it acts and "
                      "reports, once graded samples show it's accurate enough: until then a5s "
                      "holds it at level 1.", id=i.id, level=lv, action=action, part=part)
                 if lv >= 2 else
                 said("{id} works at level {level} for {action} in {part}.", id=i.id, level=lv,
                      action=action, part=part)
                 for (part, action), lv in sorted(words.actions(i).items())]
    if not settings.instances:
        told.append(said("No instances: every agent here is retired."))
    told += [said("Limit for {action}: {limit}.", action=action, limit=limit)
             for action, limit in words.limits(settings).items()]
    told += [said("An agent earns level 2 in {part} once graded samples show it's {share} "
                  "accurate.", part=part, share=_percent(share))
             for part, share in sorted(settings.thresholds.items())]
    told += [said(HOLDS, group=group, roles=names_of(list(roles), language))
             for group, roles in sorted(settings.groups.items())]
    currency = settings.spending.currency
    told += [said("The budget for the {name} is {amount} a month: what its model calls may "
                  "cost, which a5s shows spending against.", name=name,
                  amount=money(amount, currency)) if currency else
             said("The budget for the {name} is {amount} a month: what its model calls may "
                  "cost, which a5s shows spending against, in the currency models.yaml prices "
                  "models in.", name=name, amount=money(amount, currency))
             for name, amount in sorted(settings.spending.agents.items())]
    return told + protection(settings.data_protection, language)


def names_of(found: list[str], language: str = ENGLISH) -> str:
    """Things in a list, in words: a, b and c, or nobody."""
    if not found:
        return say(language, "nobody")
    return found[0] if len(found) == 1 else say(language, "{first} and {last}",
                                                first=", ".join(found[:-1]), last=found[-1])


def card(serial: int, found: list[dict], link: str, language: str = ENGLISH) -> dict:
    """The card an approver gets in Teams or Slack, in the language they read. It only opens the
    core's page, where they decide."""
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": say(language, "Settings to approve"), "weight": "Bolder",
             "size": "Medium", "wrap": True},
            {"type": "TextBlock", "wrap": True,
             "text": f"{_waits(serial, language)} {say(language, 'What it changes:')}"},
            {"type": "TextBlock", "wrap": True,
             "text": "\n".join(f"- {c['text']}" for c in found)},
            {"type": "TextBlock", "wrap": True, "isSubtle": True, "size": "Small",
             "text": say(language, "You decide on a5s's page, after signing in again. Telling an "
                                   "agent doesn't approve anything.")},
        ],
        "actions": [{"type": "Action.OpenUrl", "title": say(language, "Review and approve"),
                     "url": link}],
    }


def text(serial: int, found: list[dict], link: str, language: str = ENGLISH) -> str:
    """The same, for chats without cards. Its first line says what it's about."""
    said = "\n".join(f"- {c['text']}" for c in found)
    return (f"{_waits(serial, language)}\n{say(language, 'What it changes:')}\n{said}\n"
            + say(language, "Review it, and approve it only if you mean it, at {link}", link=link))


def _waits(serial: int, language: str = ENGLISH) -> str:
    return say(language, "Version {serial} of a5s's settings waits for its instance approvers to "
                         "approve it.", serial=serial)


# Approving

APPROVERS = ("only a part's or an agent's owner, an instance approver, the data protection "
             "officer or assurance can approve settings, and {name} is none of them")


def afresh(verifier: Verifier, scenario: Any, client_id: str, token: str, bound: str,
           salt: str, now: float, what: str, factor: str | None) -> tuple[Person, dict]:
    """Who signed in afresh to do one thing that counts, `what`, which the sign-in's nonce,
    `bound`, commits to, and what the provider signed, if the sign-in checks out for it: made
    for a5s's pages, salted as the studio salts it, from the last ten minutes rather than one
    the browser kept, with a second factor where the deployment asks for one, unless `factor`,
    the act as a refusal for want of one names it, is None, and by someone the directory
    knows. Otherwise, Refused, saying why. Every act that counts signs in through it, for its
    own route, and the gateway checks each sign-in again for itself (core/sealing.py)."""
    try:
        claims = verifier.claims(token)
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    audience = claims.get("aud")
    if client_id not in ([audience] if isinstance(audience, str) else audience or []):
        raise Refused(401, "that sign-in is for something else")
    if not isinstance(claims.get("auth_time"), int | float) or any(
            not isinstance(claims.get(c), int | float) or now - claims[c] > FRESH
            for c in ("iat", "auth_time")):  # a session's silent sign-in does nothing that counts
        raise Refused(401, f"to {what}, sign in again, from the last ten minutes, not with a "
                           "sign-in your browser kept")  # first: what one the browser kept needs
    if factor is not None and not second_factor(verifier.cfg, claims):
        raise Refused(401, without_second_factor(factor), factor.split()[0])
    if not sealing.salted(salt) or claims.get("nonce") != bound:
        raise Refused(403, f"your sign-in wasn't to {what}")
    try:
        person = whose(verifier, scenario, claims)
    except UnknownPerson as exc:
        raise Refused(403, str(exc)) from None
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    return person, claims


def check(verifier: Verifier, scenario: Any, client_id: str, token: str, version: str,
          salt: str, now: float) -> tuple[Person, dict]:
    """Who signed in to approve this version, and what the provider signed, if the sign-in
    checks out for it and they may approve settings. Otherwise, Refused."""
    person, claims = afresh(verifier, scenario, client_id, token, nonce(version, salt), salt,
                            now, "approve this version", "approve")
    if not registry.approves(person):
        raise Refused(403, APPROVERS.format(name=person.name))
    return person, claims


def record(conn: db.Connection, scenario: str, version: str, person: str, token: str,
           salt: str, claims: dict) -> dict:
    """Record an approval, with the sign-in that made it, for the gateway to seal. Refused if
    the person has approved this version already, or the sign-in was used before."""
    approval = {"scenario": scenario, "digest": version, "person": person,
                "token": HASHED + hashlib.sha256(token.encode()).hexdigest(),  # kept, not usable
                "nonce": claims["nonce"], "salt": salt, "issuer": claims["iss"],
                "subject": str(claims.get("sub") or ""), "proof": token}
    if conn.execute("select 1 from settings_approvals where scenario = %s and digest = %s "
                    "and person = %s and refused is null", (scenario, version, person)).fetchone():
        raise Refused(409, "you've approved this version already")  # unless it was refused
    row = conn.execute(
        "insert into settings_approvals (scenario, digest, person, token, nonce, salt, issuer, "
        "subject, proof) values (%(scenario)s, %(digest)s, %(person)s, %(token)s, %(nonce)s, "
        "%(salt)s, %(issuer)s, %(subject)s, %(proof)s) on conflict do nothing "
        "returning id, approved_at", approval).fetchone()
    if row is None:
        raise Refused(409, "that sign-in has been used: sign in again")
    return {**approval, **row}


def recorded(conn: db.Connection, scenario: str, version: str) -> list[str]:
    """Who has approved a version, as the channels app recorded it, sealed yet or not: for
    saying who's still needed. Only what the gateway sealed counts (approvers)."""
    return [r["person"] for r in conn.execute(
        "select person from settings_approvals where scenario = %s and digest = %s "
        "and refused is null order by id", (scenario, version))]


def seal_pending(conn: db.Connection, keys: tuple[str, ...], verifier: Verifier | None,
                 scenario: Any, client_id: str | None) -> list[sealing.Refusal]:
    """Check again each approval the channels app recorded, seal it, and let its sign-in go,
    in the gateway: or refuse it, and tell its approver, who may approve again. One whose
    sign-in can't be checked just now, since the identity provider can't be reached, waits.
    Why each refused one was."""
    if not keys:
        return []  # it waits for a gateway that can seal it
    refused = []
    for row in conn.execute("select * from settings_approvals where scenario = %s and seal is "
                            "null and refused is null order by id for update skip locked",
                            (scenario.name,)).fetchall():
        try:
            why = sealing.check(verifier, scenario, client_id, row["proof"],
                                nonce(row["digest"], row["salt"]), row["person"])
        except sealing.Unchecked:
            continue  # checked again at the next sweep
        if why is not None:
            log.error("an approval of settings %s by %s is refused: %s", row["digest"],
                      row["person"], why)
            conn.execute("update settings_approvals set refused = %s, proof = null where id = %s",
                         (why, row["id"]))
            version = conn.execute("select serial from settings_proposals where scenario = %s "
                                   "and digest = %s", (row["scenario"], row["digest"])).fetchone()
            refused.append(sealing.Refusal(
                row["person"], f"{row['person']}'s approval: {why}",
                (("Your approval of version {serial} of the settings didn't count: {why}. If it "
                  "still waits for you, approve it again on the settings page, signing in afresh."),
                 {"serial": version["serial"] if version else "?", "why": why})))
            continue
        claim = verifier.cfg.groups_claim if verifier else None  # checked, so it's there
        groups = list(memberships.shown(verifier.claims(row["proof"], expired=True), claim)
                      if verifier else ())
        kept = {**row, "groups": groups}
        conn.execute("update settings_approvals set seal = %s, groups = %s, proof = null "
                     "where id = %s", (seal(keys, kept), groups, row["id"]))
    return refused


def groups_shown(conn: db.Connection, scenario: str, version: str) -> dict[str, tuple[str, ...]]:
    """The groups each approval of a version showed, in the sign-in it was made with, as the
    core kept them under its seal once it had checked it: what it counts for, with the groups
    the approver's latest sign-in shows (core/memberships.py's as_signed)."""
    return {r["person"]: tuple(r["groups"] or ()) for r in conn.execute(
        "select person, groups from settings_approvals where scenario = %s and digest = %s "
        "and refused is null and seal is not null", (scenario, version))}


def approvers(conn: db.Connection, keys: tuple[str, ...], scenario: str,
              version: str) -> tuple[list[str], list[str]]:
    """Who approved a version, by approvals the core sealed, and what's wrong with any other."""
    valid, problems = [], []
    for row in conn.execute("select * from settings_approvals where scenario = %s and digest = %s "
                            "and refused is null and (seal is not null or proof is null) "
                            "order by id", (scenario, version)):
        if keys and row["seal"] and sealed(keys, row):
            valid.append(row["person"])
        else:
            log.error("an approval of settings %s by %s isn't one the core sealed", version,
                      row["person"])
            problems.append(f"{row['person']}'s approval isn't one the core sealed")
    return valid, problems
