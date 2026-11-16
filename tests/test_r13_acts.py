"""Round 13, reviewer A: what the gateway took on the channels app's word when it sealed or
carried out an act. Each test is a channels app broken into, writing with its own database role
and no seal key, as core/sealing.py says it can then only record what a person really signed in
to do.

A1: the gateway checked only the first row of a sign-in that decided several changes, and sealed
every row as the channels app wrote it: one person's approval as another decider's, an approval
as a rejection in words they never wrote, and a sensitive change among others. Every row of a
sign-in's decision must now share its person, decision, salt, reason and sign-in, on 1 to 20
changes they may each decide, a sensitive one alone.

A2: that a sign-in works once rested on the hash and nonce the channels app wrote beside it,
which their tables keep unique, so a sign-in used already, recorded again under others, resumed
an instance or exported someone's data again. The gateway now takes a sign-in only as recorded
by its own hash and nonce. And the channels app could clear a grade's seal, which the gateway
sealed again later: it no longer writes the seal, nor changes a sealed grade (migration 0076).

A3: a rejection's reason, or an id's last word, could move into the salt a nonce is made with,
since salts were checked by length alone: a salt is one the studio makes, base64url."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import jwt
import psycopg
import pytest

from a5s import db
from a5s.contract import record_of
from a5s.core import approvals, officer, proposals, samples, sealing, suspension
from conftest import CLIENT
from test_export import export
from test_mfa import WITH_MFA, asking
from test_officer import ask as officer_ask
from test_officer import sign_in as officer_sign_in
from test_proposals import asked, held, signed, sweep
from test_r12_grades import sealed, ungraded
from test_samples import weigh


def channels(stack) -> str:
    """The database as the channels app's own role reaches it: what a channels app broken into
    can write, and nothing more."""
    return stack.as_role("channels").database_url


def test_one_batch_sign_in_isnt_sealed_as_another_deciders_approval(stack, approving, provider):
    """Ana signs in once to approve two changes together; a channels app broken into records
    the second as Omar's approval, which Omar never signed for. Neither is sealed."""
    assert not stack.settle(serves=["ana", "ben", "chen"], parts=["billing", "orders"],
                            signers=("ana", "omar")).refused
    asked(stack)  # Ben: move Q-1002, in billing, which Ana decides
    asked(stack, ("change_due_date", {"key": "Q-1003", "due": "2026-11-20"}), person="chen",
          said="Please move Q-1003 to 2026-11-20.")  # Chen: Q-1003, in orders, Omar's to decide
    billing, orders = held(stack)
    assert (billing["deciders"], orders["deciders"]) == (["ana"], ["omar"])
    token, salt = signed(approving, provider, [billing["digest"], orders["digest"]], "approve")
    claims = jwt.decode(token, options={"verify_signature": False})
    hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
    with db.transaction(channels(stack)) as conn:
        for digest, person, proof in ((billing["digest"], "ana", token),
                                      (orders["digest"], "omar", None)):
            conn.execute(
                "insert into proposal_decisions (scenario, digest, decision, person, token, nonce, "
                "salt, issuer, subject, proof, decided_at) values ('sample', %s, 'approve', %s, "
                "%s, %s, %s, %s, %s, %s, %s)", (digest, person, hashed, claims["nonce"], salt,
                                                claims["iss"], f"u-{person}", proof,
                                                stack.gateway.clock()))
    sweep(stack)
    billing, orders = held(stack)
    with db.transaction(stack.admin) as conn:
        rows = conn.execute("select person, seal is not null as sealed from proposal_decisions "
                            "order by id").fetchall()
    assert [(r["person"], r["sealed"]) for r in rows] == [("ana", False), ("omar", False)]
    assert (billing["status"], orders["status"]) == ("waiting", "waiting")
    assert record_of(stack.gateway.scenario, "Q-1003").fields["due date"] != "2026-11-20"


def test_an_approval_isnt_sealed_as_a_rejection_in_words_she_never_wrote(stack, approving, provider):
    """Ana approves two of her own changes together; the channels app records the second as
    her rejection, with words of its own: neither counts, and Ben is told none of them."""
    asked(stack)
    asked(stack, ("close_question", {"key": "Q-1001"}), said="And close Q-1001.")
    one, two = held(stack)
    token, salt = signed(approving, provider, [one["digest"], two["digest"]], "approve")
    claims = jwt.decode(token, options={"verify_signature": False})
    hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
    with db.transaction(channels(stack)) as conn:
        for digest, decision, reason, proof in (
                (one["digest"], "approve", None, token),
                (two["digest"], "reject", "Ben, you are being let go; see HR.", None)):
            conn.execute(
                "insert into proposal_decisions (scenario, digest, decision, person, token, nonce, "
                "salt, issuer, subject, reason, proof, decided_at) values ('sample', %s, %s, "
                "'ana', %s, %s, %s, %s, 'u-ana', %s, %s, %s)",
                (digest, decision, hashed, claims["nonce"], salt, claims["iss"], reason, proof,
                 stack.gateway.clock()))
    sweep(stack)
    assert [p["status"] for p in held(stack)] == ["waiting", "waiting"]
    told = [m["text"] for m in stack.inbox("ben")]
    assert not any("let go" in t for t in told), told


def act_token(url: str, provider, action: str, person: str,
              instance: str = "assistant-finance") -> tuple[str, str]:
    """A sign-in for an act on the instance, made as its page makes one: the token, its salt."""
    salt, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    provider.person = person
    went = httpx.get(f"{provider.url}/auth", params={
        "client_id": CLIENT, "redirect_uri": f"{url}/studio/", "state": "s",
        "nonce": suspension.nonce(action, instance, salt), "code_challenge": challenge.decode(),
        "code_challenge_method": "S256", "max_age": "0"})
    code = parse_qs(went.headers["location"].split("?", 1)[1])["code"][0]
    token = httpx.post(f"{url}/studio/sign-in/token", json={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": f"{url}/studio/"}).json()["id_token"]
    return token, salt


def status(stack) -> tuple[str, str | None]:
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select status, suspended_by from instances "
                           "where id = 'assistant-finance'").fetchone()
    return row["status"], row["suspended_by"]


def test_a_resume_isnt_carried_out_again_from_a_sign_in_used_already(stack, approving, provider):
    """Ana suspends, resumes, and suspends again. A channels app broken into records her earlier
    resume once more, under a nonce and token hash of its own: it isn't carried out, and her
    latest suspension stands."""
    asking(stack)
    provider.claims = dict(WITH_MFA)
    resumed = ("", "")
    for action, then in (("suspend", "suspended"), ("resume", "active"), ("suspend", "suspended")):
        token, salt = act_token(approving, provider, action, "ana")
        r = httpx.post(f"{approving}/studio/api/instances/assistant-finance/status",
                       json={"action": action, "salt": salt},
                       headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert r.status_code == 200, r.text
        if action == "resume":
            resumed = (token, salt)
        sweep(stack)
        assert status(stack)[0] == then
    again = httpx.post(f"{approving}/studio/api/instances/assistant-finance/status",
                       json={"action": "resume", "salt": resumed[1]},
                       headers={"Authorization": f"Bearer {resumed[0]}"}, timeout=30)
    assert again.status_code == 409, again.text  # the channels app's own route says once
    with db.transaction(channels(stack)) as conn:
        conn.execute("insert into status_requests (instance_id, action, person, nonce, salt, "
                     "token, proof, issuer) values ('assistant-finance', 'resume', 'ana', "
                     "'not-the-nonce', %s, 'sha256:not-the-token', %s, %s)",
                     (resumed[1], resumed[0], provider.url))
    sweep(stack)
    assert status(stack) == ("suspended", "ana")
    with db.transaction(stack.admin) as conn:
        outcome = conn.execute("select outcome from status_requests where nonce = 'not-the-nonce'"
                               ).fetchone()["outcome"]
    assert outcome == sealing.RECORDED_ELSE


def test_one_officer_request_exports_once(stack, approving, provider):
    stack.model.reply("Noted, Ben.")
    stack.say("I'm moving to Leeds in March.", person="ben")
    token, salt = officer_sign_in(approving, provider, "export", "ben")
    assert officer_ask(approving, "export", "ben", token, salt).status_code == 200
    assert export(stack, "ben").status_code == 200
    assert export(stack, "ben").status_code == 403  # once, as the team's command says
    with db.transaction(channels(stack)) as conn:
        conn.execute("insert into officer_requests (action, person, officer, nonce, salt, token, "
                     "proof, issuer) values ('export', 'ben', 'noor', 'not-the-nonce', %s, "
                     "'sha256:not-the-token', %s, %s)", (salt, token, provider.url))
    assert export(stack, "ben").status_code == 403  # not again, from the one request


def test_the_channels_app_neither_clears_a_grades_seal_nor_changes_a_sealed_grade(
        stack, approving, provider, database):
    ids = ungraded(stack, 2)
    salt = secrets.token_urlsafe(32)
    grades = dict.fromkeys(ids, "right")
    token = provider.id_token(samples.nonce(grades, salt), "dana", int(time.time()))
    hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
    with db.transaction(channels(stack)) as conn:
        conn.execute(
            "update samples set grade = 'right', graded_by = 'dana', graded_at = %s, "
            "grade_token = %s, grade_nonce = %s, grade_salt = %s, grade_issuer = %s, "
            "grade_subject = 'u-dana', grade_proof = %s where id = any(%s)",
            (stack.gateway.clock(), hashed, samples.nonce(grades, salt), salt, provider.url,
             token, ids))
    weigh(stack)
    assert sealed(stack) == 2
    with db.transaction(stack.admin) as conn:
        before = [r["sealed_at"] for r in conn.execute(
            "select sealed_at from samples where id = any(%s) order by id", (ids,))]
    later = stack.gateway.clock() + timedelta(hours=3)
    stack.at(later.isoformat())
    with pytest.raises(psycopg.errors.InsufficientPrivilege), \
            db.transaction(channels(stack)) as conn:  # round 6's grant, from before the gateway sealed
        conn.execute("update samples set grade_seal = null, grade_proof = %s where id = any(%s)",
                     (token, ids))
    with pytest.raises(psycopg.errors.RaiseException, match="the core's"), \
            db.transaction(channels(stack)) as conn:
        conn.execute("update samples set grade = 'critical' where id = any(%s)", (ids,))
    weigh(stack)
    with db.transaction(stack.admin) as conn:
        after = [r["sealed_at"] for r in conn.execute(
            "select sealed_at from samples where id = any(%s) order by id", (ids,))]
    assert sealed(stack) == 2 and after == before


def test_a_sensitive_change_decided_in_a_batch_isnt_sealed_or_made(stack, approving, provider):
    """The channels app refuses a sensitive change in a batch, and so does the gateway."""
    asked(stack)
    asked(stack, ("close_question", {"key": "Q-1001"}), said="And close Q-1001.")
    with db.transaction(stack.admin) as conn:
        conn.execute("update proposals set sensitive = true where id = 2")
    one, two = held(stack)
    token, salt = signed(approving, provider, [one["digest"], two["digest"]], "approve")
    refused = httpx.post(f"{approving}/decide/proposals", json={
        "proposals": [one["digest"], two["digest"]], "decision": "approve", "salt": salt},
        headers={"Authorization": f"Bearer {token}"})
    assert refused.status_code == 409  # as the channels app's route has it
    claims = jwt.decode(token, options={"verify_signature": False})
    hashed = approvals.HASHED + hashlib.sha256(token.encode()).hexdigest()
    with db.transaction(channels(stack)) as conn:
        for digest in (one["digest"], two["digest"]):
            conn.execute(
                "insert into proposal_decisions (scenario, digest, decision, person, token, nonce, "
                "salt, issuer, subject, proof, decided_at) values ('sample', %s, 'approve', 'ana', "
                "%s, %s, %s, %s, 'u-ana', %s, %s)",
                (digest, hashed, claims["nonce"], salt, claims["iss"], token,
                 stack.gateway.clock()))
    sweep(stack)
    assert [p["status"] for p in held(stack)] == ["waiting", "waiting"]


def test_a_salt_is_one_the_studio_makes():
    salt, reason = secrets.token_urlsafe(32), "It's the wrong record."
    moved = f"{salt} said {proposals._hashed(reason)}"  # the reason's hash, moved into the salt
    assert proposals.nonce(["d" * 64], "reject", salt, reason) == proposals.nonce(["d" * 64], "reject", moved)
    assert sealing.salted(salt) and not sealing.salted(moved)
    assert officer.nonce("erase", "ana x", salt) == officer.nonce("erase", "ana", f"x {salt}")
    assert not sealing.salted(f"x {salt}") and not sealing.salted("short") and not sealing.salted(None)
