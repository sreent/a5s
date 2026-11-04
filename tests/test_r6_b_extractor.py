"""Round 6, reviewer b: what the extractor costs, and what it reads.

The extractor sends each document to the model whole, however long, though the run's budget
is checked only for whether any is left: one long email can cost more than the run's whole
budget, and every question about it sends it again. It reads every document in what a tool
returns before a5s withholds the records the run may not see, so it reads, and keeps for the
run's questions, the emails of records in parts the instance doesn't work in. And reading
the same email again in a run pays for reading it again.
"""

import json

from a5s.core import extractor
from a5s.core.gateway import CHARS_PER_TOKEN
from test_outside import FORM, read


def answering_for_the_reader(stack) -> list[str]:
    """a5s's reader's calls, answered as they come, whatever the script says: the documents
    the model was given to read, or asked about, in order."""
    read: list[str] = []

    def answer(_: int) -> None:
        body = stack.model.requests[-1]["body"]
        system = body["messages"][0]["content"]
        if system in (extractor.FORM, extractor.ANSWER):
            read.append(body["messages"][1]["content"])
            reply = json.dumps(FORM) if system == extractor.FORM else "It ships to Leeds."
            stack.model.script.insert(0, (reply, []))

    stack.model.on_request = answer
    return read


def test_a_document_bigger_than_a_runs_whole_budget_isnt_sent_whole(stack, monkeypatch):
    scenario = stack.gateway.scenario
    statement = "We paid £860.00 twice on 2026-10-20. " + "Our ledger, line by line. " * 80_000
    monkeypatch.setattr(scenario, "_messages", [  # an email with a long statement pasted in
        {"record": "Q-1002", "from": "billing@contoso.test", "at": "2026-10-27", "body": statement}])
    read(stack)
    [reader] = [r["body"] for r in stack.model.requests
                if r["body"]["messages"][0]["content"] == extractor.FORM]
    sent = len(json.dumps(reader))
    whole = stack.gateway.definitions["assistant"].budget.per_run * CHARS_PER_TOKEN
    assert sent < whole, f"the reader was sent {sent:,} characters: the run's budget is {whole:,}"


def test_a_run_reads_and_asks_about_only_the_documents_of_records_it_may_see(stack,
                                                                            monkeypatch):
    scenario = stack.gateway.scenario
    getting = scenario._get_messages

    def with_a_related_question(call):  # a thread that names another customer's question
        found = getting(call)
        found["related"] = [{"key": "Q-1003", "from": "orders@fabrikam.test", "at": "2026-10-26",
                             "body": "Order 7781 ships to 12 Mill Lane, Leeds, on 2026-11-09."}]
        return found

    monkeypatch.setattr(scenario, "_get_messages", with_a_related_question)
    reader = answering_for_the_reader(stack)
    _, token = stack.open_run(sender="ben")  # assistant-finance works in billing, not orders
    with stack.client(token) as c:
        got = c.post("/run/tools/get_messages", json={"args": {"key": "Q-1002"}})
        asked = c.post("/run/tools/ask_about",
                       json={"args": {"document": "D-2", "question": "Where does it ship?"}})
    assert "Q-1003" not in got.text  # a5s withheld Q-1003 from the agent
    assert not any("Mill Lane" in r for r in reader), "the reader read Q-1003's email for it"
    assert asked.status_code == 403, asked.text


def test_reading_the_same_email_again_in_a_run_doesnt_pay_the_reader_again(stack):
    reader = answering_for_the_reader(stack)
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        for _ in range(2):
            assert c.post("/run/tools/get_messages",
                          json={"args": {"key": "Q-1002"}}).status_code == 200
    assert len(reader) == 1, f"one email, read {len(reader)} times in one run"
