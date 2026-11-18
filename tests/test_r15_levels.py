"""Round 15, the grader's finding: a release that changes what an agent is told, its instructions
or its skills, keeps what its grades earned, but for an agent that may act on its own, where
nobody decides its changes before they're made, the release approver signs it too, from outside
the team that runs a5s: its owner and an engineer from that team don't keep it acting on its own
for instructions they rewrote themselves (C2). The pilot's assistant, as it ships, asks first at
most, so these weigh it as a release that lets it act on its own would have it."""

from __future__ import annotations

from a5s import levels
from a5s.core import releases
from a5s.core.releases import ENGINEER, RELEASE_APPROVER
from test_release import BASE, OWNER, agent, changed

ACTING = changed(BASE, lambda d: agent(d)["may"]["autonomy"].update({"max": levels.ACTS}))


def needed(edit, base: dict = ACTING) -> set[str]:
    return {n.role for n in releases.needs(changed(base, edit), base)}


def test_what_an_agent_that_may_act_on_its_own_is_told_needs_the_release_approver():
    assert agent(BASE)["may"]["autonomy"]["max"] == levels.ASKS_FIRST  # as the pilot's ships
    told = needed(lambda d: agent(d)["files"].update({"agents/assistant/AGENTS.md": "x"}))
    assert told == {OWNER, ENGINEER, RELEASE_APPROVER}
    [why] = [n.why for n in releases.needs(changed(ACTING, lambda d: agent(d)["files"].update(
        {"agents/assistant/AGENTS.md": "x"})), ACTING) if n.role == RELEASE_APPROVER]
    assert why.endswith("it may act on its own, where nobody decides its changes before "
                        "they're made")
    assert needed(lambda d: agent(d)["files"].update(
        {"agents/assistant/skills/refunds/SKILL.md": "x"})) == {OWNER, ENGINEER, RELEASE_APPROVER}


def test_what_else_changes_in_its_folder_needs_its_owner_and_an_engineer_alone():
    assert needed(lambda d: agent(d)["files"].update(
        {"agents/assistant/tests/records.yaml": "x"})) == {OWNER, ENGINEER}


def test_an_agent_that_never_acts_on_its_own_needs_its_owner_and_an_engineer_alone():
    assert agent(BASE, "watcher")["may"]["autonomy"]["max"] < levels.ACTS
    assert needed(lambda d: agent(d, "watcher")["files"].update(
        {"agents/watcher/AGENTS.md": "x"})) == {releases.agent_owner("watcher"), ENGINEER}
    assert needed(lambda d: agent(d)["files"].update(  # nor the pilot's assistant, as it ships
        {"agents/assistant/AGENTS.md": "x"}), BASE) == {OWNER, ENGINEER}
