"""Round 6, reviewer b: the decision and grading pages cut their lists short.

The decision page lists a decider's 50 newest changes, those they decided lately among them,
so with more waiting, the oldest, which lapse first, never show and can't be decided. The
grading page reads the 200 oldest samples waiting for a grade, and only then leaves out those
the grader may not grade, such as changes they asked for, so behind 200 of those a grader
sees nothing at all, and samples nobody else may grade wait forever.
"""

import httpx

from a5s import db
from test_proposals import asked, held


def signed_in(provider, person: str) -> dict:
    return {"Authorization": f"Bearer {provider.id_token(person=person)}"}


def test_a_decider_sees_the_oldest_change_waiting_for_them_however_many_wait(stack, approving,
                                                                              provider):
    asked(stack)  # P-1
    with db.transaction(stack.admin) as conn:  # and 50 more for Ana since, held the same way
        conn.execute(
            "insert into proposals (scenario, digest, run_id, instance_id, definition, release, "
            "tool, schema_hash, action, args, records, parts, acts_for, deciders, said, flags, "
            "sensitive, read_outside, seq, proposed_at, lapses_at) select scenario, "
            "encode(sha256(convert_to(digest || n::text, 'UTF8')), 'hex'), run_id, instance_id, "
            "definition, release, tool, schema_hash, action, args, records, parts, acts_for, "
            "deciders, said, flags, sensitive, read_outside, seq, proposed_at, lapses_at "
            "from proposals, generate_series(1, 50) n where id = 1")
    assert len(held(stack)) == 51
    review = httpx.post(f"{approving}/decide/review", headers=signed_in(provider, "ana"))
    shown = [p["key"] for p in review.json()["proposals"]]
    assert "P-1" in shown, f"{len(shown)} shown, from {shown[0]} to {shown[-1]}: P-1 lapses first"


def test_a_grader_sees_what_they_may_grade_behind_200_they_may_not(stack, approving, provider):
    with db.transaction(stack.admin) as conn:  # 200 changes Dana asked for, then one for Ben
        for who in ["dana"] * 200 + ["ben"]:
            conn.execute(
                "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
                "part, action, said, records, acts_for, drawn_at) values ('sample', 'proposal', "
                "gen_random_uuid(), 'assistant-finance', 'r', 'assistant', 'billing', "
                "'change-due-date', 'a change', '{}', %s, now())", ([who],))
    review = httpx.post(f"{approving}/grade/review", headers=signed_in(provider, "dana"))
    assert review.status_code == 200, review.text
    assert len(review.json()["samples"]) == 1, "Dana sees nothing she may grade"
