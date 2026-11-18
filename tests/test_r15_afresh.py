"""Round 15, the finance clerk's finding (A4): one file, or one look in a mailbox, marked a
person's whole conversation for good: no level 2, nothing said why, and no way out. Now the
mark lasts only while a run is given what a marked run wrote, and summaries fold none of it;
whoever asked hears why a change waits where only the mark holds it; and saying "start afresh"
starts the conversation afresh."""

from __future__ import annotations

from a5s import db
from a5s.services import context
from test_levels import MOVE, due_of, levelled
from test_proposals import held

SAID = "The invoice is for £860.00, due on 4 December."


def marked_run(stack) -> None:
    """A run of Ben's that read content from outside, as if from a file he sent."""
    def mark(n: int) -> None:
        if n == 1:
            with db.transaction(stack.admin) as conn:
                conn.execute("update runs set read_outside = true where closed_at is null")

    stack.model.on_request = mark
    stack.model.reply(SAID)
    stack.say("What's in the invoice I sent?", person="ben")
    stack.model.on_request = None


def marks(stack) -> list[bool]:
    with db.transaction(stack.admin) as conn:
        return [r["read_outside"] for r in conn.execute(
            "select read_outside from runs where trigger->>'kind' = 'message' order by opened_at")]


def flood(stack) -> None:
    """So much of Ben's conversation since that no run is given what the marked run wrote."""
    given = 4 * stack.gateway.definitions["assistant"].context.budget_tokens
    with db.transaction(stack.admin) as conn:
        for _ in range(given // 10_000 + 2):
            conn.execute("insert into turns (person, agent, topic, role, content) values "
                         "('ben', 'assistant', 'general', 'person', %s)", ("so on " * 1_700,))


def told(stack) -> list[str]:
    with db.transaction(stack.admin) as conn:
        return [r["text"] for r in conn.execute(
            "select text from outbox where person = 'ben' order by id")]


def test_the_mark_lasts_only_while_a_run_is_given_what_the_marked_run_wrote(stack):
    marked_run(stack)
    stack.model.reply("Noted.")
    stack.say("Thanks", person="ben")  # given what the marked run wrote: marked too
    flood(stack)
    stack.model.reply("Hello again.")
    stack.say("Hello", person="ben")  # it's further back than a run is given now
    assert marks(stack) == [True, True, False]


def test_a_summary_folds_none_of_what_a_marked_run_wrote(stack):
    marked_run(stack)
    flood(stack)
    stack.model.answering = lambda body: "{}" if "The turns to fold into it" in str(
        body["messages"]) else None
    stack.model.reply("Hello again.")
    stack.say("Hello", person="ben")  # whose run gives way to the summary's
    [folded] = [str(r["body"]["messages"]) for r in stack.model.requests
                if "The turns to fold into it" in str(r["body"]["messages"])]
    assert "What's in the invoice I sent?" in folded  # his own words, as ever
    assert "£860.00" not in folded and context.OUTSIDE in folded
    with db.transaction(stack.admin) as conn:
        [summary] = conn.execute("select outside from summaries").fetchall()
    assert summary["outside"] is False


def test_a_summary_kept_before_with_outside_words_marks_a_run_given_it(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into summaries (person, agent, topic, body, through, outside) "
                     "values ('ben', 'assistant', 'general', %s, 0, true)",
                     (('{"facts": [{"value": "The invoice is for £860.00.", "who": "the '
                       'assistant", "when": "17 Nov"}]}'),))
    stack.model.reply("Hello.")
    stack.say("Hello", person="ben")
    assert marks(stack) == [True]


def test_start_afresh_starts_the_conversation_afresh(stack):
    marked_run(stack)
    stack.say("Start afresh", person="ben")  # no run answers it: a5s does
    assert told(stack)[-1].startswith("Started afresh: the assistant won't read what came "
                                      "before in this chat")
    stack.model.reply("Hello.")
    stack.say("Hello", person="ben")
    assert marks(stack) == [True, False]
    assert SAID not in str(stack.model.requests[-1]["body"]["messages"])  # nor given it


def test_whoever_asked_hears_why_only_the_mark_holds_a_change_and_how_to_start_afresh(
        stack, approving, provider):
    levelled(stack)  # changing due dates in billing works at level 2
    marked_run(stack)
    stack.model.reply(None, MOVE)
    stack.model.reply("It waits for Ana Ortiz to decide.")
    stack.say("Please move Q-1002 to 2026-11-13.", person="ben")
    assert len(held(stack)) == 1  # only the mark holds it
    assert told(stack)[-2].startswith("(a5s: P-1 waits for a person to decide it, because this "
                                      "chat holds what a5s read from outside")
    assert 'after you say "start afresh"' in told(stack)[-2]
    stack.say("start afresh", person="ben")
    stack.model.reply(None, ("change_due_date", {"key": "Q-1001", "due": "2026-11-20"}))
    stack.model.reply("Done.")
    stack.say("Please move Q-1001 to 2026-11-20.", person="ben")
    assert len(held(stack)) == 1 and due_of(stack, "Q-1001") == "2026-11-20"  # at level 2


def test_a_change_held_for_its_level_says_nothing_of_the_mark(stack, approving, provider):
    marked_run(stack)  # at level 1, it waits for a person, marked or not
    stack.model.reply(None, MOVE)
    stack.model.reply("It waits for Ana Ortiz to decide.")
    stack.say("Please move Q-1002 to 2026-11-13.", person="ben")
    assert len(held(stack)) == 1
    assert not any("read from outside" in t for t in told(stack))
