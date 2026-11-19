"""Round 13, reviewer D: the desk's devices as device management holds them.

D1: device management reads the desk's data afresh for each call, but the desk's own code, which
says whose a device is and who may see it, read it once, as the gateway started. So once IT gave
Sam's phone to Pat there, a5s went on treating it as Sam's: he could read it, and lock it alone at
level 2, as his own, and Pat couldn't see it. The desk's code reads its data again whenever it
changes, as the made-up systems do.

D2: a5s counted a lock as made whenever the answer named the device, even one saying it wasn't
locked, as a real device management answers a lock it has queued until the phone next connects.
A change tool's declaration says what its answer says once made, and an answer saying otherwise
is the change in hand, not made: never counted, reported or sampled as made. The made-up system
answers so for a device that isn't connected, and refuses one that was never enrolled."""

from __future__ import annotations

import shutil

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from a5s.connectors.mcp import Declared, Served, answered
from a5s.core import parts
from a5s.service_desk import ServiceDeskScenario
from conftest import ROOT
from test_r12_systems import called, system


def a_desk(tmp_path, monkeypatch) -> tuple[ServiceDeskScenario, TestClient, object]:
    monkeypatch.setenv("A5S_SYSTEMS_STATE", str(tmp_path / "state"))
    folder = tmp_path / "service-desk"
    shutil.copytree(ROOT / "scenarios" / "service-desk", folder, ignore=shutil.ignore_patterns("agents"))
    return ServiceDeskScenario(folder, "postgresql://unused"), TestClient(system("mdm").make(folder / "data.yaml")), folder


def given(folder, key: str, **fields) -> None:
    """IT changes a device in device management, such as giving it to someone else."""
    data = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
    for device in data["devices"]:
        if device["key"] == key:
            device.update(fields)
    (folder / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_a_phone_given_to_pat_is_pats_for_a5s_too(tmp_path, monkeypatch):
    desk, mdm, folder = a_desk(tmp_path, monkeypatch)
    assert desk.sees("sam", "PH-0012") and desk.record("PH-0012").person == "sam"
    given(folder, "PH-0012", holder="pat")  # as a real desk hands phones over every week
    assert called(mdm, "get_device", {"key": "PH-0012"})["structuredContent"]["holder"] == "pat"
    assert desk.sees("pat", "PH-0012") and not desk.sees("sam", "PH-0012")
    assert desk.record("PH-0012").person == "pat"
    run = {"trigger": {"kind": "message", "conversation": "sam"}, "acts_for": ["sam"],
           "read_outside": False, "parts": {"access": 1, "hardware": 1}, "level": 1}
    standing = {"PH-0012": {"person": desk.record("PH-0012").person}}
    assert not parts.for_self(run, ["PH-0012"], standing), "locking Pat's phone is Sam's own"
    assert not parts.workable(desk, run, "PH-0012"), "Sam still works on Pat's phone"
    pats = {**run, "trigger": {"kind": "message", "conversation": "pat"}, "acts_for": ["pat"]}
    assert parts.workable(desk, pats, "PH-0012") and parts.for_self(pats, ["PH-0012"], standing)


LOCK = Served(name="lock_device", description="Lock a device", schema={"type": "object"},
              run=lambda call: None, writes=True, idempotent=True, record_arg="key",
              record_field="key", action="lock-device", server="mdm", calls="lock_device",
              returns=("key", "locked", "state", "link"), made=(("locked", True),))


def structured(found: dict) -> dict:
    return {"content": [{"type": "text", "text": "done"}], "structuredContent": found, "isError": False}


def test_a_lock_queued_until_the_phone_connects_is_in_hand_not_made():
    queued = answered(structured({"key": "PH-0012", "locked": False, "state": "pending"}), LOCK)
    assert set(queued) == {"error"} and "hasn't made it yet: locked is false, not true" in queued["error"]
    made = answered(structured({"key": "PH-0012", "locked": True, "link": "x"}), LOCK)
    assert made == {"key": "PH-0012", "locked": True, "link": "x"}


def test_what_counts_as_made_is_a_field_it_returns_of_a_tool_that_changes():
    base = {"server": "mdm", "calls": "lock_device", "description": "Lock it",
            "arguments": {"type": "object", "properties": {"key": {"type": "string"}}},
            "returns": ["key", "locked"], "writes": True, "record_arg": "key", "record_field": "key"}
    assert Declared(**base, action="lock-device", made={"locked": True}).made == {"locked": True}
    with pytest.raises(ValidationError, match="aren't among the fields it returns"):
        Declared(**base, action="lock-device", made={"wiped": True})
    with pytest.raises(ValidationError, match="only a tool that changes a record"):
        Declared(**base, made={"locked": True})


def test_the_made_up_system_queues_a_lock_for_a_phone_away_and_refuses_one_never_enrolled(tmp_path, monkeypatch):
    _, mdm, folder = a_desk(tmp_path, monkeypatch)
    refused = called(mdm, "lock_device", {"key": "LT-0101"}, "k-1")  # it isn't enrolled yet
    assert refused["isError"] and "isn't enrolled" in refused["content"][0]["text"]
    given(folder, "PH-0012", reachable=False)  # lost, and off
    queued = called(mdm, "lock_device", {"key": "PH-0012"}, "k-2")
    assert not queued["isError"] and queued["structuredContent"]["locked"] is False
    assert queued["structuredContent"]["state"] == "pending"
    assert "error" in answered(queued, LOCK)  # so a5s counts nothing made
    assert called(mdm, "get_device", {"key": "PH-0012"})["structuredContent"]["locked"] is False


def test_the_desk_declares_its_lock_made_only_once_locked():
    declared = yaml.safe_load((ROOT / "scenarios" / "service-desk" / "mcp.yaml").read_text(encoding="utf-8"))
    assert declared["tools"]["lock_device"]["made"] == {"locked": True}
