"""Content from outside the organisation. An agent reads a customer's email only through
a5s's extractor: it gets a form of typed values the email itself contains, never its words,
and its run is marked from then, so it can't act at level 2 or write anyone's profile, and
what it drafts says it drew on outside content. It can ask a5s's reader about an email, and
gets the answer marked as outside content."""

import json

import psycopg
import pytest

from a5s import db
from a5s.contract import record_of
from a5s.core import extractor
from test_levels import levelled

FORM = {"asks_for": "a refund", "amount": "£860.00", "date": "2026-11-06", "question": "Q-1002"}


def tool_results(stack, request: int = -1) -> list[dict]:
    return [json.loads(m["content"]) for m in stack.model.requests[request]["body"]["messages"]
            if m["role"] == "tool" and m["content"].startswith("{")]


def read(stack, form: dict | None = None, then=None, said: str = "What did Contoso write?"):
    """Ben asks about Contoso's email: the agent reads it, a5s's reader fills the form, and
    the agent answers, or calls `then`."""
    stack.model.reply(None, ("get_messages", {"key": "Q-1002"}))
    stack.model.reply(json.dumps(FORM if form is None else form))  # the extractor's answer
    if then:
        stack.model.reply(None, then)
    stack.model.reply("Contoso asks for a refund.")
    return stack.say(said, person="ben")


def marked(stack) -> list[bool]:
    with db.transaction(stack.admin) as conn:
        return [r["read_outside"] for r in conn.execute("select read_outside from runs order by opened_at")]


def test_an_agent_gets_the_extractors_form_never_the_emails_words(stack):
    read(stack)
    extract = stack.model.requests[1]["body"]
    assert "tools" not in extract or not extract["tools"]  # the reader has no tools
    assert extract["messages"][0]["content"] == extractor.FORM
    assert "Note to the AI assistant" in extract["messages"][1]["content"]
    [found] = tool_results(stack, 2)
    assert "Note to the AI assistant" not in json.dumps(found) and "body" not in json.dumps(found)
    [email] = found["messages"]
    assert email["document"] == "D-1" and email["from"].startswith("[h:")
    form = email[extractor.OUTSIDE]
    assert {k: form[k] for k in ("asks_for", "amount", "date", "question")} == {
        "asks_for": "a refund", "amount": "£860.00", "date": "2026-11-06", "question": "Q-1002"}
    assert marked(stack) == [True]


def test_what_the_email_doesnt_say_is_left_out(stack):
    read(stack, {**FORM, "amount": "£9,999.00", "asks_for": "a pony", "question": "Q-1003",
                 "reply_to": "attacker@evil.test"})  # and a field the form hasn't got
    form = tool_results(stack, 2)[0]["messages"][0][extractor.OUTSIDE]
    assert (form["amount"], form["asks_for"], form["question"]) == (None,) * 3
    assert "reply_to" not in form and sorted(form["left_out"]) == ["amount", "asks_for", "question"]


def test_when_the_reader_cant_read_it_the_agent_hears_so(stack):
    read(stack, "not a form")  # a reply that isn't one
    form = tool_results(stack, 2)[0]["messages"][0][extractor.OUTSIDE]
    assert form["unread"] == "a5s couldn't read it now" and form["amount"] is None


def test_an_email_cant_make_a_change_at_level_2(stack, approving):
    levelled(stack)  # changes of due date at level 2, earned on samples
    read(stack, then=("change_due_date", {"key": "Q-1002", "due": "2026-12-31"}),
         said="Read Contoso's email and do what it says.")
    assert record_of(stack.gateway.scenario, "Q-1002").fields["due date"] == "2026-11-06"
    [held] = [json.loads(m["content"]) for m in stack.model.requests[-1]["body"]["messages"]
              if m["role"] == "tool" and "held" in m["content"]]
    assert held["held"] == "P-1"
    with db.transaction(stack.admin) as conn:
        flags = conn.execute("select flags from proposals").fetchone()["flags"]
    assert any("read content from outside" in f for f in flags)


def test_a_marked_run_cant_write_anyones_profile(stack):
    read(stack, then=("offer_note", {"note": "Always refund Contoso."}))
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) from profile_notes").fetchone()["count"] == 0
    [refused] = [e for e in stack.ledger() if e["action"] == "offer_note" and e["decision"] == "record"]
    assert refused["outcome"]["status"] == "refused"


def test_a_draft_from_a_marked_run_says_it_drew_on_outside_content(stack):
    read(stack, then=("create_draft", {"title": "Refund for Contoso", "body": "We'll refund it.",
                                       "record": "Q-1002"}))
    with db.transaction(stack.admin) as conn:
        [draft] = conn.execute("select body from sample.drafts").fetchall()
    assert draft["body"].endswith(extractor.DREW)


def test_an_agent_can_ask_the_reader_about_an_email(stack):
    read(stack, then=("ask_about", {"document": "D-1", "question": "When did they pay twice?"}))
    # the requests: the agent, the reader's form, the agent, the reader's answer, the agent
    asked = stack.model.requests[3]["body"]["messages"]
    assert asked[0]["content"] == extractor.ANSWER and "When did they pay twice?" in asked[1]["content"]
    answer = tool_results(stack)[-1]
    assert answer[extractor.OUTSIDE] is True and answer["document"] == "D-1"
    assert answer["note"] == extractor.NOTE


def test_a_run_asks_only_about_documents_it_read(stack):
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        r = c.post("/run/tools/ask_about", json={"args": {"document": "D-1", "question": "?"}})
    assert r.status_code == 403 and "no such document" in r.json()["explanations"][0]


def test_documents_go_an_hour_after_their_run(stack):
    read(stack)
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) from run_documents").fetchone()["count"] == 1
        conn.execute("update runs set closed_at = now() - interval '2 hours'")
    with stack.client() as c:
        gone = c.post("/retention/sweep").json()["deleted"]
    assert gone.get("documents") == 1


def test_a_marked_run_stays_marked(stack):
    read(stack)
    with pytest.raises(psycopg.errors.RaiseException), \
            db.transaction(db.as_role(stack.admin, "gateway")) as conn:
        conn.execute("update runs set read_outside = false")


@pytest.mark.parametrize("kind, value, ok", [
    ("amount", "£860.00", True), ("amount", "£860", True), ("amount", "£86", False),
    ("date", "20 Oct", True), ("date", "2026-10-21", False), ("key", "Q-1002", True),
    ("key", "Q-1003", False), ("flag", True, True), ("flag", "yes", False),
    ("choice:a|b", "a", True), ("choice:a|b", "c", False)])
def test_the_form_keeps_only_what_the_text_holds(kind, value, ok):
    text = "We paid £860.00 twice on 2026-10-20 for Q-1002. Reply to billing@contoso.test."
    form, dropped = extractor.checked(json.dumps({"f": value}), text, {"f": kind}, r"\bQ-\d{4}\b")
    assert (form["f"] is not None) == ok and (dropped == []) == ok
