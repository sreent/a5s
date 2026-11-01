"""Round 6, reviewer a: counts, and flooding a decider.

- The same change made again in a run counts once and keeps its verdict, but at level 2 the
  gateway makes it again each time: the records system gets it three times while the run's
  limit is one. Nothing gives a tool a key to make it once, so a change that adds, rather than
  sets, goes past the limit.
- Each held change asks each of its deciders at once, past the five urgent messages a day,
  and so does each change past a limit: one message to the agent can send its decider any
  number of requests.
"""

from a5s import db
from test_levels import MOVE, levelled


def test_the_same_change_again_in_a_run_is_made_once(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_run": 1}})
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        answers = [c.post("/run/tools/change_due_date", json={"args": MOVE[1]}).json()
                   for _ in range(3)]
    with db.transaction(stack.admin) as conn:
        made = conn.execute("select count(*) as n from sample.changes where key = 'Q-1002'"
                            ).fetchone()["n"]
        counted = conn.execute("select count(*) as n from action_counts").fetchone()["n"]
    assert counted == 1
    assert made == 1, answers


def test_one_message_cant_flood_a_decider(stack, approving):
    calls = [("change_due_date", {"key": "Q-1002", "due": f"2026-12-{day:02d}"})
             for day in range(1, 31)]
    stack.model.reply(None, *calls)
    stack.model.reply("I've asked Ana Ortiz about each.")
    stack.say("Try each day in December for Q-1002.", person="ben")
    asked = [m for m in stack.inbox("ana") if "waits for your decision" in m["text"]]
    assert len(asked) <= 5, len(asked)
