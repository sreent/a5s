# Deploying a5s from git, with Flux

A signed release deploys itself. What each environment runs is a folder in git: the release, the signatures over it of the people its changes need, its image by digest, and its chart, from the release's own tag. A change to the folder goes in by pull request, and merges itself once its signatures meet what the release needs. [Flux](https://fluxcd.io) deploys what's merged, and the chart's job records the signatures, which the core checks again before it opens a run. Nobody runs `helm`, and rolling back is reverting the merge.

People still sign with their own keys, as before (`a5s release sign`): a sign-in to a page would put the identity provider's word in place of theirs, and a release's approval is the one thing in a5s that mustn't rest on the team that runs it.

## What's here

- [`flux/a5s.yaml`](flux/a5s.yaml): what a cluster's Flux reads, applied once: the repository that holds the environments, read with a deploy key, and the environment that cluster runs.
- [`environments/example`](environments/example): an environment to copy. Its `values.yaml` is its own values for the chart, everything but the release; `helmrelease.yaml` installs the chart with them and then the release's; `source.yaml` is the repository the chart comes from.
- [`verify.sh`](verify.sh): the check on a pull request that changes an environment, below.

A release's own files, which `a5s release promote` and `a5s release sign` write in an environment's folder:

| File | What it holds |
| --- | --- |
| `release.yaml` | The release's manifest, as its image prints it for the environment (`a5s release show --environment`) |
| `release.sig` | The signatures over it so far, each person's, made with their own key |
| `release-values.yaml` | Its image by digest, the approval the chart's job records, and the signatures' hash, so a signature added is an upgrade, whose job records it |
| `release-source.yaml` | The release's tag, at which `source.yaml`'s repository gives its chart |

The folder's other files say how the environment runs, and change by their own pull requests, which the team's leads review as code owners. A release needs no such review: its signatures are its review.

## Set up an environment, once

1. Copy `environments/example` to `environments/<name>`, and set its `values.yaml` as the chart's [values](../helm/a5s/values.yaml) say, and the repository in `source.yaml`.
2. On the cluster, install Flux, give it a deploy key that only reads the repository, and apply [`flux/a5s.yaml`](flux/a5s.yaml), naming the environment's folder. On AKS, Flux is the cluster's own GitOps extension.
3. Protect the branch Flux reads: changes only by pull request, with nobody bypassing that, the check below required, and code owners' review required. Give code owners to everything in the environments, the check and its workflow, but not to a release's own files, so a pull request that deploys a release merges itself once the check passes. On GitHub, that's a CODEOWNERS file such as this one, a ruleset, and auto-merge:

   ```
   /deploy/gitops/ @OWNER/a5s-leads
   /.github/workflows/promote.yml @OWNER/a5s-leads
   /deploy/gitops/environments/*/release.yaml
   /deploy/gitops/environments/*/release.sig
   /deploy/gitops/environments/*/release-values.yaml
   /deploy/gitops/environments/*/release-source.yaml
   ```

   On Forgejo, it's branch protection with the leads' approval for those files, and "merge when checks succeed" [TBC: how Forgejo requires approval for some files alone, at the first deployment].

## Deploy a release

1. The release workflow builds its image and publishes it, by its digest. A deployment with its own image, built on the release's, builds that too.
2. Someone from the team that runs a5s promotes it, on a branch, and opens the pull request. The release is what its image says it is as the environment deploys it, with its own scenario:

   ```sh
   env=deploy/gitops/environments/production image=ghcr.io/OWNER/a5s@sha256:...
   docker run --rm -v "$PWD/$env:/env:ro" "$image" release show --environment /env > release.yaml
   a5s release promote --environment "$env" --manifest release.yaml --image "$image"
   ```

   It says what the release needs, weighed against the one the environment runs, such as the release approver and assurance for a change to the core.
3. Each person it needs reviews it and signs it there, with their own key, and pushes:

   ```sh
   a5s release sign --as <them> --key <their key> --environment deploy/gitops/environments/production
   ```

4. The check on the pull request passes once the signatures meet what the release needs, weighed against the release the environment runs now. They're judged as the environment runs that release: by its image, with its directory, and with the environment's values as they are now. So a release that changes the directory can't approve itself with people it adds, and the pull request can't choose who judges it. The core judges it the same way when its job records the signatures, from who each release records may sign the next, so going around git with `helm upgrade` approves nothing more. The check also refuses a pull request that deploys a release and changes anything else in the environment, and an image that doesn't hold exactly the release's manifest.
5. The pull request merges itself. Flux deploys it, the chart's job records the signatures, and the core opens runs again once they check out.

To roll back, revert the merge: Flux deploys the release before, whose approval the core has already recorded.

## The check

[`verify.sh`](verify.sh) is the check, and [`.github/workflows/promote.yml`](../../.github/workflows/promote.yml) runs it on GitHub Actions. Forgejo Actions runs the same workflow, signing in to its own registry in place of ghcr.io; GitLab or any other CI runs the script, which needs only Docker and git, since `a5s release verify` comes from the images. Because it runs the `a5s release verify` of the release the environment runs now, it passes only arguments that earlier releases accept.

A pull request that changes an environment's other files but not its release passes the check while the release is still what its image holds as the environment deploys it. It merges once its code owners approve.
