"""Round 11, reviewer A: releases nobody on the team that runs a5s approves alone (A-1 to A-4,
A-6, A-8). What people sign is now an approval of the release: its manifest, the image it runs
as, the release it follows and the advisory it fixes, and whether it's a baseline, so neither a
pull request that swaps the image nor an administrator who edits the record approves anything."""

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from a5s import cli, db
from a5s.core import releases, signing
from a5s.core.releases import Releases
from conftest import ROOT
from test_gitops import (
    EVERYONE,
    IMAGE,
    as_it_runs,
    env,  # noqa: F401 - a fixture
    promote,
    refused,
    released,
    sign,
    verify,
)
from test_release import approval, by, deployed, joins, open_run, record, recorded, signed, this  # noqa: F401

OTHER = "ghcr.io/owner/a5s@sha256:" + "b" * 64  # an image nobody signed for
VERIFY = ROOT / "deploy" / "gitops" / "verify.sh"


def approvers(folder: Path, *people: str) -> Path:
    """deploy/gitops/approvers.yaml, as the release approvers keep it outside every release:
    the people who judge an environment's first, as the sample's directory has them."""
    data = yaml.safe_load((ROOT / "scenarios" / "sample" / "data.yaml").read_text(encoding="utf-8"))["people"]
    found = {p["id"]: {"key": (ROOT / "scenarios" / "sample" / "keys" / f"{p['id']}.pub")
                       .read_text(encoding="utf-8").strip(), "team": p.get("team"),
                       "roles": sorted(p.get("roles") or []), "above": []}
             for p in data if p["id"] in people}
    path = folder.parent / "approvers.yaml"
    path.write_text(yaml.safe_dump({"signers": found}), encoding="utf-8")
    return path


def judged_first(folder: Path, capsys, before: Path, roots: Path | None) -> str:
    args = ["release", "verify", "--environment", str(folder), "--before", str(before),
            *(["--roots", str(roots)] if roots else [])]
    try:
        cli.main(args)
    except SystemExit as e:
        return "REFUSED: " + str(e)
    return capsys.readouterr().out


# A-1: what's signed names the image

def test_another_image_of_the_same_release_needs_its_approvers_again(env, capsys, tmp_path):  # noqa: F811
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE)
    before = as_it_runs(env, tmp_path)
    promote(env, env / "release.yaml", capsys, image=OTHER)  # the pull request: a new digest
    assert yaml.safe_load((env / "release.sig").read_text(encoding="utf-8"))["signatures"] == []
    said = refused(env, capsys, before)
    assert "it needs the release approver" in said and "another image" in said
    sign(env, "rosa", "kofi")
    capsys.readouterr()
    assert "Ready to deploy" in verify(env, capsys, before)


def test_a_digest_changed_beside_the_signatures_is_refused(env, capsys, tmp_path):  # noqa: F811
    from a5s import gitops
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE)
    before = as_it_runs(env, tmp_path)
    (env / gitops.VALUES).write_text(gitops.values(OTHER, (env / gitops.SIGNATURES).read_text(encoding="utf-8")))
    assert "approve it as another image" in refused(env, capsys, before)


# A-2: editing the record approves nothing

def test_a_record_that_follows_nothing_once_others_are_approved_is_refused(deployed):  # noqa: F811
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    instructions = deployed.cfg.agents_dir / "assistant" / "AGENTS.md"
    instructions.write_text(instructions.read_text(encoding="utf-8") + "- Be brief.\n")
    second = this(deployed).raw
    assert record(deployed, second, "priya", "tomas", "rosa").ok
    digest = hashlib.sha256(second).hexdigest()
    with db.transaction(deployed.admin) as conn:  # the administrator edits one column
        conn.execute("update releases set previous = null where digest = %s", (digest,))
        verdict = releases.check(conn, digest, deployed.gateway.scenario, "platform")
    assert not verdict.ok
    deployed.gateway.releases = Releases(this(deployed))
    assert open_run(deployed).status_code == 409


def test_a_baseline_cant_bring_in_approvers_while_those_of_record_remain(deployed):  # noqa: F811
    """The team's own image adds Mallory, a release approver, and Mallet, as assurance, with
    keys it holds. As a baseline, it's judged by the release before it all the same: Rosa and
    Kofi are still there, so only they sign for their roles."""
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    mallory = joins(deployed, "mallory", "- {id: mallory, name: Mallory, team: risk, "
                                         "roles: [release-approver]}")
    mallet = joins(deployed, "mallet", "- {id: mallet, name: Mallet, team: risk, "
                                       "roles: [assurance]}")
    second = this(deployed).raw
    baseline = releases.Approval.of(second, follows=approval(deployed, second).follows,
                                    baseline=True)
    sigs = (signed(deployed, second, "priya", "tomas", approved=baseline)
            + by(second, "mallory", mallory, baseline) + by(second, "mallet", mallet, baseline))
    verdict = recorded(deployed, second, sigs, baseline)
    assert not verdict.ok and "rosa" not in verdict.signed_by
    deployed.gateway.releases = Releases(this(deployed))
    assert open_run(deployed).status_code == 409


def test_a_change_to_what_the_image_is_built_from_needs_everyone_whatever_it_says_it_fixes(
        deployed):  # noqa: F811
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    (deployed.cfg.root / "Dockerfile").write_text("FROM scratch\n# and anything else\n", encoding="utf-8")
    second = this(deployed).raw
    verdict = record(deployed, second, "tomas", advisory="GHSA-made-up")
    assert not verdict.ok and {n.role for n in verdict.needs} >= {
        releases.RELEASE_APPROVER, releases.ASSURANCE}


def test_an_advisory_added_after_the_fact_approves_nothing(deployed):  # noqa: F811
    assert record(deployed, this(deployed).raw, "priya", "tomas", "rosa", "kofi").ok
    (deployed.cfg.root / "uv.lock").write_text("# a patched dependency\n", encoding="utf-8")  # the locks alone
    second = this(deployed).raw
    assert not record(deployed, second, "tomas").ok  # it needs the release approver
    claimed = approval(deployed, second)
    with db.transaction(deployed.admin) as conn:  # the administrator says it fixes one
        conn.execute("update releases set advisory = 'GHSA-made-up' where digest = %s",
                     (claimed.release,))
        assert not releases.check(conn, claimed.release, deployed.gateway.scenario,
                                  "platform").ok


# A-3: an environment's first release, and one that's taken away

def test_an_environments_first_release_is_judged_by_the_approvers_kept_outside_it(
        env, capsys, tmp_path):  # noqa: F811
    before = as_it_runs(env, tmp_path)  # set up, running no release yet
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE)
    capsys.readouterr()
    assert "judged by the approvers kept outside it" in judged_first(env, capsys, before, None)
    assert "Ready to deploy" in judged_first(env, capsys, before, approvers(env, "rosa", "kofi"))
    stranger = approvers(env, "rosa")  # assurance isn't among them: Kofi's signature won't do
    assert judged_first(env, capsys, before, stranger).startswith("REFUSED")


def _repo(tmp_path: Path, environment: str, *, taken_away: bool) -> Path:
    """A repository holding an environment, on main, and a pull request's branch changing it."""
    repo = tmp_path / "repo"
    folder = repo / "deploy" / "gitops" / "environments" / "production"
    folder.mkdir(parents=True)
    (folder / "release.yaml").write_text("version: 1\n", encoding="utf-8")
    (folder / "release-values.yaml").write_text("image:\n  repository: a\n  digest: b\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.email=a5s@example.test", "-c", "user.name=a5s",
                        *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("add", ".")
    git("commit", "-qm", "main")
    git("checkout", "-qb", "change")
    if taken_away:
        (folder / "release.yaml").unlink()
    else:
        other = repo / "deploy" / "gitops" / "environments" / environment
        other.mkdir(parents=True)
        (other / "values.yaml").write_text("team: platform\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "change")
    return repo


def _check(repo: Path) -> subprocess.CompletedProcess:
    docker = repo.parent / "bin"
    docker.mkdir(exist_ok=True)
    (docker / "docker").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")  # nothing it would ask of an image
    (docker / "docker").chmod(0o755)
    return subprocess.run(["sh", str(VERIFY), "main"], cwd=repo, capture_output=True, text=True,
                          env={"PATH": f"{docker}:/usr/bin:/bin"}, check=False)


def test_a_change_that_takes_an_environments_release_away_is_refused(tmp_path):
    found = _check(_repo(tmp_path, "", taken_away=True))
    assert found.returncode != 0 and "takes it away" in found.stderr


@pytest.mark.parametrize("name", ["prod eu", "produção"])
def test_an_environment_named_otherwise_is_refused_not_skipped(tmp_path, name):  # A-8
    found = _check(_repo(tmp_path, name, taken_away=False))
    assert found.returncode != 0 and "lower case letters, digits and hyphens" in found.stderr


# A-4, A-6: what an environment's own files may set

def test_an_environment_that_sets_its_own_image_or_models_is_refused(env, capsys, tmp_path):  # noqa: F811
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE)
    before = as_it_runs(env, tmp_path)
    helm = yaml.safe_load((env / "helmrelease.yaml").read_text(encoding="utf-8"))
    helm["spec"]["values"] = {"image": {"digest": "sha256:" + "c" * 64}}
    (env / "helmrelease.yaml").write_text(yaml.safe_dump(helm), encoding="utf-8")
    assert "sets values or post-renderers of its own" in refused(env, capsys, before)
    shutil.copy(before / "helmrelease.yaml", env / "helmrelease.yaml")
    values = yaml.safe_load((env / "values.yaml").read_text(encoding="utf-8"))
    values["models"] = {"configMap": "our-models"}
    (env / "values.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")
    assert "approves models with a ConfigMap of its own" in refused(env, capsys, before)


def test_the_image_digest_is_part_of_what_a_signature_signs():
    raw = b"version: 1\n"
    private, public = signing.keypair()
    value = releases.sign(private, releases.Approval.of(raw, image=IMAGE))
    assert signing.verify(public, releases.Approval.of(raw, image=IMAGE).signed(), value,
                          signing.RELEASE)
    assert not signing.verify(public, releases.Approval.of(raw, image=OTHER).signed(), value,
                              signing.RELEASE)
