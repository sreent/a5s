"""Sealing: what people approve, decide and grade counts only once the gateway, in the trusted
core, has checked again the sign-in that made it, and sealed it with a key only the core holds.

The channels app, which people reach, checks each sign-in as it arrives, so people hear at
once when one doesn't check out, and records what they did with the sign-in itself. It holds
no seal key. Each minute the gateway, which nobody outside reaches, checks each recorded
sign-in again against the identity provider's own keys: that the provider signed it, for
a5s, with a nonce that commits to exactly what was recorded, from a sign-in made for it, with
a second factor if the deployment asks for one, for the person recorded, and less than a day
ago. Then it seals it and lets the sign-in go,
keeping its hash, so the seal outlasts the provider's keys. What doesn't check out is
refused, and never counts. So breaking into the channels app gives nobody the key that makes
anything count: it can only record what a person really signed in to do. A gateway without a
seal key or the identity provider leaves what's recorded waiting, which the status counts, and
so does one whose identity provider can't be reached just now: it checks again at the next
sweep, for up to a day, so a brief outage refuses nobody. A refusal doesn't stand in the way of
its person doing it again, with a new sign-in, and they hear of it in their digest.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import time
from dataclasses import dataclass
from typing import Any

import jwt

from a5s.core.identity import (
    IdentityError,
    IdentityUnavailable,
    UnknownPerson,
    Verifier,
    second_factor,
    whose,
)

FRESH = 600  # seconds: how long before a sign-in its person must have signed in afresh
OLDEST = 86_400  # seconds: a sign-in older than this, still unsealed, is refused
SALT = re.compile(r"[A-Za-z0-9_-]{16,128}")  # as the studio's `salted` makes one: base64url
RECORDED_ELSE = "the sign-in isn't recorded as itself, so it may have been used already"


def salted(salt: object) -> bool:
    """Whether a salt is one the studio makes: base64url, 16 to 128 characters. One with spaces,
    or anything else, could move words between what a nonce covers, such as a rejection's reason
    into its salt, or an id's last word (round 13, A3)."""
    return isinstance(salt, str) and SALT.fullmatch(salt) is not None


def as_itself(recorded: str | None, token: str | None) -> bool:
    """Whether a sign-in is recorded by its own hash. The channels app writes the hash beside
    the sign-in, and its table keeps the hash unique, so that each sign-in works once: one
    recorded again under another hash would work again (round 13, A2)."""
    if not recorded or not token:
        return False
    own = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(recorded.removeprefix("sha256:"), own)  # as approvals.HASHED


@dataclass(frozen=True)
class Refusal:
    """What the gateway refused to seal: whose it was, what the ledger says of it, and what
    they're told, in their digest, so they can do it again."""
    person: str | None
    what: str
    told: str | None = None


class Unchecked(Exception):
    """The identity provider couldn't be reached to check a sign-in just now, so it's neither
    sealed nor refused: it waits for the next sweep."""


def _age(token: str, now: float | None) -> float:
    """How old a sign-in says it is, unchecked: only ever to give up on one, never to take it."""
    try:
        issued = jwt.decode(token, options={"verify_signature": False}).get("iat")
    except jwt.PyJWTError:
        return math.inf
    if not isinstance(issued, int | float):
        return math.inf
    return (time.time() if now is None else now) - issued


def check(verifier: Verifier | None, scenario: Any, client_id: str | None, token: str | None,
          bound: str, person: str, now: float | None = None, factor: bool = True, *,
          recorded: tuple[str | None, str | None] | None = None,
          salt: str | None = None) -> str | None:
    """Why a recorded sign-in doesn't check out, if it doesn't: None if the provider signed it
    for a5s's client, with exactly the nonce `bound`, made afresh, for `person`, lately, with a
    second factor where the deployment asks for one, unless what it does only makes a5s safer
    (`factor` False). Where it's `recorded` by its hash and its nonce, each unique in its table,
    they must be its own, so it can't be recorded again under others and work twice; and the
    `salt` its nonce was made with must be one the studio makes. Unchecked if the provider
    couldn't be reached to say, while the sign-in is less than a day old: it waits, rather than
    being refused for a brief outage."""
    if verifier is None or not client_id:
        return "the core can't check sign-ins here: it has no identity provider"
    if not token:
        return "nothing records the sign-in that made it"
    if recorded is not None and (not as_itself(recorded[0], token) or recorded[1] != bound):
        return RECORDED_ELSE
    if salt is not None and not salted(salt):
        return "the sign-in's salt isn't one the studio makes"
    try:
        claims = verifier.claims(token, expired=True)
    except IdentityUnavailable as exc:
        if _age(token, now) > OLDEST:
            return "the sign-in is more than a day old, and the identity provider couldn't be reached to check it"
        raise Unchecked(str(exc)) from None
    except IdentityError as exc:
        return f"the sign-in doesn't check out: {exc}"
    audience = claims.get("aud")
    if client_id not in ([audience] if isinstance(audience, str) else audience or []):
        return "the sign-in is for something else"
    if claims.get("nonce") != bound:
        return "the sign-in wasn't to do what was recorded"
    issued, signed_in = claims.get("iat"), claims.get("auth_time")
    if not isinstance(issued, int | float) or not isinstance(signed_in, int | float) \
            or issued - signed_in > FRESH:
        return "the sign-in wasn't made afresh for it"
    if factor and not second_factor(verifier.cfg, claims):
        return "the sign-in wasn't made with a second factor, which this deployment asks for"
    if (time.time() if now is None else now) - issued > OLDEST:
        return "the sign-in is more than a day old"
    try:
        who = whose(verifier, scenario, claims)
    except (UnknownPerson, IdentityError) as exc:
        return f"the sign-in names nobody a5s knows: {exc}"
    if who.id != person:
        return "the sign-in is someone else's"
    return None


def waiting(conn: Any, longer_than: str = "0 minutes") -> int:
    """How many approvals, decisions, grades, suspensions and resumptions the channels app
    recorded that the gateway hasn't sealed, carried out or refused yet, for longer than that:
    none for long, while it can seal."""
    return conn.execute(
        "select (select count(*) from settings_approvals where seal is null and refused is null "
        "        and approved_at < now() - %(for)s::interval)"
        "     + (select count(*) from proposal_decisions where seal is null and refused is null "
        "        and decided_at < now() - %(for)s::interval)"
        "     + (select count(*) from samples where grade_proof is not null and grade_seal is null "
        "        and graded_at < now() - %(for)s::interval)"
        "     + (select count(*) from status_requests where ended_at is null "
        "        and asked_at < now() - %(for)s::interval) as n", {"for": longer_than}
    ).fetchone()["n"]
