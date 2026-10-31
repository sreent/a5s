"""Round 5, reviewer b: edges of the person's own day, and of reminders.

- A confirmed reminder whose person has left the directory is due at every sweep, and every
  sweep opens a run for it that the core refuses, forever: a denial in the ledger each minute.
- Working hours that cross midnight, such as a night shift's, are never "working", so such a
  person never gets a digest, nothing they owe is ever chased, and no escalation reaches them.
- A topic's summary keeps every key, amount and date ever said, and nothing bounds it, so in a
  long conversation it outgrows the budget its runs are given for the conversation.
- Escalations wait for the recipient's working hours, but once they're held for a batch, the
  batch goes an hour after the oldest, whatever the time.
"""

from dataclasses import replace
from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from a5s import db
from a5s.core import digests, obligations
from a5s.services import context

FRIDAY = "2026-10-30T09:30:00+00:00"


def test_a_reminder_for_someone_who_left_isnt_tried_again_every_minute(stack, monkeypatch):
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into reminders (person, agent, instance_id, about, due_at, offered_at, "
            "offered_run, asked_at, confirmed_at, in_digest) values ('ben', 'assistant', "
            "'assistant-finance', 'call Contoso', %s, now(), gen_random_uuid(), now(), now(), "
            "false)", (FRIDAY,))
    people = dict(stack.gateway.scenario._people)
    people.pop("ben")  # he leaves, and the directory no longer knows him
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    for minute in range(30, 35):
        stack.at(f"2026-10-30T09:{minute}:00+00:00")
        stack.scheduler().work_due()
    refused = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"
               and e["decision"] == "deny" and e["args"].get("trigger") == "reminder"]
    assert len(refused) <= 1, (
        f"the core refused his reminder's run {len(refused)} times in five minutes, and will "
        f"every minute from now on: {refused[0]['reasons']}")


def test_someone_on_a_night_shift_gets_a_digest(stack):
    night = replace(stack.gateway.scenario.person("ben"), hours=("22:00", "06:00"))
    at = datetime(2026, 11, 2, 23, 30, tzinfo=UTC)  # 23:30 on Monday in London, on his shift
    with db.transaction(stack.admin) as conn:
        due = digests.window(conn, night, at)
    assert obligations.working(night, at), "a shift that crosses midnight is never working hours"
    assert due is not None, "his digest never opens, so nothing he owes is ever chased"


def test_a_summary_never_crowds_the_conversation_out_of_a_run(stack):
    facts = [{"kind": "amount", "value": f"£{i},000.00", "norm": f"GBP {i}000.00",
              "who": "Ana Ortiz", "when": "Mon 2 Nov 2026"} for i in range(6000)]
    with db.transaction(stack.admin) as conn:  # a year of a busy topic's keys, amounts and dates
        conn.execute("insert into summaries (person, agent, topic, body, through) values "
                     "('ana', 'assistant', 'general', %s, 0)",
                     (Jsonb({"decisions": ["Ana pays suppliers on Fridays."], "facts": facts}),))
        for said in ("What's due this week?", "Q-1001, by Wednesday.", "Thanks"):
            context.add_turn(conn, person="ana", agent="assistant",
                             role="person" if said != "Q-1001, by Wednesday." else "agent",
                             content=said)
        given = context.history(conn, person="ana", agent="assistant", chars=200_000)
    size = sum(len(t["content"]) for t in given)
    assert size <= 200_000, (
        f"a run given 200,000 characters of its conversation gets {size:,}: the summary alone is "
        f"{len(given[0]['content']):,}, with {len(given) - 1} turn(s) after it")


def test_a_batch_of_held_escalations_waits_for_working_hours(stack):
    with db.transaction(stack.admin) as conn:  # Ana had her five today; these two waited
        for text in ("Q-1002, Refund for a duplicate payment, was due on Fri 6 Nov ...",
                     "Q-1005, Credit note, was due on Fri 6 Nov ..."):
            conn.execute("insert into urgent_held (person, agent, instance_id, text, at) "
                         "values ('ana', null, 'assistant-finance', %s, %s)",
                         (text, "2026-11-09T16:45:00+00:00"))  # 16:45 in London, on Monday
    stack.at("2026-11-09T17:45:00+00:00")  # her working day ended at 17:00
    stack.scheduler().work_due()
    assert stack.inbox("ana") == [], (
        "a5s's escalations wait for working hours, but the batch they were held for went at 17:45")
