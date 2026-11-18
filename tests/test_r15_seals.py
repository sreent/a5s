"""Round 15: a seal binds what it approves. Someone who can write to a5s's database, without the
core's seal key, can't change what a sealed approval makes, decide one change twice, change how a
change is undone, or make grades of samples the core never drew count, nor move grades between
parts or later in time (B1, B2, F3). And the ledger says which of a5s's parts wrote each entry,
which none of them may say for itself (F9)."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.types.json import Jsonb

from a5s import db
from a5s.contract import record_of
from a5s.core import (
    ledger,
    samples,
)
from conftest import SEAL_KEY
from test_proposals import asked, decide, held, sweep
from test_undo import swept as undo_swept
from test_undo import undo


def field(stack, key: str, name: str) -> str:
    return record_of(stack.gateway.scenario, key).fields[name]


def test_an_approved_change_edited_in_the_database_is_never_made(stack, approving, provider):
    """Ana approves moving Q-1002 to 13 Nov, signed in afresh; someone then edits the held call
    in the database. a5s makes nothing that isn't what she approved, and says why (B1, F3a)."""
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    with db.transaction(stack.admin) as conn:  # the database's owner, without the seal key
        conn.execute("update proposals set args = %s where id = %s",
                     (Jsonb({"key": "Q-1003", "due": "2027-06-30"}), p["id"]))
    assert sweep(stack)["made"] == 0
    assert field(stack, "Q-1003", "due date") != "2027-06-30"
    with db.transaction(stack.admin) as conn:
        [ended] = conn.execute("select status, outcome from proposals").fetchall()
    assert ended["status"] == "not made" and "isn't what was approved" in ended["outcome"]


def test_the_values_a_change_carries_are_what_was_approved_too(stack, approving, provider):
    """Its words, which its deciders read, and whom it's for are bound as its call is (B1)."""
    for column, value in (("said", "Change nothing at all."), ("acts_for", ["ana"])):
        asked(stack)
        [p] = held(stack)
        assert decide(approving, provider, [p["digest"]]).status_code == 200
        with db.transaction(stack.admin) as conn:
            conn.execute(f"update proposals set {column} = %s where id = %s", (value, p["id"]))
        assert sweep(stack)["made"] == 0, column
        with db.transaction(stack.admin) as conn:
            conn.execute("delete from proposal_decisions")
            conn.execute("delete from proposals")


def test_a_decision_counts_once(stack, approving, provider):
    """A made change, undone, so its record stands as it did when it was asked for, and set
    waiting again in the database, is never made twice under the same sealed approval (B1)."""
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    assert sweep(stack)["made"] == 1
    with db.transaction(stack.admin) as conn:
        [u] = conn.execute("select id from changes_made").fetchall()
    assert undo(approving, provider, u["id"], "ana").status_code == 200
    undo_swept(stack)
    assert field(stack, "Q-1002", "due date") == "2026-11-06"  # as it stood when asked for
    with db.transaction(stack.admin) as conn:
        conn.execute("update proposals set status = 'waiting', weighed = 0, ended_at = null, "
                     "outcome = null where id = %s", (p["id"],))
    assert sweep(stack)["made"] == 0
    decided = [e for e in stack.ledger() if e["kind"] == "proposal" and e["action"] == "decide"]
    assert len(decided) == 1
    assert field(stack, "Q-1002", "due date") == "2026-11-06"  # not made again


def test_an_undo_edited_in_the_database_undoes_nothing(stack, approving, provider):
    """How a change is undone, as the core kept it, is sealed: one edited after is refused, and
    Ana's undo, signed in afresh, closes no question in another part (B1, F3b)."""
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    assert sweep(stack)["made"] == 1
    with db.transaction(stack.admin) as conn:
        [u] = conn.execute("select id, seal from changes_made").fetchall()
        assert u["seal"]
        conn.execute("update changes_made set undo = %s where id = %s",
                     (Jsonb({"tool": "close_question", "args": {"key": "Q-1003"}}), u["id"]))
    assert undo(approving, provider, u["id"], "ana").status_code == 200
    undo_swept(stack)
    assert field(stack, "Q-1003", "status") != "closed"
    with db.transaction(stack.admin) as conn:
        [after] = conn.execute("select state, outcome from changes_made").fetchall()
    assert "has changed in a5s's records" in (after["outcome"] or "")


def sample(conn, release: str, part: str = "billing", grade: str = "right") -> int:
    """A sample written straight into the database, as no core drew it, graded."""
    return conn.execute(
        "insert into samples (scenario, kind, run_id, instance_id, release, definition, part, "
        "action, said, records, acts_for, drawn_at, grade, graded_by, graded_at) values "
        "('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, 'assistant', %s, "
        "'change-due-date', 'a change', '{}', '{ben}', now(), %s, 'dana', now()) returning id",
        (release, part, grade)).fetchone()["id"]


def test_only_samples_the_core_drew_count(stack):
    """224 samples written straight into the database, each graded and its grade sealed by the
    core, count for nothing: the core drew none of them (B2)."""
    from test_r6_b_caps import release
    with db.transaction(stack.admin) as conn:
        ids = [sample(conn, release(stack)) for _ in range(3)]
        for row in conn.execute("select * from samples where id = any(%s)", (ids,)).fetchall():
            conn.execute("update samples set grade_seal = %s, sealed_at = graded_at where id = %s",
                         (samples.seal((SEAL_KEY,), row), row["id"]))
        rows = conn.execute("select * from samples where id = any(%s)", (ids,)).fetchall()
    assert not any(samples.counted((SEAL_KEY,), r) for r in rows)
    with db.transaction(stack.admin) as conn:  # once the core drew them, as it draws one
        for row in rows:
            samples.sealed_draw(conn, (SEAL_KEY,), row)
            fresh = conn.execute("select * from samples where id = %s", (row["id"],)).fetchone()
            conn.execute("update samples set grade_seal = %s where id = %s",
                         (samples.seal((SEAL_KEY,), fresh), row["id"]))
        rows = conn.execute("select * from samples where id = any(%s)", (ids,)).fetchall()
    assert all(samples.counted((SEAL_KEY,), r) for r in rows)
    with db.transaction(stack.admin) as conn:  # and moved to another part, or later in time,
        conn.execute("update samples set part = 'orders' where id = %s", (ids[0],))
        conn.execute("update samples set sealed_at = sealed_at + interval '1 day' where id = %s",
                     (ids[1],))
        conn.execute("update samples set said = 'something else' where id = %s", (ids[2],))
        rows = conn.execute("select * from samples where id = any(%s)", (ids,)).fetchall()
    assert not any(samples.counted((SEAL_KEY,), r) for r in rows)  # it counts nowhere


def test_the_ledger_says_which_part_wrote_each_entry(stack):
    """The channels app writes entries of its own, as the record of what people did there, and
    the ledger keeps that it wrote them, which it may not say otherwise (F9)."""
    with db.transaction(db.as_role(stack.admin, "channels")) as conn:
        ledger.append(conn, {"kind": "proposal", "action": "decide", "run": None,
                             "instance": None, "decision": "allow",
                             "args": {"by": ["ana"], "proposal": "P-1"}})
    with db.transaction(stack.admin) as conn:
        [last] = conn.execute("select writer from ledger order by seq desc limit 1").fetchall()
    assert last["writer"] == "a5s_channels"
    with pytest.raises(psycopg.Error), db.transaction(  # it can't say it's the core
            db.as_role(stack.admin, "channels")) as conn:
        conn.execute("insert into ledger (seq, entry, prev_hash, hash, writer) values "
                     "(999999, '{}', '', '', 'a5s_gateway')")
