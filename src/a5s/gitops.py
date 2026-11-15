"""An environment's folder, from which Flux deploys a5s (deploy/gitops/README.md): the release it
runs, the signatures of the people its changes need, its image, by digest, and its chart, from
the release's own tag.

`a5s release promote` writes the folder's release files for a release, and each person it
needs signs it there with their own key (`a5s release sign --environment`), in the pull request
that deploys it. A check on the pull request, `a5s release verify`, passes once their signatures
meet what the release needs, weighed against the release the environment ran before and judged
as the environment ran it, so the pull request merges itself; Flux deploys what's merged; and the
chart's job records the signatures, which the core checks again before it opens a run. Rolling
back is reverting the merge.

A pull request that deploys a release changes nothing else in the environment, since a release
deploys by its signatures alone: the folder's other files, how the environment runs, change in
pull requests of their own, which its code owners review.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from a5s.core import releases

APPROVAL = "a5s-release"  # the ConfigMap the environment's kustomization makes of the two files
MANIFEST, SIGNATURES = "release.yaml", "release.sig"
VALUES, SOURCE = "release-values.yaml", "release-source.yaml"
RELEASE = (MANIFEST, SIGNATURES, VALUES, SOURCE)  # what promote and sign write: the release's own
REPOSITORY = "source.yaml"  # where its chart comes from, which release-source.yaml gives a tag
HELMRELEASE = "helmrelease.yaml"  # how Flux installs the chart, with its values and the release's
CHART = "a5s-release"  # that GitRepository's name, as helmrelease.yaml names it
IMAGE = re.compile(r"(?P<repository>[a-z0-9][a-z0-9._/:-]*)@(?P<digest>sha256:[0-9a-f]{64})")
SIGNED = "# Signatures over a release of a5s, made with `a5s release sign`.\n"
WRITTEN = ("# Written by `a5s release promote`, and by `a5s release sign --environment`: the "
           "release this\n# environment runs, by its image's digest, the approval its chart's "
           "job records, and its\n# signatures' hash, so a signature added is an upgrade, which "
           "records it.\n")
TAGGED = ("# Written by `a5s release promote`: the release's own tag, at which source.yaml's "
          "repository\n# gives the chart.\n")


class NotAnEnvironment(ValueError):
    """A folder that isn't an environment's, or a release it can't run."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signatures(approval: releases.Approval, *signed: str | None) -> str:
    """A release.sig for exactly this approval of a release, with every signature over it of
    those given, one for each signer, in signers' order: none if none are given. A signature
    over another approval, such as of the release with another image, or following another
    release, doesn't carry over: it isn't over this one."""
    kept: dict = {}
    for text in signed:
        found = yaml.safe_load(text or "") or {}
        if not found or found.get("release") != approval.release:
            continue  # over another release, such as the one the environment ran before
        same = releases.Approval(found["release"], found.get("image"), found.get("follows"),
                                 found.get("advisory"), bool(found.get("baseline")))
        if same == approval:
            kept.update({s["signer"]: s for s in found.get("signatures") or []})
    return SIGNED + yaml.safe_dump({**approval.shown(), "signatures": [
        {"signer": s["signer"], "value": s["value"]} for _, s in sorted(kept.items())]},
        sort_keys=False)


def values(image: str, signed: str) -> str:
    """The chart's values that make an environment run a release: its image, by digest, the
    approval its job records, and the signatures' hash."""
    found = IMAGE.fullmatch(image)
    if found is None:
        raise NotAnEnvironment(f"name the release's image by its digest, as REPOSITORY@sha256:..., "
                               f"not {image}")
    return WRITTEN + yaml.safe_dump({
        "image": {"repository": found["repository"], "digest": found["digest"]},
        "release": {"approval": APPROVAL, "signatures": _sha256(signed.encode())},
    }, sort_keys=False)


def source(version: str) -> str:
    """release-source.yaml for a release: its own tag, for the chart."""
    return TAGGED + yaml.safe_dump({
        "apiVersion": "source.toolkit.fluxcd.io/v1", "kind": "GitRepository",
        "metadata": {"name": CHART}, "spec": {"ref": {"tag": f"v{version}"}}}, sort_keys=False)


def _environment(folder: Path) -> Path:
    if not (folder / REPOSITORY).is_file() or not (folder / "kustomization.yaml").is_file():
        raise NotAnEnvironment(f"{folder} isn't an environment's folder: copy "
                               "deploy/gitops/environments/example to make one")
    return folder


def ran(folder: Path | None) -> bool:
    """Whether an environment's folder, such as the branch a pull request merges into has it,
    runs a release."""
    return folder is not None and (folder / MANIFEST).is_file() and (folder / VALUES).is_file()


def deployment(folder: Path, before: Path | None = None) -> dict[str, str]:
    """What an environment's own values (its values.yaml, the chart's) say of whom its
    releases are judged by: the scenario, its folder and agents', and the team that runs a5s,
    as the chart gives them to its parts. Only those it sets. Where it ran a release before,
    as `before` has its folder, its values then: a pull request doesn't choose who judges it."""
    judged = before if before is not None and ran(before) else _environment(folder)
    _environment(folder)
    found = yaml.safe_load((judged / "values.yaml").read_text()) or {}
    scenario = found.get("scenario") or {}
    return {k: v for k, v in (("scenario", scenario.get("class")),
                              ("scenario_folder", scenario.get("folder")),
                              ("agents_folder", scenario.get("agents")),
                              ("team", found.get("team"))) if v}


def image_of(folder: Path) -> str:
    """The image an environment runs, as REPOSITORY@sha256:..."""
    found = yaml.safe_load((_environment(folder) / VALUES).read_text())["image"]
    return f"{found['repository']}@{found['digest']}"


def promote(folder: Path, raw: bytes, image: str, signed: str | None = None, *,
            advisory: str | None = None, baseline: bool = False) -> releases.Approval:
    """Make an environment's folder run a release: its manifest; what its approvers sign of it,
    the release, its image, by digest, and the release the environment runs now, which it
    follows; the signatures over that so far, those given and any already there for it; its
    image, by digest, for the chart; and its chart, from the release's tag. The release it ran
    before stays in git, which is what the next is weighed against."""
    _environment(folder)
    version = yaml.safe_load(raw)["version"]
    sig = folder / SIGNATURES
    ran_before = (folder / MANIFEST).read_bytes() if ran(folder) else None
    if ran_before == raw and sig.is_file():  # promoted again: it follows what it followed
        follows = (yaml.safe_load(sig.read_text()) or {}).get("follows")
    else:
        follows = _sha256(ran_before) if ran_before is not None else None
    approval = releases.Approval.of(raw, image=image, follows=follows, advisory=advisory,
                                    baseline=baseline)
    kept = signatures(approval, sig.read_text() if sig.is_file() else None, signed)
    written = values(image, kept)  # before anything changes, so a bad image changes nothing
    (folder / MANIFEST).write_bytes(raw)
    sig.write_text(kept)
    (folder / VALUES).write_text(written)
    (folder / SOURCE).write_text(source(version))  # the release's own chart, as tagged
    return approval


def resigned(folder: Path) -> None:
    """After someone signs an environment's release: its values' hash of the signatures, so
    their signature is an upgrade, which records it."""
    _environment(folder)
    (folder / VALUES).write_text(values(image_of(folder), (folder / SIGNATURES).read_text()))


def consistent(folder: Path) -> list[str]:
    """What's wrong with an environment's folder as `a5s release promote` and `a5s release sign`
    leave it: nothing, if its values name the hash of the signatures it holds, and its chart is
    the release's own, at its tag and nowhere else."""
    _environment(folder)
    raw = (folder / MANIFEST).read_bytes()
    problems = []
    signed = (folder / SIGNATURES).read_text()
    if (folder / VALUES).read_text() != values(image_of(folder), signed):
        problems.append(f"{VALUES} isn't what its signatures make: run `a5s release sign "
                        f"--environment {folder}`, or promote it again")
    try:
        approved = releases.approval_in(raw, signed)
    except (ValueError, KeyError):
        approved = None
    if approved is None or approved.image != image_of(folder):  # the image it runs, signed
        problems.append(f"its signatures approve it as another image than {VALUES} runs: "
                        "promote it again, and have it signed again")
    helm = (yaml.safe_load((folder / HELMRELEASE).read_text()) or {}).get("spec") or {} if (
        folder / HELMRELEASE).is_file() else {}
    if helm.get("values") or helm.get("postRenderers"):  # which Flux merges over the release's
        problems.append(f"{HELMRELEASE} sets values or post-renderers of its own, which could "
                        f"run another image than its release: give the chart its values in "
                        "values.yaml, and its release's in release-values.yaml alone")
    own = yaml.safe_load((folder / "values.yaml").read_text()) or {} if (
        folder / "values.yaml").is_file() else {}
    if ((own.get("models") or {}).get("configMap")):  # which the manifest people sign hasn't
        problems.append("values.yaml approves models with a ConfigMap of its own, which the "
                        "release its approvers sign doesn't hold: build the approved models "
                        "into the image, in config/models.yaml, to deploy it from git")
    version = yaml.safe_load(raw)["version"]
    tagged = folder / SOURCE
    if not tagged.is_file() or tagged.read_text() != source(version):
        problems.append(f"{SOURCE} isn't the release's own tag, v{version}, as `a5s release "
                        "promote` writes it")
    if ((yaml.safe_load((folder / REPOSITORY).read_text()) or {}).get("spec") or {}).get("ref"):
        problems.append(f"{REPOSITORY} names a ref of its own, where the chart is the release's, "
                        f"at the tag {SOURCE} gives it")
    return problems


def _contents(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def alongside(folder: Path, before: Path) -> list[str]:
    """What a pull request that deploys a release changes besides it in the environment's
    folder, `before` as the branch it merges into has it: it may change nothing, since the
    release deploys by its signatures alone, while how the environment runs is for its code
    owners to review, in a pull request of its own. Its first release comes with the rest,
    which they review."""
    now, then = _contents(folder), _contents(before)
    if not ran(before) or all(now.get(f) == then.get(f) for f in RELEASE):
        return []
    others = sorted(f for f in now.keys() | then.keys()
                    if f not in RELEASE and now.get(f) != then.get(f))
    return [(f"a pull request that deploys a release changes nothing else in its environment, "
             f"and this one changes {', '.join(others)} too: make that change in a pull request "
             "of its own, for the environment's code owners to review")] if others else []
