"""Round 6, reviewer b: who decides a held change, and who hears that it waits.

A held change keeps the deciders it had when it was held. Only they may decide it, and only
while they still own the part, so once a part changes hands nobody may decide what waits in
it: the new owner can't, and isn't asked, and it lapses after ten working days. The sweep
reminds and escalates by the first decider alone: once they leave, nobody else is reminded,
and no manager hears. And the one reminder goes only to the deciders working at that minute:
one on the other side of the world is never reminded.
"""

from dataclasses import replace

from test_proposals import asked, decide, held, sweep

MONDAY = "2026-11-02T09:30:00+00:00"  # 09:30 in London, 17:30 in Singapore
TWO_DAYS_ON = "2026-11-04T10:00:00+00:00"  # Wednesday: two of Ana's working days on


def reminded(stack, person: str) -> int:
    return sum(m["text"].startswith("Still waiting for your decision")
               for m in stack.inbox(person))


def test_once_the_first_decider_leaves_the_others_are_still_reminded(stack, approving,
                                                                      monkeypatch):
    people = stack.gateway.scenario._people  # Dana owns billing with Ana
    monkeypatch.setitem(people, "dana", replace(people["dana"],
                                                roles=("grader", "part-owner:billing")))
    stack.at(MONDAY)
    asked(stack)
    [p] = held(stack)
    assert p["deciders"] == ["ana", "dana"]
    monkeypatch.delitem(people, "ana")  # Ana leaves
    stack.at(TWO_DAYS_ON)
    sweep(stack)
    assert reminded(stack, "dana") == 1, "nobody was reminded, since the first decider left"


def test_a_parts_new_owner_may_decide_what_waits_in_it(stack, approving, provider, monkeypatch):
    stack.at(MONDAY)
    asked(stack)
    [p] = held(stack)
    assert p["deciders"] == ["ana"]
    people = stack.gateway.scenario._people  # Ana hands billing to Dana
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=("instance-approver",)))
    monkeypatch.setitem(people, "dana", replace(people["dana"],
                                                roles=("grader", "part-owner:billing")))
    stack.at(TWO_DAYS_ON)
    sweep(stack)
    assert reminded(stack, "dana") == 1, "billing's owner isn't asked about what waits in it"
    decided = decide(approving, provider, [p["digest"]], person="dana")
    assert decided.status_code == 200, decided.text


def test_a_decider_off_shift_when_the_reminder_falls_due_is_reminded_in_their_hours(
        stack, approving, monkeypatch):
    people = stack.gateway.scenario._people  # Dana owns billing with Ana, from Singapore
    monkeypatch.setitem(people, "dana", replace(people["dana"], timezone="Asia/Singapore",
                                                roles=("grader", "part-owner:billing")))
    stack.at(MONDAY)
    asked(stack)
    [p] = held(stack)
    assert p["deciders"] == ["ana", "dana"]
    stack.at(TWO_DAYS_ON)  # 18:00 in Singapore: Dana has gone home
    sweep(stack)
    assert reminded(stack, "ana") == 1
    stack.at("2026-11-05T02:00:00+00:00")  # 10:00 on Thursday in Singapore
    sweep(stack)
    assert reminded(stack, "dana") == 1, "a decider off shift at the reminder is never reminded"
