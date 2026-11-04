"""Sealing in the gateway. The channels app, which people reach, records what people decide
with the sign-in that made it, and holds no seal key. The gateway checks each recorded sign-in
again against the identity provider's keys, seals it, and lets the sign-in go: what doesn't
check out is refused and never counts. So someone who can write what the channels app writes
can't make a decision count without a real sign-in, by its person, for exactly that decision."""

import secrets
import time
from dataclasses import replace

from a5s import db
from a5s.core import approvals, proposals, sealing
from test_proposals import asked, decide, due_of, held, sweep


def recorded(stack, digest: str, proof: str, person: str = "ana", salt: str | None = None):
    """A decision written as the channels app writes one, with `proof` as its sign-in."""
    salt = salt or secrets.token_urlsafe(32)
    with db.transaction(db.as_role(stack.admin, "channels")) as conn:
        conn.execute(
            "insert into proposal_decisions (scenario, digest, decision, person, token, nonce, "
            "salt, issuer, subject, proof) values ('sample', %s, 'approve', %s, %s, 'n', %s, "
            "'i', 's', %s)", (digest, person, approvals.HASHED + secrets.token_hex(32), salt, proof))


def decisions(stack) -> list[dict]:
    with db.transaction(stack.admin) as conn:
        return conn.execute("select * from proposal_decisions order by id").fetchall()


def test_the_gateway_seals_a_real_decision_and_lets_its_sign_in_go(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    [before] = decisions(stack)
    assert before["proof"] and before["seal"] is None  # recorded, not yet counting
    sweep(stack)
    [after] = decisions(stack)
    assert after["seal"] and after["proof"] is None and after["refused"] is None
    assert due_of(stack) == "2026-11-13"


def test_a_decision_without_a_real_sign_in_never_counts(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    recorded(stack, p["digest"], "not a sign-in at all")
    sweep(stack)
    [d] = decisions(stack)
    assert d["seal"] is None and "doesn't check out" in d["refused"] and d["proof"] is None
    assert due_of(stack) == "2026-11-06" and held(stack)[0]["status"] == "waiting"
    assert [e for e in stack.ledger() if e["action"] == "refuse-sign-in"]


def test_a_sign_in_for_something_else_or_someone_else_never_counts(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    now = int(time.time())
    other = provider.id_token(nonce=proposals.nonce(["0" * 64], "approve", "s" * 20), person="ana",
                              signed_in_at=now)  # Ana's real sign-in, to approve another change
    recorded(stack, p["digest"], other)
    salt = secrets.token_urlsafe(32)
    dana = provider.id_token(nonce=proposals.nonce([p["digest"]], "approve", salt), person="dana",
                             signed_in_at=now)  # a sign-in for this change, but Dana's, as Ana
    recorded(stack, p["digest"], dana, person="omar", salt=salt)
    sweep(stack)
    first, second = decisions(stack)
    assert "wasn't to do what was recorded" in first["refused"]
    assert "someone else's" in second["refused"]
    assert due_of(stack) == "2026-11-06"


def test_a_sign_in_the_browser_kept_never_counts(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    salt = secrets.token_urlsafe(32)
    kept = provider.id_token(nonce=proposals.nonce([p["digest"]], "approve", salt), person="ana",
                             signed_in_at=int(time.time()) - 3 * 3600)  # not made afresh for it
    recorded(stack, p["digest"], kept, salt=salt)
    sweep(stack)
    [d] = decisions(stack)
    assert "wasn't made afresh" in d["refused"]


def test_a_gateway_without_its_seal_key_leaves_decisions_waiting_and_says_so(stack, approving,
                                                                             provider):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    keys = stack.gateway.cfg.seal_keys
    stack.gateway.cfg = replace(stack.gateway.cfg, seal_keys=())  # as if it lost its key
    sweep(stack)
    [d] = decisions(stack)
    assert d["seal"] is None and d["refused"] is None and d["proof"]  # it waits, unrefused
    assert due_of(stack) == "2026-11-06"
    with db.transaction(stack.admin) as conn:
        assert sealing.waiting(conn) == 1
    with stack.client() as c:
        assert c.get("/status").json()["unsealed"] == 1  # decided on the test's clock, long ago
    stack.gateway.cfg = replace(stack.gateway.cfg, seal_keys=keys)
    sweep(stack)
    [d] = decisions(stack)
    assert d["seal"] and d["proof"] is None and due_of(stack) == "2026-11-13"
