# a5s on Kubernetes

**Status:** Built, and tested on a cluster of its own in CI on every push ([`test.sh`](test.sh)). Not yet run in a cloud: that waits for an account.

One Helm chart runs a5s on any Kubernetes cluster: each cloud's managed Kubernetes, such as AKS, GKE or EKS, or the organisation's own, even on a network with no way out. It runs the same parts as [`compose.yaml`](../compose.yaml), from the same image, and its network policies keep them apart as compose's networks do.

## What it runs

| Part | As | Reaches |
| --- | --- | --- |
| The gateway, in the trusted core | A Deployment and a Service, inside the cluster only | Postgres, and outside: the models, the identity provider, the chats |
| The channels, where people and their chats reach a5s | A Deployment and a Service, and the Ingress, if it's on | Postgres, and outside: the identity provider and the chats |
| The scheduler | A Deployment | Postgres, the gateway and the worker |
| The ledger's copier | A Deployment | Postgres, and the locked storage outside |
| The worker, which holds no secrets | A Deployment and a Service | The gateway alone |
| Setting up the schema and applying the signed settings | A job before each install or upgrade | Postgres |
| Recording a release's approval | A job after each install or upgrade, once a ConfigMap holds the signatures | Postgres |

Each part runs as its own service account, which can't reach Kubernetes' own API, as a5s's own user, with a filesystem it can't write to but `/tmp`. Only the gateway and the worker take traffic from other parts, and only the channels take it from outside. Network policies need a network plugin that enforces them, such as Calico, Cilium, or the one in k3s.

## Before installing

- **Postgres 16 or later**, such as the cloud's managed one, which the parts reach. Its administrator needn't be a superuser. Each pod that reaches it keeps up to 10 connections open (`A5S_DB_POOL_SIZE`), and the gateway one more for each model call in flight, so it must allow that many for every replica, which a small managed tier may not.
- **A Secret** in the release's namespace, named as `secret` says (`a5s` unless you change it), made by hand, with External Secrets, or with the cloud's secrets store driver. Each part reads only its own keys:
  - `database-admin-url`, for the jobs;
  - `database-<part>-url` and `database-<part>-password`, for `gateway`, `channels`, `scheduler` and `anchor`;
  - `service-token` and `seal-keys`;
  - and as the deployment needs them: `deepseek-api-key`, `qwen-api-key`, `teams-secret-<agent>`, `matrix-as-token` and `matrix-hs-token`.
- **Locked storage** for the ledger's copies, given as `anchor.store`, and the copier's right to write there, through the cloud's workload identity, as an annotation on its service account (`serviceAccounts.annotations.anchor`), and on AKS a label on its pods too (`podLabels.anchor`). [The first day](../../docs/first-day.md) does it on Azure.
- **Where Postgres is**, for the network policies: `networkPolicies.database`, by its pods' labels or its addresses.

## Install

```sh
helm install a5s deploy/helm/a5s -n a5s -f my-values.yaml
```

`image.digest` names a release's image, by its digest. The core then opens no run until this deployment's people approve the release, as `helm` says once it's installed: each person its changes need signs the release's manifest with their own key (`a5s release sign`), and a ConfigMap with `release.yaml` and `release.sig`, named in `release.approval`, records their signatures at the next `helm upgrade`.

## Test

[`test.sh`](test.sh) installs the chart on k3s in Docker, which enforces network policies, with Postgres beside it, and checks that the setup job runs first, that the core waits for the release's approval and runs once a job records it, that the scheduler reaches the gateway, and that the worker reaches the gateway alone, never the database, the channels or the internet. CI runs it on every push, after `helm lint`. Every image it starts is pinned by its digest.
