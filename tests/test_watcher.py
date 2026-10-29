"""The watcher: each working morning, it tells each of its people what changed in their
records since it last told them, and what fell due. Code works the facts out from the
records, so the model only puts them into words, and a morning with nothing new starts no
model at all. Each report acts for its person, so it writes to them and to nobody else."""

from dataclasses import replace
from datetime import UTC

import httpx
import pytest

from a5s import db
from a5s.core import registry

THURSDAY = "2026-10-29T09:30:00+00:00"  # 09:30 in London, before any reminder falls due
FRIDAY = "2026-10-30T09:30:00+00:00"
MONDAY = "2026-11-02T09:30:00+00:00"  # half the time for Ana's and Ben's questions has passed


@pytest.fixture
def watching(stack):
    stack.with_watcher()
    return stack


def told(stack) -> list[str]:
    """What a5s asked the agents to do, in order: the facts it worked out from the records."""
    return [r["body"]["messages"][-1]["content"] for r in stack.model.requests
            if "from a5s" in r["body"]["messages"][-1]["content"]]


def fires(stack) -> list[tuple[str, str, str]]:
    with db.transaction(stack.admin) as conn:
        rows = conn.execute("select person, due_at, outcome from report_fires "
                            "order by due_at, person").fetchall()
    return [(r["person"], r["due_at"].astimezone(UTC).isoformat(timespec="minutes"), r["outcome"])
            for r in rows]


def first_mornings(stack) -> None:
    stack.at(THURSDAY)
    stack.model.reply("Ana, you have Q-1001 open, due on Wednesday.")
    stack.model.reply("Ben, you have Q-1002 open, due next Friday.")
    assert stack.scheduler().work_due() == 2


def test_the_first_morning_it_tells_each_person_whats_open(watching):
    first_mornings(watching)
    ana, ben = told(watching)
    assert "Tell Ana Ortiz where their records stand" in ana
    assert ("- Q-1001, Invoice sent to the wrong address, is open, and due by 17:00 on Wed 4 Nov. "
            "https://sample.a5s.dev/records/Q-1001") in ana
    assert "Q-1004" not in ana  # closed before it started watching
    assert "Q-1002, Refund for a duplicate payment, is open" in ben and "Q-1001" not in ben
    assert [m["text"] for m in watching.inbox("ana")] == ["Ana, you have Q-1001 open, due on Wednesday."]
    assert [m["from"] for m in watching.inbox("ben")] == ["watcher"]
    opened = [e for e in watching.ledger() if e["kind"] == "run" and e["action"] == "open"]
    assert [(e["instance"], e["acts_for"], e["args"]["trigger"]) for e in opened] == [
        ("watcher-finance", ["ana"], "report"), ("watcher-finance", ["ben"], "report")]
    assert fires(watching) == [("ana", "2026-10-29T09:00+00:00", "run"),
                               ("ben", "2026-10-29T09:00+00:00", "run")]


def test_a_morning_with_nothing_new_starts_no_model(watching):
    first_mornings(watching)
    asked = len(watching.model.requests)
    watching.at(FRIDAY)
    assert watching.scheduler().work_due() == 0
    assert len(watching.model.requests) == asked
    assert fires(watching)[-2:] == [("ana", "2026-10-30T09:00+00:00", "nothing new"),
                                    ("ben", "2026-10-30T09:00+00:00", "nothing new")]


def test_it_tells_each_person_what_changed_in_their_records_once(watching, monkeypatch):
    first_mornings(watching)
    records = watching.gateway.scenario._records
    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer",
                                            "due": "2026-11-05"})
    monkeypatch.setitem(records, "Q-1005", {
        "key": "Q-1005", "title": "Credit note for order 7790", "status": "open",
        "customer": "Contoso", "owner": "ana", "opened": "2026-10-30", "due": "2026-11-12"})
    monkeypatch.delitem(records, "Q-1004")

    watching.at(FRIDAY)
    watching.model.reply("Ana, Q-1001 is waiting on the customer, and Q-1005 is new.")
    assert watching.scheduler().work_due() == 1  # Ben has nothing new
    ana = told(watching)[-1]
    assert "since you last looked, on Thu 29 Oct" in ana
    for fact in (("- Q-1001, Invoice sent to the wrong address: its status changed from open to "
                  "waiting on customer."),
                 ("- Q-1001, Invoice sent to the wrong address: its due date changed from "
                  "2026-11-04 to 2026-11-05."),
                 ("- Q-1005, Credit note for order 7790, is new to them: status open, due date "
                  "2026-11-12, customer Contoso."),
                 "- Q-1004, Change of billing contact, is no longer among their records."):
        assert fact in ana
    assert "don't add to it" in ana
    assert watching.inbox("ana")[-1]["text"] == "Ana, Q-1001 is waiting on the customer, and Q-1005 is new."

    watching.at(MONDAY)
    watching.model.reply("Ana, Q-1001 is due on Thursday.")  # the assistant's reminders
    watching.model.reply("Ben, Q-1002 is due on Friday.")
    assert watching.scheduler().work_due() == 2  # and nothing more from the watcher
    assert fires(watching)[-2:] == [("ana", "2026-11-02T09:00+00:00", "nothing new"),
                                    ("ben", "2026-11-02T09:00+00:00", "nothing new")]


def test_a_report_that_never_reached_its_person_is_told_next_time(watching):
    def down(_request: int) -> None:
        raise httpx.ConnectError("the provider is down")

    watching.model.on_request = down
    watching.at(THURSDAY)
    watching.scheduler().work_due()
    assert [o for _, _, o in fires(watching)] == ["run", "run"]  # the runs opened, and failed
    assert watching.inbox("ana") == []

    watching.model.on_request = None
    watching.at(FRIDAY)
    watching.model.reply("Ana, you have Q-1001 open, due on Wednesday.")
    watching.model.reply("Ben, you have Q-1002 open, due next Friday.")
    assert watching.scheduler().work_due() == 2  # what they never heard, they hear now
    assert "Tell Ana Ortiz where their records stand" in told(watching)[-2]
    assert [m["text"] for m in watching.inbox("ana")] == ["Ana, you have Q-1001 open, due on Wednesday."]


def test_each_person_hears_in_their_own_morning_and_of_what_fell_due(stack):
    stack.with_watcher(serves=("ana", "ben", "chen"))  # Chen works in Singapore
    stack.at("2026-10-29T01:30:00+00:00")  # 09:30 in Singapore, the small hours in London
    stack.model.reply("Chen, you have Q-1003 open, due on Monday.")
    assert stack.scheduler().work_due() == 1
    assert "Q-1003, Delivery date for order 7781, is open, and due by 17:00 on Mon 2 Nov." in told(stack)[-1]
    assert fires(stack) == [("chen", "2026-10-29T01:00+00:00", "run")]

    stack.at("2026-10-31T01:30:00+00:00")  # Saturday: not a working day
    assert stack.scheduler().work_due() == 0
    stack.at("2026-11-02T01:30:00+00:00")  # Monday morning: it's due this evening
    assert stack.scheduler().work_due() == 0
    stack.at("2026-11-03T01:30:00+00:00")  # Tuesday morning: it fell due, and is still open
    stack.model.reply("Chen, Q-1003 was due yesterday.")
    assert stack.scheduler().work_due() == 1
    assert "- Q-1003, Delivery date for order 7781, was due on Mon 2 Nov and is still open." in told(stack)[-1]
    assert [o for _, _, o in fires(stack)] == ["run", "nothing new", "run"]


def test_a_suspended_watcher_skips_its_mornings_and_tells_what_changed_after(watching, monkeypatch):
    first_mornings(watching)
    with db.transaction(watching.cfg.database_url) as conn:
        assert not registry.set_status(conn, "watcher-finance", by="ben", suspend=True)
    records = watching.gateway.scenario._records
    monkeypatch.setitem(records, "Q-1001", {**records["Q-1001"], "status": "waiting on customer"})
    watching.at(FRIDAY)
    assert watching.scheduler().work_due() == 0
    assert fires(watching)[-2:] == [("ana", "2026-10-30T09:00+00:00", "suspended"),
                                    ("ben", "2026-10-30T09:00+00:00", "suspended")]

    with db.transaction(watching.cfg.database_url) as conn:
        assert not registry.set_status(conn, "watcher-finance", by="ben", suspend=False)
    watching.at(MONDAY)
    watching.model.reply("Ana, Q-1001 is due on Wednesday.")
    watching.model.reply("Ben, Q-1002 is due on Friday.")
    watching.model.reply("Ana, Q-1001 is waiting on the customer now.")
    assert watching.scheduler().work_due() == 3
    ana = told(watching)[-1]
    assert "since you last looked, on Thu 29 Oct" in ana and "to waiting on customer" in ana


def test_the_core_decides_each_report(watching):
    def report(person: str = "ana", instance: str = "watcher-finance", source: str = "records"):
        with watching.client() as c:
            return c.post("/runs", json={"instance": instance, "trigger": {
                "kind": "report", "report": {"person": person, "source": source}}})

    watching.at("2026-10-29T08:30:00+00:00")  # before nine in London
    assert report().json()["detail"]["reasons"] == ["ana's report isn't due"]
    watching.at(THURSDAY)
    watching.scheduler().due()  # the obligations, which a report counts what's open from
    assert report(source="drafts").json()["detail"]["reasons"] == [
        "watcher-finance's release doesn't report on drafts"]
    assert report(instance="assistant-finance").json()["detail"]["reasons"] == [
        "assistant-finance's release doesn't report on records"]
    assert "watcher-finance doesn't serve chen" in report(person="chen").json()["detail"]["reasons"]
    opened = report()
    assert opened.status_code == 200, opened.text
    assert "Q-1001" in opened.json()["task"]
    again = report()
    assert again.status_code == 409 and again.json()["detail"]["answered"]  # once a day

    with watching.client(opened.json()["token"]) as c:
        to_ben = c.post("/run/messages", json={"to": "ben", "text": "Psst, Ben."})
        draft = c.post("/run/tools/create_draft", json={"title": "x", "body": "y"})
    assert to_ben.status_code == 403 and to_ben.json()["reasons"] == ["writes-to-whom-it-acts-for"]
    assert draft.status_code == 403  # it only reads


def test_it_never_reports_to_someone_a5s_may_not_write_to(watching, monkeypatch):
    people = watching.gateway.scenario._people
    monkeypatch.setitem(people, "ben", replace(people["ben"], in_audience=False))
    watching.at(THURSDAY)
    watching.model.reply("Ana, you have Q-1001 open.")
    assert watching.scheduler().work_due() == 1  # Ana's, and no model for Ben
    assert [person for person, _, _ in fires(watching)] == ["ana"]


def test_while_the_records_cant_be_read_the_morning_waits(watching, monkeypatch):
    scenario = watching.gateway.scenario
    watched = scenario.watched

    def down():
        raise RuntimeError("the records system is down")

    monkeypatch.setattr(scenario, "watched", down)
    watching.at(THURSDAY)
    assert watching.scheduler().work_due() == 0 and fires(watching) == []
    monkeypatch.setattr(scenario, "watched", watched)
    watching.model.reply("Ana, you have Q-1001 open.")
    watching.model.reply("Ben, you have Q-1002 open.")
    assert watching.scheduler().work_due() == 2  # the same morning, once they can be read

