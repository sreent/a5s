"""The decision page in the channels app (docs/architecture.md#proposals-and-approvals): the page
a decider's card opens, for the changes agents hold for a person to decide (core/proposals.py).
They sign in to see what waits for them, and again, afresh, to decide: that sign-in's nonce
commits to their decision on exactly the changes they chose, so the identity provider signs the
decision. The gateway checks it again, seals it and makes what's approved.
"""

import hashlib
import logging
import re
import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from a5s import db
from a5s.contract import INSTANCE_APPROVER, PART_DELEGATE, PART_OWNER
from a5s.core import ledger, proposals, web
from a5s.core.gateway import sanitize

log = logging.getLogger(__name__)


class Deciding(BaseModel):
    """What the decision page sends with a sign-in made to decide: the changes it decides, by
    their digests, the decision, the salt its nonce was made with, and, for a rejection, why,
    if the decider says."""

    proposals: list[str]
    decision: str
    salt: str
    reason: str | None = None


def router(gw: Any) -> APIRouter:
    """The decision page, its sign-in and its API, for the channels app to include."""
    pages = web.acting(gw, "decide")

    @pages.post("/decide/review")
    def review_proposals(authorization: str | None = Header(default=None)) -> dict:
        """The held changes whoever signed in may decide now, oldest first, since those lapse
        first, as the directory stands now; those they were told of as a decider's manager,
        which they may see but not decide; and those they decided lately. Each in the words
        code worked out when it was asked for, with a link to each record, and whether it has
        changed since."""
        who, _ = web.sender(gw, authorization, None)
        person = gw.scenario.person(who)
        roles = person.roles if person else ()
        mine = sorted({r.split(":", 1)[1] for r in roles
                       if r.startswith((f"{PART_OWNER}:", f"{PART_DELEGATE}:"))})
        with db.transaction(gw.url) as conn:
            rows = conn.execute(
                "select p.*, d.decision as yours from proposals p left join proposal_decisions d "
                "on d.digest = p.digest and d.person = %(who)s where p.scenario = %(scenario)s "
                "and ((p.status = 'waiting' and (p.parts && %(parts)s or %(who)s = any(p.escalated) "
                "or (%(approver)s and cardinality(p.parts) = 0))) or (d.id is not null and "
                "(p.ended_at is null or p.ended_at > %(week)s))) "
                "order by (p.status = 'waiting') desc, p.id limit 500",
                {"who": who, "scenario": gw.scenario.name, "parts": mine,
                 "approver": INSTANCE_APPROVER in roles,
                 "week": gw.clock() - timedelta(days=7)}).fetchall()
        shown = []
        for row in rows:
            waits = row["status"] == "waiting"
            decides = waits and proposals.may_decide(gw.scenario, row, who)
            if waits and not decides and who not in (row["escalated"] or []):
                continue  # they no longer own what it touches, or may no longer see it
            if len(shown) >= 50:
                break
            try:
                changed = proposals.changed(gw.scenario, row) if waits else []
            except Exception:  # the records system didn't answer: say so, rather than nothing
                log.exception("couldn't read the records of %s", proposals.key(row))
                changed = list(row["records"])
            standing = row["standing"] or {}
            shown.append({"key": proposals.key(row), "digest": row["digest"], "said": row["said"],
                          "flags": row["flags"], "sensitive": row["sensitive"],
                          "status": row["status"], "yours": row["yours"], "may_decide": decides,
                          "outcome": row["outcome"], "proposed_at": row["proposed_at"].isoformat(),
                          "lapses_at": row["lapses_at"].isoformat(),
                          "links": [r["link"] for r in standing.values() if r and r.get("link")],
                          "changed": [f"{k} has changed since it was asked for" for k in changed]})
        return {"you": person.name if person else who, "proposals": shown}

    @pages.post("/decide/proposals")
    def decide_proposals(body: Deciding, authorization: str | None = Header(default=None)
                         ) -> dict:
        """A decision on held changes, signed through the identity provider for that decision on
        exactly those changes. It's recorded once, and sealed. The gateway makes what's approved."""
        digests = sorted(set(body.proposals))
        if not 1 <= len(digests) <= 20 or not all(re.fullmatch(r"[0-9a-f]{64}", d)
                                                  for d in digests):
            raise HTTPException(400, "name from one to 20 changes to decide, by their digests")
        reason = None
        if body.reason and body.reason.strip() and body.decision == "reject":
            if len(body.reason) > proposals.REASON:
                raise HTTPException(400, f"say why in at most {proposals.REASON} characters")
            reason, _ = sanitize(" ".join(body.reason.split()), gw.scenario.record_links)
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to decide: send your sign-in as a bearer token")
        try:
            person, claims = proposals.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, digests, body.decision, body.salt, time.time())
        except proposals.Refused as exc:
            raise web.refusal(gw, exc) from None
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select * from proposals where scenario = %s and digest = any(%s) "
                                "order by id", (gw.scenario.name, digests)).fetchall()
            if len(rows) != len(digests):
                raise HTTPException(404, "a5s has no such change to decide")
            for row in rows:
                if row["status"] != "waiting":
                    raise HTTPException(409, f"{proposals.key(row)} isn't waiting for a decision: "
                                             f"it's {row['status']}")
                if not proposals.may_decide(gw.scenario, row, person.id):
                    raise HTTPException(403, f"{person.name} may not decide {proposals.key(row)}")
            if len(rows) > 1 and any(r["sensitive"] for r in rows):
                raise HTTPException(409, "a sensitive change is decided on its own, with a sign-in "
                                         "of its own")
            try:
                proposals.record(conn, gw.scenario.name, rows, body.decision, person.id, token,
                                 body.salt, claims, gw.clock(), reason)
            except proposals.Refused as exc:
                raise web.refusal(gw, exc) from None
            ledger.append(conn, {
                "kind": "admin", "action": "decide", "run": None, "instance": None, "acts_for": [],
                "decision": "record",
                "args": {"proposals": [proposals.key(r) for r in rows], "decided": body.decision,
                         "by": person.id,
                         "identity": "verified: a sign-in to make this decision on these alone",
                         "issuer": claims["iss"],
                         "token_sha256": hashlib.sha256(token.encode()).hexdigest()}})
        return {"decided": [proposals.key(r) for r in rows], "decision": body.decision,
                "by": person.name}

    return pages
