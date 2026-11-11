"""Round 9, reviewer C: the studio shows a watcher only "the runs whose every record they may
see". It finds what a run read in run_reads, which retention deletes once the run has been
over for an hour (core/retention.py). After that, nothing is left to hide a run by, unless its
trigger or its ledger entries name a record, so a run that searched records shows, by whom it
acted for and when, to every watcher of its instance."""

from __future__ import annotations

from datetime import timedelta

from a5s import db
from a5s.core import retention
from test_studio_pages import signed_in, with_ops


def _an_hour_later(stack) -> None:
    """The runs closed over an hour ago, and the hourly sweep run, as in production."""
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set closed_at = closed_at - interval '2 hours', "
                     "opened_at = opened_at - interval '2 hours', "
                     "expires_at = expires_at - interval '2 hours'")
        retention.sweep(conn, stack.gateway.clock() + timedelta(hours=2), "sample")


def test_a_run_stays_hidden_from_who_may_not_see_its_records(stack, approving, provider):
    with_ops(stack)  # an assistant in orders that Omar runs, serving Chen
    stack.model.reply(None, ("search_records", {"query": "delivery"}))
    stack.model.reply("Q-1003, the delivery date for order 7781, is open.")
    stack.say("Where are we on the delivery date?", person="chen")
    api = signed_in(approving, provider)
    before = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    assert (before["runs"], before["hidden"]) == ([], 1)  # Ana may not see Q-1003: hidden
    assert not stack.gateway.scenario.sees("ana", "Q-1003")
    _an_hour_later(stack)
    after = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    shown = after["runs"]
    run = api(f"/studio/api/runs/{shown[0]['run']}", "ana").json() if shown else None
    print(after, run and (run["records"], [c["tool"] for c in run["calls"]]))
    # FAILS: an hour on, the sweep has deleted what the run read, so Ana sees Chen's run,
    # that he asked, when, and that it searched records, which she may not see.
    assert (shown, after["hidden"]) == ([], 1)


def test_a_run_that_got_a_record_by_its_key_stays_off_the_list_too(stack, approving, provider):
    with_ops(stack)
    stack.model.reply(None, ("get_record", {"key": "Q-1003"}))
    stack.model.reply("Q-1003 is open.")
    stack.say("Where's my question about order 7781?", person="chen")  # names no key
    api = signed_in(approving, provider)
    _an_hour_later(stack)
    after = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    # The run's page still names Q-1003 in its ledger entries, so it stays hidden there...
    assert all(api(f"/studio/api/runs/{r['run']}", "ana").status_code == 404
               for r in after["runs"])
    # FAILS: ...but the list checks only what the run read and its trigger, so an hour on it
    # shows Chen's run to Ana, by name and time, though its page won't open for her.
    assert (after["runs"], after["hidden"]) == ([], 1)


import pytest as _pytest

# Round 9: this reproduces a finding still to fix. Its test moves beside the code it covers
# once its fix lands, and leaves here.
pytestmark = _pytest.mark.xfail(strict=True, reason="round 9: a finding still to fix")
