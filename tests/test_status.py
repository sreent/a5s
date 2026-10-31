"""Status: how a5s is doing, for the team that runs it, from the core's own records: the
queue, runs, denials, tokens, instances that aren't active, open breakers, and objectives."""

from a5s import db
from a5s.core import status


def test_the_team_sees_how_a5s_is_doing(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    stack.suspend(by="ben")
    assert stack.say("Hello again").startswith("The assistant is suspended")
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["queue"] == {"waiting": 0, "oldest_seconds": None}
    assert {(r["kind"], r["outcome"], r["n"]) for r in now["runs"]} == {("message", "done", 1)}
    assert {(d["kind"], d["action"]) for d in now["denied"]} == {("run", "open")}
    assert now["tokens"] == [{"instance": "assistant-finance", "tokens": 15, "budget_warnings": 0}]
    assert now["not_active"] == [{"id": "assistant-finance", "status": "suspended",
                                  "suspended_by": "ben"}]
    replies = now["objectives"]["replies"]
    assert replies["answered"] == 1 and replies["met"] and replies["p90_seconds"] < 120
    told = status.told(now)
    assert "Runs: 1 (message 1), ended done 1." in told
    assert "Not active: assistant-finance, suspended by ben." in told


def test_an_objective_missed_says_so(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:  # as if she waited ten minutes for it
        conn.execute("update inbound set received_at = received_at - interval '10 minutes'")
    with stack.client() as c:
        now = c.get("/status").json()
    assert not now["objectives"]["replies"]["met"]
    assert "(objective: nine in ten within 120s, missed)" in status.told(now)


def test_only_the_team_sees_it(stack):
    with stack.client("not the service token") as c:
        assert c.get("/status").status_code == 401


def test_nothing_to_measure_is_not_known_rather_than_met(stack):
    """With no answers, a5s can't say its replies are quick: every run may have failed."""
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["objectives"]["replies"]["met"] is None
    assert now["objectives"]["chases"]["met"] is None
    told = status.told(now)
    assert "Replies: none yet (objective: nine in ten within 120s, not known yet)." in told
    assert "Deliveries a chat didn't take: none." in told


def test_deliveries_a_chat_didnt_take_and_budget_warnings_show(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into outbox (person, channel, text, attempts, problem) values "
                     "('ana', 'teams', 'one', 2, 'teams said 502'), "
                     "('ana', 'local', 'two', 5, 'teams said 502')")
        conn.execute("insert into runs (id, instance_id, token_hash, trigger, acts_for, "
                     "expires_at, tokens) values (gen_random_uuid(), 'assistant-finance', 'x', "
                     "'{\"kind\": \"message\"}', '{ana}', now(), 900)")
        conn.execute("insert into spend (instance_id, person, day, tokens, warned_at) values "
                     "('assistant-finance', 'ana', current_date, 900, now())")
    with stack.client() as c:
        now = c.get("/status").json()
    assert now["deliveries"] == {"retrying": 1, "left_in_inbox": 1}
    assert now["tokens"] == [{"instance": "assistant-finance", "tokens": 900, "budget_warnings": 1}]
    told = status.told(now)
    assert ("Deliveries a chat didn't take: 1 being tried again, 1 left in people's local "
            "inbox.") in told
    assert "assistant-finance 900, 1 past four fifths" in told
