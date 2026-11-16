"""Suspending and resuming an instance from its page in the studio (docs/studio.md), signed in
afresh for that act alone: the sign-in's nonce commits to the act and the instance, so the
identity provider signs it.

Who may: suspend it, which makes a5s safer, those who run it, as its owner or deputy, the owners
of its agent, and the team that runs a5s; resume it, which loosens a5s, whoever suspended it,
with a second factor where the deployment asks for one, as core/registry.py's set_status keeps
the first suspender's suspension and lets only them resume it. The team can do either at the
command line too, at once (`a5s suspend`).

The channels app checks the sign-in as it arrives, so people hear at once when it doesn't check
out or isn't theirs to make, and records it with the sign-in. It can change no instance. The
gateway checks the sign-in again, as it does an approval (core/sealing.py), and whether its
person may now, as the directory stands, then carries it out at its next sweep, within the
minute, and lets the sign-in go: the ledger keeps it by its hash. What it can't carry out, its
person hears of in their digest.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from a5s import db
from a5s.contract import Person
from a5s.core import ledger, registry, sealing
from a5s.core.approvals import FRESH, HASHED, Refused
from a5s.core.identity import (
    IdentityError,
    UnknownPerson,
    Verifier,
    second_factor,
    whose,
    without_second_factor,
)
from a5s.core.releases import agent_owner

ACTIONS = ("suspend", "resume")
COLUMNS = "id, definition, owner, deputy, status, suspended_by"  # what deciding who may reads


def nonce(action: str, instance: str, salt: str) -> str:
    """What a sign-in to do this carries, so the provider's signature covers the act. The page
    picks the salt, so each sign-in is different."""
    bound = hashlib.sha256(f"a5s {action} instance {instance} {salt}".encode()).digest()
    return base64.urlsafe_b64encode(bound).rstrip(b"=").decode()


def verified(action: str) -> str:
    return f"verified: a sign-in to {action} it alone"


def may(scenario: Any, person: Person, inst: dict, action: str,
        team: str | None) -> Refused | None:
    """Why someone may not suspend or resume this instance now, if they may not: as the
    instance stands (409), or since it isn't theirs to do (403)."""
    if inst["status"] == "retired":
        return Refused(409, f"{inst['id']} is retired")
    by = scenario.person(inst["suspended_by"] or "")
    suspender = by.name if by else inst["suspended_by"]
    if action == "suspend":
        if not (person.id in (inst["owner"], inst["deputy"])
                or agent_owner(inst["definition"]) in person.roles
                or (team is not None and person.team == team)):
            return Refused(403, "suspending it is for those who run it, as its owner or deputy, "
                                "the owners of its agent, and the team that runs a5s")
        if inst["status"] == "suspended":
            return Refused(409, f"{inst['id']} is suspended already, by {suspender}")
        return None
    if inst["status"] != "suspended":
        return Refused(409, f"{inst['id']} isn't suspended")
    if inst["suspended_by"] != person.id:
        return Refused(403, f"only {suspender}, who suspended it, can resume it. Resuming someone "
                            "else's suspension needs the release approver, at the command line")
    return None


def check(verifier: Verifier, scenario: Any, client_id: str, token: str, action: str,
          instance: str, salt: str, now: float) -> tuple[Person, dict]:
    """Who signed in to do this, and what the provider signed, if the sign-in checks out for
    it alone, made afresh, with a second factor to resume where the deployment asks for one.
    Otherwise, Refused. Whether they may is for `may`, as the instance stands."""
    if action not in ACTIONS:
        raise Refused(404, "an instance is suspended or resumed, and nothing else, from its page")
    try:
        claims = verifier.claims(token)
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    audience = claims.get("aud")
    if client_id not in ([audience] if isinstance(audience, str) else audience or []):
        raise Refused(401, "that sign-in is for something else")
    if not sealing.salted(salt) or claims.get("nonce") != nonce(action, instance, salt):
        raise Refused(403, f"your sign-in wasn't to {action} {instance}")
    if not isinstance(claims.get("auth_time"), int | float) or any(
            not isinstance(claims.get(c), int | float) or now - claims[c] > FRESH
            for c in ("iat", "auth_time")):  # a session's silent sign-in asks for nothing
        raise Refused(401, f"to {action} it, sign in again, from the last ten minutes, not with "
                           "a sign-in your browser kept")
    if action == "resume" and not second_factor(verifier.cfg, claims):
        raise Refused(401, without_second_factor("resume it"), "resume")
    try:
        person = whose(verifier, scenario, claims)
    except UnknownPerson as exc:
        raise Refused(403, str(exc)) from None
    except IdentityError as exc:
        raise Refused(401, f"your sign-in doesn't check out: {exc}") from None
    return person, claims


def record(conn: db.Connection, action: str, instance: str, person: str, token: str,
           salt: str, claims: dict) -> dict:
    """Record the act, with the sign-in that made it, for the gateway to check again and carry
    out, and the ledger that it was asked for. Refused if the sign-in was used before."""
    hashed = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        "insert into status_requests (instance_id, action, person, nonce, salt, token, proof, "
        "issuer) values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing "
        "returning id, asked_at",
        (instance, action, person, claims["nonce"], salt, HASHED + hashed, token,
         claims["iss"])).fetchone()
    if row is None:
        raise Refused(409, "that sign-in has been used: sign in again")
    ledger.append(conn, {"kind": "admin", "action": "ask-status", "run": None, "instance": instance,
                         "acts_for": [], "decision": "record",
                         "args": {"to": action, "by": person, "identity": verified(action),
                                  "issuer": claims["iss"], "token_sha256": hashed}})
    return dict(row)


def asked(conn: db.Connection, instance: str) -> dict | None:
    """The latest act asked for on this instance that the gateway hasn't carried out yet."""
    return conn.execute("select action, person, asked_at from status_requests where "
                        "instance_id = %s and ended_at is null order by asked_at desc limit 1",
                        (instance,)).fetchone()


def carry_out(conn: db.Connection, verifier: Verifier | None, scenario: Any,
              client_id: str | None, team: str | None) -> list[sealing.Refusal]:
    """In the gateway alone: check again each act recorded, and whether its person may now,
    and carry it out, or refuse it; those the identity provider can't be reached to check wait
    for the next sweep, for up to a day. What was refused, for its person to hear of."""
    refused = []
    for row in conn.execute("select * from status_requests where ended_at is null "
                            "order by asked_at for update skip locked").fetchall():
        action, instance, who = row["action"], row["instance_id"], row["person"]
        try:
            why = sealing.check(verifier, scenario, client_id, row["proof"],
                                nonce(action, instance, row["salt"]), who,
                                factor=action == "resume",  # suspending only makes a5s safer
                                recorded=(row["token"], row["nonce"]), salt=row["salt"])
        except sealing.Unchecked:
            continue
        inst = conn.execute(f"select {COLUMNS} from instances where id = %s for update",
                            (instance,)).fetchone()
        person = scenario.person(who)
        if why is None:
            not_now = None if inst is None or person is None else may(scenario, person, inst,
                                                                       action, team)
            why = ("there's no such instance" if inst is None else
                   "who asked isn't in the directory now" if person is None else
                   not_now.reason if not_now else None)
        if why is None:
            why = registry.set_status(
                conn, instance, by=who, suspend=action == "suspend", identity=verified(action),
                proof={"issuer": row["issuer"], "token_sha256": row["token"].removeprefix(HASHED)}
            ) or None
        conn.execute("update status_requests set ended_at = now(), outcome = %s, proof = null "
                     "where id = %s", (why or "made", row["id"]))
        if why:
            refused.append(sealing.Refusal(
                who, f"{action} {instance}: {why}",
                f"a5s didn't {action} {instance}, as you asked on its page in the studio: {why}."))
    return refused
