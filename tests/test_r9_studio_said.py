"""Round 9 of the critique: the ledger keeps, beside each message's digest, the keys, amounts
and dates an agent wrote that came from nothing it read; a watcher's page carries no ledger
entries, so what an agent told someone reaches nobody who watches (docs/critique.md, round 9)."""

from __future__ import annotations

from test_studio_pages import signed_in


def test_what_an_agent_said_reaches_no_watcher(stack, approving, provider):
    stack.model.reply("Ana, your advance of £2,750.00 is due back on 19 December.")
    stack.say("When do I repay my salary advance?", person="ana")
    api = signed_in(approving, provider)
    [run] = api("/studio/api/instances/assistant-finance/runs", "ben").json()["runs"]
    shown = api(f"/studio/api/runs/{run['run']}", "ben")  # Ben, its deputy
    assert shown.status_code == 200 and "entries" not in shown.json()
    for said in ("salary advance", "2,750.00", "19 December"):  # neither Ana's words nor the
        assert said not in shown.text  # agent's, nor their digests
