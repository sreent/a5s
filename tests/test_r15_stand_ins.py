"""Round 15, the data protection officer's findings on the auditors' and administrators' pages:
until the officer agrees to names, someone who has left shows as a stand-in still, never by
their id (E1), and whoever asked to undo a change made for them is never named beside the
stand-in it was for (E2)."""

from __future__ import annotations

import httpx

from a5s import db
from a5s.core import audit
from test_audit_page import reading, strings
from test_departures import MONDAY, TUESDAY
from test_departures import sweep as departures_sweep
from test_levels import asked, levelled
from test_undo import kept, undo


def administering(url: str, provider, person: str = "ana") -> dict:
    r = httpx.get(f"{url}/admin/api", timeout=30,
                  headers={"Authorization": f"Bearer {provider.id_token(person=person)}"})
    assert r.status_code == 200, r.text
    return r.json()


def test_someone_who_left_shows_as_a_stand_in_still(stack, approving, provider, monkeypatch):
    """Ben leaves, and the directory names him no more: what agents did for him, what they
    sent him and his archiving show as his stand-in still (E1)."""
    stack.model.reply("Noted, Ben.")
    stack.say("I'm Ben, and I'm leaving on Friday.", person="ben")
    kofi = reading(approving, provider)
    assert "ben" not in strings(kofi("/audit/api/entries").json()["entries"])
    people = dict(stack.gateway.scenario._people)
    del people["ben"]  # he leaves
    monkeypatch.setattr(stack.gateway.scenario, "_people", people)
    stack.at(MONDAY)
    departures_sweep(stack)
    stack.at(TUESDAY)
    assert departures_sweep(stack)["archived"] == 1
    with db.transaction(stack.admin) as conn:
        his = audit.stand_in(audit.key(conn), "ben")
    after = kofi("/audit/api/entries").json()["entries"]
    assert "ben" not in strings(after)
    assert any(his in (e.get("acts_for") or []) for e in after)  # his, as it was
    [archived] = [e for e in after if e["action"] == "archive"]
    assert archived["args"]["person"] == his
    assert "ben" not in strings(kofi("/audit/api/report").json()["acts"])
    assert "ben" not in strings(administering(approving, provider)["latest"])


def test_who_asked_to_undo_a_change_shows_as_the_stand_in_it_was_for(stack, approving,
                                                                    provider):
    """Ben asks to undo a change made for him: the entry names him as its stand-in alone, so
    nobody reading the page learns whose the stand-in is (E2)."""
    levelled(stack)
    asked(stack)  # made for Ben at level 2
    change = kept(stack)["id"]
    assert undo(approving, provider, change, "ben").status_code == 200
    kofi = reading(approving, provider)
    every = kofi("/audit/api/entries").json()["entries"]
    [asking] = [e for e in every if e["action"] == "ask-undo"]
    with db.transaction(stack.admin) as conn:
        his = audit.stand_in(audit.key(conn), "ben")
    assert asking["acts_for"] == [his] and asking["args"]["asker"] == his
    assert "ben" not in strings(asking)
    assert "ben" not in strings(kofi("/audit/api/report").json()["acts"])
    assert "ben" not in strings(administering(approving, provider)["latest"])
