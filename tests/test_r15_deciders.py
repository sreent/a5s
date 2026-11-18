"""Round 15, the decider's findings: once one decider's decision settles a held change, a second
hears at once that it doesn't count, rather than that it stands (B3); an escalation never goes
back to the decider who let a change wait, whoever asked hears that it waits still, and a lapse
is told to those it waited for (B4); and an approval while the instance is suspended is refused,
rather than accepted and dropped at the sweep (B9)."""

from __future__ import annotations

from dataclasses import replace

import httpx

from a5s import db
from test_proposals import asked, decide, held, signed, sweep

MONDAY = "2026-11-02T09:30:00+00:00"


def decided(url, provider, digests, decision="approve", person="ana", reason=None):
    token, salt = signed(url, provider, digests, decision, person, reason=reason)
    return httpx.post(f"{url}/decide/proposals", json={
        "proposals": digests, "decision": decision, "salt": salt,
        **({"reason": reason} if reason else {})},
        headers={"Authorization": f"Bearer {token}"})


def delegate(stack, monkeypatch, who: str = "dana") -> None:
    """Dana, of quality, decides billing's changes beside Ana."""
    people = stack.gateway.scenario._people
    monkeypatch.setitem(people, who, replace(people[who], roles=(*people[who].roles,
                                                                 "part-delegate:billing")))


def recorded(stack) -> list[tuple[str, str]]:
    with db.transaction(stack.admin) as conn:
        return [(r["person"], r["decision"]) for r in conn.execute(
            "select person, decision from proposal_decisions order by id")]


def digest(stack, person: str) -> list[str]:
    with db.transaction(stack.admin) as conn:
        return [r["text"] for r in conn.execute(
            "select text from digest_items where person = %s order by id", (person,))]


def test_once_one_decider_settles_a_change_the_second_hears_so_at_once(stack, approving,
                                                                       provider, monkeypatch):
    delegate(stack, monkeypatch)
    asked(stack)
    [p] = held(stack)
    assert decide(approving, provider, [p["digest"]], "approve", person="ana").status_code == 200
    late = decided(approving, provider, [p["digest"]], "reject", person="dana",
                   reason="Contoso hasn't paid yet")
    assert late.status_code == 409, late.text
    assert late.json()["detail"].startswith("Ana Ortiz decided P-1 already")
    assert recorded(stack) == [("ana", "approve")]  # hers alone
    sweep(stack)
    assert held(stack)[0]["status"] == "made"


def test_a_rejection_first_settles_it_as_well(stack, approving, provider, monkeypatch):
    delegate(stack, monkeypatch)
    asked(stack)
    [p] = held(stack)
    assert decided(approving, provider, [p["digest"]], "reject", person="dana",
                   reason="Contoso hasn't paid yet").status_code == 200
    late = decide(approving, provider, [p["digest"]], "approve", person="ana")
    assert late.status_code == 409 and late.json()["detail"].startswith(
        "Dana Price decided P-1 already"), late.text
    assert recorded(stack) == [("dana", "reject")]


def test_an_approval_while_the_instance_is_suspended_is_refused(stack, approving, provider):
    asked(stack)
    [p] = held(stack)
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set status = 'suspended' where id = 'assistant-finance'")
    refused = decide(approving, provider, [p["digest"]], "approve", person="ana")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"].startswith("assistant-finance is suspended")
    assert recorded(stack) == []
    assert decide(approving, provider, [p["digest"]], "reject", person="ana").status_code == 200


def test_an_escalation_never_goes_back_to_the_decider_who_let_it_wait(stack, approving):
    """Ana decides billing's changes, nobody is above her, and she owns the instance; its
    deputy, Ben, asked for the change. Nobody else may hear of it, so nobody is told it waits
    but Ben, who asked, in his digest (B4)."""
    stack.at(MONDAY)
    asked(stack)
    stack.at("2026-11-04T10:00:00+00:00")  # two working days on: she's reminded
    sweep(stack)
    stack.at("2026-11-09T10:00:00+00:00")  # five
    sweep(stack)
    [p] = held(stack)
    assert p["status"] == "waiting" and p["escalated"] == []
    assert not any(m["text"].startswith("P-1 has waited") for m in stack.inbox("ana"))
    assert digest(stack, "ben") == [(
        "P-1, which you asked for, waits still for Ana Ortiz to decide it, after 5 working "
        "days. It lapses on Mon 16 Nov unless it's decided before then.")]


def test_a_change_that_lapsed_is_told_to_those_it_waited_for(stack, approving):
    """Nobody decided it in ten working days: whoever asked hears, and so does Ana, whom it
    waited for, in her digest (B4)."""
    stack.at(MONDAY)
    asked(stack)
    stack.at("2026-11-16T10:00:00+00:00")  # ten working days on
    sweep(stack)
    assert held(stack)[0]["status"] == "lapsed"
    assert any(t.startswith("What became of P-1, which waited for your decision: Nobody "
                            "decided P-1") for t in digest(stack, "ana")), digest(stack, "ana")
