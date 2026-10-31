"""Round 5, reviewer b: work that's lost when something fails after the core commits to it.

The core marks a reminder reminded, or an obligation chased, when it opens the run that
gives it, and a digest sent when it closes the day. If the run then fails, because the
model isn't answering, or the chat a5s writes to doesn't take the message, nothing is
tried again, and the person never hears.
"""

import uuid

import httpx
import pytest

from a5s import db
from a5s.core import breakers, inbox
from a5s.core.matrix import Matrix, MatrixConfig
from conftest import free_port, serve
from test_matrix import AS_TOKEN, DM, HS_TOKEN, Homeserver, invite, said

FRIDAY = "2026-10-30T09:30:00+00:00"  # 09:30 in London: only what a test sets up falls due


def a_reminder_at(stack, when: str, *, in_digest: bool) -> int:
    with db.transaction(stack.admin) as conn:
        return conn.execute(
            "insert into reminders (person, agent, instance_id, about, due_at, offered_at, "
            "offered_run, asked_at, confirmed_at, in_digest) values ('ana', 'assistant', "
            "'assistant-finance', 'call Northwind', %s, now(), gen_random_uuid(), now(), now(), "
            "%s) returning id", (when, in_digest)).fetchone()["id"]


def test_a_reminder_whose_run_fails_is_still_given(stack):
    a_reminder_at(stack, FRIDAY, in_digest=False)  # for a particular time: it goes at once
    stack.at(FRIDAY)
    stack.model.failing = 1  # the provider fails this once
    stack.scheduler().work_due()
    [told] = stack.inbox("ana")  # the model wasn't answering, so a5s reminded her itself
    assert "Northwind" in told["text"] and "a5s is reminding you itself" in told["text"]
    stack.model.reply("Ana, it's time to call Northwind.")
    stack.at("2026-10-30T09:35:00+00:00")
    stack.scheduler().work_due()
    assert stack.inbox("ana") == []  # once


def test_a_chase_whose_run_fails_is_given_later_and_no_escalation_says_it_went(stack):
    stack.at("2026-11-02T09:30:00+00:00")  # half the time for Ana's and Ben's questions has passed
    stack.model.failing = 2  # both chases' runs: the provider isn't answering
    stack.scheduler().work_due()
    [told] = stack.inbox("ben")  # so a5s chased him itself, in his digest
    assert "Q-1002" in told["text"] and "a5s is telling you itself" in told["text"]
    first = [told["text"]]
    stack.gateway.breakers = breakers.Breakers()  # and it's back

    for when in ("2026-11-03T09:30:00+00:00", "2026-11-04T09:30:00+00:00",
                 "2026-11-05T09:30:00+00:00"):
        stack.at(when)
        stack.model.reply("Ben, Q-1002 is due on Friday.")
        stack.scheduler().work_due()
    stack.model.script.clear()
    chased = first + [m["text"] for m in stack.inbox("ben") if "Q-1002" in m["text"]]

    stack.at("2026-11-09T09:30:00+00:00")  # Q-1002 is overdue: Ana, Ben's manager, hears
    stack.scheduler().work_due()
    [escalated] = [m["text"] for m in stack.inbox("ana") if m["text"].startswith("Q-1002")]
    claims = "The assistant reminded them on Mon 2 Nov." in escalated
    assert chased or not claims, (
        "Ben was never reminded of Q-1002, yet the escalation tells Ana he was: " + escalated)
    assert chased, "the chase was marked done when its run opened, and never given"


class Down(Homeserver):
    """A homeserver that doesn't take messages while it's down."""

    down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down and "/send/" in request.url.path:
            return httpx.Response(503, json={"errcode": "M_UNKNOWN", "error": "overloaded"})
        return super().handler(request)


@pytest.fixture
def flaky(stack):
    fake = Down()
    cfg = MatrixConfig("https://matrix.test", "a5s.test", AS_TOKEN, HS_TOKEN)
    stack.gateway.matrix = Matrix(cfg, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    from dataclasses import replace
    endpoint = replace(stack.gateway, cfg=stack.as_role("channels"))
    with serve(inbox.create_app(endpoint), free_port()) as url:
        fake.url = f"{url}/channels/matrix/_matrix/app/v1"
        yield fake


def deliver(fake, *events):
    return httpx.put(f"{fake.url}/transactions/{uuid.uuid4().hex}", json={"events": list(events)},
                     headers={"Authorization": f"Bearer {HS_TOKEN}"})


def test_a_digest_matrix_didnt_take_goes_once_matrix_takes_messages_again(stack, flaky):
    deliver(flaky, invite())
    stack.model.reply("Hello, Ana.")
    deliver(flaky, said("Hello"))
    stack.scheduler().answer_waiting()
    assert flaky.sent[-1]["body"] == "Hello, Ana."

    flaky.down = True  # the homeserver is overloaded at 09:30 on Monday
    stack.at("2026-11-02T09:30:00+00:00")
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2
    failed = [e for e in stack.ledger() if e["action"] == "deliver"
              and e["outcome"]["status"] == "error"]
    assert failed  # the ledger knows Matrix didn't take Ana's digest

    flaky.down = False  # back ten minutes later
    for when in ("2026-11-02T09:40:00+00:00", "2026-11-02T11:00:00+00:00",
                 "2026-11-03T09:30:00+00:00"):
        stack.at(when)
        stack.scheduler().work_due()
    reached = [m["body"] for m in flaky.sent if m["room"] == DM] + [
        m["text"] for m in stack.inbox("ana")]
    assert any("Q-1001 is due on Wednesday" in text for text in reached), (
        "Ana's digest, with her chase in it, was closed before Matrix took it, and never sent again")
