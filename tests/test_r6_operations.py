"""Round 6: what the team that runs a5s can see and do about phase 2. They can list the held
changes that wait or that a5s stopped part way through making, end one of the latter once
they've checked the records system, and lower a cap, which anyone with the role may do alone:
only graded samples raise one. The status says what's stuck, not made, lapsed or lowered."""

from a5s import db
from a5s.core import status
from test_levels import asked, due_of, levelled
from test_proposals import held
from test_samples import cap


def test_a_part_owner_lowers_a_cap_alone_and_its_owners_hear(stack):
    levelled(stack)
    with stack.client() as c:
        r = c.post("/caps/lower", json={"agent": "assistant", "part": "billing",
                                        "action": "change-due-date", "by": "ana"})
        assert r.status_code == 200 and r.json()["lowered"], r.text
        refused = c.post("/caps/lower", json={"agent": "assistant", "part": "billing",
                                              "action": "change-due-date", "by": "ben"})
    assert refused.status_code == 403
    assert cap(stack) == 1
    asked(stack)
    assert due_of(stack) == "2026-11-06"  # it waits for Ana now
    [lowered] = [e for e in stack.ledger() if e["kind"] == "cap" and e["action"] == "lower"]
    assert lowered["args"]["why"] == "lowered by ana"
    with db.transaction(stack.admin) as conn:
        told = [r["text"] for r in conn.execute("select text from digest_items where person = 'ana'")]
    assert any("cap on assistant-finance for change-due-date in billing is now 1" in t for t in told)


def test_a_change_stopped_part_way_is_listed_and_ended_by_hand(stack, approving, provider):
    asked(stack)
    with db.transaction(stack.admin) as conn:  # as if a5s stopped while it made it
        conn.execute("update proposals set status = 'making', decided_at = now() - interval '1 hour'")
        report = status.report(conn, [], stack.gateway.cfg.seal_keys)
    assert report["changes"]["stuck"] == 1
    assert "stopped part way through being made (a5s proposals)" in status.told(report)
    with stack.client() as c:
        listed = c.get("/proposals").json()["proposals"]
        assert [(p["key"], p["status"]) for p in listed] == [("P-1", "making")]
        chen = {"identity": provider.id_token(person="chen")}  # signed in, as suspending is
        assert c.post("/proposals/P-1/end", json=chen).status_code == 403  # not his to end
        ended = c.post("/proposals/P-1/end", json={"identity": provider.id_token(person="ana")})
    assert ended.status_code == 200, ended.text
    [p] = held(stack)
    assert p["status"] == "stopped"
    assert any("stopped part way through making P-1" in m["text"] for m in stack.inbox("ben"))


def test_a_threshold_needs_its_parts_owner(stack):
    import yaml

    from a5s.core import registry
    from conftest import signed
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
    settings["thresholds"]["orders"] = 0.9  # no instance works in orders, but its owner decides
    signed(folder, settings, ("ana",))
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        refused = registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                 scenario.tools(), scenario.person, scenario.name).refused
    assert refused == ["the owner of orders hasn't approved it"]
