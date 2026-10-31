"""Round 5, reviewer b: one digest a day for each person, from all the agents together.

The digest waits until the agents' work for it is done (Gateway.busy). Work the core will
refuse to open, such as a chase once its instance's budget for the person is spent, is
never done, so the digest waits all day, with every other agent's news in it. And the day's
digest is keyed by the time it went, so changing the time after it went opens the day again.
"""

from a5s import db

MONDAY = "2026-11-02T09:30:00+00:00"  # half the time for Ana's and Ben's questions has passed


def waiting_for(stack, person: str, text: str, agent: str = "watcher") -> None:
    """An item another agent left for someone's next digest."""
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into digest_items (person, agent, instance_id, text, at) "
                     "values (%s, %s, null, %s, now())", (person, agent, text))


def test_a_spent_budget_for_one_chase_doesnt_hold_the_whole_digest_all_day(stack):
    waiting_for(stack, "ben", "Ben, Q-1002 is waiting on finance.")
    with db.transaction(stack.admin) as conn:  # the assistant spent its day for Ben already
        conn.execute("insert into spend (instance_id, person, day, tokens) "
                     "values ('assistant-finance', 'ben', '2026-11-02', 1000000)")
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")  # Ana's chase runs; Ben's can't
    stack.scheduler().work_due()
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, Q-1001 is due on Wednesday."]

    for when in ("2026-11-02T10:30:00+00:00", "2026-11-02T13:00:00+00:00",
                 "2026-11-02T16:59:00+00:00", "2026-11-02T17:30:00+00:00"):
        stack.at(when)
        stack.scheduler().work_due()
    refused = [e for e in stack.ledger() if e["kind"] == "run" and e["action"] == "open"
               and e["decision"] == "deny" and e["acts_for"] == ["ben"]]
    told = [m["text"] for m in stack.inbox("ben")]
    assert any("Ben, Q-1002 is waiting on finance." in t for t in told), (
        f"Ben's digest waited all day for a chase the core refused {len(refused)} times, so the "
        "watcher's news for him didn't go that day")


def test_changing_the_digest_time_after_it_went_sends_no_second_digest_that_day(stack):
    stack.at(MONDAY)
    stack.model.reply("Ana, Q-1001 is due on Wednesday.")
    stack.model.reply("Ben, Q-1002 is due on Friday.")
    stack.scheduler().work_due()
    assert [m["text"] for m in stack.inbox("ana")] == ["Ana, Q-1001 is due on Wednesday."]

    stack.at("2026-11-02T10:00:00+00:00")  # she asks for her digest at 09:45 from now on,
    with db.transaction(stack.admin) as conn:  # as set_digest_time keeps it
        conn.execute("insert into preferences (person, name, value, set_at) "
                     "values ('ana', 'digest-time', '09:45', now())")
    waiting_for(stack, "ana", "Ana, Q-1001's customer wrote again.")  # news after today's went
    stack.at("2026-11-02T10:01:00+00:00")
    stack.scheduler().work_due()
    with db.transaction(stack.admin) as conn:
        days = conn.execute("select due_at from digests where person = 'ana' "
                            "order by due_at").fetchall()
    assert stack.inbox("ana") == [] and len(days) == 1, (
        f"a second digest went to Ana on Monday: {[d['due_at'].isoformat() for d in days]}")
