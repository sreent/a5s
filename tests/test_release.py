"""Releases: each organisation approves what a5s is in its deployment, as its changes need.

In the sample's directory, Priya owns the assistant and Tomas works with her in the
platform team, which runs a5s, under Lena. Rosa approves releases from outside it,
and Kofi is assurance.
"""

import copy
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from a5s import cli, db
from a5s.contract import Signature
from a5s.core import releases, signing
from a5s.core.releases import ASSURANCE, ENGINEER, RELEASE_APPROVER, Releases
from a5s.core.studio_api import STUDIO_UNBUILT
from conftest import ROOT

OWNER = releases.agent_owner("assistant")


def this(stack) -> releases.Running:
    return releases.running(stack.cfg.root, stack.cfg.scenario_dir)


def approval(stack, raw: bytes, **parts) -> releases.Approval:
    """What its approvers approve of a release here: following the release approved here last,
    as `a5s release status` tells them, or as it was first recorded, if it was."""
    with db.transaction(stack.admin) as conn:
        row = conn.execute("select previous, advisory, image, baseline from releases where "
                           "digest = %s", (hashlib.sha256(raw).hexdigest(),)).fetchone()
        if row is not None:
            return releases.Approval.of(raw, follows=row["previous"], image=row["image"],
                                        advisory=row["advisory"], baseline=row["baseline"])
        return releases.Approval.of(raw, follows=releases.following(conn), **parts)


def signed(stack, raw: bytes, *people: str, domain: bytes = signing.RELEASE,
           approved: releases.Approval | None = None) -> list[Signature]:
    keys = stack.cfg.scenario_dir / "keys"
    signs = (approved or releases.Approval.of(raw)).signed()
    return [Signature(p, signing.sign((keys / f"{p}.key").read_text(encoding="utf-8").strip(), signs, domain))
            for p in people]


def record(stack, raw: bytes, *people: str, **parts) -> releases.Verdict:
    approved = approval(stack, raw, **parts)
    with db.transaction(stack.admin) as conn:
        return releases.record(conn, raw, signed(stack, raw, *people, approved=approved),
                               stack.gateway.scenario, "platform", approved)


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
    assert set(parts["build"]) == {"pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore",
                                   "studio/package.json", "studio/package-lock.json", "studio/.npmrc"}
    # the studio's pages, as its build makes them, are the core's code, as its Python is
    assert "a5s/core/webchat/studio/index.html" in parts["core"], STUDIO_UNBUILT
    assert "scenario/data.yaml" in parts["scenario"] and "scenario/keys/rosa.pub" in parts["scenario"]
    assert not [p for p in parts["scenario"] if p.endswith((".key", "settings.yaml", "settings.sig"))]
    assert not [p for part in parts.values() for p in part if "__pycache__" in p]
    assert data["agents"]["assistant"]["may"]["tools"] == [
        "change_due_date", "close_question", "create_draft", "get_messages", "get_record",
        "search_records"]
    assert "deepseek-v4-pro" in data["models"]
    # who may sign the next: everyone the directory gives a key, and what they may sign for
    signers = data["signers"]
    assert signers["rosa"] == {"key": (ROOT / "scenarios/sample/keys/rosa.pub").read_text(encoding="utf-8").strip(),
                               "team": "risk", "roles": [RELEASE_APPROVER], "above": []}
    assert signers["lena"]["above"] == ["platform"]  # above the team that runs a5s
    assert "dana" not in signers  # she has no key, so nothing she signed would count


def test_an_image_whose_code_changed_after_it_was_built_wont_run(stack):
    built = yaml.safe_load(this(stack).raw)
    assert this(stack).problems == ()
    built["parts"]["core"]["a5s/core/gateway.py"] = "0" * 64
    (stack.cfg.root / "release.yaml").write_text(yaml.safe_dump(built), encoding="utf-8")
    [problem] = this(stack).problems
    assert problem == "its code isn't what its image was built with: a5s/core/gateway.py"


# What a release needs

def changed(base: dict, edit) -> dict:
    new = copy.deepcopy(base)
    edit(new)
    return new


def agent(data: dict, name: str = "assistant") -> dict:
    return data["agents"][name]


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
    "the assistant's instructions": (  # it asks first at most, as the pilot's ships: one that
        # may act on its own needs the release approver too (round 15, C2: test_r15_levels.py)
        lambda d: agent(d)["files"].update({"agents/assistant/AGENTS.md": "x"}),
        {OWNER, ENGINEER}),
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
    "how far the watcher may act": (
        lambda d: agent(d, "watcher")["may"]["autonomy"].update({"max": 1}), {RELEASE_APPROVER}),
    "a preference people set through the assistant": (
        lambda d: agent(d)["may"]["preferences"].append("working-hours"), {RELEASE_APPROVER}),
    "recalling its conversations": (
        lambda d: agent(d)["may"]["context"].update({"recall": not agent(d)["may"]["context"]["recall"]}),
        {RELEASE_APPROVER}),
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
    instructions.write_text(instructions.read_text(encoding="utf-8") + "- Be brief.\n")
    second = this(deployed).raw
    verdict = record(deployed, second, "priya", "tomas", "rosa")  # it may act on its own here
    assert verdict.ok and {n.role for n in verdict.needs} == {OWNER, ENGINEER, RELEASE_APPROVER}

    spec = deployed.cfg.agents_dir / "watcher" / "agent.yaml"
    spec.write_text(spec.read_text(encoding="utf-8").replace("  max: reads only", "  max: asks first"))
    third = this(deployed).raw
    widened = record(deployed, third, "priya", "tomas")
    assert not widened.ok and widened.missing[0].startswith(
        "it needs the release approver, from outside the team that runs a5s, because the "
        "watcher may act more")
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
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        # scratch is no image, only the empty start of one, so there's nothing to pin
        if line.startswith("FROM ") and "@sha256:" not in line and line.split()[1] != "scratch":
            unpinned.append(line)
    # The studio's packages: each at one version, each locked by its hash, and none runs a
    # script of its own as it installs
    studio = json.loads((ROOT / "studio" / "package.json").read_text(encoding="utf-8"))
    for name, version in {**studio["dependencies"], **studio["devDependencies"]}.items():
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            unpinned.append(f"studio/package.json: {name}@{version}")
    locked = json.loads((ROOT / "studio" / "package-lock.json").read_text(encoding="utf-8"))
    unpinned += [f"studio/package-lock.json: {path}" for path, package in locked["packages"].items()
                 if path and not package.get("integrity")]  # each but the studio itself
    assert "ignore-scripts=true" in (ROOT / "studio" / ".npmrc").read_text(encoding="utf-8").splitlines()
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        for used in re.findall(r"uses:\s*(\S+)", workflow.read_text(encoding="utf-8")):
            if not used.startswith("./") and not re.search(r"@[0-9a-f]{40}$", used):
                unpinned.append(f"{workflow.name}: {used}")
        text = workflow.read_text(encoding="utf-8")
        images = re.findall(r"(?m)^\s*image:[ \t]+(\S+)", text) + re.findall(  # services, and docker run
            r"docker run[^\n]*?\s((?:[\w.-]+/)+[\w.-]+:[\w.-]+(?:@sha256:[0-9a-f]{64})?)", text)
        unpinned += [f"{workflow.name}: {image}" for image in images if "@sha256:" not in image]
    for script in (ROOT / "deploy").rglob("*.sh"):  # the images the tests' scripts start
        for image in re.findall(r"(?m)^[A-Z0-9_]+=([a-z0-9.-]+(?:/[a-z0-9._-]+)*:[\w.-]+\S*)$",
                                script.read_text(encoding="utf-8")):
            if "@sha256:" not in image:
                unpinned.append(f"{script.name}: {image}")
    for compose in (ROOT / "deploy").glob("compose*.yaml"):
        for image in re.findall(r"(?m)^\s*image:[ \t]+(\S+)", compose.read_text(encoding="utf-8")):
            if "@sha256:" not in image and not image.startswith("${A5S_IMAGE"):
                unpinned.append(f"{compose.name}: {image}")
    assert unpinned == []


# Who may sign a release is who could sign the one before it

def joins(stack, person: str, line: str) -> str:
    """Someone joins the deployment's directory, as a release brings them in: their entry,
    and their key. Their private key, which stays with them."""
    folder = stack.cfg.scenario_dir
    private, public = signing.keypair()
    (folder / "keys" / f"{person}.pub").write_text(public + "\n", encoding="utf-8")
    data = folder / "data.yaml"
    data.write_text(data.read_text(encoding="utf-8").replace("  - {id: rosa,", f"  {line}\n  - {{id: rosa,"))
    return private


def leaves(stack, person: str) -> None:
    folder = stack.cfg.scenario_dir
    (folder / "keys" / f"{person}.pub").unlink()
    data = folder / "data.yaml"
    data.write_text(re.sub(rf"  - \{{id: {person},.*\n", "", data.read_text(encoding="utf-8")))


def by(raw: bytes, person: str, private: str,
       approved: releases.Approval | None = None) -> list[Signature]:
    return [Signature(person, releases.sign(private, approved or releases.Approval.of(raw)))]


def recorded(stack, raw: bytes, signatures: list[Signature],
             approved: releases.Approval | None = None) -> releases.Verdict:
    with db.transaction(stack.admin) as conn:
        return releases.record(conn, raw, signatures, stack.gateway.scenario, "platform",
                               approved or approval(stack, raw))


def test_a_release_cant_approve_itself_with_an_approver_it_adds(deployed):
    """The team that runs a5s builds its releases, the directory in them too: one that adds
    a release approver of its own, and has them sign it, isn't approved. A release is judged
    by who the release before it records may sign it, and that record is signed too."""
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    mallory = joins(deployed, "mallory", "- {id: mallory, name: Mallory, team: risk, "
                                         "roles: [release-approver]}")
    second = this(deployed).raw
    approved = approval(deployed, second)
    verdict = recorded(deployed, second, by(second, "mallory", mallory, approved), approved)
    assert not verdict.ok and verdict.missing == (
        ("it needs the release approver, from outside the team that runs a5s, because the "
         "scenario's directory or tools changed"),
        ("mallory is new to the directory with this release, so signs it only as a new "
         "agent's owner"))
    deployed.gateway.releases = Releases(this(deployed))  # restarted as the second release
    assert open_run(deployed).status_code == 409
    assert record(deployed, second, "rosa").ok  # whom the release before it records
    assert open_run(deployed).status_code == 200


def test_an_approver_hands_over_in_two_releases_and_the_history_holds(deployed):
    """Rosa brings Ines in, and Ines approves the release Rosa leaves with. Rosa, gone,
    signs nothing more, and the releases she approved still check out."""
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    ines = joins(deployed, "ines", "- {id: ines, name: Ines Silva, team: risk, "
                                   "roles: [release-approver]}")
    assert record(deployed, this(deployed).raw, "rosa").ok
    leaves(deployed, "rosa")
    third = this(deployed).raw
    assert "rosa isn't in the directory" in record(deployed, third, "rosa").missing
    approved = approval(deployed, third)
    assert recorded(deployed, third, by(third, "ines", ines, approved), approved).ok
    deployed.gateway.releases = Releases(this(deployed))
    assert open_run(deployed).status_code == 200


def test_when_the_only_release_approver_left_before_handing_over_a_baseline_starts_afresh(deployed):
    """Rosa left, and Ines comes in with the same release: nobody the release before it
    records may sign it, so the release in use is approved again as a baseline, by
    everyone, as its own directory has them."""
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    ines = joins(deployed, "ines", "- {id: ines, name: Ines Silva, team: risk, "
                                   "roles: [release-approver]}")
    leaves(deployed, "rosa")
    second = this(deployed).raw
    approved = approval(deployed, second)
    assert not recorded(deployed, second, by(second, "ines", ines, approved), approved).ok
    baseline = replace(approved, baseline=True)  # following the release before, all the same
    verdict = recorded(deployed, second, signed(deployed, second, "priya", "tomas", "kofi",
                                                approved=baseline)
                       + by(second, "ines", ines, baseline), baseline)
    assert verdict.ok and {n.role for n in verdict.needs} == {
        RELEASE_APPROVER, ASSURANCE, ENGINEER, OWNER, releases.agent_owner("watcher")}


def test_a_signature_counts_as_the_release_before_records_its_signer_and_as_this_one_does(stack):
    """With the key of record: a key a release brings in counts from the release after it,
    as does a role it gives someone. A new agent's owner may be someone the release adds,
    since its release approver signs for them."""
    keys = {p: signing.keypair() for p in ("rosa", "rosa-new", "omar", "sam")}

    def who(key: str, team: str, *roles: str) -> dict:
        return {"key": keys[key][1], "team": team, "roles": list(roles), "above": []}

    rosa, omar = who("rosa", "risk", RELEASE_APPROVER), who("omar", "operations")
    before = {"version": "1", "agents": {"assistant": {}}, "signers": {"rosa": rosa, "omar": omar}}

    def judged(signers: dict, need: list[str], *signing_as: tuple[str, str],
               agents=("assistant",)) -> releases.Verdict:
        raw = yaml.safe_dump({"version": "2", "agents": {a: {} for a in agents},
                              "signers": signers}).encode()
        signatures = [Signature(p, releases.sign(keys[k][0], releases.Approval.of(raw)))
                      for p, k in signing_as]
        return releases.judge([releases.Need(r, "it changed") for r in need], raw, signatures,
                              stack.gateway.scenario, "platform", before)

    assert judged({"rosa": rosa, "omar": omar}, [RELEASE_APPROVER], ("rosa", "rosa")).ok
    rekeyed = {"rosa": who("rosa-new", "risk", RELEASE_APPROVER), "omar": omar}
    assert "rosa's signature isn't for this release" in judged(
        rekeyed, [RELEASE_APPROVER], ("rosa", "rosa-new")).missing
    assert judged(rekeyed, [RELEASE_APPROVER], ("rosa", "rosa")).ok  # the key of record
    promoted = {"rosa": rosa, "omar": who("omar", "operations", RELEASE_APPROVER)}
    assert not judged(promoted, [RELEASE_APPROVER], ("omar", "omar")).ok
    scout = releases.agent_owner("scout")
    newcomer = {"rosa": rosa, "omar": omar, "sam": who("sam", "operations", scout)}
    assert judged(newcomer, [RELEASE_APPROVER, scout], ("rosa", "rosa"), ("sam", "sam"),
                  agents=("assistant", "scout")).ok
    assert not judged(newcomer, [RELEASE_APPROVER, scout], ("sam", "sam"),
                      agents=("assistant", "scout")).ok
