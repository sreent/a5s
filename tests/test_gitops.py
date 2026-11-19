"""Deploying a5s from git (deploy/gitops/README.md, a5s/gitops.py): `a5s release promote` writes
what an environment runs, the people its release needs sign it there with their own keys, and
`a5s release verify`, the check on the pull request that deploys it, passes once their
signatures meet what the release needs, weighed against the release the environment ran
before and judged as it ran that, and the pull request changes nothing else there. The chart
deploys what the environment's folder says, and its job records the signatures it holds.

In the sample's directory, Priya owns the agents, Tomas works with her in the platform team,
which runs a5s, Rosa approves releases from outside it, and Kofi is assurance."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from a5s import cli, gitops
from conftest import ROOT
from test_configuration import HELM

EXAMPLE = ROOT / "deploy" / "gitops" / "environments" / "example"
IMAGE = "ghcr.io/owner/a5s@sha256:" + "a" * 64
EVERYONE = ("priya", "tomas", "rosa", "kofi")  # whom the sample's first release needs


@pytest.fixture
def env(tmp_path, monkeypatch) -> Path:
    """An environment, copied from the example, as someone sets one up."""
    monkeypatch.setenv("A5S_ROOT", str(ROOT))
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "production"
    shutil.copytree(EXAMPLE, folder)
    return folder


def released(capsys) -> Path:
    """The manifest of the release this checkout is, as its image would be built with."""
    cli.main(["release", "show"])
    path = Path("release.yaml")
    path.write_bytes(capsys.readouterr().out.encode())
    return path


def promote(env: Path, manifest: Path, capsys, image: str = IMAGE) -> str:
    cli.main(["release", "promote", "--environment", str(env), "--manifest", str(manifest),
              "--image", image])
    return capsys.readouterr().out


def sign(env: Path, *people: str) -> None:
    for person in people:
        cli.main(["release", "sign", "--as", person, "--environment", str(env)])


def verify(env: Path, capsys, before: Path | None = None) -> str:
    """The check, with the environment's folder as the branch it merges into has it, if given."""
    cli.main(["release", "verify", "--environment", str(env),
              *(["--before", str(before)] if before else [])])
    return capsys.readouterr().out


def refused(env: Path, capsys, before: Path | None = None) -> str:
    with pytest.raises(SystemExit) as stopped:
        verify(env, capsys, before)
    return str(stopped.value)


def as_it_runs(env: Path, tmp_path: Path) -> Path:
    """The environment's folder as it is, as the branch a pull request merges into has it."""
    before = tmp_path / "before"
    shutil.rmtree(before, ignore_errors=True)
    shutil.copytree(env, before)
    return before


def next_release(manifest: Path) -> Path:
    """The next release, which changes only the assistant's instructions: it needs the
    assistant's owner and an engineer."""
    changed = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    changed["agents"]["assistant"]["files"] = {**changed["agents"]["assistant"].get("files", {}),
                                               "instructions.md": "0" * 64}
    changed["version"] = f"{changed['version']}-next"
    manifest.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")
    return manifest


def test_a_release_deploys_once_everyone_it_needs_has_signed_it_in_the_environment(env, capsys):
    said = promote(env, released(capsys), capsys)
    assert "It needs the release approver" in said and "signs it there" in said
    assert sorted(p.name for p in env.iterdir()) == [
        "helmrelease.yaml", "kustomization.yaml", "kustomizeconfig.yaml", "release-source.yaml",
        "release-values.yaml", "release.sig", "release.yaml", "source.yaml", "values.yaml"]
    assert refused(env, capsys).startswith("Not ready to deploy: it needs")
    sign(env, *EVERYONE[:-1])
    assert "assurance" in refused(env, capsys)  # one short
    sign(env, EVERYONE[-1])
    capsys.readouterr()
    assert verify(env, capsys).rstrip().endswith("Ready to deploy: its signatures meet what it needs.")
    values = yaml.safe_load((env / "release-values.yaml").read_text(encoding="utf-8"))
    assert values["image"] == {"repository": "ghcr.io/owner/a5s", "digest": "sha256:" + "a" * 64}
    assert values["release"]["approval"] == "a5s-release"
    version = yaml.safe_load((env / "release.yaml").read_text(encoding="utf-8"))["version"]
    tagged = yaml.safe_load((env / "release-source.yaml").read_text(encoding="utf-8"))
    assert tagged["spec"] == {"ref": {"tag": f"v{version}"}}  # the release's own chart
    source = yaml.safe_load((env / "source.yaml").read_text(encoding="utf-8"))
    assert source["spec"]["url"] == "https://github.com/OWNER/a5s"  # as the environment said
    assert tagged["metadata"] == source["metadata"]  # which the tag patches


def test_a_signature_made_beside_the_environment_leaves_its_values_stale(env, capsys):
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE[:-1])
    cli.main(["release", "sign", "--as", "kofi", "--manifest", str(env / "release.yaml"),
              "--out", str(env / "release.sig")])  # not --environment: no upgrade would record it
    assert "release-values.yaml isn't what its signatures make" in refused(env, capsys)
    sign(env, "kofi")  # as it's done there
    capsys.readouterr()
    assert "Ready to deploy" in verify(env, capsys)


def test_a_release_is_weighed_against_the_one_the_environment_ran(env, capsys, tmp_path):
    manifest = released(capsys)
    promote(env, manifest, capsys)
    sign(env, *EVERYONE)
    before = as_it_runs(env, tmp_path)
    said = promote(env, next_release(manifest), capsys)
    assert "It needs the assistant's owner" in said and "the release approver" not in said
    assert yaml.safe_load((env / "release.sig").read_text(encoding="utf-8"))["signatures"] == []  # the last's
    sign(env, "priya", "tomas")
    capsys.readouterr()
    assert "Ready to deploy" in verify(env, capsys, before)
    assert "its approval follows release" in refused(env, capsys)  # and not nothing


def test_a_pull_request_that_deploys_a_release_changes_nothing_else_in_its_environment(
        env, capsys, tmp_path):
    """The release deploys by its signatures alone, so it can't bring in, say, a patch that
    swaps the image the chart runs: how the environment runs is for its code owners to review,
    in a pull request of its own, and that passes the check with the release as it was."""
    manifest = released(capsys)
    promote(env, manifest, capsys)
    sign(env, *EVERYONE)
    before = as_it_runs(env, tmp_path)
    promote(env, next_release(manifest), capsys)
    sign(env, "priya", "tomas")
    (env / "patch.yaml").write_text("kind: Deployment\n", encoding="utf-8")
    capsys.readouterr()
    assert "this one changes patch.yaml too" in refused(env, capsys, before)
    (env / "patch.yaml").unlink()
    assert "Ready to deploy" in verify(env, capsys, before)
    shutil.rmtree(env)
    shutil.copytree(before, env)  # no release, and how it runs changes
    (env / "values.yaml").write_text((env / "values.yaml").read_text(encoding="utf-8") + "# more replicas\n")
    assert "Ready to deploy" in verify(env, capsys, before)


def test_a_release_is_judged_with_the_environments_values_as_it_runs_now(env, capsys, tmp_path):
    """So a pull request can't choose who judges it, such as by naming another team as the one
    that runs a5s, or another scenario's directory. Its first release is judged with its own."""
    before = as_it_runs(env, tmp_path)
    values = yaml.safe_load((env / "values.yaml").read_text(encoding="utf-8"))
    values["team"] = "risk"
    (env / "values.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")
    assert gitops.deployment(env, before) == {"team": "risk"}  # it runs no release yet
    promote(before, released(capsys), capsys)
    assert gitops.deployment(env, before) == {}  # as it runs that one
    assert gitops.deployment(env) == {"team": "risk"}  # as it's to run, as `show` says


def test_a_release_takes_its_chart_from_its_own_tag_alone(env, capsys):
    """Flux takes a commit or a branch over a tag, so neither may come in beside it."""
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE)
    tagged = env / "release-source.yaml"
    kept = tagged.read_text(encoding="utf-8")
    tagged.write_text(kept.replace("  ref:\n", "  ref:\n    commit: " + "0" * 40 + "\n"), encoding="utf-8")
    assert "isn't the release's own tag" in refused(env, capsys)
    tagged.write_text(kept, encoding="utf-8")
    repository = env / "source.yaml"
    repository.write_text(repository.read_text(encoding="utf-8").replace(
        "  interval: 30m\n", "  interval: 30m\n  ref:\n    branch: main\n"))
    assert "names a ref of its own" in refused(env, capsys)


def test_an_environment_shows_and_judges_its_release_as_it_deploys_a5s(env, capsys, tmp_path):
    """Its values name the scenario's folder and the team that runs a5s, as the chart gives
    them to its parts. So the release it shows, which the check compares with what its image
    holds, is the one they run, and that directory and team judge it."""
    folder = tmp_path / "scenario"
    shutil.copytree(ROOT / "scenarios" / "sample", folder)
    (folder / "handbook.yaml").write_text("deliveries: by noon\n", encoding="utf-8")  # the deployment's own
    values = yaml.safe_load((env / "values.yaml").read_text(encoding="utf-8"))
    values["scenario"]["folder"] = str(folder)
    values["team"] = "risk"  # Rosa's: her signature is the team's, not a release approver's
    (env / "values.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")
    sample = released(capsys).read_text(encoding="utf-8")
    cli.main(["release", "show", "--environment", str(env)])
    shown = capsys.readouterr().out
    assert "scenario/handbook.yaml" in shown and "scenario/handbook.yaml" not in sample
    manifest = tmp_path / "deployed.yaml"
    manifest.write_text(shown, encoding="utf-8")
    promote(env, manifest, capsys)
    sign(env, *EVERYONE)
    capsys.readouterr()
    assert "it needs the release approver" in refused(env, capsys)


def test_promoting_the_same_release_again_keeps_its_signatures_for_the_same_image(env, capsys):
    manifest = released(capsys)
    promote(env, manifest, capsys)
    sign(env, "rosa")
    promote(env, manifest, capsys)
    assert [s["signer"] for s in yaml.safe_load((env / "release.sig").read_text(encoding="utf-8"))["signatures"]
            ] == ["rosa"]
    promote(env, manifest, capsys, image="ghcr.io/owner/a5s@sha256:" + "b" * 64)  # rebuilt
    assert yaml.safe_load((env / "release.sig").read_text(encoding="utf-8"))["signatures"] == []  # not over it


@pytest.mark.parametrize("image", ["ghcr.io/owner/a5s:1.2.3", "ghcr.io/owner/a5s@sha256:abc"])
def test_an_image_not_named_by_its_digest_is_refused_and_changes_nothing(env, capsys, image):
    with pytest.raises(SystemExit, match="by its digest"):
        promote(env, released(capsys), capsys, image=image)
    assert not (env / "release.yaml").exists()


def test_a_folder_that_isnt_an_environment_is_refused(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("A5S_ROOT", str(ROOT))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="isn't an environment's folder"):
        promote(tmp_path, released(capsys), capsys)


def test_the_environment_is_what_flux_and_kustomize_deploy(env, capsys):
    """Every file its kustomization names is there once a release is promoted, and the
    HelmRelease takes its values from the ConfigMaps the kustomization makes, the release's
    last, so they win."""
    promote(env, released(capsys), capsys)
    kustomization = yaml.safe_load((env / "kustomization.yaml").read_text(encoding="utf-8"))
    named = [*kustomization["resources"], *kustomization["configurations"],
             *(p["path"] for p in kustomization["patches"]),
             *(f.split("=")[-1] for g in kustomization["configMapGenerator"] for f in g["files"])]
    assert all((env / f).is_file() for f in named), named
    generated = {g["name"] for g in kustomization["configMapGenerator"]}
    release = yaml.safe_load((env / "helmrelease.yaml").read_text(encoding="utf-8"))
    assert [v["name"] for v in release["spec"]["valuesFrom"]] == ["a5s-values", "a5s-release-values"]
    assert {v["name"] for v in release["spec"]["valuesFrom"]} <= generated
    assert release["spec"]["chart"]["spec"]["sourceRef"]["name"] == yaml.safe_load(
        (env / "source.yaml").read_text(encoding="utf-8"))["metadata"]["name"] == gitops.CHART


def test_the_chart_runs_the_environments_release_and_its_job_records_its_signatures(env, capsys):
    promote(env, released(capsys), capsys)
    sign(env, *EVERYONE)
    charts = ROOT / "deploy" / "helm"
    args = ["template", "a5s", "/charts/a5s", "-f", "/env/values.yaml",
            "-f", "/env/release-values.yaml"]
    if shutil.which("helm"):
        command = ["helm", *[a.replace("/charts", str(charts)).replace("/env", str(env))
                             for a in args]]
    elif shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True,
                                                   check=False).returncode == 0:
        command = ["docker", "run", "--rm", "-v", f"{charts}:/charts:ro", "-v", f"{env}:/env:ro",
                   HELM, *args]
    else:
        pytest.skip("neither helm nor docker is here to render the chart")
    run = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    assert run.returncode == 0, run.stderr
    docs = [d for d in yaml.safe_load_all(run.stdout) if d]
    approve = next(d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "a5s-approve")
    signed = yaml.safe_load((env / "release-values.yaml").read_text(encoding="utf-8"))["release"]["signatures"]
    assert approve["metadata"]["annotations"]["a5s.dev/signatures"] == signed
    images = {c["image"] for d in docs if d["kind"] == "Deployment"
              for c in d["spec"]["template"]["spec"]["containers"]}
    assert images == {IMAGE}  # every part runs the release, by its digest
