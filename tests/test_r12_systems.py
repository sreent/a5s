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
           "master-data": ("master", ("sap",)), "procure-to-pay": ("p2p", ("erp",))}


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
    declared = yaml.safe_load((ROOT / "scenarios" / scenario / "mcp.yaml").read_text(encoding="utf-8"))["servers"]
    compose = yaml.safe_load((ROOT / "deploy" / f"compose.{overlay}.yaml").read_text(encoding="utf-8"))["services"]
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
    compose = yaml.safe_load((ROOT / "deploy" / "compose.sandbox.yaml").read_text(encoding="utf-8"))["services"]
    sandbox = compose["sandbox"]
    assert sandbox["environment"]["A5S_SYSTEMS_STATE"] == "/systems-state"
    assert "sandbox-systems-state:/systems-state:ro" in sandbox["volumes"]


def test_in_tests_the_sandbox_calls_its_own_copies():
    from conftest import SPARE, scenario_systems
    found = scenario_systems("master-data")
    assert {"sap", "sandbox-sap"} <= set(found)
    assert found["sap"] is not found["sandbox-sap"]
    declared = yaml.safe_load((ROOT / "scenarios" / "master-data" / "mcp.yaml").read_text(encoding="utf-8"))["servers"]
    assert declared["sap"]["sandbox"] == f"http://127.0.0.1:{9204 + SPARE}/mcp"
    assert Path(found["sandbox-sap"].state) != Path(found["sap"].state or "/nowhere")


def test_the_made_up_exchange_answers_the_cores_own_graph_client(monkeypatch, database):
    """The procure-to-pay scenario's invoices mailbox, on a5s's containers: the made-up Exchange
    (deploy/systems/mailbox.py) signs in the deployment's app alone, gives the core where the
    inbox stands, with mail already there starting nothing, finds and reads the made-up
    messages, keeps a reply among the drafts, and sends nothing."""
    from datetime import UTC, datetime
    from urllib.parse import quote

    from a5s.connectors import mailboxes
    from a5s.connectors.rest import ConnectorError
    monkeypatch.setenv("A5S_MAIL_CLIENT_SECRET", "made-up-secret")
    folder = ROOT / "scenarios" / "procure-to-pay"
    client = TestClient(system("mailbox").make(folder))
    invoices = mailboxes.declared(folder).mailboxes["invoices"]

    def box(secret: str) -> mailboxes._Exchange:
        app = mailboxes.App("harbour", "a5s-mail", secret, "http://testserver/v1.0",
                            "http://testserver")
        return mailboxes._Exchange("invoices", invoices, mailboxes.Graph(app, lambda: client),
                                   database)

    with pytest.raises(ConnectorError, match="didn't give a5s's app a token"):
        box("guessed").graph.token()
    exchange = box("made-up-secret")
    found, link = exchange.new(None, datetime(2026, 11, 24, tzinfo=UTC))
    assert found == [] and link.startswith("http://testserver/v1.0/")  # mail already there
    assert exchange.new(link, datetime(2026, 11, 24, 0, 1, tzinfo=UTC))[0] == []
    hits = exchange.search(["INV-9002"])
    assert [h["from"] for h in hits] == ["billing@litware.example"]
    read = exchange.read(hits[0]["key"])
    assert read and "INV-9002" in read["text"] and not read["attachments"]
    assert exchange.draft(hits[0]["key"], "Thank you: we're looking into it.") is None
    assert client.app.state.drafts[0]["message"]["toRecipients"] == [  # to whom it came from
        {"emailAddress": {"address": "billing@litware.example"}}]
    token = exchange.graph.token()
    message = quote(client.app.state.held[invoices.address][1]["id"], safe="")
    path = f"/v1.0/users/{invoices.address}/messages/{message}/send"
    sent = client.post(path, headers={"Authorization": f"Bearer {token}"})
    assert sent.status_code == 403  # a5s sends nothing, and nor does it here
    elsewhere = client.get("/v1.0/users/ceo@harbour.test/messages",
                           headers={"Authorization": f"Bearer {token}"})
    assert elsewhere.status_code == 403  # a mailbox the app isn't given


def test_on_the_containers_the_core_alone_reads_the_made_up_exchange():
    compose = yaml.safe_load((ROOT / "deploy" / "compose.p2p.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    mailbox = services["p2p-mailbox"]
    assert mailbox["network_mode"] == "service:gateway" and mailbox["restart"] == "unless-stopped"
    assert mailbox["depends_on"]["gateway"]["restart"]
    gateway = services["gateway"]["environment"]
    assert gateway["A5S_MAIL_GRAPH"].startswith("http://127.0.0.1:")  # on its own loopback
    assert gateway["A5S_MAIL_CLIENT_SECRET"] == mailbox["environment"]["A5S_MAIL_CLIENT_SECRET"]
    for part in ("channels", "scheduler"):  # who reads the mailbox is the core's alone
        assert "A5S_MAIL_CLIENT_SECRET" not in (services[part].get("environment") or {}), part
