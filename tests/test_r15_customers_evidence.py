"""Round 15's gap, customers in mail: a change an agent asked for that names a customer stays,
as evidence of what agents did, through an erasure of their address, as any change does through
anyone's erasure; while it waits for a decision, the erasure waits for it, since making it would
use their address again."""

from __future__ import annotations

from a5s import db
from test_erase import erase
from test_officer import asked as officer_asks
from test_proposals import asked, decide, held, sweep

PAT = "pat@customer.example"


def test_a_change_that_names_a_customer_holds_up_their_erasure_then_stays(
        stack, approving, provider):
    asked(stack)
    with db.transaction(stack.admin) as conn:  # its words name them, as a handle's value would
        conn.execute("update proposals set said = said || %s", (f"\nFor {PAT}.",))
    officer_asks(approving, provider, "erase", PAT)  # by their address, as for anyone
    refused = erase(stack, PAT)
    assert refused.status_code == 409 and refused.json()["detail"].startswith("P-1 name")
    decide(approving, provider, [p["digest"] for p in held(stack)], "reject")
    sweep(stack)
    done = erase(stack, PAT)  # on the same request: a refused erasure uses none
    assert done.status_code == 200, done.text
    assert done.json()["kept"] == ["P-1"]  # evidence, until its time to keep ends
    [p] = held(stack)
    assert PAT in p["said"]
