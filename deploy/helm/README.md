# a5s on Kubernetes

**Status:** Built, and tested on a cluster of its own in CI on every push ([`test.sh`](test.sh)). Not yet run in a cloud: that waits for an account.

One Helm chart runs a5s on any Kubernetes cluster: each cloud's managed Kubernetes, such as AKS, GKE or EKS, or the organisation's own, even on a network with no way out. It runs the same parts as [`compose.yaml`](../compose.yaml), from the same image, and its network policies keep them apart as compose's networks do.

## What it runs

| Part | As | Reaches |
| --- | --- | --- |
| The gateway, in the trusted core | A Deployment and a Service, inside the cluster only | Postgres, and outside: the models, the identity provider, the chats |
| The channels, where people and their chats reach a5s | A Deployment and a Service, and the Ingress, if it's on | Postgres, and outside: the identity provider and the chats |
| The scheduler | A Deployment | Postgres, the gateway and each pool of workers |
| The ledger's copier | A Deployment | Postgres, and the locked storage outside |
| The workers, which hold no secrets, in pools: one for each agent `workers.pools` names, and the shared pool for every other | A Deployment and a Service for each pool | The gateway alone |
| Setting up the schema and applying the signed settings | A job before each install or upgrade | Postgres |
| Recording a release's approval | A job after each install or upgrade, once a ConfigMap holds the signatures | Postgres |
| The sandbox, where the studio tries the agents people are making, in a release of its own | A Deployment of one pod and a Service, inside the cluster only | Its own database server alone, and outside only for the approved models, if `sandbox.realModels` lets it |

Each part runs as its own service account, which can't reach Kubernetes' own API, as a5s's own user, with a filesystem it can't write to but `/tmp`. Only the gateway and the workers take traffic from other parts, and only the channels take it from outside. Network policies need a network plugin that enforces them, such as Calico, Cilium, or the one in k3s.

## Before installing

- **Postgres 16 or later**, such as the cloud's managed one, which the parts reach. Its administrator needn't be a superuser. Each pod that reaches it keeps up to 10 connections open (`A5S_DB_POOL_SIZE`), and the gateway one more for each model call in flight, so it must allow that many for every replica, which a small managed tier may not.
- **A Secret** in the release's namespace, named as `secret` says (`a5s` unless you change it), made by hand, with External Secrets, or with the cloud's secrets store driver. Each part reads only its own keys:
  - `database-admin-url`, for the jobs;
  - `database-<part>-url` and `database-<part>-password`, for `gateway`, `channels`, `scheduler` and `anchor`;
  - `service-token` and `seal-keys`;
  - and as the deployment needs them: `deepseek-api-key`, `qwen-api-key`, `teams-secret-<agent>`, `matrix-as-token`, `matrix-hs-token`, and, for a store with S3's object lock that takes keys, `anchor-s3-access-key-id` and `anchor-s3-secret-access-key`.
- **Locked storage** for the ledger's copies, given as `anchor.store`, and the copier's right to write there: in a cloud, through its workload identity, as an annotation on its service account (`serviceAccounts.annotations.anchor`), and on AKS a label on its pods too (`podLabels.anchor`); on premises, a store with S3's object lock, such as MinIO, at `anchor.s3Endpoint`, with its keys in the Secret. [The first day](../../docs/first-day.md#4-the-cluster-postgres-and-locked-storage) gives each cloud's side by side.
- **How people sign in**, if through an identity provider: `people.oidcIssuer`, and `people.oidcMfa`, how that provider shows a second factor, such as `amr:mfa` or `acr:<level>`, or `none`. The chart assumes no provider, so it won't install with an issuer and no `oidcMfa`. [The first day](../../docs/first-day.md#2-peoples-sign-in) gives each provider's.
- **Where Postgres is**, for the network policies: `networkPolicies.database`, by its pods' labels or its addresses.
- **Publishing drafts from the studio as pull requests on GitHub**, if you want a5s to open them as their authors: a GitHub App's client id and the repository, as `publishing.githubClientId` and `publishing.repo`. The App has the device flow on, and Contents and Pull requests to read and write, on that repository alone; a5s holds no secret for it. Without it, authors open their pull requests themselves, on any git host, with what the studio gives them ([publishing](../../docs/studio.md#publishing)).
- **Where traces and operators' figures go**, if anywhere: `telemetry.endpoint`, an OpenTelemetry collector reached over HTTP, such as one that passes them on to Prometheus or Azure Monitor. A collector in the cluster also needs `networkPolicies.telemetry`, by its pods' and namespace's labels. Neither carries what anyone said, nor names a person or a record.

## Worker pools

Each agent `workers.pools` names runs in a pool of its own, `a5s-worker-<agent>`: a Deployment with its own replicas and resources, which the scheduler gives slots of their own, the most of the agent's runs it works on there at once. So a burst of one agent's work, such as the watcher's reports, never slows another's chats, and a fault in one pool's process reaches only its agent's runs in flight. Every other agent runs in the shared pool, `a5s-worker`. Each pool refuses any other agent's runs, so a run sent to the wrong one fails, and says so. No pool reaches another. A question one agent asks another, with `ask_agent`, is answered in the asker's pool, as part of the run that asked, so no question waits on another pool's slots.

```yaml
workers:
  pools:
    assistant: {replicas: 2, slots: 8}
    watcher: {}                        # one replica, a5s's default slots, resources.worker
    desk-assistant: {resources: {limits: {memory: 2Gi}}}
```

By default, the pilot's two agents, the assistant and the watcher, each have one. Each pool keeps one of its slots for people's messages, which work that falls due, such as a task's slices and reports, never takes, so a task at work never holds up its owner's chat; a pool of one slot has none to keep. On the containers of `deploy/compose.yaml`, two agents have pools of their own, the sample's unless `A5S_POOL_ASSISTANT` and `A5S_POOL_WATCHER` name others, such as `mdg-assistant` and `mdg-watcher` for master data, and `A5S_WORKER_SLOTS` gives each its slots, such as `assistant=8`. Another scenario names its own agents, and drops the pilot's, which Helm keeps unless they're set to null: `workers.pools: {assistant: null, watcher: null, desk-assistant: {}}`. A new agent runs in the shared pool from its first release, with no change here: giving it a pool of its own is the platform team's change to the chart, as any other part's resources are. The pools are for load and the reach of a fault, not for keeping people's data apart: every agent's runs go through the core's checks whichever pool runs them, and a pool runs many people's runs.

A pool's pods stay up whether there's work or not: nothing scales them to zero. A worker starts in about two seconds, and builds each run's agent afresh in milliseconds. Nothing of an agent lives in a worker between runs, since its conversations, notes and tasks are the core's. On an upgrade, a pool's pods are replaced one at a time. A new one is ready before an old one stops, and the old one finishes the runs it has in flight first, for up to `timeouts.workerWait`. The core and the channels app are replaced the same way, so neither is away on an upgrade, however long the new image takes to pull: the old core finishes the requests it has in flight, a model call included, for up to `timeouts.provider`. Only the scheduler and the copier are replaced the other way, the old one stopped first, since two of either must never run at once, and nothing waits on either. Asked to stop, the scheduler takes no more work and finishes the runs it has in flight first, for up to `timeouts.workerWait`, so none loses its answer, and messages that arrive meanwhile wait in the database, where the channels app puts them, for the next one. When a part restarts on its own, as after a crash, what the others send it meanwhile waits for it, for up to a minute, so a run in flight goes on once it's back.

## The sandbox

The sandbox ([the studio's plan](../../docs/studio.md#the-sandbox)) is where the studio tries the agents people are making: every part of a5s in one process, on the scenario's made-up records, with a stand-in model, run as a second release of this chart, `mode: sandbox`, from the same image, in a namespace of its own, with a database server of its own. It runs no jobs: it sets up its database when it starts, and signs its settings with keys it makes for the scenario's made-up people and keeps in memory alone. It holds none of a5s's keys, and only a5s's channels reach it, by a token they share. It runs one pod, the old one stopped first, since two would each sign its settings with keys of their own.

```sh
kubectl create namespace a5s-sandbox
kubectl -n a5s-sandbox create secret generic a5s \
  --from-literal=sandbox-database-url=postgresql://a5s:<password>@<its own server>:5432/postgres \
  --from-literal=sandbox-token=<the token a5s's Secret has as sandbox-token>
helm install a5s deploy/helm/a5s -n a5s-sandbox --set mode=sandbox --set image.digest=<a5s's> \
  --set sandbox.studio.namespace=a5s --set networkPolicies.database.cidrs={<its server's address>/32}
```

Then a5s's own release reaches it, with the same token as `sandbox-token` in its Secret:

```yaml
sandbox:
  url: http://a5s-sandbox.a5s-sandbox:8710
  namespace: a5s-sandbox
```

Its database server must be its own, not a5s's, even another database on the same server: a5s's parts' roles belong to a whole server. The sandbox refuses a database whose ledger holds a deployment's work, and a scenario whose records aren't all made up. It serves the scenario `scenario` names, as a5s's release should. With `sandbox.realModels`, it may try drafts on the approved models too, with their keys from its own Secret and reaching outside as `networkPolicies.outside` lets it, on the scenario's made-up records alone; without it, it has the stand-in alone and reaches nothing but its database.

## Install

```sh
helm install a5s deploy/helm/a5s -n a5s -f my-values.yaml
```

`image.digest` names a release's image, by its digest. The core then opens no run until this deployment's people approve the release, as `helm` says once it's installed: each person its changes need signs the release's manifest with their own key (`a5s release sign`), and a ConfigMap with `release.yaml` and `release.sig`, named in `release.approval`, records their signatures at the next `helm upgrade`.

## Test

[`test.sh`](test.sh) installs the chart on k3s in Docker, which enforces network policies, with Postgres beside it, and checks that the setup job runs first, that the core waits for the release's approval and runs once a job records it, that the scheduler reaches the gateway and each pool of workers, and that each pool reaches the gateway alone, never the database, the channels, another pool or the internet. It then installs the sandbox as a second release, in a namespace of its own with a Postgres of its own, and checks that a5s's channels try a draft there, that nothing else of a5s's reaches it, and that it reaches its own database alone, not a5s's, a5s's parts or the internet. CI runs it on every push, after `helm lint`. Every image it starts is pinned by its digest.
