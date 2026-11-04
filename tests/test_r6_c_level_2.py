"""Round 6, reviewer c: what people are told of a change an agent makes at level 2, and of
what samples raise it to.

The instance's owner reads it in their digest, to reverse it through the scenario's own
process if they need to. But a call the records system refused is reported as made, and the
report never says what the change replaced. Whoever the run acted for hears nothing from
a5s, though the plan says they're told, and the agent's instructions say never to say a
change is made until a5s says so. And the whole settings, in words, say an instance works at
level 2 where a5s's cap still holds it at 1.

Each test fails now and says what a5s should do instead.
"""

from __future__ import annotations

import yaml

from a5s import db
from a5s.contract import parse_settings
from a5s.core import approvals
from test_levels import asked, due_of, levelled


def owners_digest(stack) -> list[str]:
    with db.transaction(stack.admin) as conn:
        return [r["text"] for r in conn.execute(
            "select text from digest_items where person = 'ana' order by id")]


def test_a_change_the_records_system_refused_isnt_reported_as_made(stack, approving):
    """The sample's records system answers a due date it can't read with an error, as many
    systems do, without raising. At level 2, a5s reports to the owner that the agent made the
    change, draws it as a sample for grading, and counts it: held changes treat the same
    answer as a failure."""
    levelled(stack)
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "next Friday"}),
          said="Move Q-1002 to next Friday.")
    assert due_of(stack) == "2026-11-06"  # nothing changed: the system refused it
    with db.transaction(stack.admin) as conn:
        drawn = conn.execute("select count(*) as n from samples").fetchone()["n"]
    made = [t for t in owners_digest(stack) if "made a change" in t]
    assert made == [] and drawn == 0, f"reported as made: {made}; drawn as samples: {drawn}"


def test_the_owners_report_says_what_a_change_replaced(stack, approving):
    """The owner reviews level-2 changes and reverses wrong ones. The report says Q-1002's due
    date is now 2026-11-13, not that it was 2026-11-06, though a5s read the record before the
    change, for the sample."""
    levelled(stack)
    asked(stack)
    [item] = owners_digest(stack)
    assert "2026-11-06" in item, item


def test_whoever_a_level_2_change_was_for_hears_it_from_a5s(stack, approving):
    """The plan says a level-2 change is reported to whoever the run acted for. a5s tells only
    the instance's owner. Ben has only the agent's words, which its instructions say never to
    give until a5s says the change is made, and the agent's next run has no notice of it."""
    levelled(stack)
    asked(stack)
    assert due_of(stack) == "2026-11-13"
    with db.transaction(stack.admin) as conn:
        notices = [r["content"] for r in conn.execute(
            "select content from turns where person = 'ben' and role = 'notice'")]
    told = notices + [m["text"] for m in stack.inbox("ben")]
    assert any("Q-1002" in t for t in told), told


def test_a_change_held_past_a_limit_tells_its_decider_so(stack, approving):
    """At level 2, the second change in a run past a limit of one waits for Ana. Her card reads
    as any held change's: nothing says the agent made one already in this run, or that it's
    past the scenario's limit, which is why it waits, and what she most needs to weigh."""
    levelled(stack, limits={"change-due-date": {"per_run": 1}})
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        c.post("/run/tools/change_due_date", json={"args": {"key": "Q-1002", "due": "2026-11-13"}})
        c.post("/run/tools/change_due_date", json={"args": {"key": "Q-1002", "due": "2026-11-20"}})
    with db.transaction(stack.admin) as conn:
        [p] = conn.execute("select * from proposals").fetchall()
    assert any("limit" in f for f in p["flags"]), p["flags"]


def test_the_whole_settings_say_level_2_waits_for_samples(stack):
    """A part owner reviewing the version in force reads that the assistant works at level 2
    for changing due dates, while a5s's cap holds it at level 1 until graders' samples raise
    it, and nothing they read says so."""
    raw = yaml.safe_load(stack.gateway.scenario.settings().raw)
    raw["serial"] += 1
    raw["instances"]["assistant-finance"]["parts"] = {
        "billing": {"level": 1, "actions": {"change-due-date": 2}}}
    whole = approvals.described(parse_settings(yaml.safe_dump(raw).encode()),
                                stack.gateway.definitions, stack.gateway.scenario.person)
    [line] = [w for w in whole if "change-due-date in billing" in w]
    assert "sample" in line, line
