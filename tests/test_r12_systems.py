"""Round 12 of the critique: the made-up systems the scenarios run on (docs/critique.md, round 12,
A5, A7, A8, C7, D7, D12). SAP carries on where it was when it starts again, each change still made
once for its key; a review the forge was asked for reaches the delivery scenario's view, so the
reviewer may see the pull request and is chased for it; and the studio's sandbox has its own copy
of each system, at an address of its own, which the containers run in its network, each started
again with what it shares a network with."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import ROOT

SERVERS = {"service-desk": ("desk", ("itsm", "idp", "mdm")), "software-delivery": ("delivery", ("forge",)),
           "master-data": ("master", ("sap",))}


def system(name: str):
    spec = importlib.util.spec_from_file_location(f"r12_made_up_{name}", ROOT / "deploy" / "systems" / f"{name}.py")
    assert spec and spec.loader
    found = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = found  # as an import would, for its dataclasses
    spec.loader.exec_module(found)
    return found


def called(client: TestClient, tool: str, args: dict, key: str | None = None) -> dict:
    params = {"name": tool, "arguments": args, **({"_meta": {"a5s/key": key}} if key else {})}
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": params}).json()["result"]


def test_sap_carries_on_where_it_was_when_it_starts_again(tmp_path):
    sap = system("sap")
    data = ROOT / "scenarios" / "master-data" / "data.yaml"
    first = TestClient(sap.make(data, state=tmp_path))
    made = called(first, "update_change_request", {"key": "CR0000104", "base_unit": "EA"}, "k-1")
    assert not made["isError"], made
    again = sap.make(data, state=tmp_path)  # it stopped, and started again
    assert again.state.written.request("CR0000104")["values"]["base_unit"] == "EA"
    second = TestClient(again)
    repeat = called(second, "update_change_request", {"key": "CR0000104", "base_unit": "EA"}, "k-1")
    assert repeat["structuredContent"] == made["structuredContent"]  # made once, for its key
    called(second, "update_change_request", {"key": "CR0000106", "description": "Hex bolt M8"}, "k-2")
    kept = sap.make(data, state=tmp_path).state.written
    assert kept.request("CR0000104")["values"]["base_unit"] == "EA"  # nothing it did is lost


def test_a_review_the_forge_was_asked_for_reaches_the_delivery_scenarios_view(monkeypatch, tmp_path):
    from a5s.software_delivery import SoftwareDeliveryScenario
    monkeypatch.setenv("A5S_SYSTEMS_STATE", str(tmp_path))
    forge = system("forge")
    client = TestClient(forge.make(ROOT / "scenarios" / "software-delivery" / "data.yaml"))
    scenario = SoftwareDeliveryScenario(ROOT / "scenarios" / "software-delivery", "postgresql://unused")
    assert not scenario.sees("sol", "PR-17")
    made = called(client, "request_review", {"key": "PR-17", "reviewer": "sol"}, "k")
    assert not made["isError"], made
    assert scenario.sees("sol", "PR-17")  # the reviewer it asked may read what they review
    assert "sol" in {o.person for o in scenario.obligations() if o.record == "PR-17"}  # and is chased


@pytest.mark.parametrize("scenario", SERVERS)
def test_the_sandbox_has_its_own_copy_of_each_system(scenario):
    overlay, names = SERVERS[scenario]
    declared = yaml.safe_load((ROOT / "scenarios" / scenario / "mcp.yaml").read_text())["servers"]
    compose = yaml.safe_load((ROOT / "deploy" / f"compose.{overlay}.yaml").read_text())["services"]
    for name in names:
        server = declared[name]
        assert server["sandbox"] != server["url"], name  # nothing tried there reaches the deployment's
        port = server["sandbox"].split(":")[2].split("/")[0]
        copies = [s for s in compose.values() if s.get("network_mode") == "service:sandbox"
                  and f"/systems/{name}.py" in s["entrypoint"]]
        assert len(copies) == 1 and copies[0]["environment"]["A5S_SYSTEM_PORT"] == port, name
        assert copies[0]["profiles"] == ["sandbox"]
        deployed = [s for s in compose.values() if s.get("network_mode") == "service:gateway"
                    and f"/systems/{name}.py" in s["entrypoint"]]
        assert len(deployed) == 1, name
        for service in (*copies, *deployed):  # started again, and with what they share a network with
            assert service["restart"] == "unless-stopped"
            assert any(d.get("restart") for d in service["depends_on"].values())


def test_the_sandbox_reads_its_own_copies_state():
    compose = yaml.safe_load((ROOT / "deploy" / "compose.sandbox.yaml").read_text())["services"]
    sandbox = compose["sandbox"]
    assert sandbox["environment"]["A5S_SYSTEMS_STATE"] == "/systems-state"
    assert "sandbox-systems-state:/systems-state:ro" in sandbox["volumes"]


def test_in_tests_the_sandbox_calls_its_own_copies():
    from conftest import SPARE, scenario_systems
    found = scenario_systems("master-data")
    assert {"sap", "sandbox-sap"} <= set(found)
    assert found["sap"] is not found["sandbox-sap"]
    declared = yaml.safe_load((ROOT / "scenarios" / "master-data" / "mcp.yaml").read_text())["servers"]
    assert declared["sap"]["sandbox"] == f"http://127.0.0.1:{9204 + SPARE}/mcp"
    assert Path(found["sandbox-sap"].state) != Path(found["sap"].state or "/nowhere")
