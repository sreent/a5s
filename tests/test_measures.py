"""The measures a5s's first users baseline (docs/pilot.md): what people owed that fell due and
was done on time, reminders that came on time, how late the rest was, who came back to an
agent, and what a run costs, worked out from a5s's own records; and what the pilot's later
stages show, of held changes and grades, questions between agents, group chats and notes."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from a5s import db
from a5s.config import Prices
from a5s.core import groups, measures, notebook
from test_asking import ASKED, may_ask
from test_notebook import NOTED, learn, with_notebook
from test_proposals import asked, decide, held, sweep


def test_a_run_keeps_its_tokens_in_and_out_apart_and_the_model_it_called(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    with db.transaction(stack.admin) as conn:
        [run] = conn.execute("select tokens, tokens_in, tokens_out, model from runs").fetchall()
    assert (run["tokens"], run["tokens_in"], run["tokens_out"], run["model"]) == (15, 10, 5, "fake")


def test_the_measures_say_what_fell_due_and_was_met(stack):
    with db.transaction(stack.admin) as conn:
        for record, due, done in (("Q-1", "3 days", "4 days"),  # done a day before it was due
                                  ("Q-2", "3 days", "1 day"),  # done two days late
                                  ("Q-3", "2 days", None),  # still open
                                  ("Q-4", "40 days", "1 day")):  # due before the window
            conn.execute(  # each, as an agent acts on it
                "insert into obligations (scenario, source, record, person, title, opened_at, "
                "due_at, done_at, instance_id) values ('sample', 'records', %s, 'ana', "
                "'A question', now() - interval '50 days', now() - %s::interval, "
                "now() - %s::interval, 'assistant-finance')" if done else
                "insert into obligations (scenario, source, record, person, title, opened_at, "
                "due_at, instance_id) values ('sample', 'records', %s, 'ana', 'A question', "
                "now() - interval '50 days', now() - %s::interval, 'assistant-finance')",
                (record, due, done) if done else (record, due))
        conn.execute(  # owed under a scenario the deployment no longer runs
            "insert into obligations (scenario, source, record, person, title, opened_at, "
            "due_at, instance_id) values ('before', 'records', 'Q-5', 'ana', 'A question', "
            "now() - interval '50 days', now() - interval '2 days', 'assistant-finance')")
        conn.execute(  # owed by someone no agent serves, which an agent can't act on
            "insert into obligations (scenario, source, record, person, title, opened_at, "
            "due_at) values ('sample', 'records', 'Q-6', 'chen', 'A question', "
            "now() - interval '50 days', now() - interval '2 days')")
        conn.execute(  # handed to someone else before it fell due: counted as theirs
            "insert into obligations (scenario, source, record, person, title, opened_at, "
            "due_at, done_at, handed_on, instance_id) values ('sample', 'records', 'Q-3', "
            "'ben', 'A question', now() - interval '50 days', now() - interval '2 days', "
            "now() - interval '4 days', true, 'assistant-finance')")
        conn.execute(  # done between two reads of the records, as it fell due: by when, a5s
            "insert into obligations (scenario, source, record, person, title, opened_at, "  # can't
            "due_at, done_at, seen_owed_at, instance_id) values ('sample', 'records', 'Q-7', "
            "'ana', 'A question', now() - interval '50 days', now() - interval '3 days', "
            "now() - interval '2 days', now() - interval '3 days 6 hours', "
            "'assistant-finance')")
        conn.execute("update obligations set chased_at = due_at, escalations = 1 "
                     "where record = 'Q-2'")  # chased, then taken up the line
        conn.execute("update obligations set chased_at = due_at where record = 'Q-3'")
        for due, reminded, in_digest in (("2 days", "2 days", False),  # at its time
                                         ("3 days", "1 day", False),  # two days late
                                         ("5 days", None, False),  # never sent
                                         ("4 days", "3 days 18 hours", True),  # in that day's
                                         ("2 hours", None, True)):  # digest; today's, still to
            conn.execute(  # come
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
        found = measures.report(conn, "sample", {}, 30)
    assert found["obligations"] == {"due": 4, "on_time": 1, "late": 1, "unknown": 1,
                                    "open": 1, "chased": 2, "escalated": 1,
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
        found = measures.report(conn, "sample", {}, 30, served={  # as the directory says
            "assistant": ["ana", "ben", "chen", "dana", "omar", "kofi"]})
    assert found["returning"] == [{"agent": "assistant", "wrote_before": 2, "came_back": 1,
                                   "share": 0.5, "served": 6, "came_back_served": 1,
                                   "served_share": 1 / 6}]  # which the pilot's stop rule reads
    assert found["returning_team"] == {"served": 6, "came_back": 1, "share": 1 / 6}
    assert "1 of the 6 it serves" in measures.told(found)


def test_the_measures_say_what_a_run_costs_on_a_model_with_prices(stack):
    stack.model.reply("Hello, Ana.")
    stack.say("Hello")
    stack.model.reply("Hello again.")
    stack.say("Hello again")
    priced = {"fake": replace(stack.gateway.models["fake"], prices=Prices(3.0, 15.0))}
    with stack.client() as c:
        unpriced = c.get("/measures", params={"days": 7}).json()
    assert unpriced["runs"] == [{"instance": "assistant-finance", "model": "fake", "runs": 2,
                                 "tokens_per_run": 15, "tokens_p90": 15, "cached_share": 0.0,
                                 "cost_per_run": None}]
    with db.transaction(stack.admin) as conn:  # its settings since move it to another model
        conn.execute("update instances set model = 'fake-2' where id = 'assistant-finance'")
        [run] = measures.report(conn, "sample", priced, 7)["runs"]
        assert run["model"] == "fake" and run["cost_per_run"] == (10 * 3.0 + 5 * 15.0) / 1_000_000
        told = measures.told(measures.report(conn, "sample", priced, 7))
    assert "assistant-finance, 2 on fake, 15 tokens each, costing 0.000 each at its prices" in told


def test_an_approved_model_may_say_what_it_costs(tmp_path):
    from a5s.config import load_models
    from conftest import FAKE_MODELS
    path = tmp_path / "models.yaml"
    path.write_text(FAKE_MODELS + "    prices: {input: 3, output: 15}\n")
    assert load_models(path)["fake"].prices == Prices(3.0, 15.0)
    path.write_text(FAKE_MODELS)
    assert load_models(path)["fake"].prices is None


def test_the_measures_say_how_held_changes_were_decided_and_graded(stack, approving, provider):
    """What the pilot's held changes show (docs/pilot.md, stage 3), by the core's clock."""
    asked(stack)  # P-1, approved and made
    decide(approving, provider, [held(stack)[0]["digest"]])
    sweep(stack)
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
          said="Please move Q-1002 to 2026-11-20.")  # P-2, rejected
    decide(approving, provider, [held(stack)[1]["digest"]], "reject")
    sweep(stack)
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-27"}),
          said="Please move Q-1002 to 2026-11-27.")  # P-3, still waiting
    with db.transaction(stack.admin) as conn:  # a grader finds the approved one right
        conn.execute("update samples set grade = case decided when 'approve' then 'right' "
                     "else 'wrong' end, graded_by = 'grace', graded_at = %s",
                     (stack.gateway.clock(),))
        found = measures.report(conn, "sample", {}, 30, stack.gateway.clock())
    decided = {k: found["held"].pop(k) for k in ("decided_hours_p50", "decided_hours_p90")}
    assert found["held"] == {"held": 3, "approved": 1, "rejected": 1, "lapsed": 0, "waiting": 1,
                             "approved_share": 0.5}
    assert None not in decided.values()
    assert found["samples"] == {"graded": 2, "right": 1, "wrong": 1, "critical": 0, "lapsed": 0,
                                "right_share": 0.5}
    told = measures.told({**found, "held": {**found["held"], **decided}})
    assert ("Changes held for a decision: 3, 1 approved, 1 rejected, 0 lapsed undecided and 1 "
            "waiting; half decided within") in told
    assert "Samples graded: 2, 50% right, 1 wrong and 0 critical." in told


def test_the_measures_count_questions_agents_asked_and_mentions_in_groups(stack):
    """What the pilot's last stage shows of agents together and group chats (stage 4)."""
    may_ask(stack)
    stack.model.reply(None, ("ask_agent", {"agent": "watcher", "question": ASKED}))
    stack.model.reply("Nothing changed on Q-1001.")  # the watcher
    stack.model.reply("The watcher says nothing changed on Q-1001.")
    stack.say(ASKED)
    room = groups.key("matrix", "!team:example.org")
    with db.transaction(stack.admin) as conn:
        for person in ("ana", "ben", "ana"):  # what mentions the assistant there
            conn.execute("insert into inbound (id, channel, source_id, person, agent, text, "
                         "reply_to, conversation, members) values (gen_random_uuid(), 'matrix', "
                         "gen_random_uuid()::text, %s, 'assistant', 'Hello', '{}', %s, "
                         "array['ana', 'ben'])", (person, room))
        found = measures.report(conn, "sample", {}, 30)
    [question] = found["questions"]
    assert {k: v for k, v in question.items() if k != "answered_seconds_p90"} == {
        "instance": "watcher-finance", "asked": 1, "answered": 1, "unanswered": 0}
    assert found["groups"] == [{"agent": "assistant", "messages": 3, "chats": 1, "people": 2}]
    told = measures.told(found)
    assert "watcher-finance was asked 1 and answered 1" in told
    assert "the assistant, 3 times in 1 chat, by 2 people" in told


def test_the_measures_count_notes_kept_refused_given_and_let_go(stack):
    with_notebook(stack)
    learn(stack, ("get_record", {"key": "Q-1001"}),
          ("note_learned", {"note": NOTED, "sources": ["Q-1001"]}),
          ("note_learned", {"note": "Q-1001 is due on 2031-01-01.", "sources": ["Q-1001"]}))
    stack.model.reply("Q-1001 is about an invoice.")
    stack.say("What's Q-1001?")  # a run given the note kept
    with db.transaction(stack.admin) as conn:  # Q-1001 is closed in the records, a day later
        conn.execute("insert into sample.changes (key, field, value, made_for) "
                     "values ('Q-1001', 'status', 'closed', 'test')")
        conn.execute("update notebook set checked_at = checked_at - interval '2 days'")
    assert notebook.check(stack.admin, stack.gateway.scenario,
                          stack.gateway.clock() + timedelta(days=1)) == {"kept": 0, "lapsed": 1}
    with db.transaction(stack.admin) as conn:
        found = measures.report(conn, "sample", {}, 30, stack.gateway.clock())
    assert found["notebook"] == [{"instance": "assistant-finance", "notes": 0, "kept": 1,
                                  "refused": 1, "let_go": 1, "given": 1, "runs_given": 1}]
    assert ("assistant-finance, 0 notes now, 1 kept and 1 refused, 1 let go, given 1 time in "
            "1 run") in measures.told(found)
