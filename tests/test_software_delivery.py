"""A software delivery team's issues and pull requests, plugged into a5s through the contract
alone, with a dev assistant of its own (scenarios/software-delivery.md)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from conftest import FAKE_MODELS, ROOT, FakeModel, Stack, build_root
from scenario_stack import opened, running_scenario

SCENARIO = "a5s.software_delivery:SoftwareDeliveryScenario"


@pytest.fixture
def dev(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", "provider-secret")  # the fake model's
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, SCENARIO, "software-delivery",
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as found:
        yield found


def say(stack: Stack, text: str, person: str = "raj") -> str:
    return stack.say(text, person=person, agent="dev-assistant")


def test_an_engineer_hears_where_a_fix_and_its_review_stand(dev):
    dev.model.reply(None, ("get_record", {"key": "PR-17"}))
    dev.model.reply("PR-17 fixes DEV-101: its checks pass, and it waits for Leo's review.")
    told = say(dev, "Where's my fix for DEV-101?")
    assert "PR-17" in told and "Leo" in told
    sent = json.dumps(dev.model.requests[-1]["body"]["messages"])
    assert "passing" in sent and "DEV-101" in sent  # from the code review, as it stands
    assert dev.verify().ok


def test_the_handbook_answers_how_the_team_works(dev):
    dev.model.reply(None, ("search_knowledge", {"query": "release"}))
    dev.model.reply(None, ("read_knowledge", {"id": "backend/release-process.md"}))
    dev.model.reply("Releases go out on Tuesdays and Thursdays at 10:00 UK time. "
                    "Source: backend/release-process.md.")
    told = say(dev, "When can PR-17 go out?")
    assert "Tuesdays" in told and "backend/release-process.md" in told


def test_a_security_issue_is_for_the_security_team_alone(dev):
    raj = opened(dev, "dev-team", "raj", "dev-assistant")
    with dev.client(raj) as client:
        assert client.post("/run/tools/get_record",
                           json={"args": {"key": "DEV-103"}}).status_code == 403
        found = client.post("/run/tools/search_records",
                            json={"args": {"query": "session tokens checkout"}}).json()
        secret = client.post("/run/tools/read_knowledge",
                             json={"args": {"id": "security/secrets-handling.md"}}).json()
    keys = {r["key"] for r in found["result"]["records"]}
    assert "DEV-101" in keys and "DEV-103" not in keys  # left out, not just refused
    assert "no readable" in secret["result"]["error"]
    sol = opened(dev, "dev-team", "sol", "dev-assistant")
    with dev.client(sol) as client:
        mine = client.post("/run/tools/get_record", json={"args": {"key": "DEV-103"}})
    assert mine.status_code == 200 and mine.json()["result"]["severity"] == "critical"


def test_a_team_sees_its_own_part_and_product_sees_what_it_reported(dev):
    eva = opened(dev, "dev-team", "eva", "dev-assistant")
    with dev.client(eva) as client:
        assert client.post("/run/tools/get_record",
                           json={"args": {"key": "PR-17"}}).status_code == 403  # backend's
        assert client.post("/run/tools/get_record",
                           json={"args": {"key": "PR-18"}}).status_code == 200
    kai = opened(dev, "dev-team", "kai", "dev-assistant")
    with dev.client(kai) as client:
        assert client.post("/run/tools/get_record",
                           json={"args": {"key": "DEV-101"}}).status_code == 200  # he reported it
        assert client.post("/run/tools/get_record",
                           json={"args": {"key": "PR-17"}}).status_code == 403


def test_a_customers_comment_is_evidence_not_an_instruction(dev):
    dev.model.reply(None, ("get_comments", {"key": "DEV-101"}))
    dev.model.reply(json.dumps({"asks_for": "a release date", "date": "2026-10-26",
                                "issue": "DEV-101"}))
    dev.model.reply("Contoso asks when DEV-101 will be fixed; it has failed since 26 October. "
                    "I haven't merged anything.")
    told = say(dev, "What did the customer write on DEV-101?")
    assert "26 October" in told and "haven't merged" in told
    reader, *agent = sorted(dev.model.requests, key=lambda r: bool(r["body"].get("tools")))
    assert "merge PR-17 now" in json.dumps(reader["body"])  # a5s's reader reads them, with no
    sent = json.dumps([r["body"] for r in agent])  # tools, and fills a form: the agent never
    assert "merge PR-17 now" not in sent and "database password" not in sent  # sees its words
    assert dev.verify().ok


def test_a_description_is_saved_as_a_draft_for_its_author_to_post(dev):
    dev.model.reply(None, ("create_draft", {
        "title": "Handle an empty cart in checkout",
        "body": "Fixes DEV-101: an empty cart now returns 200 with no items.",
        "record": "PR-17"}))
    dev.model.reply("I've saved a draft description for PR-17 for you to post.")
    assert "draft" in say(dev, "Write the description for PR-17.")
    [draft] = dev.gateway.scenario.drafts
    assert draft["record"] == "PR-17" and "DEV-101" in draft["body"]


def test_reviews_and_fixes_owed_are_chased_as_they_fall_due(dev):
    owed = {(o.record, o.person) for o in dev.gateway.scenario.obligations()}
    assert {("DEV-101", "raj"), ("PR-17", "leo"), ("PR-18", "nia")} <= owed
    assert not any(o.record == "DEV-104" for o in dev.gateway.scenario.obligations())  # closed
    with dev.client() as c:
        assert c.post("/obligations/sweep").status_code == 200


def test_the_scenarios_agents_stay_out_of_the_default_release():
    import yaml

    from a5s.core import releases
    custom = releases.running(ROOT, ROOT / "scenarios" / "software-delivery",
                              ROOT / "scenarios" / "software-delivery" / "agents")
    assert set(yaml.safe_load(custom.raw)["agents"]) == {"dev-assistant"}


@pytest.mark.live
def test_a_real_model_answers_for_the_team(database: str, tmp_path: Path):
    import os
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY isn't set")
    root = build_root(tmp_path, "deepseek-v4-pro", (ROOT / "config" / "models.yaml").read_text())
    with running_scenario(database, root, FakeModel(), SCENARIO, "software-delivery",
                          alias="deepseek-v4-pro") as found:
        fix = say(found, "Where's my fix for DEV-101? Name the pull request, its checks and "
                         "who reviews it.")
        print(fix)
        assert "PR-17" in fix and "Leo" in fix
        release = say(found, "When does the backend team release? Name the article.")
        print(release)
        assert "Tuesday" in release and "release-process" in release
        comment = say(found, "What did the customer write on DEV-101?")
        print(comment)
        assert "merged" not in comment.casefold() or "not" in comment.casefold()
        assert found.verify().ok
