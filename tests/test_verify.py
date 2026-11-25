"""Reply verification (core/verify.py): a record key a run names must be one it read; a
made-up key is answered once more, with the correction, and what remains is the agent's
own, said so in a note apart from its words."""

from a5s import db
from a5s.core import verify


def test_a_key_the_run_read_isnt_unknown(database):
    with db.transaction(database) as conn:
        conn.execute("insert into run_reads (run_id, source, kind, norm, text) values "
                     "(%s, %s, %s, %s, %s)", ("00000000-0000-0000-0000-000000000001", "a5s", "key", "Q-1001", "Q-1001"))
        assert verify.unknown_keys(conn, "00000000-0000-0000-0000-000000000001", "Q-1001 is open.", r"\bQ-\d{4}\b") == []


def test_a_key_the_run_never_read_is_unknown(database):
    with db.transaction(database) as conn:
        assert verify.unknown_keys(conn, "00000000-0000-0000-0000-000000000001", "Q-1001 is open and Q-9999 is too.",
                                   r"\bQ-\d{4}\b") == ["Q-1001", "Q-9999"]


def test_a_reply_without_keys_has_nothing_unknown(database):
    with db.transaction(database) as conn:
        assert verify.unknown_keys(conn, "00000000-0000-0000-0000-000000000001", "The question I saw is open.",
                                   r"\bQ-\d{4}\b") == []


def test_the_correction_is_answered_once_before_the_person_hears(stack):
    """The whole loop: a reply naming a key its run never read is held back, the run is
    asked once more with the correction, and what the person hears is the re-written one."""
    stack.model.reply("Q-9999 is open.")  # its first answer, naming a key it never read
    stack.model.reply("The question I saw is open.")  # what the correction brings back
    message = stack.send("What's the key of the open question?")
    assert stack.scheduler().answer_waiting() == 1
    [said] = stack.answers(message)
    assert said == "The question I saw is open."  # one correction, then it went out
    with db.transaction(stack.admin) as conn:
        [sent] = conn.execute("select count(*) as n from outbox").fetchall()
    assert sent["n"] == 1  # the first answer was held back, nothing was sent twice


def test_what_still_names_the_key_goes_out_with_a5s_note(stack):
    """Bounded: one correction, and what persists goes out, with a5s's own note apart."""
    stack.model.reply("Q-9999 is open.")
    stack.model.reply("Q-9999 is open, I'm sure.")  # the correction didn't take
    message = stack.send("What's the key of the open question?")
    assert stack.scheduler().answer_waiting() == 1
    [said] = stack.answers(message)
    assert said.startswith("Q-9999 is open, I'm sure.") and "(a5s:" in said and "Q-9999" in said  # the agent's words, and a5s's note apart from them

def test_a_key_the_person_asked_about_isnt_made_up(stack):
    """Round 16, A10: a key someone asks about that their run can't read, in a part they
    can't see or one there isn't, was taken as made up when the agent said it back, so the run
    was asked again to leave out what they asked about. What they said counts as read."""
    stack.model.reply("I can't find Q-9999.")
    message = stack.send("What's happening with Q-9999?")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == ["I can't find Q-9999."]  # as it was, at once
    assert len(stack.model.requests) == 1  # never asked again
