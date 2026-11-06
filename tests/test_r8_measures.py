"""Round 8 of the critique: the measures the pilot baselines and stops by. What fell due counts
what an agent acts on, once, by whoever owed it as it fell due; what the records handed to
someone else isn't done; what was done between two reads of the records as it fell due is
neither on time nor late, since a5s can't know; and who came back is read against everyone
the agents serve (docs/critique.md, round 8)."""

from datetime import UTC, datetime

from a5s import db
from a5s.core import measures

MONDAY, FRIDAY = "2026-11-02T10:00:00+00:00", "2026-11-09T10:00:00+00:00"


def sweep_at(stack, when: str) -> None:
    stack.at(when)
    with stack.client() as c:
        assert c.post("/obligations/sweep").status_code == 200


def owed(stack, when: str = FRIDAY) -> dict:
    with db.transaction(stack.admin) as conn:
        return measures.report(conn, "sample", {}, 30, datetime.fromisoformat(when))["obligations"]


def test_what_the_records_hand_to_someone_else_isnt_done(stack):
    sweep_at(stack, MONDAY)
    with db.transaction(stack.admin) as conn:  # Ben's Q-1002 goes to Ana before it's due
        conn.execute("insert into sample.changes (key, field, value, made_for) "
                     "values ('Q-1002', 'owner', 'ana', 'the records system')")
    sweep_at(stack, "2026-11-03T10:00:00+00:00")
    sweep_at(stack, FRIDAY)  # Q-1001 and Q-1002 fell due, both open: Chen's Q-1003 is in
    o = owed(stack)  # orders, where no agent works, so it isn't counted
    assert (o["due"], o["on_time"], o["open"]) == (2, 0, 2)
    with db.transaction(stack.admin) as conn:
        [handed] = conn.execute("select person, done_at from obligations where handed_on"
                                ).fetchall()
    assert handed["person"] == "ben" and handed["done_at"] is not None  # chased no more


def test_what_was_done_between_two_reads_as_it_fell_due_is_neither_on_time_nor_late(stack):
    sweep_at(stack, MONDAY)
    with db.transaction(stack.admin) as conn:  # Ana closes Q-1001, due Wednesday, while
        conn.execute("insert into sample.changes (key, field, value, made_for) "  # a5s reads
                     "values ('Q-1001', 'status', 'closed', 'test')")  # nothing till Thursday
    sweep_at(stack, "2026-11-05T09:00:00+00:00")
    o = owed(stack)
    assert (o["on_time"], o["late"], o["unknown"]) == (0, 0, 1)
    assert "by when isn't known" in measures.told({**_empty(), "obligations": o})


def test_who_came_back_is_read_against_everyone_the_agents_serve(stack):
    six = ["ana", "ben", "chen", "omar", "dana", "kofi"]
    assert not stack.settle(serves=six).refused
    with db.transaction(stack.admin) as conn:
        for ago in ("20 days", "3 days"):  # only Ana writes, in each fortnight
            conn.execute("insert into inbound (id, channel, source_id, person, agent, text, "
                         "reply_to, received_at) values (gen_random_uuid(), 'local', "
                         "gen_random_uuid()::text, 'ana', 'assistant', 'Hello', '{}', "
                         "now() - %s::interval)", (ago,))
    stack.at(datetime.now(UTC).isoformat())  # the core's clock, as the database's runs
    with stack.client() as c:  # as `a5s measures --days 14` asks the core
        found = c.get("/measures", params={"days": 14}).json()
    [returning] = found["returning"]
    assert (returning["came_back"], returning["served"], returning["served_share"]) == (
        1, 6, 1 / 6)  # below a third, which stops the pilot
    assert found["returning_team"]["share"] == 1 / 6


def _empty() -> dict:
    with_nothing = {"due": 0, "on_time": 0, "late": 0, "unknown": 0, "open": 0, "chased": 0,
                    "escalated": 0, "on_time_share": None, "late_hours_p50": None,
                    "late_hours_p90": None}
    return {"days": 30, "obligations": with_nothing,
            "reminders": {"due": 0, "on_time": 0, "missed": 0, "on_time_share": None},
            "returning": [], "returning_team": {"served": 0, "came_back": 0, "share": None},
            "groups": [], "runs": [],
            "held": {"held": 0, "approved": 0, "rejected": 0, "lapsed": 0, "waiting": 0,
                     "approved_share": None, "decided_hours_p50": None,
                     "decided_hours_p90": None},
            "samples": {"graded": 0, "right": 0, "wrong": 0, "critical": 0, "lapsed": 0,
                        "right_share": None},
            "questions": [], "notebook": []}
