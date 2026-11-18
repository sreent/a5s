"""Round 15, C4: one grader alone could raise an agent to level 2 within minutes, grading 20
samples a sign-in. Now no grader's own grades count toward a raise beyond everyone else's
together, so one alone never raises a cap, whatever they grade, though their errors always
count against it; and one sample in five is drawn twice, for a second grader, and counts toward
a raise once both are graded, as the worse of the two. A grader is offered one of the two, and
whoever graded one never grades the other."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from a5s import db
from a5s.contract import Person
from a5s.core import samples
from conftest import SEAL_KEY, seal_grades
from test_samples import cap, given, graded, release, weigh


def test_one_grader_alone_never_raises_a_cap(stack):
    graded(stack, 400, by=("dana",))  # far past the 224 a 98% threshold needs
    assert weigh(stack) == [] and cap(stack) == 1
    graded(stack, 224, by=("eli",))  # a second grader's, as many: together, they show it
    [raised] = weigh(stack)
    assert raised["cap"] == 2
    [entry] = [e for e in stack.ledger() if e["kind"] == "cap"]
    assert (entry["args"]["graders"], entry["args"]["set_aside"]) == (2, 176)


def test_their_errors_count_whoever_gave_them(stack):
    graded(stack, 223)  # two graders, taking turns: one short of a raise
    graded(stack, 1, wrong=1, by=("dana",))  # an error, from the grader with more
    assert weigh(stack) == [] and cap(stack) == 1


def drawn(stack, n: int) -> list[dict]:
    """n samples the core draws of decided changes, as it draws them."""
    with db.transaction(stack.admin) as conn:
        for _ in range(n):
            assert samples.draw(conn, (SEAL_KEY,), "sample", "proposal", release(stack),
                                "assistant", "assistant-finance", "00000000-0000-4000-8000-"
                                "000000000001", "billing", "change-due-date", "a change", {},
                                ["ben"], datetime.now(UTC), decided="approve",
                                decided_by=["ana"])
        return conn.execute("select * from samples order by id").fetchall()


def test_one_sample_in_five_is_drawn_twice_for_a_second_grader(stack):
    found = drawn(stack, 5)
    assert [(s["id"], s["twin_of"]) for s in found] == [
        (1, None), (2, None), (3, None), (4, None), (5, None), (6, 5)]
    assert all(samples.drawn_by_core((SEAL_KEY,), s) for s in found)  # its twin too
    with db.transaction(stack.admin) as conn:
        assert samples.mates(conn, found) == {5: None, 6: None}
        conn.execute("update samples set grade = 'right', graded_by = 'dana', graded_at = now() "
                     "where id = 5")
        assert samples.mates(conn, found) == {5: None, 6: "dana"}
    dana = stack.gateway.scenario.person("dana")
    assert "a second grader" in samples.may_grade(stack.gateway.scenario, found[5], dana,
                                                  mate="dana")


def graded_pair(stack, first: str | None, second: str | None, lapsed: bool = False) -> list[dict]:
    """A sample drawn twice, each graded as given, the first by Dana and its twin by Eli."""
    drawn(stack, 5)
    with db.transaction(stack.admin) as conn:
        for sample, grade, who in ((5, first, "dana"), (6, second, "eli")):
            if grade:
                conn.execute("update samples set grade = %s, graded_by = %s, graded_at = now() "
                             "where id = %s", (grade, who, sample))
        if lapsed:
            conn.execute("update samples set lapsed_at = now() where id = 6")
    seal_grades(stack)
    with db.transaction(stack.admin) as conn:
        fresh = conn.execute("select * from samples where id in (5, 6) and grade is not null "
                             "order by id").fetchall()
        return samples.items(conn, fresh)


def test_a_sample_drawn_twice_counts_once_both_are_graded_as_the_worse(stack):
    assert graded_pair(stack, "right", "wrong") == [
        {"grade": "wrong", "graders": {"dana", "eli"}, "twice": True}]


def test_until_its_second_grade_comes_or_its_twin_lapses(stack):
    assert graded_pair(stack, "right", None) == []  # it waits for its second grader


def test_a_twin_that_lapsed_leaves_its_first_counting_alone(stack):
    assert graded_pair(stack, "right", None, lapsed=True) == [
        {"grade": "right", "graders": {"dana"}}]


def offered(stack, person: Person) -> list[int]:
    with db.transaction(stack.admin) as conn:
        return [s["id"] for s in samples.gradeable(conn, stack.gateway.scenario, person)]


def test_a_grader_is_offered_one_of_a_pair_and_its_other_goes_to_someone_else(stack):
    assert len(drawn(stack, 5)) == 6  # the fifth, drawn twice
    dana = stack.gateway.scenario.person("dana")
    eli = replace(dana, id="eli", name="Eli Stone", identities=())  # a grader, as Dana is
    assert offered(stack, dana) == offered(stack, eli) == [1, 2, 3, 4, 5]  # one of the two
    with db.transaction(stack.admin) as conn:
        conn.execute("update samples set grade = 'right', graded_by = 'dana', graded_at = now() "
                     "where id = 5")
    assert (offered(stack, dana), offered(stack, eli)) == ([1, 2, 3, 4], [1, 2, 3, 4, 6])


def test_one_sign_in_grades_one_of_a_pair_and_its_grader_not_the_other(stack, approving,
                                                                       provider):
    drawn(stack, 5)
    both = given(approving, provider, {5: "right", 6: "right"})
    assert both.status_code == 403 and "grade one of the two" in both.json()["detail"]
    assert given(approving, provider, {5: "right"}).status_code == 200
    again = given(approving, provider, {6: "right"})  # Dana graded its other
    assert again.status_code == 403 and "you graded the other" in again.json()["detail"]
