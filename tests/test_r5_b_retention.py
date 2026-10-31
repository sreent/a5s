"""Round 5, reviewer b: retention, and the words people said.

The design says a note someone asks to forget goes at once, that reminders go 12 months after
they ended, and that the ledger "keeps nothing that was said". But the ledger records the
arguments of a5s's own tools, masked only when they're longer than 120 characters, and the
ledger can't be changed or deleted, and is copied to locked storage every hour.
"""

import json

from a5s import db

NOTE = "Ana prefers short answers, and no calls before ten."  # her words, under 120 characters
WAITING = "a letter from Dr Okafor's clinic"  # what Ben says he's waiting on


def everything_kept(stack) -> str:
    """Every table a5s keeps that holds text, as one string, including the ledger."""
    with db.transaction(stack.admin) as conn:
        ledger = [r["entry"] for r in conn.execute("select entry from ledger")]
        notes = [r["text"] for r in conn.execute("select text from profile_notes")]
    return json.dumps(ledger) + json.dumps(notes)


def test_a_note_someone_asks_to_forget_leaves_no_words_behind_in_the_ledger(stack):
    stack.model.reply(None, ("offer_note", {"note": NOTE}))
    stack.model.reply(f'Shall I note: "{NOTE}"?')
    stack.say("Please remember I like short answers and no calls before ten.")
    stack.model.reply(None, ("confirm_note", {}))
    stack.model.reply("Noted.")
    stack.say("Yes")
    stack.model.reply(None, ("forget_note", {}))
    stack.model.reply("I've forgotten it.")
    stack.say("Actually, forget my note.")
    with db.transaction(stack.admin) as conn:
        assert not conn.execute("select 1 from profile_notes where text <> ''").fetchone()
    assert NOTE not in everything_kept(stack), (
        "the note she asked a5s to forget is still in the ledger, word for word, where nothing "
        "can delete it")


def test_what_someone_says_theyre_waiting_on_isnt_kept_for_good(stack):
    stack.scheduler().due()  # the obligations, which the scheduler brings in line every minute
    stack.model.reply(None, ("note_waiting", {"record": "Q-1002", "waiting_on": WAITING,
                                              "until": "2026-11-05"}))
    stack.model.reply("Noted.")
    stack.say("I'm waiting on a letter from my doctor's clinic for Q-1002", person="ben")
    with db.transaction(stack.admin) as conn:  # thirteen months on, with nothing said since
        for table, at in (("turns", "at"), ("inbound", "received_at"), ("outbox", "at")):
            conn.execute(f"update {table} set {at} = {at} - interval '13 months'")
        conn.execute("update obligations set waiting_until = waiting_until - interval '13 months', "
                     "waiting_noted_at = waiting_noted_at - interval '13 months'")
    with stack.client() as c:
        c.post("/retention/sweep").raise_for_status()
    with db.transaction(stack.admin) as conn:
        assert not conn.execute("select 1 from turns").fetchone()  # the conversation went
        kept = conn.execute("select waiting_on from obligations where record = 'Q-1002'").fetchone()
    assert WAITING not in everything_kept(stack) + json.dumps(kept), (
        "what Ben said he was waiting on outlives his conversation, in the ledger and the "
        "obligation")
