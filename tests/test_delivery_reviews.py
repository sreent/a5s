"""Software delivery's held change (phase 5, step 4): asking someone to review a pull request,
through the forge's MCP server, as the scenario's mcp.yaml declares it, a change of type
`assign-reviewer`. Below level 2, a5s holds each for the owners of the pull request's
repository, its part, never anyone it's for; once they approve it, a5s asks the forge, once for
its key; and whoever asked is told. Someone who may not see a pull request can't ask for its
review."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, SYSTEMS, FakeModel, Stack, build_root, deciding
from scenario_stack import running_scenario
from test_proposals import decide, held, sweep
from test_software_delivery import SCENARIO

ASK = ("request_review", {"key": "PR-17", "reviewer": "sol"})


@pytest.fixture
def dev(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "software-delivery",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


@pytest.fixture
def approving(dev: Stack, provider) -> Iterator[str]:
    with deciding(dev, provider) as url:
        yield url


def asked(dev: Stack, call=ASK, person: str = "raj", said: str = "Ask Sol to review PR-17 too: it "
          "touches how sessions are logged.") -> None:
    dev.model.reply(None, call)
    dev.model.reply("It waits for the repository's owners to decide.")
    dev.say(said, person=person, agent="dev-assistant")


def reviewers(key: str = "PR-17") -> list[str] | None:
    return (SYSTEMS["software-delivery"]["forge"].changed.get(key) or {}).get("reviewers")


def test_a_review_request_waits_for_the_owners_of_its_repository(dev, approving):
    asked(dev)
    [p] = held(dev)
    assert (p["tool"], p["action"], p["deciders"], p["acts_for"], p["parts"], p["status"]) == (
        "request_review", "assign-reviewer", ["leo"], ["raj"], ["backend"], "waiting")
    assert p["said"].startswith("Ask someone to review an open pull request, which its repository's "
                                "owners decide: PR-17, with reviewer sol.")
    assert reviewers() is None  # nobody asked yet


def test_one_in_the_other_repository_waits_for_its_owner(dev, approving):
    asked(dev, ("request_review", {"key": "PR-18", "reviewer": "raj"}), person="eva",
          said="Ask Raj to review PR-18 as well.")
    assert held(dev)[0]["deciders"] == ["nia"]


def test_what_the_owner_approves_is_asked_of_the_forge_once(dev, approving, provider):
    asked(dev)
    [p] = held(dev)
    assert decide(approving, provider, [p["digest"]], person="leo").status_code == 200
    assert sweep(dev)["made"] == 1
    assert reviewers() == ["leo", "sol"]
    assert sweep(dev)["made"] == 0
    assert any(m["text"].startswith("Leo Park approved P-1, and a5s has made it: Ask someone to review")
               for m in dev.inbox("raj"))


def test_someone_who_may_not_see_a_pull_request_cant_ask_for_its_review(dev, approving):
    asked(dev, person="kai", said="Get Sol to review PR-17.")  # product, who reported DEV-101
    assert held(dev) == []
    [entry] = [e for e in dev.ledger() if e["kind"] == "tool" and e["action"] == "request_review"]
    assert entry["decision"] == "deny" and "people-see-only-what-they-may" in entry["reasons"]
