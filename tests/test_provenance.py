"""Provenance: the keys, amounts and dates an agent writes are matched, in code, against what
its run read and what its person said. A match carries its source, and what matches nothing
is the agent's own, which a5s says apart from the agent's words."""

from a5s import db
from a5s.core import handles, values

PATTERN = r"\bQ-\d{4}\b"


def sent(stack) -> dict:
    return [e for e in stack.ledger() if e["kind"] == "message" and e["action"] == "send"][-1]


def test_values_are_found_and_matched_however_they_are_written():
    said = values.found("Q-1001: refund £1,240.5 by Wed 4 Nov; 300 EUR paid 2026-10-28.", PATTERN)
    assert [(v.kind, v.norm) for v in said] == [
        ("key", "Q-1001"), ("amount", "GBP 1240.50"), ("date", "--11-04"), ("amount", "EUR 300.00"),
        ("date", "2026-10-28")]
    written = values.found("€300 on 28 Oct, £1240.50 by 2026-11-04, and Q-1002 at $5.", PATTERN)
    assert [v.text for v in values.unmatched(written, said)] == ["Q-1002", "$5"]
    assert values.unmatched(values.found("4 Nov 2025", PATTERN), said) == []  # a year, but 4 Nov
    assert values.unmatched(values.found("2025-11-04", PATTERN),
                            values.found("2026-11-04", PATTERN)) != []  # two years, two dates


def test_what_the_agent_read_from_the_records_carries_its_source(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1003"}))
    stack.model.reply("Q-1003 is open, and due on 2026-11-02.")
    told = stack.say("What's the delivery question about?")
    assert told == "Q-1003 is open, and due on 2026-11-02."  # nothing to flag
    assert sent(stack)["args"]["values"] == {"sourced": 2, "own": []}


def test_what_the_person_said_is_theirs(stack):
    stack.model.reply("Noted: £1,240.50 for Contoso by 6 Nov.")
    assert stack.say("Contoso's refund is £1,240.50, due 2026-11-06.") == (
        "Noted: £1,240.50 for Contoso by 6 Nov.")
    assert sent(stack)["args"]["values"] == {"sourced": 2, "own": []}


def test_what_the_agent_wrote_itself_is_said_apart(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1002"}))
    stack.model.reply("Q-1002's refund is £999.00, due on 2026-11-06.")
    told = stack.say("How much is the duplicate refund?")
    assert told == ("Q-1002's refund is £999.00, due on 2026-11-06.\n\n(a5s: £999.00 came from the "
                    "assistant itself, not from the records or from you, so check it before you "
                    "rely on it.)")
    assert sent(stack)["args"]["values"] == {"sourced": 2, "own": ["£999.00"]}


def test_a_draft_says_what_its_agent_wrote_itself(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply(None, ("create_draft", {"title": "Q-1001", "body": "We'll credit £50 by 9 Nov."}))
    stack.model.reply("Here's the draft.")
    stack.say("Draft an apology to Northwind for Q-1001")
    with db.transaction(stack.admin) as conn:
        body = conn.execute("select body from sample.drafts").fetchone()["body"]
    assert body == ("We'll credit £50 by 9 Nov.\n\n(a5s: £50 and 9 Nov came from the assistant "
                    "itself, not from the records or from you, so check them before you rely on "
                    "them.)")


def test_what_another_person_said_is_never_a_source(stack):
    stack.model.reply("Noted.")
    stack.say("The Contoso refund is £1,240.50.", person="ben")
    stack.model.reply("It's £1,240.50.")
    told = stack.say("How much is the Contoso refund?")
    assert told.endswith("so check it before you rely on it.)")  # Ben said it, not Ana


# Handles: sensitive values an agent passes on without seeing them

CONTACT = "accounts@northwind.test"


def echoing(stack, reply: str | None, *tools: tuple[str, dict]) -> None:
    """The scripted model's next step after a tool call, with the handle the tool gave it
    wherever the reply or a tool's arguments say {h}."""
    armed = len(stack.model.requests)

    def write(n: int) -> None:
        if n == armed + 2:
            given = handles.TOKEN.search(stack.model.requests[-1]["body"]["messages"][-1]["content"])
            h = given.group(0)
            stack.model.script.insert(0, (reply and reply.format(h=h), [
                (name, {k: v.format(h=h) for k, v in args.items()}) for name, args in tools]))
    stack.model.on_request = write


def test_a_sensitive_value_reaches_the_person_but_never_the_model(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    echoing(stack, "Write to {h} about Q-1001.")
    assert stack.say("Who do I write to about Q-1001?") == f"Write to {CONTACT} about Q-1001."
    assert CONTACT not in str(stack.model.requests)  # the model only had the handle
    assert CONTACT not in str(stack.ledger())
    with db.transaction(stack.admin) as conn:  # the conversation keeps the handle, too
        said = conn.execute("select content from turns where role = 'agent'").fetchone()["content"]
    assert handles.TOKEN.search(said) and CONTACT not in said


def test_a_system_gets_the_value_and_a_handle_works_only_in_its_run(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    echoing(stack, "Drafted.")
    stack.say("Who do I write to about Q-1001?")
    with db.transaction(stack.admin) as conn:
        [held] = conn.execute("select * from run_handles").fetchall()
    handle = f"[h:{held['handle']}]"
    _, token = stack.open_run()  # another run
    with stack.client(token) as c:
        c.post("/run/tools/create_draft", json={"args": {"title": "Q-1001", "body": f"To {handle}"}})
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select body from sample.drafts").fetchone()["body"].startswith(
            f"To {handle}")  # not this run's: left as it is

    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    echoing(stack, None, ("create_draft", {"title": "Q-1001", "body": "Send it to {h}."}))
    stack.model.reply("Here's the draft.")
    stack.say("Draft a note to Northwind's contact about Q-1001")
    with db.transaction(stack.admin) as conn:
        bodies = [r["body"] for r in conn.execute("select body from sample.drafts order by id")]
    assert bodies[-1] == f"Send it to {CONTACT}."  # the draft is for people: the value


def test_what_a_search_found_is_read_but_the_agents_own_words_are_not(stack):
    stack.model.reply("Noted: it's £50.")  # the agent made the amount up
    stack.say("Northwind wants a credit for Q-1001.")
    stack.model.reply(None, ("search_conversation", {"query": "Northwind"}))
    stack.model.reply("You said Northwind wants a credit for Q-1001, and the credit is £50.")
    told = stack.say("What did I say about Northwind, and when?")
    assert told.endswith("(a5s: £50 came from the assistant itself, not from the records or from "
                         "you, so check it before you rely on it.)")  # a search doesn't launder it
    with db.transaction(stack.admin) as conn:
        read = {(r["kind"], r["text"]) for r in conn.execute(
            "select kind, text from run_reads where source = 'search_conversation'")}
    assert ("amount", "£50") not in read and ("key", "Q-1001") in read
    assert any(kind == "date" for kind, _ in read)  # when each was said, which a5s knows
