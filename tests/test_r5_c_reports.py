"""Round 5, reviewer c: the facts code works out for the watcher's reports.

A report compares the person's records the instance may tell them of now with those it told
them of last time (core/reports.py). A record it may no longer tell them of, because the
settings took its part away, is reported as "no longer among their records", though it's
still theirs, open and owed. The watcher is told to give the facts, and only those."""


def task_sent(stack) -> str:
    return stack.model.requests[-1]["body"]["messages"][-1]["content"]


def test_a_record_the_watcher_stops_covering_isnt_reported_as_gone(stack):
    stack.with_watcher()
    stack.at("2026-10-29T09:30:00+00:00")  # Ana's first morning: what's open
    stack.model.reply("Ana, you have Q-1001 open.")
    stack.model.reply("Ben, you have Q-1002 open.")
    stack.scheduler().work_due()
    assert "Q-1001" in task_sent(stack) or "Q-1002" in task_sent(stack)
    stack.with_watcher(parts=["orders"], signers=("ana", "omar"))  # billing's owner withdraws it
    stack.at("2026-10-30T09:30:00+00:00")
    stack.model.reply("Ana, Q-1001 is no longer yours.")
    stack.model.reply("Ben, Q-1002 is no longer yours.")
    stack.scheduler().work_due()
    asked = [r["body"]["messages"][-1]["content"] for r in stack.model.requests[2:]]
    gone = [line for task in asked for line in task.splitlines() if "no longer among" in line]
    assert gone == [], (
        "Ana and Ben still own Q-1001 and Q-1002, open and owed, but the watcher no longer "
        f"works in billing, and a5s gives it these facts to tell them: {gone}")
