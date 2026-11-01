"""Round 6, reviewer b: a slow records system stalls everyone while a change is held.

The ledger takes one lock for every entry, held until the transaction commits, so no two
entries are written at once. The gateway holds a change in the transaction that writes its
ledger entry, and reads each record the change names from the scenario's records system
after that entry, inside the same transaction. So while the records system is slow, every
call that writes to the ledger, from any run of any agent, waits for it: model calls, tool
calls, messages and runs opening. Making an approved change does the same, reading its
record again for the grading sample after the ledger entry that records it.
"""

import threading
import time

import httpx

SLOW = 5.0  # seconds the records system takes to answer, as a busy one might


def test_a_slow_records_system_doesnt_stall_other_runs_while_a_change_is_held(
        stack, approving, monkeypatch):
    _, holding = stack.open_run(sender="ben")
    _, other = stack.open_run(sender="ana")
    scenario = stack.gateway.scenario
    reading = scenario.record

    def slow(key: str):
        time.sleep(SLOW)
        return reading(key)

    monkeypatch.setattr(scenario, "record", slow)
    answers: list[httpx.Response] = []

    def hold() -> None:
        with stack.client(holding) as c:
            answers.append(c.post("/run/tools/change_due_date",
                                  json={"args": {"key": "Q-1002", "due": "2026-11-13"}}))

    holder = threading.Thread(target=hold)
    holder.start()
    time.sleep(1.5)  # the hold is waiting on the records system now
    stack.model.reply("Hello, Ana.")
    started = time.monotonic()
    with stack.client(other) as c:  # another run's model call, which reads no record
        r = c.post("/v1/chat/completions", json={
            "model": "fake", "messages": [{"role": "user", "content": "Hello"}]})
    took = time.monotonic() - started
    holder.join()
    assert r.status_code == 200 and answers[0].json()["result"]["held"] == "P-1"
    assert took < 2.0, f"a model call for another run waited {took:.1f}s on the records system"
