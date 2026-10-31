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
