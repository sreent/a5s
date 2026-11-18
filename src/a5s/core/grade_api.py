"""The grading page's API in the channels app (docs/phase-2.md): where people outside the team
that built an agent grade samples of its changes, whose grades raise or lower a5s's cap on its
level (core/samples.py). The page is the studio's, /studio/grade. They sign in to see what they
may grade, and again, afresh, to grade: that sign-in's nonce commits to exactly those grades of
exactly those samples, so the identity provider signs them. The core checks each again and
seals it.
"""

import hashlib
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from a5s import db
from a5s.contract import Person
from a5s.core import approvals, languages, ledger, masking, proposals, samples, web, words
from a5s.core import studio_models as shapes  # what each route answers, as the studio's types say


class Grading(BaseModel):
    """What the grading page sends with a sign-in made to grade: the grades, by sample, and the
    salt its nonce was made with."""

    grades: dict[int, str]
    salt: str


GRADERS = "grading is for the people who grade agents' work"


def router(gw: Any) -> APIRouter:
    """The grading page's API, and its old address, for the channels app to include."""
    pages = web.acting(gw, "grade")

    def grader(authorization: str | None) -> Person:
        who, _ = web.sender(gw, authorization, None)
        person = gw.scenario.person(who)
        if person is None or samples.GRADER not in person.roles:
            raise HTTPException(403, GRADERS)
        return person

    @pages.post("/grade/review", **shapes.answers(shapes.GradeNow))
    def review_samples(authorization: str | None = Header(default=None)) -> dict:
        """The samples waiting for a grade that whoever signed in may grade, oldest first: read
        in pages, leaving out in the query what it can, until 20 are found."""
        person = grader(authorization)
        with db.transaction(gw.url) as conn:
            rows = samples.gradeable(conn, gw.scenario, person)
            names = gw.data_protection(conn).studio_names  # as a shadow's pairs are masked
            spoken = languages.of(conn, person)  # what to know, in their language (round 15, B6)
            everyone = [] if names else masking.known(conn, gw.scenario)

        def heard(r: dict) -> str | None:  # what was asked, masked until names are agreed
            asked = samples.asked_of(r)
            if not asked or names:
                return asked
            return masking.mask(asked, gw.scenario, [*(r["acts_for"] or []), *everyone])[0]

        return {"you": person.name, "samples": [
            {"id": r["id"], "kind": r["kind"], "agent": r["definition"], "part": r["part"],
             "action": r["action"], "said": r["said"], "records": r["records"],
             "flags": words.flags(r, spoken), "decided": r["decided"],
             "drawn_at": r["drawn_at"].isoformat(),
             "asked": heard(r)}  # (round 15, C1)
            for r in rows]}

    @pages.post("/grade/samples", **shapes.answers(shapes.Graded))
    def grade_samples(body: Grading, authorization: str | None = Header(default=None)) -> dict:
        """Grades of samples, signed through the identity provider for exactly those grades of
        exactly those samples, by someone who may grade each, once. The core seals each."""
        return grading(body.grades, body.salt, authorization)

    def grading(grades: dict[int, str], salt: str, authorization: str | None) -> dict:
        if not 1 <= len(grades) <= samples.MOST_GRADED or any(g not in samples.GRADES
                                                              for g in grades.values()):
            raise HTTPException(400, f"grade from one to {samples.MOST_GRADED} samples, each "
                                     "right, wrong or critical")
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "sign in to grade: send your sign-in as a bearer token")
        try:
            person, claims = proposals.fresh(gw.identity, gw.scenario, gw.cfg.webchat_client_id,
                                             token, samples.nonce(grades, salt), salt, time.time(),
                                             "grade these samples")
        except proposals.Refused as exc:
            raise web.refusal(gw, exc) from None
        if samples.GRADER not in person.roles:
            raise HTTPException(403, GRADERS)
        hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
        with db.transaction(gw.url) as conn:
            if conn.execute("select 1 from samples where grade_token = %s limit 1",
                            (hashed,)).fetchone():
                raise HTTPException(409, "that sign-in has graded already: sign in again")
            rows = {r["id"]: r for r in conn.execute(
                "select * from samples where scenario = %s and id = any(%s) order by id for update",
                (gw.scenario.name, sorted(grades)))}
            minders = {r["id"]: (r["owner"], r["deputy"]) for r in conn.execute(
                "select id, owner, deputy from instances")}
            paired = samples.mates(conn, rows.values())  # a second grader for a twin (C4)
            together = {rows[s]["twin_of"] for s in grades if s in rows and rows[s]["twin_of"]}
            if together & set(grades):
                raise HTTPException(403, "a second grader grades a sample drawn twice: grade "
                                         "one of the two")
            for sample in sorted(grades):
                row = rows.get(sample)
                if row is None:
                    raise HTTPException(404, f"a5s has no sample {sample}")
                if (why := samples.may_grade(gw.scenario, row, person,
                                             minders.get(row["instance_id"], ()),
                                             samples.drafted(conn, row["definition"]),
                                             paired.get(sample))) is not None:
                    raise HTTPException(403, why)
                if row["grade"] is not None or row["lapsed_at"] is not None:
                    raise HTTPException(409, f"sample {sample} has been graded already, or lapsed")
            now = gw.clock()
            for sample, grade in sorted(grades.items()):
                entry = {**rows[sample], "grade": grade, "graded_by": person.id, "graded_at": now,
                         "grade_token": hashed, "grade_nonce": claims["nonce"], "grade_salt": salt,
                         "grade_issuer": claims["iss"],
                         "grade_subject": str(claims.get("sub") or ""), "grade_proof": token}
                conn.execute(  # with the sign-in, which the gateway checks again and seals
                    "update samples set grade = %(grade)s, graded_by = %(graded_by)s, "
                    "graded_at = %(graded_at)s, grade_token = %(grade_token)s, grade_nonce = "
                    "%(grade_nonce)s, grade_salt = %(grade_salt)s, grade_issuer = %(grade_issuer)s, "
                    "grade_subject = %(grade_subject)s, grade_proof = %(grade_proof)s "
                    "where id = %(id)s", entry)
                ledger.append(conn, {
                    "kind": "admin", "action": "grade", "run": str(rows[sample]["run_id"]),
                    "instance": rows[sample]["instance_id"], "acts_for": [], "decision": "record",
                    "args": {"sample": sample, "grade": grade, "by": person.id,
                             "release": rows[sample]["release"], "part": rows[sample]["part"],
                             "action": rows[sample]["action"],
                             "identity": "verified: a sign-in to give these grades alone",
                             "token_sha256": hashed.removeprefix(approvals.HASHED)}})
        return {"graded": sorted(grades), "grades": {str(k): v for k, v in grades.items()},
                "by": person.name}

    return pages
