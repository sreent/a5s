"""The desk's devices, through device management's MCP server (deploy/systems/mdm.py), as its
pack says (scenarios/it-service-desk.md): each person's devices, in hardware, which only their
holder and hardware's resolvers may see. Locking one, such as a lost phone, is a change a5s holds
for hardware's decider below level 2, and makes once they approve it, once for a5s's key. It runs
alone, at level 2, only where the service owner's settings give it and graded samples raise
a5s's cap, and only for the person asking, on their own device: anyone else's waits for a
person, at any level."""

from __future__ import annotations

import json

import yaml
from fastapi.testclient import TestClient

from a5s import db
from a5s.core import registry
from conftest import ROOT, SYSTEMS, Stack, raise_cap, signed
from test_desk_self_service import approving, asked, decisions, desk  # noqa: F401
from test_proposals import decide, held, sweep
from test_r12_systems import called, system


def mdm() -> object:
    return SYSTEMS["service-desk"]["mdm"]


def locks_alone(desk: Stack) -> None:  # noqa: F811
    """The service owner's settings give the desk assistant level 2 for locking devices in
    hardware, as Ivy, Ola and Hugo signed them, and graded samples have raised a5s's cap there."""
    folder = desk.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    settings["instances"]["desk-access"]["parts"] = {
        "access": {"level": 1}, "hardware": {"level": 1, "actions": {"lock-device": 2}}}
    signed(folder, settings, ("ivy", "ola", "hugo"))
    scenario = desk.gateway.scenario
    with db.transaction(desk.admin) as conn:
        applied = registry.apply(conn, desk.gateway.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    raise_cap(desk, part="hardware", action="lock-device", instance="desk-access")


def test_a_device_is_seen_by_its_holder_and_hardwares_resolvers_alone(desk, approving):  # noqa: F811
    scenario = desk.gateway.scenario
    assert scenario.part_of("PH-0012") == "hardware"
    assert scenario.sees("sam", "PH-0012") and scenario.sees("hal", "PH-0012")  # its holder; hardware
    assert not scenario.sees("pat", "PH-0012") and not scenario.sees("rae", "PH-0012")
    asked(desk, ("search_devices", {"query": "laptop"}), person="pat", said="Which laptops are mine?")
    told = desk.model.requests[-1]["body"]["messages"][-1]["content"]
    assert "LT-0077" in told and "LT-0042" not in told and "LT-0101" not in told, told
    assert "its disk isn't encrypted" in told  # why it doesn't meet the rules, as the system says


def test_a_lock_of_someone_elses_device_waits_for_hardwares_decider(desk, approving, provider):  # noqa: F811
    asked(desk, ("lock_device", {"key": "PH-0012"}), person="hal",
          said="Sam's phone was stolen: lock PH-0012.")
    [p] = held(desk)
    assert (p["action"], p["deciders"], p["acts_for"], p["status"]) == (
        "lock-device", ["hugo"], ["hal"], "waiting")
    assert mdm().changed == {}  # nothing locked yet
    assert decide(approving, provider, [p["digest"]], person="hugo").status_code == 200
    sweep(desk)
    assert held(desk)[0]["status"] == "made" and mdm().changed["PH-0012"]["locked"] is True
    assert desk.gateway.scenario.record("PH-0012").fields == {"locked": "yes"}  # as the system holds it


def test_a_holders_lock_of_their_own_device_runs_alone_at_level_2(desk, approving):  # noqa: F811
    locks_alone(desk)
    asked(desk, ("lock_device", {"key": "PH-0012"}), said="I lost my phone, PH-0012: lock it, please.")
    assert decisions(desk, "lock_device") == [("allow", ["active-instances-use-their-grant"])]
    assert mdm().changed["PH-0012"]["locked"] is True
    told = json.loads(desk.model.requests[-1]["body"]["messages"][-1]["content"])
    assert told == {"key": "PH-0012", "locked": True, "link": "https://mdm.desk.test/devices/PH-0012"}
    assert held(desk) == []  # nobody had to decide it


def test_anyone_elses_lock_waits_for_a_person_even_at_level_2(desk, approving):  # noqa: F811
    locks_alone(desk)
    asked(desk, ("lock_device", {"key": "PH-0012"}), person="hal",
          said="Sam's phone was stolen: lock PH-0012.")
    [(decision, reasons)] = decisions(desk, "lock_device")
    assert decision == "hold" and "desk-locks-only-for-the-person-asking" in reasons
    [p] = held(desk)
    assert (p["action"], p["deciders"]) == ("lock-device", ["hugo"])
    assert mdm().changed == {}


def test_someone_who_may_not_see_a_device_cant_lock_it(desk, approving):  # noqa: F811
    locks_alone(desk)
    asked(desk, ("lock_device", {"key": "LT-0042"}), person="pat", said="Lock LT-0042.")
    [(decision, reasons)] = decisions(desk, "lock_device")
    assert decision == "deny" and "people-see-only-what-they-may" in reasons
    assert mdm().changed == {} and held(desk) == []


def test_a_lock_is_made_once_for_its_key_and_kept_through_a_restart(tmp_path):
    mdm_system = system("mdm")
    data = ROOT / "scenarios" / "service-desk" / "data.yaml"
    first = TestClient(mdm_system.make(data, state=tmp_path))
    made = called(first, "lock_device", {"key": "LT-0077"}, "k-1")
    assert not made["isError"] and made["structuredContent"]["locked"] is True, made
    again = TestClient(mdm_system.make(data, state=tmp_path))  # it stopped, and started again
    repeat = called(again, "lock_device", {"key": "LT-0077"}, "k-1")
    assert repeat["structuredContent"] == made["structuredContent"]  # made once, for its key
    found = called(again, "get_device", {"key": "LT-0077"})["structuredContent"]
    assert found["locked"] is True and found["reasons"] == ["its disk isn't encrypted"]
    assert called(again, "get_device", {"key": "LT-9999"})["isError"]  # no such device
