"""The desk's self-service (phase 5, step 3), as its pack says (scenarios/it-service-desk.md): a
password reset is the identity provider's own flow, through its MCP server, which the account's
holder finishes there, verifying themselves, so the agent never sees a secret. It runs alone, at
level 2, only where the service owner's settings give it and graded samples raise a5s's cap, and
only for the person asking, on their own account: anyone else's goes to the ITSM's approvals. An
authenticator change never runs alone, at any level: it goes to a person. And below level 2, or
once a run has read what a requester wrote, a reset waits for the decider of access, as every
change does."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from a5s import db
from a5s.core import registry
from conftest import (
    FAKE_MODELS,
    ROOT,
    SYSTEMS,
    FakeModel,
    Stack,
    build_root,
    deciding,
    raise_cap,
    signed,
)
from test_proposals import held
from test_service_desk import running_desk


@pytest.fixture
def desk(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    """The desk, its agent with the identity provider's self-service, up to level 2 by its
    release, on a copy of the desk's folder whose settings a test may sign afresh."""
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    folder = tmp_path / "service-desk"
    shutil.copytree(ROOT / "scenarios" / "service-desk", folder, ignore=shutil.ignore_patterns("agents"))
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_desk(database, root, model, httpx.Client(transport=httpx.MockTransport(model.handler)),
                      folder=folder) as found:
        yield found


@pytest.fixture
def approving(desk: Stack, provider) -> Iterator[str]:
    with deciding(desk, provider) as url:
        yield url


def at_level_2(desk: Stack, *actions: str) -> None:
    """The service owner's settings give the desk assistant level 2 for `actions` in access, as
    Ivy, Ola and Hugo signed them, and graded samples have raised a5s's cap for each there."""
    folder = desk.cfg.scenario_dir
    settings = yaml.safe_load((folder / "settings.yaml").read_text())
    settings["instances"]["desk-access"]["parts"] = {
        "access": {"level": 1, "actions": dict.fromkeys(actions, 2)}, "hardware": {"level": 1}}
    signed(folder, settings, ("ivy", "ola", "hugo"))
    scenario = desk.gateway.scenario
    with db.transaction(desk.admin) as conn:
        applied = registry.apply(conn, desk.gateway.definitions, scenario.settings(), scenario.tools(),
                                 scenario.person, scenario.name)
    assert not applied.refused, applied.refused
    for action in actions:
        raise_cap(desk, part="access", action=action, instance="desk-access")


def asked(desk: Stack, *calls, person: str = "sam", said: str = "I forgot my password: reset it, please.") -> str:
    desk.model.reply(None, *calls)
    desk.model.reply("Done what I could.")
    return desk.say(said, person=person, agent="desk-assistant")


def decisions(desk: Stack, tool: str) -> list[tuple[str, list]]:
    return [(e["decision"], e.get("reasons") or []) for e in desk.ledger()
            if e["kind"] == "tool" and e["action"] == tool and e["decision"] != "record"]


def idp() -> object:
    return SYSTEMS["service-desk"]["idp"]


def test_a_reset_of_the_askers_own_account_runs_alone_at_level_2(desk, approving):
    at_level_2(desk, "reset-password")
    asked(desk, ("reset_password", {"key": "ACC-sam"}))
    assert decisions(desk, "reset_password") == [("allow", ["active-instances-use-their-grant"])]
    [started] = idp().resets["ACC-sam"]
    assert started["flow"].startswith("started: its holder finishes it with the identity provider")
    told = json.loads(desk.model.requests[-1]["body"]["messages"][-1]["content"])
    assert set(told) == {"key", "flow", "link"}  # nothing secret comes back to the agent
    assert held(desk) == []  # nobody had to decide it


def test_a_reset_of_anyone_elses_account_waits_for_accesss_decider_even_at_level_2(desk, approving):
    """The pack rules level 2 out for it, so it never runs alone: it waits for a person, as it
    would at level 1 (round 12, B5)."""
    at_level_2(desk, "reset-password")
    asked(desk, ("reset_password", {"key": "ACC-pat"}), person="rae",
          said="Pat's locked out: reset Pat's password.")
    [(decision, reasons)] = decisions(desk, "reset_password")
    assert decision == "hold" and "desk-self-service-only-for-the-person-asking" in reasons
    assert "ACC-pat" not in idp().resets
    [p] = held(desk)
    assert (p["action"], p["deciders"], p["acts_for"]) == ("reset-password", ["ola"], ["rae"])


def test_someone_who_may_not_see_an_account_cant_reset_it(desk, approving):
    at_level_2(desk, "reset-password")
    asked(desk, ("reset_password", {"key": "ACC-pat"}), said="Reset Pat's password.")
    [(decision, reasons)] = decisions(desk, "reset_password")
    assert decision == "deny" and "people-see-only-what-they-may" in reasons
    assert idp().resets == {}


def test_an_authenticator_change_never_runs_alone_whatever_the_settings(desk, approving):
    at_level_2(desk, "reset-authenticators")
    asked(desk, ("reset_authenticators", {"key": "ACC-sam"}), said="I lost my phone: remove my authenticator.")
    [(decision, reasons)] = decisions(desk, "reset_authenticators")
    assert decision == "hold" and "desk-authenticators-go-to-a-person" in reasons
    assert idp().removed == {}
    [p] = held(desk)
    assert (p["action"], p["deciders"]) == ("reset-authenticators", ["ola"])


def test_below_level_2_a_reset_and_an_authenticator_change_wait_for_accesss_decider(desk, approving):
    asked(desk, ("reset_password", {"key": "ACC-sam"}))
    asked(desk, ("reset_authenticators", {"key": "ACC-sam"}), said="I lost my phone: remove my authenticator.")
    assert [(p["action"], p["deciders"], p["acts_for"], p["status"]) for p in held(desk)] == [
        ("reset-password", ["ola"], ["sam"], "waiting"),
        ("reset-authenticators", ["ola"], ["sam"], "waiting")]
    assert held(desk)[1]["sensitive"]  # removing them can't be undone: decided on its own
    assert idp().resets == {} and idp().removed == {}


def test_after_a_requesters_words_a_reset_waits_for_a_person_even_at_level_2(desk, approving):
    at_level_2(desk, "reset-password")
    desk.model.reply(None, ("get_messages", {"key": "INC0000001"}))
    desk.model.reply(json.dumps({"asks_for": "a reset"}))  # a5s's reader, filling its form
    asked(desk, ("reset_password", {"key": "ACC-sam"}), said="Read my VPN ticket, then reset my password.")
    [p] = held(desk)
    assert (p["action"], p["deciders"], p["read_outside"]) == ("reset-password", ["ola"], True)
    assert idp().resets == {}


def accounts_down(desk: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    def down(*_):
        raise ConnectionError("the directory of accounts is down")
    monkeypatch.setattr(desk.gateway.scenario, "record", down)


def test_a_reset_fails_closed_when_whose_account_it_is_cant_be_read(desk, approving, monkeypatch):
    at_level_2(desk, "reset-password")
    accounts_down(desk, monkeypatch)
    asked(desk, ("reset_password", {"key": "ACC-sam"}))
    assert decisions(desk, "reset_password") == [("deny", ["records-can-be-read"])]
    assert idp().resets == {}


def test_nor_is_one_held_for_a_decider_who_couldnt_see_it(desk, approving, monkeypatch):
    accounts_down(desk, monkeypatch)
    asked(desk, ("reset_password", {"key": "ACC-sam"}))
    assert decisions(desk, "reset_password") == [("deny", ["records-can-be-read"])]
    assert held(desk) == []
