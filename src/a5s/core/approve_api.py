"""The approval page's API in the channels app (docs/architecture.md#proposals-and-approvals):
where the people a version of the settings needs approve it, from the card in their chat. The
page is the studio's, /studio/approve. They read the version signed in to the studio, and sign
in afresh to approve it, with a nonce that commits to approving that version alone, so the
identity provider signs the approval (core/approvals.py). It's recorded once; the gateway
checks it again, seals it and applies the version once everyone it needs has approved.
"""

import hashlib
import re
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from a5s import db
from a5s.contract import parse_settings
from a5s.core import approvals, impact, languages, ledger, memberships, registry, web
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say


class Approval(BaseModel):
    """What the approval page sends with its sign-in: the salt its nonce was made with."""

    salt: str


def router(gw: Any) -> APIRouter:
    """The approval page's API, and its old address, for the channels app to include."""
    pages = web.acting(gw, "approve")

    def approver(version: str, body: Approval, authorization: str | None) -> tuple:
        """Who signed in to approve this version, what the provider signed, and the token."""
        if not re.fullmatch(r"[0-9a-f]{64}", version):
            raise HTTPException(404, "a5s has no such version of the settings")
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to approve: send your sign-in as a bearer token")
        try:
            person, claims = approvals.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, version, body.salt, time.time())
        except approvals.Refused as exc:
            raise web.refusal(gw, exc) from None
        return person, claims, token

    def proposal(conn: Any, version: str) -> tuple[dict, dict | None, str]:
        """A version proposed for approval, the version in force, and where it stands."""
        row = conn.execute("select * from settings_proposals where scenario = %s and digest = %s",
                           (gw.scenario.name, version)).fetchone()
        if row is None:
            raise HTTPException(404, "a5s has no such version of the settings to approve")
        last = approvals.latest(conn, gw.scenario.name)
        if row["outcome"]:
            status = row["outcome"]
        elif (last and row["serial"] <= last["serial"]) or approvals.stale(row, last):
            status = "superseded"  # or written against a version that's no longer in force
        else:
            status = "waiting"
        return row, last, status

    @pages.get("/approve/settings/{version}", **shapes.answers(shapes.VersionReview))
    def review(version: str, authorization: str | None = Header(default=None)) -> dict:
        """What a version changes from the one in force, as code works it out, for someone who
        approves versions of the settings, signed in to the studio: what they read before they
        sign in afresh to approve it."""
        if not re.fullmatch(r"[0-9a-f]{64}", version):
            raise HTTPException(404, "a5s has no such version of the settings")
        person = web.known(gw, authorization)
        if not registry.approves(person):
            raise HTTPException(403, approvals.APPROVERS.format(name=person.name))
        with db.transaction(gw.url) as conn:
            row, last, status = proposal(conn, version)
            approved = approvals.recorded(conn, gw.scenario.name, version)
            asked = conn.execute("select person from settings_requests where scenario = %s and "
                                 "digest = %s order by id limit 1",
                                 (gw.scenario.name, version)).fetchone()
            spoken = languages.of(person)  # in their language, where a5s has the words
        before = parse_settings(bytes(last["raw"])) if last else None
        settings = parse_settings(bytes(row["raw"]))
        found = approvals.changes(before, settings, gw.definitions, gw.scenario.person, spoken)
        asker = (p.name if (p := gw.scenario.person(asked["person"])) else asked["person"]
                 ) if asked else None  # who asked for it in the settings app, if anyone did
        valid, _ = registry.signers(settings, gw.scenario.person, approved)
        preview = impact.shown(gw, before, settings, person) if status == "waiting" else None
        return {"serial": row["serial"], "proposed_at": row["proposed_at"].isoformat(),
                **({"impact": preview} if preview is not None else {}),
                "in_force": last["serial"] if last else None, "changes": found,
                "whole": approvals.described(settings, gw.definitions, gw.scenario.person, spoken),
                "needs": registry.missing(settings, gw.scenario.person, valid, before,
                                          memberships.rooted(gw.scenario).person, spoken)
                if status == "waiting" else [],
                "approved_by": [p.name if (p := gw.scenario.person(a)) else a for a in approved],
                "asked_by": asker, "you": person.name, "you_approved": person.id in approved,
                "status": status}

    @pages.post("/approve/settings/{version}", **shapes.answers(shapes.Approved))
    def approve(version: str, body: Approval, authorization: str | None = Header(default=None)
                ) -> dict:
        """An approval of a version, signed through the identity provider for this version
        alone. It's recorded once, and sealed. The gateway applies the version."""
        person, claims, token = approver(version, body, authorization)
        with db.transaction(gw.url) as conn:
            row, _, status = proposal(conn, version)
            if status != "waiting":
                raise HTTPException(409, f"this version isn't waiting for approval: it's {status}")
            try:
                approvals.record(conn, gw.scenario.name, version, person.id, token, body.salt,
                                 claims)
            except approvals.Refused as exc:
                raise web.refusal(gw, exc) from None
            ledger.append(conn, {
                "kind": "admin", "action": "approve", "run": None, "instance": None, "acts_for": [],
                "decision": "record",
                "args": {"settings": row["version"], "serial": row["serial"], "digest": version,
                         "by": person.id,
                         "identity": "verified: a sign-in to approve this version alone",
                         "issuer": claims["iss"],
                         "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
            approved = approvals.recorded(conn, gw.scenario.name, version)
            last = approvals.latest(conn, gw.scenario.name)
            spoken = languages.of(person)
        settings = parse_settings(bytes(row["raw"]))
        valid, _ = registry.signers(settings, gw.scenario.person, approved)
        before = parse_settings(bytes(last["raw"])) if last else None
        return {"approved": True, "serial": row["serial"], "by": person.name,
                "needs": registry.missing(settings, gw.scenario.person, valid, before,
                                          memberships.rooted(gw.scenario).person, spoken)}

    return pages
