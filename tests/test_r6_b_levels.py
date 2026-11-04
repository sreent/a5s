"""Round 6, reviewer b: level 2 without its cap, and without telling anyone.

A change works at the level the settings set for its type of action in its record's part,
up to a5s's cap for the release, or else at level 1 at most. But a record in no part has no
part to look up, so the change works at the instance's own level: an instance whose parts
are at level 2, as phase 1 set levels, makes such a change at once, with no level set for
its type of action, no cap earned on graded samples, and no sample drawn to grade.

And a change made at level 2 is reported only in the digest of the instance's owner, which
the settings may leave out, as neither of a5s's releases names one: then a5s tells nobody,
though it promises never to let an agent act without telling anyone.
"""

import yaml

from a5s import db
from a5s.contract import record_of
from a5s.core import registry
from conftest import raise_cap, signed
from test_levels import MOVE, asked, due_of

LOOSE = {"key": "Q-1005", "title": "Copy of a receipt", "status": "open", "customer": "Contoso",
         "owner": "ben", "opened": "2026-10-27", "due": "2026-11-06",
         "contact": "billing@contoso.test"}  # a question the records system puts in no part


def test_a_change_to_a_record_in_no_part_works_at_level_1_at_most(stack, approving, monkeypatch):
    scenario = stack.gateway.scenario
    monkeypatch.setattr(scenario, "_records", {**scenario._records, "Q-1005": LOOSE})
    # billing at level 2, as the part's level, with no type of action set to 2, and no cap
    assert not stack.settle(parts={"billing": 2}).refused
    asked(stack, ("change_due_date", {"key": "Q-1005", "due": "2026-11-13"}),
          said="Please move Q-1005 to 2026-11-13.")
    with db.transaction(stack.admin) as conn:
        caps = conn.execute("select count(*) from caps").fetchone()["count"]
    assert caps == 0  # nothing has earned level 2
    assert record_of(scenario, "Q-1005").fields["due date"] == "2026-11-06", (
        "made at level 2, with no level for its type of action and no cap earned")


def test_a_change_made_at_level_2_is_reported_to_someone_when_the_instance_has_no_owner(stack):
    folder = stack.cfg.scenario_dir  # level 2 for due dates in billing, as levelled() sets it,
    settings = yaml.safe_load((folder / "settings.yaml").read_text())  # with no owner named
    instance = settings["instances"]["assistant-finance"]
    instance["parts"] = {"billing": {"level": 1, "actions": {"change-due-date": 2}}}
    del instance["owner"], instance["deputy"]
    signed(folder, settings, ("ana",))
    scenario = stack.gateway.scenario
    with db.transaction(stack.admin) as conn:
        assert not registry.apply(conn, stack.gateway.definitions, scenario.settings(),
                                  scenario.tools(), scenario.person, scenario.name).refused
    raise_cap(stack)  # as graded samples raise it
    _, token = stack.open_run(sender="ben")
    with stack.client(token) as c:
        assert c.post("/run/tools/change_due_date", json={"args": MOVE[1]}).status_code == 200
    assert due_of(stack) == "2026-11-13"  # made at level 2
    with db.transaction(stack.admin) as conn:
        told = [r["text"] for r in conn.execute(
            "select text from digest_items union all select text from outbox")]
    assert any("made a change itself" in t for t in told), "a5s told nobody of a change it made"
