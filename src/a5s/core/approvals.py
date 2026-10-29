"""Approving settings where people work: a card in their chat, and the decision on the
core's own page.

A version of the settings can be proposed to the instance approvers rather than signed
with their keys. Each approver gets a card in the chat they last had with a5s, such as
Teams, or a message with a link elsewhere, saying what the version changes in words code
works out. The card only opens the core's page. Decisions are taken there, apart from the
conversation, and never by telling an agent.

On the page, the approver signs in afresh at the organisation's identity provider, with a
nonce that commits to approving exactly this version, so the provider's signature covers
the decision. The core checks the sign-in: that it's recent, for this version, and from an
instance approver. It records it once, since a signature works for one decision. Then it
seals the approval with a key only the core holds. The approval keeps counting after the
provider rotates its keys, and nobody who can only edit the database can make one. The core
checks the seal again at every run, as it checks signatures made with keys, and the
approver must still hold the role. Once a version has an instance approver's approval,
the gateway applies it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from collections.abc import Callable
from typing import Any

import psycopg

from a5s.contract import INSTANCE_APPROVER, InstanceSettings, Person, Settings
from a5s.core.identity import IdentityError, UnknownPerson, Verifier, whose
from a5s.core.ledger import canonical
from a5s.definitions import Definition

log = logging.getLogger(__name__)
FRESH = 600  # seconds: how recent the sign-in that approves a version must be
_SEALED = ("scenario", "digest", "person", "nonce", "salt", "issuer", "subject")

Directory = Callable[[str], Person | None]


class Refused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


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
    fields["token"] = hashlib.sha256(approval["token"].encode()).hexdigest()
    return hmac.new(key.encode(), canonical(fields).encode(), hashlib.sha256).hexdigest()


# Proposing a version, and saying what it changes

def propose(conn: psycopg.Connection, scenario: str, settings: Settings) -> tuple[dict, bool]:
    """Record a version for the instance approvers to approve: its record, and whether it's new."""
    version = digest(settings.raw)
    row = conn.execute(
        "insert into settings_proposals (scenario, digest, version, serial, raw) "
        "values (%s, %s, %s, %s, %s) on conflict do nothing returning *",
        (scenario, version, settings.version, settings.serial, settings.raw)).fetchone()
    if row is not None:
        return row, True
    return conn.execute("select * from settings_proposals where scenario = %s and digest = %s",
                        (scenario, version)).fetchone(), False


def latest(conn: psycopg.Connection, scenario: str) -> dict | None:
    """The version in force: the one applied last."""
    return conn.execute("select serial, version, raw from settings_versions where scenario = %s "
                        "order by serial desc limit 1", (scenario,)).fetchone()


def changes(before: Settings | None, after: Settings, definitions: dict[str, Definition],
            directory: Directory) -> list[dict]:
    """What a version changes from the one in force, in words code works out, each with
    whether it widens what agents do."""

    def names(people: Any) -> str:
        found = [p.name if (p := directory(pid)) else pid for pid in sorted(people)]
        return found[0] if len(found) == 1 else f"{', '.join(found[:-1])} and {found[-1]}"

    def level(instance: InstanceSettings) -> int | None:
        release = definitions.get(instance.definition)
        if release is None:
            return instance.level
        return min(release.autonomy.start if instance.level is None else instance.level,
                   release.autonomy.max)

    def owner(instance: InstanceSettings, who: str) -> str | None:
        release = definitions.get(instance.definition)
        return getattr(instance, who) or (getattr(release, who) if release else None)

    was = {i.id: i for i in before.instances} if before else {}
    found: list[dict] = []
    for new in after.instances:
        old = was.pop(new.id, None)
        if old is None:
            run_by = f", run by {names([o])}" if (o := owner(new, "owner")) else ""
            found.append({"text": f"Adds {new.id}: the {new.definition}, at level {level(new)}, "
                                  f"serving {names(new.serves)}{run_by}.", "widens": True})
            continue
        if new.definition != old.definition:
            found.append({"text": f"{new.id} becomes the {new.definition}, instead of the "
                                  f"{old.definition}.", "widens": True})
        if more := set(new.serves) - set(old.serves):
            found.append({"text": f"{new.id} serves {names(more)} as well.", "widens": True})
        if fewer := set(old.serves) - set(new.serves):
            found.append({"text": f"{new.id} no longer serves {names(fewer)}.", "widens": False})
        if (a := level(old)) != (b := level(new)):
            found.append({"text": f"{new.id}'s level goes from {a} to {b}.",
                          "widens": (b or 0) > (a or 0)})
        for who in ("owner", "deputy"):
            if (a := owner(old, who)) != (b := owner(new, who)):
                found.append({"text": f"{new.id}'s {who} changes from "
                                      f"{names([a]) if a else 'nobody'} to "
                                      f"{names([b]) if b else 'nobody'}.", "widens": False})
    for gone in was.values():
        found.append({"text": f"Retires {gone.id}, which served {names(gone.serves)}.",
                      "widens": False})
    return found or [{"text": "It changes nothing the agents do: only its serial or notes.",
                      "widens": False}]


def card(serial: int, found: list[dict], link: str) -> dict:
    """The card an approver gets in Teams. It only opens the core's page, where they decide."""
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": "Settings to approve", "weight": "Bolder",
             "size": "Medium", "wrap": True},
            {"type": "TextBlock", "wrap": True, "text": f"{_waits(serial)} What it changes:"},
            {"type": "TextBlock", "wrap": True,
             "text": "\n".join(f"- {c['text']}" for c in found)},
            {"type": "TextBlock", "wrap": True, "isSubtle": True, "size": "Small",
             "text": "You decide on a5s's page, after signing in again. Telling an agent "
                     "doesn't approve anything."},
        ],
        "actions": [{"type": "Action.OpenUrl", "title": "Review and approve", "url": link}],
    }


def text(serial: int, found: list[dict], link: str) -> str:
    """The same, for chats without cards. Its first line says what it's about."""
    said = "\n".join(f"- {c['text']}" for c in found)
    return (f"{_waits(serial)}\nWhat it changes:\n{said}\n"
            f"Review it, and approve it only if you mean it, at {link}")


def _waits(serial: int) -> str:
    return f"Serial {serial} of a5s's settings waits for an instance approver to approve it."


# Approving

def check(verifier: Verifier, scenario: Any, client_id: str, token: str, version: str,
          salt: str, now: float) -> tuple[Person, dict]:
    """Who signed in to approve this version, and what the provider signed, if the sign-in
    checks out for it. Otherwise, Refused."""
    try:
        claims = verifier.claims(token)
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    audience = claims.get("aud")
    if client_id not in ([audience] if isinstance(audience, str) else audience or []):
        raise Refused(401, "that sign-in is for something else")
    if not 16 <= len(salt) <= 128 or claims.get("nonce") != nonce(version, salt):
        raise Refused(403, "your sign-in wasn't to approve this version")
    if any(isinstance(claims.get(c), int | float) and now - claims[c] > FRESH
           for c in ("iat", "auth_time")):
        raise Refused(401, "approving needs a sign-in from the last ten minutes: sign in again")
    try:
        person = whose(verifier, scenario, claims)
    except UnknownPerson as exc:
        raise Refused(403, str(exc)) from None
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    if INSTANCE_APPROVER not in person.roles:
        raise Refused(403, f"only an {INSTANCE_APPROVER} can approve settings, and "
                           f"{person.name} isn't one")
    return person, claims


def record(conn: psycopg.Connection, keys: tuple[str, ...], scenario: str, version: str,
           person: str, token: str, salt: str, claims: dict) -> dict:
    """Record an approval, sealed. Refused if the person has approved this version already,
    or the sign-in was used before."""
    approval = {"scenario": scenario, "digest": version, "person": person, "token": token,
                "nonce": claims["nonce"], "salt": salt, "issuer": claims["iss"],
                "subject": str(claims.get("sub") or "")}
    approval["seal"] = seal(keys, approval)
    if conn.execute("select 1 from settings_approvals where scenario = %s and digest = %s "
                    "and person = %s", (scenario, version, person)).fetchone():
        raise Refused(409, "you've approved this version already")
    row = conn.execute(
        "insert into settings_approvals (scenario, digest, person, token, nonce, salt, issuer, "
        "subject, seal) values (%(scenario)s, %(digest)s, %(person)s, %(token)s, %(nonce)s, "
        "%(salt)s, %(issuer)s, %(subject)s, %(seal)s) on conflict do nothing "
        "returning id, approved_at", approval).fetchone()
    if row is None:
        raise Refused(409, "that sign-in has been used: sign in again")
    return {**approval, **row}


def approvers(conn: psycopg.Connection, keys: tuple[str, ...], scenario: str,
              version: str) -> tuple[list[str], list[str]]:
    """Who approved a version, by approvals the core sealed, and what's wrong with any other."""
    valid, problems = [], []
    for row in conn.execute("select * from settings_approvals where scenario = %s and digest = %s "
                            "order by id", (scenario, version)):
        if keys and sealed(keys, row):
            valid.append(row["person"])
        else:
            log.error("an approval of settings %s by %s isn't one the core sealed", version,
                      row["person"])
            problems.append(f"{row['person']}'s approval isn't one the core sealed")
    return valid, problems
