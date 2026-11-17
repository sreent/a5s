"""Round 15, who may suspend and resume: the release approver, from outside the team that runs
a5s, resumes someone else's suspension on its page, which nobody but whoever suspended it could
(D6); and the owners and delegates of a part suspend an instance at work in it (B7)."""

from __future__ import annotations

from dataclasses import replace

from test_proposals import sweep
from test_studio_home import api
from test_studio_suspension import act, standing, status


def test_the_release_approver_resumes_someone_elses_suspension(stack, approving, provider):
    """Ben, its deputy, suspends it and is away. Ana, its owner, may not lift his suspension;
    Rosa, the release approver, sees it while it's suspended, and resumes it (D6)."""
    at_work = api(approving, provider, "rosa", "instances/assistant-finance/standing")
    assert at_work.status_code in (403, 404)  # at work, it isn't hers to watch
    assert act(approving, provider, "suspend", "ben").status_code == 200
    sweep(stack)
    assert status(stack) == ("suspended", "ben")
    refused = act(approving, provider, "resume", "ana")
    assert refused.status_code == 403 and "or the release approver" in refused.json()["detail"]
    assert standing(approving, provider, "rosa")["may"] == "resume"
    assert act(approving, provider, "resume", "rosa").status_code == 200
    sweep(stack)
    assert status(stack) == ("active", None)
    [lifted] = [e for e in stack.ledger() if e["action"] == "resume"]
    assert (lifted["args"]["by"], lifted["args"]["lifted"]) == ("rosa", "ben")


def test_a_parts_delegate_suspends_an_instance_at_work_in_it(stack, approving, provider,
                                                             monkeypatch):
    """Dana decides billing's changes beside Ana, and may stop an instance at work there (B7)."""
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, "dana", replace(people["dana"], roles=(
        *people["dana"].roles, "part-delegate:billing")))
    assert standing(approving, provider, "dana")["may"] == "suspend"
    assert act(approving, provider, "suspend", "dana").status_code == 200
    sweep(stack)
    assert status(stack) == ("suspended", "dana")
