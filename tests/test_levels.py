"""Level 2 and counts. A change works at level 2 only where the settings set it for its type
of action in the record's part, someone who approved them still owns the part, and a5s's cap
for the release has been raised by graded samples. At level 2 it's made, and reported to the
instance's owner. Past the scenario's limits it waits for a person, whatever the level."""

import json
import threading
from dataclasses import replace

import yaml

from a5s import db
from a5s.contract import parse_settings, record_of
from a5s.core import approvals, registry
from conftest import raise_cap, signed

MOVE = ("change_due_date", {"key": "Q-1002", "due": "2026-11-13"})


def levelled(stack, actions: dict | None = None, limits: dict | None = None, cap: int = 2):
    """The assistant at level 2 for changing due dates in billing, as Ana, who owns billing,
    signed it, with a5s's cap for its release raised, as samples would raise it."""
    folder = stack.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
    settings["instances"]["assistant-finance"]["parts"] = {
        "billing": {"level": 1, "actions": actions or {"change-due-date": 2}}}
    if limits is not None:
        settings["limits"] = limits
    signed(folder, settings, ("ana",))
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        applied = registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                 scenario.tools(), scenario.person, scenario.name)
        assert not applied.refused, applied.refused
    if cap:
        raise_cap(stack, cap=cap)


def asked(stack, *calls, person: str = "ben", said: str = "Please move Q-1002 to 2026-11-13."):
    stack.model.reply(None, *(calls or (MOVE,)))
    stack.model.reply("Done what I could.")
    stack.say(said, person=person)


def due_of(stack, key: str = "Q-1002") -> str:
    return record_of(stack.gateway.scenario, key).fields["due date"]


def decisions(stack, tool: str = "change_due_date") -> list[tuple[str, list]]:
    return [(e["decision"], e.get("reasons") or []) for e in stack.ledger()
            if e["kind"] == "tool" and e["action"] == tool and e["decision"] != "record"]


def test_at_level_2_a_change_is_made_and_reported_to_the_instances_owner(stack, approving):
    levelled(stack)
    asked(stack)
    assert due_of(stack) == "2026-11-13"
    assert decisions(stack) == [("allow", ["active-instances-use-their-grant"])]
    [made] = [e for e in stack.ledger() if e["action"] == "change_due_date"
              and e["decision"] == "record"]
    assert made["level"] == 2 and made["outcome"]["status"] == "ok"
    with db.transaction(stack.admin) as conn:
        [item] = conn.execute("select * from digest_items where person = 'ana'").fetchall()
        assert conn.execute("select count(*) from proposals").fetchone()["count"] == 0
    assert item["text"] == (
        "The assistant made a change itself, at level 2, for Ben Okafor: Change a customer "
        "question's due date: Q-1002, with due 2026-11-13. Q-1002, Refund for a duplicate "
        "payment, as it stood before: status waiting on finance, due date 2026-11-06, customer "
        "Contoso. https://sample.a5s.dev/records/Q-1002")


def test_level_2_waits_for_samples_to_raise_a5s_cap(stack, approving):
    levelled(stack, cap=0)  # no samples yet: the cap is 1
    asked(stack)
    assert due_of(stack) == "2026-11-06"
    assert decisions(stack) == [("hold", ["level-1-changes-wait-for-their-decider"])]


def test_only_the_types_of_action_set_to_level_2_act(stack, approving):
    levelled(stack)
    asked(stack, ("close_question", {"key": "Q-1002"}), said="Close Q-1002.")
    assert record_of(stack.gateway.scenario, "Q-1002").fields["status"] == "waiting on finance"
    assert decisions(stack, "close_question")[0][0] == "hold"


def test_level_2_drops_to_1_once_nobody_who_approved_it_owns_the_part(stack, approving,
                                                                       monkeypatch):
    levelled(stack)
    people = stack.gateway.scenario._people  # Ana hands billing to Ben
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=("instance-approver",)))
    monkeypatch.setitem(people, "ben", replace(people["ben"], roles=("part-owner:billing",)))
    asked(stack, person="ben")
    assert due_of(stack) == "2026-11-06"  # no run opens until billing's new owner approves
    assert all(d != "allow" for d, _ in decisions(stack))


def test_a_run_that_read_outside_content_never_acts_at_level_2(stack, approving):
    levelled(stack)
    run, token = stack.open_run(sender="ben")
    with db.transaction(stack.admin) as conn:
        conn.execute("update runs set read_outside = true where id = %s", (run,))
    with stack.client(token) as c:
        r = c.post("/run/tools/change_due_date", json={"args": MOVE[1]})
    assert r.status_code == 200 and r.json()["result"]["held"] == "P-1"
    assert due_of(stack) == "2026-11-06"


def test_a_change_past_a_runs_limit_waits_even_at_level_2(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_run": 1}})
    asked(stack, MOVE, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
          said="Move Q-1002 to 2026-11-13, and then to 2026-11-20.")
    assert due_of(stack) in ("2026-11-13", "2026-11-20")  # one made: the calls run at once
    assert sorted(decisions(stack)) == [("allow", ["active-instances-use-their-grant"]),
                                        ("hold", ["changes-past-a-limit-wait-for-their-decider"])]


def test_a_change_past_someones_limit_for_30_days_waits(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_person_30_days": 1}})
    asked(stack)
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-11-20"}),
          said="Now move Q-1002 to 2026-11-20.")
    assert due_of(stack) == "2026-11-13"
    assert [d for d, _ in decisions(stack)] == ["allow", "hold"]
    stack.at("2026-12-15T10:00:00+00:00")  # a month on, Ben's count starts again
    asked(stack, ("change_due_date", {"key": "Q-1002", "due": "2026-12-22"}),
          said="Move Q-1002 to 2026-12-22.")
    assert due_of(stack) == "2026-12-22"


def test_the_same_change_again_in_a_run_counts_once_and_keeps_its_verdict(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_run": 1}})
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        first = c.post("/run/tools/change_due_date", json={"args": MOVE[1]}).json()["result"]
        other = {"key": "Q-1002", "due": "2026-11-20"}
        held = c.post("/run/tools/change_due_date", json={"args": other}).json()["result"]
        again = c.post("/run/tools/change_due_date", json={"args": other}).json()["result"]
    assert first["due"] == "2026-11-13" and held["held"] == again["held"] == "P-1"
    with db.transaction(stack.admin) as conn:
        assert conn.execute("select count(*) from action_counts").fetchone()["count"] == 2


def test_changes_made_at_once_cant_each_squeeze_under_a_limit(stack, approving):
    levelled(stack, limits={"change-due-date": {"per_run": 1}})
    _, token = stack.open_run(sender="ben")
    answers: list[dict] = []

    def change(due: str) -> None:
        with stack.client(token) as c:
            answers.append(c.post("/run/tools/change_due_date",
                                  json={"args": {"key": "Q-1002", "due": due}}).json()["result"])

    threads = [threading.Thread(target=change, args=(f"2026-11-{d}",)) for d in (13, 16, 17, 18)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum("held" not in a for a in answers) == 1 and sum("held" in a for a in answers) == 3


def test_approvers_read_level_2_and_limits_in_words(stack):
    before = stack.gateway.scenario.settings()
    raw = yaml.safe_load(before.raw)
    raw["serial"] += 1
    raw["limits"]["change-due-date"] = {"per_run": 3, "per_person_30_days": 20}
    raw["instances"]["assistant-finance"]["parts"] = {
        "billing": {"level": 1, "actions": {"change-due-date": 2}}}
    after = parse_settings(yaml.safe_dump(raw).encode())
    found = approvals.changes(before, after, stack.gateway.definitions, stack.gateway.scenario.person)
    assert {"text": "The limit for change-due-date becomes 3 in one run and 20 for one person "
                    "in 30 days, instead of 5 in one run and 20 for one person in 30 days.",
            "widens": False} in found  # a tighter limit narrows
    assert {"text": "assistant-finance's level for change-due-date in billing goes from 1 to 2, "
                    "where it acts and reports, once samples show it's accurate enough.",
            "widens": True} in found
    whole = approvals.described(after, stack.gateway.definitions, stack.gateway.scenario.person)
    assert ("assistant-finance works at level 2 for change-due-date in billing, where it acts "
            "and reports, once graded samples show it's accurate enough: until then a5s holds "
            "it at level 1.") in whole


def test_the_core_refuses_an_instance_whose_action_levels_were_edited(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set actions = %s where id = 'assistant-finance'",
                     (json.dumps({"billing": {"change-due-date": 2}}),))
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello")}})
    assert r.status_code == 409
    assert "doesn't match its signed settings" in " ".join(r.json()["detail"]["reasons"])

