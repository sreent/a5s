"""Round 15, A14: a record in a part the instance doesn't work in, one the people a run is for
may not see, and one there isn't all get the same answer, so what an agent says tells nobody
that a record is there, nor in which part. The answer points whoever asked to someone who runs
the assistant, never to a part's owner, whom the part would give away; the ledger keeps which
rule refused each call, as the run's page shows. In the sample, the finance assistant works in
billing alone, Ana runs it with Ben as her deputy, and Omar owns orders."""

from __future__ import annotations

import pytest

from a5s.core import parts
from test_parts import OMAR_TOO, tool

ASK_ANA = f"{parts.UNSEEN}. If they think they should, they can ask Ana Ortiz, who runs this assistant"
ANSWER = {"denied": True, "decision": "deny", "reasons": [parts.REFUSED], "errors": [],
          "explanations": [ASK_ANA]}


def refusals(stack, run: str, name: str) -> list[list[str]]:
    """The rules that refused each call a run made of a tool, as the ledger keeps them."""
    return [e["reasons"] for e in stack.ledger(run)
            if e["action"] == name and e["decision"] == "deny"]


def test_a_record_elsewhere_one_unseen_and_one_there_isnt_get_one_answer(stack):
    assert not stack.settle(serves=OMAR_TOO).refused
    run, token = stack.open_run(sender="omar")
    elsewhere = tool(stack, token, "get_record", key="Q-1003")  # orders: Omar may see it
    unseen = tool(stack, token, "get_record", key="Q-1001")  # billing: finance's alone
    none = tool(stack, token, "get_record", key="Q-9999")
    assert [r.status_code for r in (elsewhere, unseen, none)] == [403] * 3
    assert elsewhere.json() == unseen.json() == none.json() == ANSWER, (
        "the agent can tell a record of another part, or one it may not see, from one there isn't")
    assert "Omar" not in ASK_ANA  # orders' owner, whom the part would give away
    assert refusals(stack, run, "get_record") == [  # the ledger keeps which, for the run's page
        ["instances-work-only-in-their-parts"], ["people-see-only-what-they-may"],
        ["people-see-only-what-they-may"]]


def test_so_does_a_change_whatever_else_would_refuse_it(stack):
    assert not stack.settle(serves=OMAR_TOO).refused
    _, token = stack.open_run(sender="omar")
    answers = [tool(stack, token, "change_due_date", key=key, due="2026-12-01")
               for key in ("Q-1003", "Q-1001", "Q-9999")]
    assert [a.json() for a in answers] == [ANSWER] * 3
    drafts = [tool(stack, token, "create_draft", title="Delivery", body="When?", record=key)
              for key in ("Q-1003", "Q-9999")]
    assert [d.json() for d in drafts] == [ANSWER] * 2


def test_a_record_it_may_not_work_on_is_refused_so_even_when_it_cant_be_read(
        stack, monkeypatch: pytest.MonkeyPatch):
    """A change's records are read before it's decided, for whoever decides it: one there isn't
    may fail to read where another part's reads, so the refusal comes first."""
    assert not stack.settle(serves=OMAR_TOO).refused

    def down(*_):
        raise ConnectionError("the records system is down")

    monkeypatch.setattr(stack.gateway.scenario, "record", down)
    _, token = stack.open_run(sender="omar")
    assert tool(stack, token, "change_due_date", key="Q-1003", due="2026-12-01").json() == ANSWER
    _, token = stack.open_run(sender="ben")  # one Ben may work on: a5s says it can't be read
    readable = tool(stack, token, "change_due_date", key="Q-1001", due="2026-12-01").json()
    assert readable["reasons"] == ["records-can-be-read"]


def test_whoever_runs_the_assistant_is_pointed_to_its_deputy(stack):
    _, token = stack.open_run(sender="ana")
    answer = tool(stack, token, "get_record", key="Q-1003").json()
    assert answer["explanations"] == [(
        f"{parts.UNSEEN}. If they think they should, they can ask Ben Okafor, who runs this "
        "assistant")]


def test_what_a_tool_gives_of_a_record_the_run_may_not_work_on_says_the_same(stack):
    run = {"parts": {"billing": 1}, "level": 1, "acts_for": ["omar"], "owner": "ana",
           "deputy": "ben"}
    found, withheld = parts.kept(stack.gateway.scenario, run, "key", {"key": "Q-1003"})
    assert (found, withheld) == ({"error": ASK_ANA}, 1)
    nobody = {**run, "acts_for": []}  # such as an event's: nobody to point anywhere
    assert parts.kept(stack.gateway.scenario, nobody, "key", {"key": "Q-1003"})[0] == {
        "error": parts.NOWHERE}
