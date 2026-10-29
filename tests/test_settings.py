"""Settings count only when an instance approver signs them, and never go backwards."""

import shutil

import pytest
import yaml

from a5s import db, definitions
from a5s.core import ledger, registry, signing
from a5s.sample import SampleScenario
from conftest import ROOT


@pytest.fixture
def sample(tmp_path, database):
    folder = tmp_path / "sample"
    shutil.copytree(ROOT / "scenarios" / "sample", folder)
    keys = {}
    for person in ("ana", "ben"):  # ana is an instance approver, ben isn't
        private, public = signing.keypair()
        (folder / "keys" / f"{person}.pub").write_text(public)
        keys[person] = private
    return folder, keys, database


def write(folder, serial, level=1):
    settings = {"serial": serial, "instances": {"assistant-finance": {
        "definition": "assistant", "serves": ["ana", "ben"], "level": level}}}
    (folder / "settings.yaml").write_text(yaml.safe_dump(settings))
    (folder / "settings.sig").unlink(missing_ok=True)


def sign(folder, person, private):
    sig_file = folder / "settings.sig"
    signed = yaml.safe_load(sig_file.read_text()) if sig_file.exists() else {"signatures": []}
    value = signing.sign(private, (folder / "settings.yaml").read_bytes())
    signed["signatures"].append({"signer": person, "value": value})
    sig_file.write_text(yaml.safe_dump(signed))


def apply(folder, database):
    scenario = SampleScenario(folder, database)
    with db.transaction(database) as conn:
        return registry.apply(conn, definitions.load_all(ROOT / "agents"), scenario.settings(),
                              scenario.tools(), scenario.person, scenario.name)


def instances(database):
    with db.transaction(database) as conn:
        return conn.execute("select id, level from instances").fetchall()


def test_a_signed_version_applies_and_records_its_signer(sample):
    folder, keys, database = sample
    write(folder, 1)
    sign(folder, "ana", keys["ana"])
    result = apply(folder, database)
    assert result.instances == ["assistant-finance"] and result.signers == ["ana"]
    with db.transaction(database) as conn:
        entry = ledger.entries(conn)[-1]
    assert entry["args"]["signed_by"] == ["ana"] and entry["args"]["serial"] == 1


def test_an_unsigned_version_doesnt_count(sample):
    folder, _, database = sample
    write(folder, 1)
    result = apply(folder, database)
    assert result.refused == ["no instance-approver signed this version"]
    assert instances(database) == []
    with db.transaction(database) as conn:
        assert ledger.entries(conn)[-1]["decision"] == "deny"


def test_a_signature_for_another_version_doesnt_count(sample):
    folder, keys, database = sample
    write(folder, 1, level=0)
    sign(folder, "ana", keys["ana"])
    signature = (folder / "settings.sig").read_text()
    write(folder, 1, level=1)  # someone raises the level after Ana signed
    (folder / "settings.sig").write_text(signature)
    result = apply(folder, database)
    assert "ana's signature isn't for this version" in result.refused


def test_only_an_instance_approver_can_sign(sample):
    folder, keys, database = sample
    write(folder, 1)
    sign(folder, "ben", keys["ben"])
    assert "ben doesn't hold the instance-approver role" in apply(folder, database).refused


def test_an_older_version_cant_be_replayed(sample):
    folder, keys, database = sample
    write(folder, 1, level=1)
    sign(folder, "ana", keys["ana"])
    old_settings, old_signature = (folder / "settings.yaml").read_text(), (folder / "settings.sig").read_text()
    write(folder, 2, level=0)
    sign(folder, "ana", keys["ana"])
    assert not apply(folder, database).refused
    (folder / "settings.yaml").write_text(old_settings)  # the old, looser version, still signed
    (folder / "settings.sig").write_text(old_signature)
    assert "serial 1 is older than 2, the version in force" in apply(folder, database).refused
    assert instances(database)[0]["level"] == 0


def test_a_serial_belongs_to_one_version(sample):
    folder, keys, database = sample
    write(folder, 1, level=0)
    sign(folder, "ana", keys["ana"])
    assert not apply(folder, database).refused
    write(folder, 1, level=1)
    sign(folder, "ana", keys["ana"])
    assert "serial 1 already belongs to another version" in apply(folder, database).refused


def test_the_same_version_can_be_applied_again(sample):
    folder, keys, database = sample
    write(folder, 1)
    sign(folder, "ana", keys["ana"])
    assert not apply(folder, database).refused
    assert not apply(folder, database).refused  # for example, to roll out a new release


def test_runs_dont_open_for_settings_nobody_signed(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set level = 2, settings_version = 'forged'")
    assert reasons(stack) == ["assistant-finance isn't in the settings in force"]


def reasons(stack) -> list[str]:
    """Why a run for Ana's next message doesn't open, if it doesn't."""
    with stack.client() as c:
        r = c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello")}})
    return r.json()["detail"]["reasons"] if r.status_code == 409 else []


def test_an_instance_the_signed_settings_leave_out_is_retired_and_stops(stack):
    original = {"assistant-finance": {"definition": "assistant", "serves": ["ana", "ben"], "level": 1}}
    assert stack.settle(instances={}).instances == []
    assert reasons(stack) == ["assistant-finance is retired", "assistant-finance isn't in the settings in force"]
    assert stack.say("Hi") == "There's no assistant for you yet."
    stack.settle(instances=original)  # brought back by a later signed version
    stack.model.reply("I'm back.")
    assert stack.say("Hi") == "I'm back."
    actions = [e["action"] for e in stack.ledger() if e["kind"] == "admin" and e.get("instance")]
    assert "retire" in actions and "restore" in actions


@pytest.mark.parametrize("edit, reason", [
    ("update instances set serves = serves || '{chen}'", "doesn't match its signed settings"),
    ("update instances set level = 2", "doesn't match its signed settings"),
    ("update instances set grants = grants || '{delete_everything}'",
     "doesn't match its signed settings"),
    ("update instances set owner = 'chen'", "doesn't match its signed settings"),
], ids=["serves", "level", "grants", "owner"])
def test_editing_an_instance_in_the_database_doesnt_change_what_it_may_do(stack, edit, reason):
    with db.transaction(stack.admin) as conn:
        conn.execute(edit)
    [why] = reasons(stack)
    assert reason in why


def test_a_suspension_lifted_in_the_database_doesnt_count(stack):
    stack.suspend()
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set status = 'active', suspended_by = null")
    assert reasons(stack) == ["assistant-finance's status doesn't match the ledger"]


def test_the_settings_in_force_are_checked_from_the_bytes_that_were_signed(stack):
    with db.transaction(stack.admin) as conn:
        conn.execute("update settings_versions set raw = "
                     "convert_to(replace(convert_from(raw, 'UTF8'), 'ben', 'chen'), 'UTF8')")
        conn.execute("update instances set serves = array_replace(serves, 'ben', 'chen')")
    stack.gateway._checked.clear()  # as a gateway that starts after the edit would be
    assert reasons(stack) == ["the settings in force aren't what was signed"]


def test_an_older_signed_version_cant_be_put_back(stack):
    with db.transaction(stack.admin) as conn:
        older = conn.execute("select version from settings_versions").fetchone()["version"]
    stack.settle(level=0)
    with db.transaction(stack.admin) as conn:
        conn.execute("update instances set level = 1, settings_version = %s", (older,))
    assert reasons(stack) == ["assistant-finance isn't in the settings in force"]


def test_a_release_that_needs_tools_the_scenario_lacks_isnt_applied(sample):
    folder, keys, database = sample
    write(folder, 1)
    sign(folder, "ana", keys["ana"])
    scenario = SampleScenario(folder, database)
    tools = {n: t for n, t in scenario.tools().items() if n != "create_draft"}
    with db.transaction(database) as conn:
        result = registry.apply(conn, definitions.load_all(ROOT / "agents"), scenario.settings(),
                                tools, scenario.person, scenario.name)
    assert result.refused == ["assistant names tools the scenario doesn't have: create_draft"]
    assert instances(database) == []
