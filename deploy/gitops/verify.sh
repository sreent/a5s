#!/bin/sh
# Whether each environment a change makes different is ready to deploy (deploy/gitops/README.md):
# the signatures over its release meet what the release needs, weighed against the release the
# environment runs now and judged as it runs it, by that release's image and with its values, so
# a release can't approve itself with people it adds, nor a change choose who judges it; a change
# that deploys a release changes nothing else in the environment; and the release's own image
# holds exactly its manifest. It needs only git and Docker, so any CI runs it: GitHub's,
# Forgejo's or another. It runs the `a5s release verify` of the release the environment runs
# now, so it asks only what earlier releases' take.
# Usage: sh deploy/gitops/verify.sh <base>, the branch the change merges into, such as origin/main
set -eu
base=$1

image_of() {  # REPOSITORY@DIGEST, from the release values `a5s release promote` writes
  repository=$(sed -n 's/^  repository: //p' "$1")
  digest=$(sed -n 's/^  digest: //p' "$1")
  [ -n "$repository" ] && [ -n "$digest" ] || { echo "$1 names no image" >&2; exit 1; }
  echo "$repository@$digest"
}

for env in $(git diff --name-only "$base"...HEAD -- deploy/gitops/environments | cut -d/ -f1-4 | sort -u); do
  if [ ! -f "$env/release.yaml" ]; then
    echo "$env runs no release yet"
    continue
  fi
  released=$(image_of "$env/release-values.yaml")
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
  docker run --rm -v "$PWD/$env:/env:ro" -v "$before:/before:ro" "$judge" \
    release verify --environment /env --before /before
  echo "$env: $released holds exactly that release, as the environment deploys it"
  docker run --rm -v "$PWD/$env:/env:ro" "$released" release show --environment /env \
    | cmp - "$env/release.yaml"
  rm -rf "$before"
done
