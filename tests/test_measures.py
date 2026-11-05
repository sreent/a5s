"""The measures a5s's first users baseline (docs/pilot.md): what people owed that fell due and
was done on time, reminders that came on time, how late the rest was, who came back to an
agent, and what a run costs, worked out from a5s's own records."""

from __future__ import annotations

from dataclasses import replace

from a5s import db
from a5s.core import measures


def test_a_run_keeps_its_tokens_in_and_out_apart(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select tokens, tokens_in, tokens_out from runs").fetchall()
    assert (run["tokens"], run["tokens_in"], run["tokens_out"]) == (15, 10, 5)


def test_the_measures_say_what_fell_due_and_was_met(stack):
    with db.transaction(stack.admin) as conn:
        for record, due, done in (("Q-1", "3 days", "4 days"),  # done a day before it was due
                                  ("Q-2", "3 days", "1 day"),  # done two days late
                                  ("Q-3", "2 days", None),  # still open
                                  ("Q-4", "40 days", "1 day")):  # due before the window
            conn.execute(
                "insert into obligations (scenario, source, record, person, title, opened_at, "
                "due_at, done_at) values ('sample', 'records', %s, 'ana', 'A question', "
                "now() - interval '50 days', now() - %s::interval, "
                "now() - %s::interval)" if done else
                "insert into obligations (scenario, source, record, person, title, opened_at, "
                "due_at) values ('sample', 'records', %s, 'ana', 'A question', "
                "now() - interval '50 days', now() - %s::interval)",
                (record, due, done) if done else (record, due))
        for due, reminded, in_digest in (("2 days", "2 days", False),  # at its time
                                         ("3 days", "1 day", False),  # two days late
                                         ("5 days", None, False),  # never sent
                                         ("4 days", "3 days 18 hours", True)):  # in that day's
            conn.execute(  # digest
                "insert into reminders (person, agent, instance_id, about, due_at, offered_at, "
                "offered_run, asked_at, confirmed_at, reminded_at, in_digest) values ('ana', "
                "'assistant', 'assistant-finance', 'something', now() - %s::interval, "
                "now() - interval '9 days', gen_random_uuid(), now() - interval '9 days', "
                "now() - interval '9 days', now() - %s::interval, %s)",
                (due, reminded, in_digest)) if reminded else conn.execute(
                "insert into reminders (person, agent, instance_id, about, due_at, offered_at, "
                "offered_run, asked_at, confirmed_at, in_digest) values ('ana', 'assistant', "
                "'assistant-finance', 'something', now() - %s::interval, "
                "now() - interval '9 days', gen_random_uuid(), now() - interval '9 days', "
                "now() - interval '9 days', %s)", (due, in_digest))
        found = measures.report(conn, {}, 30)
    assert found["obligations"] == {"due": 3, "on_time": 1, "late": 1, "open": 1,
                                    "on_time_share": 1 / 3, "late_hours_p50": 48.0,
                                    "late_hours_p90": 48.0}
    assert found["reminders"] == {"due": 4, "on_time": 2, "missed": 1, "on_time_share": 0.5}


def test_the_measures_count_who_came_back_to_an_agent(stack):
    with db.transaction(stack.admin) as conn:
        for person, ago in (("ana", "40 days"), ("ana", "3 days"),  # came back
                            ("ben", "45 days"),  # didn't
                            ("former:3f9a", "50 days"),  # left: not counted
                            ("chen", "2 days")):  # new this month
            conn.execute("insert into inbound (id, channel, source_id, person, agent, text, "
                         "reply_to, received_at) values (gen_random_uuid(), 'local', "
                         "gen_random_uuid()::text, %s, 'assistant', 'Hello', '{}', "
                         "now() - %s::interval)", (person, ago))
        found = measures.report(conn, {}, 30)
    assert found["returning"] == [{"agent": "assistant", "wrote_before": 2, "came_back": 1,
                                   "share": 0.5}]


def test_the_measures_say_what_a_run_costs_on_a_model_with_prices(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    stack.model.reply("Hello again.")
    stack.say("Hello again")
    priced = {"fake": replace(stack.gateway.models["fake"], prices=(3.0, 15.0))}
    with stack.client() as c:
        unpriced = c.get("/measures", params={"days": 7}).json()
    assert unpriced["runs"] == [{"instance": "assistant-finance", "model": "fake", "runs": 2,
                                 "tokens_per_run": 15, "tokens_p90": 15, "cost_per_run": None}]
    with db.transaction(stack.admin) as conn:
        [run] = measures.report(conn, priced, 7)["runs"]
        assert run["cost_per_run"] == (10 * 3.0 + 5 * 15.0) / 1_000_000
        told = measures.told(measures.report(conn, priced, 7))
    assert "assistant-finance, 2 on fake, 15 tokens each, 0.000 each" in told


def test_an_approved_model_may_say_what_it_costs(tmp_path):
    from a5s.config import load_models
    from conftest import FAKE_MODELS
    path = tmp_path / "models.yaml"
    path.write_text(FAKE_MODELS + "    prices: {input: 3, output: 15}\n")
    assert load_models(path)["fake"].prices == (3.0, 15.0)
    path.write_text(FAKE_MODELS)
    assert load_models(path)["fake"].prices is None
