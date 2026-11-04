"""Round 5, reviewer a: whether the settings in force keep needing the approvals they need,
whether an older version can be put back, and whether settings can lift a suspension.

The sample's settings in force are signed by Ana, who owns billing and is an instance
approver: both instances work in billing, so her approval is the one they need.
"""

from dataclasses import replace

import psycopg
import pytest
from psycopg.types.json import Jsonb

from a5s import db
from conftest import SAMPLE_SETTINGS

ASSISTANT = SAMPLE_SETTINGS["instances"]["assistant-finance"]


def open_for(stack, person: str):
    with stack.client() as c:
        return c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello", person)}})


def test_once_its_only_approver_loses_the_role_the_version_in_force_stops_counting(
        stack, monkeypatch):
    """phase-1.md, step 6: 'The core checks this again at every run, so if a part's owner
    leaves, no run opens until whoever owns it now approves the version in force.'"""
    assert open_for(stack, "ana").status_code == 200  # the gateway has checked the version
    people = stack.gateway.scenario._people  # the directory, as a live one would change
    monkeypatch.setitem(people, "ana", replace(people["ana"], roles=()))  # she has moved on
    refused = open_for(stack, "ben")
    assert refused.status_code == 409, "a run opened on approvals nobody holds any more"
    assert any("aren't approved" in r for r in refused.json()["detail"]["reasons"])


def test_the_gateways_own_role_cant_put_back_an_older_wider_version(stack):
    """Ana stops the assistant serving Ben. With the gateway's database role, which migration
    0013 lets update settings_versions and instances, the older version is put back."""
    with db.transaction(stack.admin) as conn:
        older = conn.execute("select version from settings_versions").fetchone()["version"]
    assert not stack.settle(serves=["ana"]).refused  # tighter: Ben is no longer served
    assert open_for(stack, "ben").status_code == 409

    with (pytest.raises(psycopg.errors.InsufficientPrivilege),  # it may add signatures, no more
          db.transaction(db.as_role(stack.admin, "gateway")) as conn):
        newest = conn.execute("select max(serial) as s from settings_versions").fetchone()["s"]
        conn.execute("update settings_versions set serial = -1 where serial = %s", (newest,))
    with db.transaction(db.as_role(stack.admin, "gateway")) as conn:  # nor dress the old one up
        newest = conn.execute("select raw, signatures from settings_versions where serial = "
                              "(select min(serial) from settings_versions)").fetchone()
        conn.execute("update settings_versions set raw = %s, signatures = %s where serial = "
                     "(select max(serial) from settings_versions)",
                     (newest["raw"], Jsonb(newest["signatures"])))
        conn.execute("update instances set serves = '{ana,ben}', settings_version = %s "
                     "where id = 'assistant-finance'", (older,))
    assert open_for(stack, "ben").status_code == 409, "an older version was put back"


def test_retiring_and_restoring_an_instance_doesnt_lift_someone_elses_suspension(stack):
    """Ben suspends the assistant. Ana, who owns billing, approves a version that leaves it
    out, and then one that brings it back. registry.apply: 'applying settings never resumes a
    suspended instance'; agent-model.md: resuming someone else's suspension needs someone
    outside the team."""
    stack.suspend(by="ben")
    assert open_for(stack, "ana").status_code == 409
    assert not stack.settle(instances={}).refused  # it leaves the assistant out: retired
    assert not stack.settle(instances={"assistant-finance": ASSISTANT}).refused  # and back
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select status, suspended_by from instances "
                           "where id = 'assistant-finance'").fetchone()
    assert row["status"] == "suspended", f"restored as {row['status']}, Ben's suspension gone"
    assert open_for(stack, "ana").status_code == 409
