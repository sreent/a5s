"""Round 15, the grader's finding: a release that changes what an agent is told, its instructions
or its skills, keeps the level its grades earned, but for an agent that may work at level 2,
where nobody decides its changes before they're made, the release approver signs it too, from
outside the team that runs a5s: its owner and an engineer from that team don't keep level 2 for
instructions they rewrote themselves (C2)."""

from __future__ import annotations

from a5s.core import releases
from a5s.core.releases import ENGINEER, RELEASE_APPROVER
from test_release import BASE, OWNER, agent, changed


def needed(edit) -> set[str]:
    return {n.role for n in releases.needs(changed(BASE, edit), BASE)}


def test_what_an_agent_that_may_work_at_level_2_is_told_needs_the_release_approver():
    assert agent(BASE)["may"]["autonomy"]["max"] == 2
    told = needed(lambda d: agent(d)["files"].update({"agents/assistant/AGENTS.md": "x"}))
    assert told == {OWNER, ENGINEER, RELEASE_APPROVER}
    [why] = [n.why for n in releases.needs(changed(BASE, lambda d: agent(d)["files"].update(
        {"agents/assistant/AGENTS.md": "x"})), BASE) if n.role == RELEASE_APPROVER]
    assert why.endswith("it may work at level 2, where nobody decides its changes before "
                        "they're made")
    assert needed(lambda d: agent(d)["files"].update(
        {"agents/assistant/skills/refunds/SKILL.md": "x"})) == {OWNER, ENGINEER, RELEASE_APPROVER}


def test_what_else_changes_in_its_folder_needs_its_owner_and_an_engineer_alone():
    assert needed(lambda d: agent(d)["files"].update(
        {"agents/assistant/tests/records.yaml": "x"})) == {OWNER, ENGINEER}


def test_an_agent_that_never_works_at_level_2_needs_its_owner_and_an_engineer_alone():
    assert agent(BASE, "watcher")["may"]["autonomy"]["max"] < 2
    assert needed(lambda d: agent(d, "watcher")["files"].update(
        {"agents/watcher/AGENTS.md": "x"})) == {releases.agent_owner("watcher"), ENGINEER}
