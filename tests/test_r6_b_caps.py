"""Round 6, reviewer b: the cap on a release's level, and the sequential test that moves it.

The test weighs every grade a release, part and type of action ever had, whenever it runs.
So a critical error lowers the cap for one minute: the next sweep weighs the same grades,
which still show the threshold met, and raises it again. And once level 2 is earned, the
grades that earned it outweigh the ones after: a fall from 98% to 88% over a quarter goes
unnoticed (a fall to 93% takes about four quarters at 100 samples a quarter, where the
starting values promise to notice it four times in five). A cap earned under one threshold
stands when the part's owner raises it. While the settings don't check out, the sweep reads
every part as having no threshold, and lowers every earned cap. And every release starts
again at 1, even one that changes only the agent's instructions and widens nothing.
"""

from dataclasses import replace

import yaml

from a5s import db, definitions
from a5s.core import registry
from conftest import seal_grades, signed
from test_levels import asked, due_of, levelled
from test_samples import cap, release, weigh


def grades(stack, n: int, wrong: int = 0, critical: int = 0, part: str = "orders") -> None:
    """n samples of the assistant's changes of due dates, graded now by the core's clock."""
    with db.transaction(stack.admin) as conn:
        for i in range(n):
            grade = "critical" if i < critical else "wrong" if i < critical + wrong else "right"
            conn.execute(
                "insert into samples (scenario, kind, run_id, instance_id, release, definition, "
                "part, action, said, records, acts_for, drawn_at, grade, graded_by, graded_at) "
                "values ('sample', 'proposal', gen_random_uuid(), 'assistant-finance', %s, "
                "'assistant', %s, 'change-due-date', 'a change', '{}', '{ben}', %s, %s, 'dana', "
                "%s)", (release(stack), part, stack.gateway.clock(), grade, stack.gateway.clock()))
    seal_grades(stack)  # as the grading page has the core seal them


def test_a_critical_error_keeps_the_cap_down_until_new_grades_earn_it_back(stack):
    stack.at("2026-11-02T10:00:00+00:00")
    grades(stack, 150)  # orders' threshold is 95%: 88 right earn level 2, or 134 with an error
    weigh(stack)
    assert cap(stack, "orders") == 2
    stack.at("2026-11-02T11:00:00+00:00")
    grades(stack, 1, critical=1)
    [lowered] = weigh(stack)
    assert (lowered["cap"], lowered["why"]) == (1, "a critical error")
    stack.at("2026-11-02T11:01:00+00:00")  # the next sweep, with no grade since
    assert weigh(stack) == [], "the critical error's lowering lasted one sweep"
    assert cap(stack, "orders") == 1


def test_a_fall_in_accuracy_after_level_2_lowers_the_cap(stack):
    stack.at("2026-11-02T10:00:00+00:00")
    grades(stack, 400, part="billing")  # billing's threshold is 98%
    weigh(stack)
    assert cap(stack, "billing") == 2
    stack.at("2027-02-01T10:00:00+00:00")  # a quarter on, its accuracy has fallen to 88%
    grades(stack, 100, wrong=12, part="billing")
    lowered = weigh(stack)
    assert [c["cap"] for c in lowered] == [1], "12 wrong in the 100 graded since went unnoticed"
    assert cap(stack, "billing") == 1


def test_raising_a_parts_threshold_lowers_a_cap_its_grades_no_longer_earn(stack):
    stack.at("2026-11-02T10:00:00+00:00")
    grades(stack, 150)  # enough for orders' 95%, not for 98%, which needs 224
    weigh(stack)
    assert cap(stack, "orders") == 2
    folder = stack.cfg.scenario_dir  # the owners raise orders' threshold to 98%
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
    settings["thresholds"]["orders"] = 0.98
    signed(folder, settings, ("ana", "omar"))  # orders' owner approves its threshold (round 6)
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert not registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name).refused
    weigh(stack)
    assert cap(stack, "orders") == 1, "level 2 stands on grades that don't meet the threshold"


def test_earned_caps_stand_while_the_settings_dont_check_out(stack, monkeypatch):
    stack.at("2026-11-02T10:00:00+00:00")
    grades(stack, 150)
    weigh(stack)
    assert cap(stack, "orders") == 2
    people = stack.gateway.scenario._people  # billing changes hands: until its new owner
    monkeypatch.setitem(people, "ana",  # approves, the settings in force don't check out
                        replace(people["ana"], roles=("instance-approver",)))
    stack.at("2026-11-02T10:01:00+00:00")
    assert weigh(stack) == [], "a moment's settings problem lowered a cap earned on grades"
    assert cap(stack, "orders") == 2
    assert not [e for e in stack.ledger() if e["kind"] == "cap" and e["action"] == "lower"]


def test_a_release_that_widens_nothing_keeps_the_level_its_grades_earned(stack, approving):
    levelled(stack)  # change-due-date at level 2 in billing, with the cap earned on samples
    asked(stack)
    assert due_of(stack) == "2026-11-13"  # made at level 2
    before = release(stack)
    agents = stack.cfg.agents_dir  # a release that changes one sentence of the instructions
    instructions = agents / "assistant" / "AGENTS.md"
    instructions.write_text(instructions.read_text() + "\nThank people when they help you.\n")
    stack.gateway.definitions.update(definitions.load_all(agents))
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert not registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name).refused
    assert release(stack) != before
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
          said="Now move Q-1002 to 2026-11-20.")
    assert due_of(stack) == "2026-11-20", "a release that widened nothing lost level 2"
