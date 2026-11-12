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
seal key or the identity provider leaves what's recorded waiting, which the status counts.
"""

from __future__ import annotations

import time
from typing import Any

from a5s.core.identity import IdentityError, UnknownPerson, Verifier, second_factor, whose

FRESH = 600  # seconds: how long before a sign-in its person must have signed in afresh
OLDEST = 86_400  # seconds: a sign-in older than this, still unsealed, is refused


def check(verifier: Verifier | None, scenario: Any, client_id: str | None, token: str | None,
          bound: str, person: str, now: float | None = None) -> str | None:
    """Why a recorded sign-in doesn't check out, if it doesn't: None if the provider signed it
    for a5s's client, with exactly the nonce `bound`, made afresh, for `person`, lately."""
    if verifier is None or not client_id:
        return "the core can't check sign-ins here: it has no identity provider"
    if not token:
        return "nothing records the sign-in that made it"
    try:
        claims = verifier.claims(token, expired=True)
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
    if not second_factor(verifier.cfg, claims):
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
    """How many approvals, decisions and grades the channels app recorded that the gateway
    hasn't sealed or refused yet, for longer than that: none for long, while it can seal."""
    return conn.execute(
        "select (select count(*) from settings_approvals where seal is null and refused is null "
        "        and approved_at < now() - %(for)s::interval)"
        "     + (select count(*) from proposal_decisions where seal is null and refused is null "
        "        and decided_at < now() - %(for)s::interval)"
        "     + (select count(*) from samples where grade_proof is not null and grade_seal is null "
        "        and graded_at < now() - %(for)s::interval) as n", {"for": longer_than}
    ).fetchone()["n"]
