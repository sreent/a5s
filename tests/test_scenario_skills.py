"""The skills the shipped scenarios' agents bring, as the manual's page on skills walks through
them (docs/manual/skills.md): each keeps the Agent Skills format's rules for its name and what
it's for, names each file beside it, so a run knows to read it, and a run of its agent, on its
scenario's own stack, is told of it by name and purpose, and reads it, and what's beside it,
only when the work matches."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import FAKE_MODELS, PROVIDER_KEY, ROOT, FakeModel, build_root
from scenario_stack import running_scenario

# Each scenario's example: its class, its agent, who asks it what, the skill and the file beside
# its SKILL.md it reads, if any, the tool it calls next, if any, and what that tool's answer says.
EXAMPLES = {
    "service-desk": ("a5s.service_desk:ServiceDeskScenario", "desk-assistant", "sam",
                     "My password doesn't work any more.", "sign-in-help", "what-people-say.csv",
                     ("get_account", {"key": "ACC-sam"}), "active"),
    "procure-to-pay": ("a5s.procure_to_pay:ProcureToPayScenario", "ap-assistant", "hana",
                       "Draft a reply to the supplier of INV-9001, please.", "supplier-replies",
                       "reply.md", None, None),
    "master-data": ("a5s.master_data:MasterDataScenario", "mdg-assistant", "tess",
                    "What did the check find on CR0000101?", "check-results", None,
                    ("check_request", {"key": "CR0000101"}), "the same VAT number"),
}
NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")  # the format's: lower case and digits, single hyphens
FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def shipped() -> list[Path]:
    """Each skill an agent a5s ships brings, the reference agents' and each scenario's."""
    return sorted(p.parent for agents in (ROOT / "agents", *(ROOT / "scenarios").glob("*/agents"))
                  for p in agents.glob("*/skills/*/SKILL.md"))


def front(text: str) -> dict:
    return yaml.safe_load(text.split("---", 2)[1])


def seen(text: str) -> str:
    """A text as it reads in what the model is sent, which is JSON."""
    return json.dumps(text)[1:-1]


@pytest.mark.parametrize("folder", shipped(), ids=lambda f: f"{f.parents[2].name}/{f.name}")
def test_each_shipped_skill_keeps_the_formats_rules_and_names_what_it_brings(folder):
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    meta = front(text)
    assert set(meta) <= FIELDS and meta["name"] == folder.name
    assert NAME.fullmatch(folder.name) and len(folder.name) <= 64
    assert 0 < len(meta["description"]) <= 1024
    for beside in (p for p in folder.rglob("*") if p.is_file() and p.name != "SKILL.md"):
        assert f"`{beside.relative_to(folder).as_posix()}`" in text  # or no run knows to read it


def test_each_scenarios_example_is_a_skill_it_ships():
    assert {f"{f.parents[3].name}/{f.name}" for f in shipped()} >= {
        f"{scenario}/{example[4]}" for scenario, example in EXAMPLES.items()}


@pytest.mark.parametrize("scenario", sorted(EXAMPLES))
def test_a_run_is_told_of_its_skill_and_reads_it_only_when_the_work_matches(
        scenario, database, tmp_path, monkeypatch):
    kind, agent, person, said, skill, beside, then, found = EXAMPLES[scenario]
    folder = ROOT / "scenarios" / scenario / "agents" / agent / "skills" / skill
    files = ["SKILL.md", *([beside] if beside else [])]
    monkeypatch.setenv("A5S_TEST_PROVIDER_KEY", PROVIDER_KEY)
    model = FakeModel()
    root = build_root(tmp_path, "fake", FAKE_MODELS)
    with running_scenario(database, root, model, kind, scenario,
                          httpx.Client(transport=httpx.MockTransport(model.handler))) as stack:
        for name in files:  # as a5s tells a run to read one
            model.reply(None, ("read_file", {"file_path": f"/skills/{skill}/{name}", "limit": 1000}))
        if then:
            model.reply(None, then)
        model.reply("Done what I could.")
        stack.say(said, person=person, agent=agent)
    text = {name: (folder / name).read_text(encoding="utf-8") for name in files}
    told = json.dumps(model.requests[0]["body"]["messages"][0])
    assert seen(skill) in told and seen(front(text["SKILL.md"])["description"]) in told
    body = max(text["SKILL.md"].split("---", 2)[2].splitlines(), key=len)
    assert seen(body) not in told  # only once it's read
    for request, name in zip(model.requests[1:], files):
        assert seen(max(text[name].splitlines(), key=len)) in json.dumps(request["body"]["messages"][-1])
    if found:
        assert found in json.dumps(model.requests[-1]["body"]["messages"][-1])  # what code said
