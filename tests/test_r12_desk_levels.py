"""Round 12 of the critique: levels, on the service desk (docs/critique.md, round 12, B4, B5,
B9). A change is someone's own only in a run that answers their own message, one to one, as the
records stood when the call read them, so a chase never resets the password of someone who
asked for nothing; and a change the desk's pack rules out at level 2 waits for a person, as at
level 1, and one they approved is made, whatever level the agent earned meanwhile."""

from __future__ import annotations

from a5s import db
from test_desk_self_service import approving, asked, at_level_2, decisions, desk, idp  # noqa: F401
from test_proposals import decide, held, sweep


def test_a_chase_never_resets_its_person_s_password_at_level_2(desk, approving):  # noqa: F811
    """Rae owes INC0000001 a next step, and a5s chases her: that run acts for her alone, but she
    asked for nothing in it, so a reset of her own account isn't hers to have run alone."""
    at_level_2(desk, "reset-password")
    desk.at("2026-11-02T09:30:00+00:00")
    desk.scheduler().due()
    with db.transaction(desk.admin) as conn:
        found = conn.execute("select id, person from obligations where record = 'INC0000001'"
                             ).fetchone()
    with desk.client() as c:
        opened = c.post("/runs", json={"instance": "desk-access", "trigger": {
            "kind": "obligation", "obligation": found["id"]}})
    assert opened.status_code == 200
    with desk.client(opened.json()["token"]) as c:
        c.post("/run/tools/reset_password", json={"args": {"key": f"ACC-{found['person']}"}})
    [(decision, reasons)] = decisions(desk, "reset_password")
    assert decision == "hold" and "desk-self-service-only-for-the-person-asking" in reasons
    assert idp().resets == {}


def test_a_reset_its_decider_approved_is_made_once_level_2_is_earned(desk, approving, provider):  # noqa: F811
    asked(desk, ("reset_password", {"key": "ACC-pat"}), person="rae",
               said="Pat's locked out: reset Pat's password.")
    [p] = held(desk)
    assert (p["status"], p["deciders"]) == ("waiting", ["ola"])  # at level 1, it goes to Ola
    assert decide(approving, provider, [p["digest"]], person="ola").status_code == 200
    at_level_2(desk, "reset-password")  # graded samples raise the cap meanwhile
    sweep(desk)
    [p] = held(desk)
    assert p["status"] == "made" and "ACC-pat" in idp().resets  # as Ola approved it


def test_a_reset_of_one_s_own_account_reads_its_records_once(desk, approving, monkeypatch):  # noqa: F811
    at_level_2(desk, "reset-password")
    scenario, reads = desk.gateway.scenario, []
    was = scenario.record
    monkeypatch.setattr(scenario, "record", lambda key: reads.append(key) or was(key))
    asked(desk, ("reset_password", {"key": "ACC-sam"}))
    assert decisions(desk, "reset_password") == [("allow", ["active-instances-use-their-grant"])]
    assert reads.count("ACC-sam") == 1  # whose it is, from what the call read, not again


