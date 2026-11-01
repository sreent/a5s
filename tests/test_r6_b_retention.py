"""Round 6, reviewer b: what phase 2 keeps forever.

Retention deletes graded samples a year after they're graded, but a sample nobody grades
keeps its snapshot of the records, with customers' names, and whom it was for, forever. And
the counts of changes, each naming the people it was for, are never deleted, though nothing
reads one after its 30 days.
"""

from a5s import db


def swept(stack) -> dict:
    with stack.client() as c:
        r = c.post("/retention/sweep")
    r.raise_for_status()
    return r.json()["deleted"]


def test_a_sample_nobody_graded_goes_in_time(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, part, "
            "action, said, records, acts_for, drawn_at) values ('sample', 'proposal', "
            "gen_random_uuid(), 'assistant-finance', 'r', 'assistant', 'billing', "
            "'change-due-date', 'Q-1002, Refund for a duplicate payment, as it stands: customer "
            "Contoso.', '{\"Q-1002\": {\"title\": \"Refund for a duplicate payment\"}}', '{ben}', "
            "now() - interval '13 months')")
    swept(stack)
    with db.transaction(stack.admin) as conn:
        left = conn.execute("select count(*) from samples").fetchone()["count"]
    assert left == 0, "a sample drawn 13 months ago, never graded, is kept forever"


def test_counts_of_changes_dont_outlive_their_use(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into action_counts (run_id, instance_id, action, change, acts_for, "
                     "at) values (gen_random_uuid(), 'assistant-finance', 'change-due-date', "
                     "'c', '{ben}', now() - interval '13 months')")
    swept(stack)
    with db.transaction(stack.admin) as conn:
        left = conn.execute("select count(*) from action_counts").fetchone()["count"]
    assert left == 0, "a count from 13 months ago, naming whom it was for, is kept forever"
