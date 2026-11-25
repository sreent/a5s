"""What of an instance waits, on its page in the studio (core/home.py's of_instance,
docs/studio.md): the changes it asked for, for the viewer's decision or someone else's; its
samples, for the viewer's grade or other graders'; and its notebook, for those who keep it.
Each where it's done, with the oldest's time, and counts alone: what each is, someone sees
where they may act on it. Only those who may watch the instance see any of it."""

from __future__ import annotations

from a5s import db
from test_group_roles import MAP, OWNERS, mapped
from test_proposals import asked, held
from test_samples import release
from test_studio_home import api


def sample(stack) -> None:
    """A sample of the assistant's work in billing, waiting for a grade."""
    with db.transaction(stack.admin) as conn:
        conn.execute(
            "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
            "part, action, said, records, acts_for, drawn_at) values ('sample', 'proposal', "
            "gen_random_uuid(), 'assistant-finance', %s, 'assistant', 'billing', "
            "'change-due-date', 'a change', '{}', '{ben}', now())", (release(stack),))


def note(stack, source: str = "Q-1002") -> None:
    """A note the assistant kept in billing, from one record."""
    with db.transaction(stack.admin) as conn:
        conn.execute("insert into notebook (instance_id, agent, text, sources, read_records, "
                     "written_run) values ('assistant-finance', 'assistant', "
                     "'Northwind pays late in December', %s, %s, gen_random_uuid())",
                     ([source], [source]))


def waits(url: str, provider, person: str, *groups: str) -> dict[str, dict]:
    found = api(url, provider, person, "instances/assistant-finance/standing", *groups)
    found.raise_for_status()
    return {w["kind"]: w for w in found.json()["waiting"]}


def test_it_says_what_of_an_instance_waits_and_for_whom(stack, approving, provider):
    asked(stack)  # Ben asks for a change, which waits for Ana, who owns billing
    [change] = held(stack)
    sample(stack)
    note(stack)
    ana = waits(approving, provider, "ana")
    assert set(ana) == {"decide", "graded", "notebook"}
    assert (ana["decide"]["what"], ana["decide"]["go"]) == (
        "1 change it asked for waits for your decision", "/studio/decide")
    assert ana["decide"]["since"].startswith(change["proposed_at"].isoformat()[:19])
    assert ana["graded"] == {  # others' to grade: since when isn't hers to know (round 13, B5)
        "kind": "graded", "go": None, "why": [],
        "what": "1 sample of its work waits for a grade, from graders outside the team that "
                "built it"}
    assert (ana["notebook"]["what"], ana["notebook"]["go"]) == (
        "1 note it keeps from what it learned, which you may read and remove", "/studio/notebook")
    # Ben asked for it, so it's never his to decide; he runs it, as its deputy, so he keeps
    # its notebook
    ben = waits(approving, provider, "ben")
    assert ben["held"]["what"] == ("1 change it asked for waits for someone else's decision, as "
                                   "its parts' owners and delegates decide them")
    assert ben["held"]["go"] is None and "decide" not in ben
    assert "notebook" in ben
    # Priya owns the assistant, so she keeps its notebook, but sees no note whose records
    # she may not see
    priya = waits(approving, provider, "priya")
    assert set(priya) == {"held", "graded"}
    for outside in ("chen", "dana"):  # nobody else may watch it, nor any instance
        assert api(approving, provider, outside, "instances/assistant-finance/standing").status_code == 403


def test_a_grader_who_watches_it_is_sent_to_grade_its_samples(stack, approving, provider):
    mapped(stack, approving, provider, {**MAP, OWNERS: ["part-owner:billing"]})
    sample(stack)
    # Dana grades, outside the team that built it, and, by her group, owns billing beside Ana
    dana = waits(approving, provider, "dana", OWNERS)
    assert (dana["grade"]["what"], dana["grade"]["go"]) == (
        "1 sample of its work waits for your grade", "/studio/grade")
    assert "graded" not in dana  # none waits for anyone else
    assert set(waits(approving, provider, "ana")) == {"graded"}  # Ana runs it: never hers


def test_nothing_waits_on_a_quiet_instance(stack, approving, provider):
    assert waits(approving, provider, "ana") == {}
    assert api(approving, provider, "ana", "instances/nobodys/standing").status_code == 404
