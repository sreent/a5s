"""Round 15, the operator's finding (D2): a seal key couldn't be rotated through. Nothing was
sealed again under a new key, and dropping the old one silently dropped level 2 and refused
every run. Now `a5s seal-again` seals again with the new key what the old one sealed, and
retires it; the core won't start without a key it sealed with that isn't retired; and a key
that leaked is retired at once, sealing nothing again, and never comes back."""

from __future__ import annotations

from dataclasses import replace

import pytest

from a5s import cli, db
from a5s.core import delegation, rotation, status, undoing
from conftest import SEAL_KEY
from test_approvals import decide as approve
from test_approvals import proposed, sign_in
from test_proposals import asked, decide, held, sweep
from test_samples import cap, graded, weigh

NEW = "the new seal key, as long as a seal key must be"
TOKENS = {"access_token": "for Ben's account in the records system"}


def keyed(stack, *keys: str) -> tuple:
    """The core started with these keys: the version of the settings in force, why none is,
    and the cap on changing due dates in billing."""
    stack.gateway.cfg = replace(stack.gateway.cfg, seal_keys=keys)
    with db.transaction(stack.cfg.database_url) as conn:
        rotation.started(conn, keys)
        settings, problem = stack.gateway.settings_in_force(conn)
    return settings and settings.serial, problem, cap(stack)


def sealed_all_round(stack, approving, provider) -> None:
    """Under the old key: an approval of the settings in force, a decision on a held change, the
    change kept to undo, its sample, grades that earned level 2, and an account Ben connected."""
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    sweep(stack)
    graded(stack, 224)
    weigh(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into delegations (person, system, sealed) values ('ben', 'records', "
                     "%s)", (delegation.seal((SEAL_KEY,), "ben", "records", TOKENS),))
    found = proposed(stack, level=0)  # last, as its level would hold no change
    token, salt = sign_in(approving, provider, found["digest"])
    assert approve(approving, found["digest"], token, salt).status_code == 200
    stack.scheduler().apply_approved()


def test_seal_again_moves_what_the_old_key_sealed_to_the_new_and_retires_it(stack, approving,
                                                                           provider):
    sealed_all_round(stack, approving, provider)
    before = keyed(stack, SEAL_KEY)
    assert before[1] is None and before[2] == 2
    assert keyed(stack, NEW, SEAL_KEY) == before  # moving to the new key, all of it counts
    with db.transaction(stack.cfg.database_url) as conn:
        moving = rotation.waiting(conn, (NEW, SEAL_KEY))
        found = status.report(conn, [], (NEW, SEAL_KEY))
    assert set(moving) >= {"approvals of the settings", "decisions on held changes", "caps",
                           "samples and their grades", "changes kept to undo",
                           "connected accounts"}, moving
    assert found["seals_waiting"] == moving and "Run `a5s seal-again`" in status.told(found)
    with db.transaction(stack.cfg.database_url) as conn:
        done = rotation.again(conn, (NEW, SEAL_KEY))
    assert done["sealed"] == moving and done["retired"] == [rotation.fingerprint(SEAL_KEY)]
    assert "Sealed again with the first key" in rotation.told(done)
    assert keyed(stack, NEW) == before  # the old key dropped: all of it counts still
    with db.transaction(stack.admin) as conn:
        [kept] = conn.execute("select * from changes_made").fetchall()
        [account] = conn.execute("select sealed from delegations").fetchall()
    assert undoing.intact((NEW,), kept)
    assert delegation.unseal((NEW,), "ben", "records", bytes(account["sealed"])) == TOKENS


def test_the_core_wont_start_without_a_key_it_sealed_with(stack):
    """Dropped before what it sealed is sealed again, it would take level 2 and the settings'
    approvals with it, unsaid."""
    with db.transaction(stack.cfg.database_url) as conn:
        rotation.started(conn, (SEAL_KEY,))
    with pytest.raises(rotation.Refused, match="run `a5s seal-again`"):
        cli._service(replace(stack.cfg, seal_keys=(NEW,)), "gateway")
    with db.transaction(stack.cfg.database_url) as conn, pytest.raises(  # it seals with the old
            rotation.Refused, match="start it with this A5S_SEAL_KEYS first"):
        rotation.again(conn, (NEW, SEAL_KEY))


def test_a_leaked_key_is_retired_sealing_nothing_again_and_never_comes_back(stack):
    graded(stack, 224)
    weigh(stack)
    assert keyed(stack, NEW, SEAL_KEY)[2] == 2
    with db.transaction(stack.cfg.database_url) as conn:
        done = rotation.again(conn, (NEW, SEAL_KEY), leaked=True)
    assert done["sealed"] == {} and "caps" in done["stopped"]
    assert "These stop counting: " in rotation.told(done)
    assert keyed(stack, NEW)[2] == 1  # what it sealed counts no more: level 2 is earned again
    with pytest.raises(rotation.Refused, match="retired as leaked"):
        keyed(stack, NEW, SEAL_KEY)
