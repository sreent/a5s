"""Round 5, reviewer c: a conversation that lasts months.

Code adds every key, amount and date of the turns it folds into a topic's summary to the
summary's facts (services/summaries.py), and never drops one. Each run in the topic is
given the whole summary first, and the turns get what's left of the budget
(services/context.py). The watcher's daily reports, and a resolver's tickets, are all in
the general topic, so its facts grow with every record and date ever mentioned, until a run
is given the facts and one turn, and the summary run is asked to fold them all again."""

from datetime import UTC, datetime, timedelta

from a5s import db
from a5s.core import topics
from a5s.services import context, summaries

WATCHER_CHARS = 4 * 30_000  # the watcher's budget for its conversation, in characters


def a_year_of_facts(count: int) -> list[dict]:
    """Facts as code keeps them: each record and day a report mentioned, once."""
    start = datetime(2025, 11, 2, tzinfo=UTC)
    facts = []
    for n in range(count):
        when = start + timedelta(days=n // 10)
        facts.append({"kind": "key", "value": f"Q-{n:04d}", "norm": f"Q-{n:04d}", "who": "you",
                      "when": f"{when:%a} {when.day} {when:%b} {when:%Y}"})
    return facts


def test_a_run_still_gets_its_latest_turns_once_a_topic_has_a_long_history(stack):
    with db.transaction(stack.admin) as conn:
        for n in range(10):
            context.add_turn(conn, person="ana", agent="watcher", role="agent",
                             content=f"Report {n}: " + "Q-1001 is still open. " * 25)
        last = conn.execute("select min(id) as id from turns").fetchone()["id"]
        summaries.keep(conn, "ana", "watcher", topics.GENERAL,
                       {"decisions": [], "commitments": [], "open_questions": [],
                        "facts": a_year_of_facts(4_000), "corrections": []}, last - 1,
                       "00000000-0000-0000-0000-000000000000")
        given = context.history(conn, person="ana", agent="watcher", chars=WATCHER_CHARS)
    told = sum(len(t["content"]) for t in given if t["role"] == "summary")
    turns = [t for t in given if t["role"] != "summary"]
    assert len(turns) == 10, (
        f"the summary's facts alone are {told:,} characters of the run's {WATCHER_CHARS:,}, so "
        f"of its 10 latest turns, about 5,000 characters, it's given {len(turns)}")
