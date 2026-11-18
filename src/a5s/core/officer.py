"""The data protection officer's requests: to see, or to erase, all a5s keeps about someone
(core/export.py, core/erasure.py).

The officer asks on the core's page, `/officer/`, signed in afresh for that request alone: the
sign-in's nonce commits to the action and the person, so the identity provider signs the
request. Someone from the team that runs a5s, whose service token reaches the core, then
carries it out, once, within ten minutes. Neither can do it alone: the team can't without the
officer's request, and the officer's sign-in does nothing else, for nobody else, and only once,
so nobody who sees it can use it again.

The channels app records the request with the sign-in that made it. The gateway checks the
sign-in again before it carries the request out, as it does an approval (core/sealing.py), and
lets it go. The ledger keeps it by its hash.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from a5s import db
from a5s.contract import DATA_PROTECTION, Person
from a5s.core import groups, sealing
from a5s.core.approvals import HASHED, Refused, afresh
from a5s.core.identity import Verifier

ACTIONS = ("export", "erase")
LASTS = "10 minutes"  # how long a request waits for the team to carry it out
PAGE = "/studio/officer"


def nonce(action: str, person: str, salt: str) -> str:
    """What a sign-in to ask for this carries, so the provider's signature covers the request.
    The page picks the salt, so each sign-in is different."""
    bound = hashlib.sha256(f"a5s officer {action} {person} {salt}".encode()).digest()
    return base64.urlsafe_b64encode(bound).rstrip(b"=").decode()


def check(verifier: Verifier, scenario: Any, client_id: str, token: str, action: str,
          person: str, salt: str, now: float) -> tuple[Person, dict]:
    """Who signed in to ask for this, and what the provider signed, if the sign-in checks out
    for it alone, and its person is the data protection officer. Otherwise, Refused."""
    if action not in ACTIONS:
        raise Refused(404, f"the officer asks to {' or '.join(ACTIONS)} what a5s keeps")
    if not person or groups.of(person):
        raise Refused(400, "a group chat's conversation is nobody's own: name a person")
    officer, claims = afresh(verifier, scenario, client_id, token, nonce(action, person, salt),
                             salt, now, f"{action} what a5s keeps about {person}", "ask for this")
    if DATA_PROTECTION not in officer.roles:
        raise Refused(403, f"only the data protection officer asks for this, and {officer.name} "
                           "isn't")
    return officer, claims


def record(conn: db.Connection, action: str, person: str, officer: str, token: str,
           salt: str, claims: dict) -> dict:
    """Record the officer's request, with the sign-in that made it, for the gateway to check
    again and carry out. Refused if the sign-in was used before."""
    row = conn.execute(
        "insert into officer_requests (action, person, officer, nonce, salt, token, proof, "
        "issuer) values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing "
        "returning id, asked_at",
        (action, person, officer, claims["nonce"], salt,
         HASHED + hashlib.sha256(token.encode()).hexdigest(), token, claims["iss"])).fetchone()
    if row is None:
        raise Refused(409, "that sign-in has been used: sign in again")
    return dict(row)


def take(conn: db.Connection, verifier: Verifier | None, scenario: Any,
         client_id: str | None, action: str, person: str) -> dict:
    """The officer's latest request to do this, from the last ten minutes, checked again, and
    used up, so it does nothing more. Refused if there's none, or it doesn't check out."""
    row = conn.execute(
        "select * from officer_requests where action = %s and person = %s and used_at is null "
        "and asked_at > now() - %s::interval order by asked_at desc limit 1 for update",
        (action, person, LASTS)).fetchone()
    if row is None:
        raise Refused(403, f"the data protection officer hasn't asked to {action} what a5s "
                           f"keeps about {person} in the last ten minutes: they ask on the "
                           f"core's page, {PAGE}, signed in")
    conn.execute("update officer_requests set used_at = now(), proof = null where id = %s",
                 (row["id"],))
    try:
        why = sealing.check(verifier, scenario, client_id, row["proof"],
                            nonce(action, person, row["salt"]), row["officer"],
                            recorded=(row["token"], row["nonce"]), salt=row["salt"])
    except sealing.Unchecked:
        raise Refused(503, "the identity provider can't be reached just now to check the "
                           "officer's request: they ask again, on the core's page, once it can") from None
    officer = scenario.person(row["officer"])
    if why is None and (officer is None or DATA_PROTECTION not in officer.roles):
        why = "who asked isn't the data protection officer now"
    if why is not None:
        raise Refused(403, f"the officer's request doesn't check out: {why}")
    return dict(row)
