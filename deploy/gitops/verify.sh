#!/bin/sh
# Whether each environment a change makes different is ready to deploy (deploy/gitops/README.md):
# the signatures over its release meet what the release needs, weighed against the release the
# environment runs now and judged as it runs it, by that release's image and with its values, so
# a release can't approve itself with people it adds, nor a change choose who judges it; what
# they sign names the image it runs as, so a change can't swap it; an environment's first
# release is judged by the approvers kept outside every release, in approvers.yaml as the branch
# it merges into has it; a change that deploys a release changes nothing else in the
# environment; an environment that runs a release keeps running one; and the release's own image
# holds exactly its manifest. It needs only git and Docker, so any CI runs it: GitHub's,
# Forgejo's or another. It runs the `a5s release verify` of the release the environment runs
# now, so it asks only what earlier releases' take. Where the CI says which repository's release
# workflow attests its images (A5S_ATTESTED_BY, as owner/name), it checks that attestation too,
# with GitHub's command line.
# Usage: sh deploy/gitops/verify.sh <base>, the branch the change merges into, such as origin/main
set -eu
base=$1
here=deploy/gitops

image_of() {  # REPOSITORY@DIGEST, from the release values `a5s release promote` writes
  repository=$(sed -n 's/^  repository: //p' "$1")
  digest=$(sed -n 's/^  digest: //p' "$1")
  [ -n "$repository" ] && [ -n "$digest" ] || { echo "$1 names no image" >&2; exit 1; }
  echo "$repository@$digest"
}

# Each environment the change touches, by its folder, read as git writes its paths, unquoted: a
# folder's name is lower case letters, digits and hyphens, so none is split, or skipped
changed=$(git -c core.quotePath=false diff --name-only "$base"...HEAD -- "$here/environments" \
  | cut -d/ -f1-4 | sort -u)
roots=$(mktemp)  # the approvers kept outside every release, as the branch it merges into has them
if git cat-file -e "$base:$here/approvers.yaml" 2>/dev/null; then
  git cat-file blob "$base:$here/approvers.yaml" > "$roots"
  chmod a+r "$roots"
else
  rm -f "$roots"
  roots=
fi
echo "$changed" | while IFS= read -r env; do
  [ -n "$env" ] || continue
  name=${env#"$here/environments/"}
  case "$name" in
    ""|*[!a-z0-9-]*|-*) echo "$env: an environment's folder is named in lower case letters, digits and hyphens" >&2; exit 1 ;;
  esac
  if [ ! -f "$env/release.yaml" ]; then
    if git cat-file -e "$base:$env/release.yaml" 2>/dev/null; then
      echo "$env runs a release, and this change takes it away: an environment keeps running one, and stops by a release of its own" >&2
      exit 1
    fi
    echo "$env runs no release yet"
    continue
  fi
  released=$(image_of "$env/release-values.yaml")
  if [ -n "${A5S_ATTESTED_BY:-}" ]; then  # built by the release workflow, from the repository
    echo "$env: $released, as $A5S_ATTESTED_BY's release workflow built and attested it"
    gh attestation verify "oci://$released" --repo "$A5S_ATTESTED_BY" \
      --signer-workflow "$A5S_ATTESTED_BY/.github/workflows/release.yml"
  fi
  before=$(mktemp -d)  # the environment as it is on the base branch, if it's there
  git ls-tree -r --name-only "$base" -- "$env/" | while IFS= read -r file; do
    mkdir -p "$before/$(dirname "${file#"$env"/}")"
    git cat-file blob "$base:$file" > "$before/${file#"$env"/}"
  done
  chmod -R a+rX "$before"  # for the image's own user
  judge=$released  # the first release an environment runs is judged by its own image
  if [ -f "$before/release-values.yaml" ]; then
    judge=$(image_of "$before/release-values.yaml")
  fi
  echo "$env: its release, judged by $judge, which it runs now"
  if [ ! -f "$before/release.yaml" ] && [ -n "$roots" ]; then  # its first, by those kept outside
    docker run --rm -v "$PWD/$env:/env:ro" -v "$before:/before:ro" -v "$roots:/roots.yaml:ro" \
      "$judge" release verify --environment /env --before /before --roots /roots.yaml
  else
    docker run --rm -v "$PWD/$env:/env:ro" -v "$before:/before:ro" "$judge" \
      release verify --environment /env --before /before
  fi
  echo "$env: $released holds exactly that release, as the environment deploys it"
  docker run --rm -v "$PWD/$env:/env:ro" "$released" release show --environment /env \
    | cmp - "$env/release.yaml"
  rm -rf "$before"
done
[ -z "$roots" ] || rm -f "$roots"
