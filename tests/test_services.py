"""a5s's parts as separate services: the core's channels, the scheduler, and a worker."""

import httpx

from a5s import db, worker
from a5s.services.scheduler import Scheduler, remote_worker
from conftest import free_port, serve


def test_a_message_through_the_core_the_scheduler_and_a_worker_service(stack):
    stack.model.reply("Hello from a worker that holds no secrets.")
    with serve(worker.create_app(stack.url), free_port()) as worker_url:
        scheduler = stack.scheduler(worker=remote_worker(worker_url))
        assert stack.say("Hi", scheduler=scheduler) == "Hello from a worker that holds no secrets."
    assert stack.verify().ok


def lease(stack, key: str, holder: str, seconds: int = 60) -> None:
    with db.transaction(stack.as_role("scheduler").database_url) as conn:
        conn.execute("insert into leases (key, holder, expires_at) "
                     "values (%s, %s, now() + make_interval(secs => %s))", (key, holder, seconds))


def test_a_busy_conversations_message_waits_in_the_queue_then_is_answered(stack):
    stack.model.reply("Here's the answer to your second message.")
    lease(stack, "ana/assistant/general", "the run answering the first message")
    message = stack.send("And another thing")
    assert stack.scheduler().answer_waiting() == 0  # it waits, holding nothing up
    with db.transaction(stack.admin) as conn:
        conn.execute("delete from leases")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == ["Here's the answer to your second message."]


def test_a_message_outlives_a_scheduler_that_stopped_half_way(stack):
    stack.model.reply("Answered by the next scheduler.")
    message = stack.send("Hello")
    assert stack.scheduler()._claim()["id"] == message  # then that scheduler stops
    assert stack.scheduler().answer_waiting() == 0  # its lease still holds the conversation
    with db.transaction(stack.admin) as conn:
        conn.execute("update leases set expires_at = now() - interval '1 second'")  # it ran out
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == ["Answered by the next scheduler."]


def test_a_message_waits_while_the_core_is_down_and_is_answered_after(stack):
    stack.model.reply("Sorry for the wait.")
    message = stack.send("Hello")
    down = Scheduler(stack.as_role("scheduler"), stack.gateway.scenario,
                     http=httpx.Client(base_url=f"http://127.0.0.1:{free_port()}"))
    assert down.answer_waiting() == 1
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select attempts, retry_at > now() as later, answered_at "
                           "from inbound").fetchone()
    assert row["attempts"] == 1 and row["later"] and row["answered_at"] is None
    assert stack.scheduler().answer_waiting() == 0  # not yet
    with db.transaction(stack.admin) as conn:
        conn.execute("update inbound set retry_at = now()")
    assert stack.scheduler().answer_waiting() == 1
    assert stack.answers(message) == ["Sorry for the wait."]


def test_a_run_that_outlives_its_time_is_closed_its_token_dies_and_its_person_is_told(stack):
    run, token = stack.open_run()
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set expires_at = now() - interval '1 second'")
        message = conn.execute("select id::text from inbound").fetchone()["id"]
    with stack.client(token) as c:
        assert c.get("/run").status_code == 401
    stack.scheduler().sweep()
    assert [e["outcome"] for e in stack.ledger(run) if e["action"] == "close"] == ["abandoned"]
    assert stack.answers(message) == [
        "I couldn't finish your last message, so I stopped. Send it again if you still need it."]


def test_a_model_that_ends_with_nothing_to_say_is_asked_once_more(stack):
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("")  # it read the record, and said nothing
    stack.model.reply("Q-1001 is open, and due on Wednesday.")
    assert stack.say("What's Q-1001?") == "Q-1001 is open, and due on Wednesday."
    asked = stack.model.requests[-1]["body"]["messages"][-1]["content"]
    assert asked.startswith("[from a5s, not the person] Your last message was empty")


def test_a_reply_that_stays_empty_isnt_sent(stack):
    stack.model.reply("")
    stack.model.reply("")
    told = stack.say("Hello")
    assert told.startswith("I couldn't finish that.") and len(stack.model.requests) == 2
