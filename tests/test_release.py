"""Releases: each organisation approves what a5s is in its deployment, as its changes need.

In the sample's directory, Priya owns the assistant and Tomas works with her in the
platform team, which runs a5s, under Lena. Rosa approves releases from outside it,
and Kofi is assurance.
"""

import copy
import hashlib
import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from a5s import cli, db
from a5s.contract import Signature
from a5s.core import releases, signing
from a5s.core.releases import ASSURANCE, ENGINEER, RELEASE_APPROVER, Releases
from conftest import ROOT

OWNER = releases.agent_owner("assistant")


def this(stack) -> releases.Running:
    return releases.running(stack.cfg.root, stack.cfg.scenario_dir)


def signed(stack, raw: bytes, *people: str, domain: bytes = signing.RELEASE) -> list[Signature]:
    keys = stack.cfg.scenario_dir / "keys"
    return [Signature(p, signing.sign((keys / f"{p}.key").read_text().strip(), raw, domain))
            for p in people]


def record(stack, raw: bytes, *people: str, advisory: str | None = None) -> releases.Verdict:
    with db.transaction(stack.admin) as conn:
        return releases.record(conn, raw, signed(stack, raw, *people), stack.gateway.scenario,
                               "platform", advisory)


def open_run(stack):
    with stack.client() as c:
        return c.post("/runs", json={"instance": "assistant-finance", "trigger": {
            "kind": "message", "inbound": stack.send("Hello")}})


@pytest.fixture
def deployed(stack):
    """The stack as deployed, not in development, so its release must be approved."""
    stack.gateway.cfg = replace(stack.gateway.cfg, development=False)
    stack.gateway.releases = Releases(this(stack))
    return stack


# What a release holds

def test_a_release_lists_every_file_it_runs_and_what_its_agents_may_do():
    raw = releases.manifest(ROOT, ROOT / "scenarios" / "sample")
    assert raw == releases.manifest(ROOT, ROOT / "scenarios" / "sample")  # the same every time
    data = yaml.safe_load(raw)
    parts = data["parts"]
    assert "a5s/core/gateway.py" in parts["core"] and "a5s/worker.py" in parts["services"]
    assert set(parts["build"]) == {"pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore"}
    assert "scenario/data.yaml" in parts["scenario"] and "scenario/keys/rosa.pub" in parts["scenario"]
    assert not [p for p in parts["scenario"] if p.endswith((".key", "settings.yaml", "settings.sig"))]
    assert not [p for part in parts.values() for p in part if "__pycache__" in p]
    assert data["agents"]["assistant"]["may"]["tools"] == ["create_draft", "get_record", "search_records"]
    assert "deepseek-v4-pro" in data["models"]


def test_an_image_whose_code_changed_after_it_was_built_wont_run(stack):
    built = yaml.safe_load(this(stack).raw)
    assert this(stack).problems == ()
    built["parts"]["core"]["a5s/core/gateway.py"] = "0" * 64
    (stack.cfg.root / "release.yaml").write_text(yaml.safe_dump(built))
    [problem] = this(stack).problems
    assert problem == "its code isn't what its image was built with: a5s/core/gateway.py"


# What a release needs

def changed(base: dict, edit) -> dict:
    new = copy.deepcopy(base)
    edit(new)
    return new


def agent(data: dict) -> dict:
    return data["agents"]["assistant"]


BASE = yaml.safe_load(releases.manifest(ROOT, ROOT / "scenarios" / "sample"))
CHANGES = {
    "the trusted core": (lambda d: d["parts"]["core"].update({"a5s/core/policy.py": "x"}),
                         {RELEASE_APPROVER, ASSURANCE}),
    "its dependencies": (lambda d: d["parts"]["build"].update({"uv.lock": "x"}),
                         {RELEASE_APPROVER, ASSURANCE}),
    "the services": (lambda d: d["parts"]["services"].update({"a5s/worker.py": "x"}), {ENGINEER}),
    "the scenario": (lambda d: d["parts"]["scenario"].update({"scenario/data.yaml": "x"}),
                     {RELEASE_APPROVER}),
    "a newly approved model": (lambda d: (d["parts"]["models"].update({"config/models.yaml": "x"}),
                                          d["models"].update({"ours": {"data_classes": []}})),
                               {RELEASE_APPROVER}),
    "a model approved for more data": (
        lambda d: (d["parts"]["models"].update({"config/models.yaml": "x"}),
                   d["models"]["qwen3.7-max"]["data_classes"].append("confidential")),
        {RELEASE_APPROVER}),
    "a model withdrawn": (lambda d: (d["parts"]["models"].update({"config/models.yaml": "x"}),
                                     d["models"].pop("qwen3.7-max")), {ENGINEER}),
    "the assistant's instructions": (
        lambda d: agent(d)["files"].update({"agents/assistant/AGENTS.md": "x"}), {OWNER, ENGINEER}),
    "a tool for the assistant": (lambda d: agent(d)["may"]["tools"].append("send_email"),
                                 {RELEASE_APPROVER}),
    "a tool the assistant uses": (lambda d: agent(d)["may"]["pins"].update({"get_record": "x"}),
                                  {RELEASE_APPROVER}),
    "the assistant's model": (lambda d: agent(d)["may"].update({"model": "qwen3.7-max"}),
                              {RELEASE_APPROVER}),
    "a schedule for the assistant": (
        lambda d: agent(d)["may"]["schedules"].append({"name": "morning"}), {RELEASE_APPROVER}),
    "a report for the assistant": (
        lambda d: agent(d)["may"]["reports"].append({"source": "records"}),
        {RELEASE_APPROVER}),
    "how far the assistant may act": (
        lambda d: agent(d)["may"]["autonomy"].update({"max": 2}), {RELEASE_APPROVER}),
    "less the assistant may do": (lambda d: agent(d)["may"]["tools"].remove("create_draft"),
                                  {OWNER, ENGINEER}),
    "a new agent": (lambda d: d["agents"].update({"librarian": agent(BASE)}),
                    {RELEASE_APPROVER, releases.agent_owner("librarian")}),
    "nothing": (lambda d: None, set()),
}


@pytest.mark.parametrize("what", CHANGES)
def test_what_a_release_needs_depends_on_what_changed(what):
    edit, expected = CHANGES[what]
    assert {n.role for n in releases.needs(changed(BASE, edit), BASE)} == expected


def test_the_first_release_a_deployment_approves_needs_everyone():
    assert {n.role for n in releases.needs(BASE, None)} == {
        RELEASE_APPROVER, ASSURANCE, ENGINEER, OWNER, releases.agent_owner("watcher")}


def test_a_security_fix_goes_in_at_once_only_if_it_changes_only_dependencies():
    lock = changed(BASE, CHANGES["its dependencies"][0])
    assert [n.role for n in releases.needs(lock, BASE, "GHSA-xxxx")] == [ENGINEER]
    both = changed(lock, CHANGES["the trusted core"][0])
    assert {n.role for n in releases.needs(both, BASE, "GHSA-xxxx")} == {RELEASE_APPROVER, ASSURANCE}


# Who may approve it

def judge(stack, need: set[str], *people: str, raw: bytes = b"a release", **kwargs) -> releases.Verdict:
    needs = [releases.Need(role, "it changed") for role in sorted(need)]
    return releases.judge(needs, raw, kwargs.pop("signatures", None) or signed(stack, raw, *people),
                          stack.gateway.scenario, "platform")


def test_the_trusted_core_needs_the_release_approver_and_assurance(stack):
    assert judge(stack, {RELEASE_APPROVER, ASSURANCE}, "rosa", "kofi").ok
    missing = judge(stack, {RELEASE_APPROVER, ASSURANCE}, "rosa").missing
    assert missing == ("it needs assurance, after their tests, because it changed",)


def test_nobody_in_the_team_that_runs_a5s_or_above_it_approves_its_releases(stack, monkeypatch):
    people = stack.gateway.scenario._people
    for person in ("tomas", "lena"):  # in the team, and its manager
        monkeypatch.setitem(people, person, replace(people[person], roles=(RELEASE_APPROVER,)))
        assert not judge(stack, {RELEASE_APPROVER}, person).ok
    assert judge(stack, {RELEASE_APPROVER}, "rosa").ok


def test_instructions_need_the_owner_and_a_second_engineer(stack):
    assert judge(stack, {OWNER, ENGINEER}, "priya", "tomas").ok
    alone = judge(stack, {OWNER, ENGINEER}, "priya")  # she's an engineer too, but one person
    assert not alone.ok and alone.missing[0].startswith("it needs 2 different people")


def test_only_a_signature_over_exactly_this_release_counts(stack):
    elsewhere = signed(stack, b"another release", "rosa")
    assert "rosa's signature isn't for this release" in judge(
        stack, {RELEASE_APPROVER}, signatures=elsewhere).missing
    as_settings = signed(stack, b"a release", "rosa", domain=signing.SETTINGS)
    assert not judge(stack, {RELEASE_APPROVER}, signatures=as_settings).ok
    stranger = [Signature("mallory", elsewhere[0].value)]
    assert "mallory isn't in the directory" in judge(
        stack, {RELEASE_APPROVER}, signatures=stranger).missing


# The core runs only what its deployment approved

def test_the_core_opens_no_run_for_a_release_its_deployment_hasnt_approved(deployed):
    refused = open_run(deployed)
    assert refused.status_code == 409
    [reason] = [r for r in refused.json()["detail"]["reasons"] if "release" in r]
    assert reason == "release 0.1.0 of a5s isn't approved here: nobody here has approved it yet"

    raw = this(deployed).raw
    assert not record(deployed, raw, "rosa", "kofi").ok  # the first needs the agent owner, too
    assert record(deployed, raw, "priya", "tomas").ok  # and signatures add up
    assert open_run(deployed).status_code == 200


def test_editing_the_record_approves_nothing(deployed):
    raw = this(deployed).raw
    with db.transaction(deployed.admin) as conn:
        conn.execute("insert into releases (digest, version, manifest, approved_at) "
                     "values (%s, '0.1.0', %s, now())", (hashlib.sha256(raw).hexdigest(), raw))
    assert open_run(deployed).status_code == 409


def test_a_release_is_weighed_against_the_one_approved_before_it(deployed):
    first = this(deployed).raw
    assert record(deployed, first, "priya", "tomas", "rosa", "kofi").ok
    instructions = deployed.cfg.agents_dir / "assistant" / "AGENTS.md"
    instructions.write_text(instructions.read_text() + "- Be brief.\n")
    second = this(deployed).raw
    verdict = record(deployed, second, "priya", "tomas")
    assert verdict.ok and {n.role for n in verdict.needs} == {OWNER, ENGINEER}

    spec = deployed.cfg.agents_dir / "assistant" / "agent.yaml"
    spec.write_text(spec.read_text().replace("  max: 1", "  max: 2"))
    third = this(deployed).raw
    widened = record(deployed, third, "priya", "tomas")
    assert not widened.ok and widened.missing[0].startswith(
        "it needs the release approver, from outside the team that runs a5s, because the "
        "assistant may act more")
    assert record(deployed, third, "rosa").ok


def test_people_sign_and_the_administrator_records_with_the_command_line(deployed, tmp_path,
                                                                          monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("A5S_ROOT", str(deployed.cfg.root))
    monkeypatch.setenv("A5S_DATABASE_URL", deployed.admin)
    cli.main(["release", "show"])
    Path("release.yaml").write_bytes(capsys.readouterr().out.encode())
    for person in ("priya", "tomas", "rosa", "kofi"):
        cli.main(["release", "sign", "--as", person])
    with pytest.raises(SystemExit):
        cli.main(["release", "status"])  # signed, but not yet recorded here
    cli.main(["release", "approve"])
    cli.main(["release", "status"])
    assert capsys.readouterr().out.rstrip().endswith("Approved here.")
    assert open_run(deployed).status_code == 200


# Everything it's built from is pinned

def test_everything_a5s_is_built_and_tested_with_is_pinned():
    unpinned = []
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        if line.startswith("FROM ") and "@sha256:" not in line:
            unpinned.append(line)
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        for used in re.findall(r"uses:\s*(\S+)", workflow.read_text()):
            if not used.startswith("./") and not re.search(r"@[0-9a-f]{40}$", used):
                unpinned.append(f"{workflow.name}: {used}")
        text = workflow.read_text()
        images = re.findall(r"(?m)^\s*image:[ \t]+(\S+)", text) + re.findall(  # services, and docker run
            r"docker run[^\n]*?\s((?:[\w.-]+/)+[\w.-]+:[\w.-]+(?:@sha256:[0-9a-f]{64})?)", text)
        unpinned += [f"{workflow.name}: {image}" for image in images if "@sha256:" not in image]
    for compose in (ROOT / "deploy").glob("compose*.yaml"):
        for image in re.findall(r"(?m)^\s*image:[ \t]+(\S+)", compose.read_text()):
            if "@sha256:" not in image and not image.startswith("${A5S_IMAGE"):
                unpinned.append(f"{compose.name}: {image}")
    assert unpinned == []


def test_when_an_approver_leaves_the_release_in_use_is_approved_again_as_a_baseline(deployed,
                                                                                    monkeypatch):
    first = this(deployed).raw
    assert record(deployed, first, "priya", "tomas", "rosa", "kofi").ok
    instructions = deployed.cfg.agents_dir / "assistant" / "AGENTS.md"
    instructions.write_text(instructions.read_text() + "- Be brief.\n")
    second = this(deployed).raw
    assert record(deployed, second, "priya", "tomas").ok

    people = deployed.gateway.scenario._people
    private, public = signing.keypair()
    monkeypatch.setitem(people, "rosa", replace(people["rosa"], roles=()))  # she has moved on
    monkeypatch.setitem(people, "ines", replace(people["rosa"], id="ines", name="Ines Silva",
                                                roles=(RELEASE_APPROVER,), public_key=public))
    with db.transaction(deployed.admin) as conn:
        history = releases.check(conn, hashlib.sha256(second).hexdigest(),
                                 deployed.gateway.scenario, "platform")
    assert not history.ok and history.missing[0].startswith("the release before it isn't approved")

    with db.transaction(deployed.admin) as conn:  # Ines approves in Rosa's place, with everyone
        signatures = signed(deployed, second, "priya", "tomas", "kofi") + [
            Signature("ines", signing.sign(private, second, signing.RELEASE))]
        verdict = releases.record(conn, second, signatures, deployed.gateway.scenario, "platform",
                                  baseline=True)
    assert verdict.ok and {n.role for n in verdict.needs} == {
        RELEASE_APPROVER, ASSURANCE, ENGINEER, OWNER, releases.agent_owner("watcher")}
