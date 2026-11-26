"""The decision page's API in the channels app (docs/architecture.md#proposals-and-approvals),
for the changes agents hold for a person to decide (core/proposals.py). The page is the
studio's, /studio/decide, which a decider's card opens. They sign in to see what waits for
them, and again, afresh, to decide: that sign-in's nonce commits to their decision on exactly
the changes they chose, so the identity provider signs the decision. The gateway checks it
again, seals it and makes what's approved.
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
from a5s.core import acting, approvals, languages, ledger, proposals, web, words
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say


class _EveryPart(dict):
    """Four eyes in every part, at any amount: while no settings in force can be read, one
    approval never settles a change on the page (round 16, B5)."""

    def __contains__(self, part: object) -> bool:
        return True

    def __getitem__(self, part: object) -> tuple[str, float]:
        return ("", float("-inf"))

    def __bool__(self) -> bool:
        return True


def unknown(two: dict[str, tuple[str, float]] | None) -> dict[str, tuple[str, float]]:
    """Four eyes as the settings in force say, or in every part where none can be read."""
    return _EveryPart() if two is None else two

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
    """The decision page's API, and its old address, for the channels app to include."""
    pages = web.acting(gw, "decide")

    @pages.post("/decide/review", **shapes.answers(shapes.DecideNow))
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
                "on d.digest = p.digest and d.person = %(who)s and d.refused is null "  # theirs, if it counts
                "where p.scenario = %(scenario)s "
                "and ((p.status = 'waiting' and (p.parts && %(parts)s or %(who)s = any(p.escalated) "
                "or (%(approver)s and cardinality(p.parts) = 0))) or (d.id is not null and "
                "(p.ended_at is null or p.ended_at > %(week)s))) "
                "order by (p.status = 'waiting') desc, p.id limit 500",
                {"who": who, "scenario": gw.scenario.name, "parts": mine,
                 "approver": INSTANCE_APPROVER in roles,
                 "week": gw.clock() - timedelta(days=7)}).fetchall()
            spoken = languages.of(person) if person else languages.ENGLISH  # (B6)
            two = unknown(gw.four_eyes(conn))  # what they approved that waits for another
            waits_another = {r["digest"] for r in rows if r["status"] == "waiting"
                             and r["yours"] == "approve" and not proposals.settled(
                                 conn, gw.scenario, r, two)}
        shown = []
        deciding: list[list[str]] = []  # the parts of each change they may decide now
        for row in rows:
            waits = row["status"] == "waiting"
            decides = waits and proposals.may_decide(gw.scenario, row, who)
            if waits and not decides and who not in (row["escalated"] or []):
                continue  # they no longer own what it touches, or may no longer see it
            if len(shown) >= 50:
                break
            if decides:
                deciding.append(list(row["parts"] or []))
            try:
                changed = proposals.changed(gw.scenario, row) if waits else []
            except Exception:  # the records system didn't answer: say so, rather than nothing
                log.exception("couldn't read the records of %s", proposals.key(row))
                changed = list(row["records"])
            standing = row["standing"] or {}
            shown.append({"key": proposals.key(row), "digest": row["digest"], "said": row["said"],
                          "agent": row["definition"],  # who asked, and for whom, as recorded
                          "for": [p.name if (p := gw.scenario.person(i)) else i
                                  for i in row["acts_for"]],
                          "flags": words.flags(row, spoken), "sensitive": row["sensitive"],
                          "status": row["status"], "yours": row["yours"], "may_decide": decides,
                          "outcome": row["outcome"] or (words.say(
                              spoken, proposals.WAITS_ANOTHER, key=proposals.key(row))
                              if row["digest"] in waits_another else None),
                          "proposed_at": row["proposed_at"].isoformat(),
                          "lapses_at": row["lapses_at"].isoformat(),
                          "links": [r["link"] for r in standing.values() if r and r.get("link")],
                          "records": [{"key": k, "link": r["link"]} for k, r in standing.items()
                                      if r and r.get("link")],
                          "changed": [words.say(spoken, proposals.CHANGED, key=k)
                                      for k in changed]})
        return {"you": person.name if person else who, "proposals": shown,
                **acting.shown(acting.deciding(person, deciding, spoken) if person else None)}

    @pages.post("/decide/proposals", **shapes.answers(shapes.Decided))
    def decide_proposals(body: Deciding, authorization: str | None = Header(default=None)
                         ) -> dict:
        """A decision on held changes, signed through the identity provider for that decision on
        exactly those changes. It's recorded once, and sealed. The gateway makes what's approved."""
        digests = sorted(set(body.proposals))
        if not 1 <= len(digests) <= proposals.MOST_DECIDED or not all(re.fullmatch(r"[0-9a-f]{64}", d)
                                                  for d in digests):
            raise HTTPException(400, "name from one to 20 changes to decide, by their digests")
        reason = None  # as the decider wrote it, which their sign-in covers: the core cleans it
        if body.reason and body.reason.strip() and body.decision == "reject":
            if len(body.reason) > proposals.REASON:
                raise HTTPException(400, f"say why in at most {proposals.REASON} characters")
            reason = body.reason
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to decide: send your sign-in as a bearer token")
        try:
            person, claims = proposals.check(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, digests, body.decision, body.salt, time.time(),
                                             reason)
        except proposals.Refused as exc:
            raise web.refusal(gw, exc) from None
        with db.transaction(gw.url) as conn:
            for digest in digests:  # one decision on a change at a time, in order, so a second
                conn.execute(  # hears whether the first settled it (round 15, B3)
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))", (digest,))
            rows = conn.execute("select * from proposals where scenario = %s and digest = any(%s) "
                                "order by id", (gw.scenario.name, digests)).fetchall()
            if len(rows) != len(digests):
                raise HTTPException(404, "a5s has no such change to decide")
            two = unknown(gw.four_eyes(conn))  # four eyes above an amount
            for row in rows:
                if row["status"] != "waiting":
                    raise HTTPException(409, f"{proposals.key(row)} isn't waiting for a decision: "
                                             f"it's {row['status']}")
                if not proposals.may_decide(gw.scenario, row, person.id):
                    raise HTTPException(403, f"{person.name} may not decide {proposals.key(row)}")
                if body.decision == "approve" and conn.execute(
                        "select 1 from proposal_decisions where digest = %s and person = %s "
                        "and decision = 'approve' and refused is null",
                        (row["digest"], person.id)).fetchone():  # four eyes are two people
                    raise HTTPException(409, f"{person.name} approved {proposals.key(row)} "
                                             "already: it waits for another of its deciders")
                if first := proposals.settled(conn, gw.scenario, row, two):
                    raise HTTPException(409, f"{approvals.names_of(first)} decided "
                                             f"{proposals.key(row)} already, and the first "
                                             "decision is the one that counts: yours isn't "
                                             "recorded")
                at_work = conn.execute("select status from instances where id = %s",
                                       (row["instance_id"],)).fetchone()
                if body.decision == "approve" and at_work and at_work["status"] != "active":
                    raise HTTPException(409, f"{row['instance_id']} is {at_work['status']}, and "
                                             "a5s makes none of its changes until it's at work "
                                             f"again: approve {proposals.key(row)} then, or "
                                             "reject it now")
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
            # what this approval leaves waiting for another of its deciders, as the page says
            waits = [proposals.key(r) for r in rows if body.decision == "approve"
                     and not proposals.settled(conn, gw.scenario, r, two)]
        return {"decided": [proposals.key(r) for r in rows], "decision": body.decision,
                "by": person.name, "waits": waits}

    return pages
