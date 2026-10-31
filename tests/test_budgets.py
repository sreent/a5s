"""Budgets: each run, and each instance for each person each day, may use only so many tokens,
as its release says. A fifth of each person's day is kept for chases and reminders. The core
checks before it opens a run and before each model call, and once a budget is spent, the work
waits, and someone asking is told so, in a5s's own words."""

from datetime import date

from a5s import db

MONDAY = "2026-11-02T09:30:00+00:00"  # half the time for Ana's and Ben's questions has passed


def budget(stack, agent: str = "assistant", **limits: int) -> None:
    for name, value in limits.items():
        setattr(stack.gateway.definitions[agent].budget, name, value)


def spent_already(stack, person: str, day: str, tokens: int, instance: str = "assistant-finance"):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into spend (instance_id, person, day, tokens) values (%s, %s, %s, %s)",
                     (instance, person, date.fromisoformat(day), tokens))


def test_each_model_call_counts_against_its_run_and_its_persons_day(stack):
    stack.model.tokens = 40
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("What's Q-1001?")
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select tokens from runs").fetchall()
        [day] = conn.execute("select * from spend").fetchall()
    assert run["tokens"] == 80
    assert (day["instance_id"], day["person"], day["day"], day["tokens"]) == (
        "assistant-finance", "ana", date(2026, 10, 28), 80)  # her day, in her time zone


def test_a_run_stops_at_its_own_budget(stack):
    budget(stack, per_run=40)
    stack.model.tokens = 40
    stack.model.reply(None, ("search_records", {"query": "invoice"}))
    stack.model.reply("Q-1001 mentions an invoice.")  # never asked: the run's budget is spent
    told = stack.say("Which questions mention an invoice?")
    assert told.startswith("That took more work than one run may do, so I stopped.")
    assert len(stack.model.requests) == 1
    refused = [e for e in stack.ledger() if e["kind"] == "model" and e["decision"] == "deny"]
    assert refused[0]["reasons"] == ["budgets"]


def test_answers_stop_short_of_the_share_kept_for_chases(stack):
    budget(stack, per_person_per_day=1000)
    spent_already(stack, "ana", "2026-10-28", 800)  # four fifths of her day
    told = stack.say("Hello")
    assert told == ("The assistant has used its budget for you today, so it can't help with that "
                    "until tomorrow. Ask Ben Okafor if it can't wait.")
    assert stack.model.requests == []  # no run opened, and no model asked

    spent_already(stack, "ana", "2026-11-02", 800)
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    assert stack.scheduler().work_due() == 2  # her chase may use the fifth kept for it
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, Q-1001 is due on Wednesday."]


def test_a_warning_is_recorded_once_a_persons_day_passes_four_fifths(stack):
    budget(stack, per_person_per_day=1000)
    stack.model.tokens = 450
    stack.model.reply(None, ("get_record", {"key": "Q-1001"}))
    stack.model.reply("Q-1001 is open.")
    stack.say("What's Q-1001?")
    warned = [e for e in stack.ledger() if e["kind"] == "budget"]
    assert [(e["action"], e["acts_for"], e["args"]) for e in warned] == [
        ("warn", ["ana"], {"used": 900, "budget": 1000})]


def test_a_report_waits_for_the_next_day_when_its_budget_is_spent(stack):
    stack.with_watcher()
    budget(stack, "watcher", per_person_per_day=1000)
    spent_already(stack, "ana", "2026-10-29", 900, instance="watcher-finance")
    stack.at("2026-10-29T09:30:00+00:00")  # Thursday: the watcher's first morning
    stack.model.reply("Ben, you have Q-1002, waiting on finance.")
    stack.scheduler().work_due()
    assert stack.inbox("ana") == [] and len(stack.inbox("ben")) == 1  # Ben's report, not Ana's
    refused = [e for e in stack.ledger() if e["action"] == "open" and e["decision"] == "deny"]
    assert refused[-1]["reasons"] == ["watcher-finance has used its budget for ana today"]
    stack.at("2026-10-30T09:30:00+00:00")  # a new day, and a new budget
    stack.model.reply("Ana, you have Q-1001, open, due 2026-11-04.")
    stack.scheduler().work_due()
    assert "Q-1001" in stack.inbox("ana")[0]["text"]
