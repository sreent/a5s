"""Round 7: the notebook, and the tools a run is offered.

A note reaches only people who may see every record its run read, and only runs on a case it
names, where it isn't taken as found. It's checked against what the run read of the records it
names, it goes once they change, and the notebook keeps its newest notes, checked apart from the
retention sweep. A run is offered only the tools that can work for it. Each test failed before
round 7's fixes.
"""

from __future__ import annotations

import httpx

from a5s import db
from a5s.core import notebook, provenance
from test_groups import homeserver, mention  # noqa: F401  (a fixture)
from test_matrix import deliver
from test_notebook import NOTED, entries, learn, outcome, with_notebook


def told(stack, request: int = -1) -> str:
    return stack.model.requests[request]["body"]["messages"][0]["content"]


def test_a_note_reaches_only_people_who_may_see_every_record_its_run_read(stack):
    """It draws on billing's Q-1001, naming only orders' Q-1003: Chen, who may not see billing,
    isn't given it, though he may see Q-1003 (A1)."""
    with_notebook(stack)
    assert not stack.settle(parts=["billing", "orders"], serves=["ana", "ben", "chen"],
                            signers=("ana", "omar")).refused
    note = "Q-1003's customer had an invoice go to the wrong address too."
    learn(stack, ("get_record", {"key": "Q-1001"}), ("get_record", {"key": "Q-1003"}),
          ("note_learned", {"note": note, "sources": ["Q-1003"]}))
    [entry] = entries(stack)
    assert entry["sources"] == ["Q-1003"] and sorted(entry["read_records"]) == ["Q-1001", "Q-1003"]
    stack.model.reply("Q-1003 is a delivery.")
    stack.say("What's Q-1003 about?", person="chen")
    assert "a5s has nothing on Q-1003" not in told(stack)  # his run is on Q-1003's case
    assert note not in told(stack)


def test_a_note_may_say_what_the_run_read_of_a_record_beyond_its_fields(stack):
    """get_record gave Q-1001's opened date, which isn't one of the fields a decider weighs
    (C9)."""
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": "Q-1001 was opened on 2026-10-26.", "sources": ["Q-1001"]}))
    assert [e["text"] for e in entries(stack)] == ["Q-1001 was opened on 2026-10-26."]


def test_a_note_says_nothing_another_record_it_read_holds(stack):
    """What the run read of Q-1004 doesn't count for a note naming Q-1001 (C9, A1)."""
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}), ("get_record", {"key": "Q-1004"}),
          ("note_learned", {"note": "Q-1001 was opened on 2026-10-29.", "sources": ["Q-1001"]}))
    assert entries(stack) == [] and "they don't hold 2026-10-29" in outcome(
        stack, "note_learned")["reason"]


def test_a_note_reaches_only_runs_on_a_case_it_names_and_isnt_taken_as_found(stack):
    """Not every run, as a standing instruction (A13), and its values aren't a5s's (A18)."""
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1002"}),
          ("note_learned", {"note": "Q-1002 is Contoso's.", "sources": ["Q-1002"]}))
    stack.model.reply("Q-1004 is closed.")
    stack.say("Is Q-1004 closed?", person="ben")
    assert "Q-1002 is Contoso's." not in told(stack)
    stack.model.reply("Hello.")
    stack.say("Hello", person="ben")
    assert "What you've learned from records" not in told(stack)
    stack.model.reply("It's Contoso's.")
    stack.say("Whose is Q-1002?", person="ben")
    assert "What you've learned from records, about Q-1002" in told(stack)
    assert "Q-1002 is Contoso's." in told(stack)
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select id from runs where trigger->>'topic' = 'Q-1002' "
                             "and trigger->>'kind' = 'message'").fetchall()
        sources = {r["source"] for r in conn.execute(
            "select source from run_reads where run_id = %s", (run["id"],))}
    assert provenance.A5S not in sources


def test_the_notebook_keeps_its_newest_notes(stack, monkeypatch):
    """A new note makes room, oldest first: it never fills and stops (C10, B15)."""
    monkeypatch.setattr(notebook, "MOST", 2)
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}), ("get_record", {"key": "Q-1004"}),
          ("note_learned", {"note": "Q-1001 is Northwind's.", "sources": ["Q-1001"]}),
          ("note_learned", {"note": "Q-1004 is Northwind's too.", "sources": ["Q-1004"]}),
          ("note_learned", {"note": "Q-1001 and Q-1004 are both Northwind's.",
                            "sources": ["Q-1001", "Q-1004"]}))
    assert [e["text"] for e in entries(stack)] == [
        "Q-1004 is Northwind's too.", "Q-1001 and Q-1004 are both Northwind's."]
    assert [e["args"]["why"] for e in stack.ledger() if e["kind"] == "notebook"] == [
        "the notebook keeps the newest 2"]


def test_a_records_system_that_fails_holds_up_no_other_sweep(stack, monkeypatch):
    """Notes are checked apart, outside the retention sweep's transaction: retention still
    deletes what's past its time, and the note waits to be checked again (A12, B3)."""
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}))
    with db.transaction(stack.admin) as conn:  # a note due to be checked, and words past
        conn.execute("update notebook set checked_at = checked_at - interval '2 days'")
        conn.execute("insert into turns (person, agent, topic, role, content, at) values "
                     "('ben', 'assistant', 'general', 'person', 'old words', "
                     "now() - interval '13 months')")

    def down(key: str):
        raise httpx.ConnectError("the records system is down")

    monkeypatch.setattr(stack.gateway.scenario, "record", down)
    with stack.client() as c:
        swept = c.post("/retention/sweep")
        checked = c.post("/notebook/sweep")  # apart, so the records hold up no other sweep
    assert swept.status_code == 200 and checked.json() == {"kept": 0, "lapsed": 0}
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) as n from turns where content = 'old words'"
                            ).fetchone()["n"] == 0
    assert len(entries(stack)) == 1  # it waits, unchecked, for the records


def test_a_run_is_offered_only_tools_that_can_work_for_it(stack, homeserver):  # noqa: F811
    """note_learned only in a run for nobody, and one person's own tools never in a group
    (C13)."""
    with_notebook(stack)
    stack.model.reply("Hello.")
    stack.say("Hello")
    assert "note_learned" not in stack.model.tool_names(-1)
    assert {"offer_note", "list_reminders"} <= set(stack.model.tool_names(-1))
    stack.model.reply("Hello, both.")
    deliver(homeserver, mention("Hello"))
    stack.scheduler().answer_waiting()
    offered = set(stack.model.tool_names(-1))
    assert not offered & {"offer_note", "confirm_note", "forget_note", "list_reminders",
                          "cancel_reminder", "note_waiting", "set_digest_time"}
    assert {"offer_reminder", "confirm_reminder", "search_conversation"} <= offered
