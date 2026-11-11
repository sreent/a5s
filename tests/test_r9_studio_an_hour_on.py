"""Round 9 of the critique: the studio shows a watcher only the runs whose every record they
may see, and an hour on is no different: a5s keeps the keys a run handled with the run, in
run_records, while what it read goes after an hour (docs/critique.md, round 9)."""

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
    assert (shown, after["hidden"]) == ([], 1)  # the records it handled are kept with the run


def test_a_run_that_got_a_record_by_its_key_stays_off_the_list_too(stack, approving, provider):
    with_ops(stack)
    stack.model.reply(None, ("get_record", {"key": "Q-1003"}))
    stack.model.reply("Q-1003 is open.")
    stack.say("Where's my question about order 7781?", person="chen")  # names no key
    api = signed_in(approving, provider)
    _an_hour_later(stack)
    after = api("/studio/api/instances/assistant-ops/runs", "ana").json()
    assert all(api(f"/studio/api/runs/{r['run']}", "ana").status_code == 404
               for r in after["runs"])
    assert (after["runs"], after["hidden"]) == ([], 1)  # the list and the page agree

