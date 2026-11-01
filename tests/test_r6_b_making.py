"""Round 6, reviewer b: changes approved but never made, made but never recorded, and
changes reported as made that weren't.

Each minute the gateway marks each approved change as being made, in a transaction of its
own, and makes the marked ones only after its loop over every waiting change. If anything in
the loop raises for a later change, such as the records system not answering for its record,
the sweep stops there: the changes already marked are never made, and a5s never tries them
again. One decided change whose record can't be read stops the sweep at it every minute, so
no change after it is made, reminded or let go. A change made while its record can't be read
straight after is made, but the ledger never says so and nobody is told. The same change
asked for again in a new run, as a person does after "try again" or days of silence, is held
again, so its deciders are asked twice and can approve it twice. At level 2, a change the
records system refused is reported to the instance's owner as made, and drawn for grading;
and a made change whose report fails answers the agent with an error, so it asks again.
"""

from a5s import db
from a5s.core import digests
from test_levels import levelled
from test_proposals import asked, decide, due_of, held

ALSO = ("change_due_date", {"key": "Q-1001", "due": "2026-11-20"})


def sweep_anyway(stack) -> int:
    """The proposals' sweep, as the scheduler asks for it: its status, whatever it is."""
    with stack.client() as c:
        return c.post("/proposals/sweep").status_code


def test_an_approved_change_is_made_even_when_a_later_one_in_the_sweep_fails(
        stack, approving, provider, monkeypatch):
    asked(stack)  # P-1, Q-1002's due date
    asked(stack, ALSO, said="And move Q-1001 to 2026-11-20.")  # P-2, Q-1001's
    one, two = held(stack)
    assert decide(approving, provider, [one["digest"], two["digest"]]).status_code == 200
    scenario = stack.gateway.scenario
    reading = scenario.record

    def unanswered(key: str):
        if key == "Q-1001":  # the records system times out on this one, this once
            raise RuntimeError("the records system didn't answer")
        return reading(key)

    monkeypatch.setattr(scenario, "record", unanswered)
    sweep_anyway(stack)
    monkeypatch.setattr(scenario, "record", reading)
    sweep_anyway(stack)  # and a minute later all is well
    statuses = [p["status"] for p in held(stack)]
    assert due_of(stack, "Q-1002") == "2026-11-13", statuses  # P-1 was approved: it's made
    assert statuses == ["made", "made"]


def test_one_change_whose_record_cant_be_read_doesnt_stop_every_other(
        stack, approving, provider, monkeypatch):
    asked(stack, ALSO, said="Please move Q-1001 to 2026-11-20.")  # P-1, Q-1001's due date
    asked(stack)  # P-2, Q-1002's
    one, two = held(stack)
    assert decide(approving, provider, [one["digest"], two["digest"]]).status_code == 200
    scenario = stack.gateway.scenario
    reading = scenario.record

    def unanswered(key: str):
        if key == "Q-1001":  # the records system can't read this one, from now on
            raise RuntimeError("the records system didn't answer")
        return reading(key)

    monkeypatch.setattr(scenario, "record", unanswered)
    for _ in range(3):  # three minutes of sweeps
        sweep_anyway(stack)
    statuses = [p["status"] for p in held(stack)]
    assert due_of(stack, "Q-1002") == "2026-11-13", statuses  # P-2 has nothing wrong with it


def test_a_change_made_is_recorded_and_told_even_if_its_record_cant_be_read_after(
        stack, approving, provider, monkeypatch):
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]]).status_code == 200
    scenario = stack.gateway.scenario
    changing, reading, made = scenario._change_due_date, scenario.record, []

    def change(call):
        result = changing(call)
        made.append(call.args)
        return result

    def unanswered(key: str):
        if made:  # the records system stops answering just after it took the change
            raise RuntimeError("the records system didn't answer")
        return reading(key)

    monkeypatch.setattr(scenario, "_change_due_date", change)
    monkeypatch.setattr(scenario, "record", unanswered)
    sweep_anyway(stack)
    monkeypatch.setattr(scenario, "record", reading)
    sweep_anyway(stack)
    assert made and due_of(stack) == "2026-11-13"  # the change was made
    outcomes = [e["outcome"]["status"] for e in stack.ledger()
                if e["kind"] == "tool" and e["action"] == "change_due_date"
                and e["decision"] == "record"]
    assert outcomes == ["ok"], "the ledger has no record of a change a5s made"
    [p] = held(stack)
    assert p["status"] == "made"
    assert any(m["text"].startswith("Ana Ortiz approved P-1, and a5s has made it")
               for m in stack.inbox("ben"))


def test_the_same_change_asked_for_again_while_it_waits_isnt_held_twice(stack, approving):
    first = asked(stack)  # Ben asks; then, having heard nothing, or after "try again", again
    again = asked(stack, said="Please move Q-1002 to 2026-11-13, as I asked.")
    asking = [m for m in stack.inbox("ana") if m["text"].startswith(("P-1 waits", "P-2 waits"))]
    assert (first["held"], again["held"]) == ("P-1", "P-1"), [p["status"] for p in held(stack)]
    assert len(asking) == 1  # Ana is asked once, so she can't approve it twice


def test_a_level_2_change_the_records_system_refused_isnt_reported_as_made(stack):
    levelled(stack)
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        r = c.post("/run/tools/change_due_date",
                   json={"args": {"key": "Q-1002", "due": "next Friday"}})
    assert r.json()["result"] == {"error": "a due date is written as YYYY-MM-DD"}
    assert due_of(stack) == "2026-11-06"  # nothing changed
    with db.transaction(stack.admin) as conn:
        told = [r["text"] for r in conn.execute("select text from digest_items where person = 'ana'")]
        drawn = conn.execute("select count(*) from samples").fetchone()["count"]
    assert not any("made a change itself" in t for t in told), told
    assert drawn == 0  # nothing to grade: no change was made


def test_a_level_2_change_answers_the_agent_even_when_reporting_it_fails(stack, monkeypatch):
    levelled(stack)
    _, token = stack.open_run(sender="ben")

    def unreported(*args, **kwargs):  # the report fails, just after the change was made
        raise RuntimeError("the digest couldn't be kept")

    # (a5s no longer reads the record after the change: the report comes from what it read
    # before, so the failure is put in the report itself)
    monkeypatch.setattr(digests, "keep", unreported)
    with stack.client(token) as c:
        r = c.post("/run/tools/change_due_date",
                   json={"args": {"key": "Q-1002", "due": "2026-11-13"}})
    assert due_of(stack) == "2026-11-13"  # it was made
    # so the agent hears it was, rather than "the tool failed", which it would try again
    assert r.status_code == 200 and r.json()["result"]["due"] == "2026-11-13", r.text
