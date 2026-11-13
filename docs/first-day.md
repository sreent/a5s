# The first day

**Status:** Draft, for stage 0 of the [pilot](pilot.md) · **Under:** [Pilot](pilot.md)

The first day puts a5s on the organisation's own Kubernetes cluster, wherever it runs, signed in through its identity provider and reached through a chat its people already use, and makes the four checks in [phase 1's first day](phase-1.md#progress), which only the real services can make: signing in, the chat, the cluster's own Postgres, locked storage and network policies, and what they send, kept as fixtures. It runs the sample scenario, with test accounts in place of the sample's made-up people, so no real data reaches a model, and DeepSeek takes only the sample's made-up records.

a5s assumes no cloud and no identity provider. Each step says what it needs, and which of the chart's values or the Secret's keys it fills, which come together in step 6; where providers differ, a table gives each one's settings side by side. [A worked example](#a-worked-example-azure-entra-id-and-teams) gives every command for one combination. Most of the week is waiting on accounts. Never paste a secret into a chat, an issue or a commit: each goes straight from the command that makes it into the Secret.

## Before the day

| What | Who | Why |
| --- | --- | --- |
| A Kubernetes cluster to install into, with a budget and an alert at 80% where it costs money: a cloud's managed Kubernetes, or the organisation's own | The platform owner | a5s runs from one Helm chart on any cluster ([the chart](../deploy/helm/README.md)) [TBC: the budget] |
| A test account in the identity provider for each sample person who'll sign in: at least Ana, an instance approver, and Ben | The identity provider's administrator | The directory finds each person by the id the provider sends |
| A chat for the test: a Matrix homeserver of the organisation's own, or Teams in a test tenant with leave to upload custom apps | The chat's administrator | People reach the agents where they already talk; the web chat needs nothing more |
| A host name, such as `a5s-test.example.org`, and a TLS certificate for it | The platform owner | People reach the pages, and a chat the bots, only over HTTPS |
| `DEEPSEEK_API_KEY` and `QWEN_API_KEY` in the repository's secrets (Settings, Secrets and variables, Actions) | The repository's administrator | The release runs each agent's regression suite against them, on the sample's made-up data only |

## 1. The release

Once `main` is green, tag it. The release workflow runs the suites, each agent's own against its model, builds the image, smoke-tests it, pushes it with its provenance signed, and publishes the release with the image's digest:

```sh
git tag v0.1.0 && git push origin v0.1.0
gh attestation verify oci://ghcr.io/sreent/a5s@sha256:<digest> --owner sreent  # from the release's notes
```

## 2. People's sign-in

One OpenID Connect client for the pages: a public client, since the core redeems the code with PKCE and no secret, whose redirect URIs are `https://<host>/` followed by `chat/`, `approve/`, `decide/`, `grade/`, `notebook/`, `settings/`, `officer/`, `studio/`, `tasks/`, `audit/` and `admin/`. The pages that approve, decide and grade ask for a fresh sign-in, and need its time in the token (`auth_time`). Approvals, decisions, grades and the officer's requests count only from a sign-in with a second factor, which the provider's own policy must ask for, and its token must show, so a5s can check it ([administration](administration.md)). For the settings to give groups roles, the token lists the groups too.

Fills: `people.oidcIssuer`, `people.webchatClientId` (the client's id), `people.oidcPersonClaim`, `people.oidcDirectoryPrefix` if the directory names people's accounts with one, `people.publicUrl: https://<host>`, `people.oidcMfa`, which the chart needs whenever an issuer is set, and `people.oidcGroupsClaim`.

| Provider | `oidcIssuer` | `oidcPersonClaim` | `oidcMfa`: how it shows a second factor | Groups |
| --- | --- | --- | --- | --- |
| Entra ID | `https://login.microsoftonline.com/<tenant>/v2.0` | `oid`, with `oidcDirectoryPrefix: entra` | `amr:mfa`, with a Conditional Access policy that requires multifactor authentication for the client, and `amr` and `auth_time` as optional claims | `groups`, once the client sends the groups assigned to it; past 200, Entra ID sends none, and a5s gives nothing it can't see |
| Okta | Its authorization server's, such as `https://<org>.okta.com/oauth2/default` | `sub`, or the claim the directory knows people by | `amr:mfa`, with a sign-on policy that asks for a second factor: Okta lists the methods used in `amr` | `groups`, with a groups claim on the authorization server |
| Keycloak | `https://<host>/realms/<realm>` | `preferred_username` | `acr:<level>`, with a step-up flow that gives the level what counts needs, which the pages then ask for (`acr_values`) | `groups`, with a group membership mapper |
| Google | `https://accounts.google.com` | `sub` or `email` | `none`: its tokens show no second factor, so require one in the Admin console, which a5s can't check, as `a5s status` says | None in its tokens: roles come from the directory alone |
| Any other | Its issuer | The claim that holds each person's id in the directory | Its claim and values, or `none` | The claim that lists them |

A deployment whose people chat in Teams signs them in with Entra ID too, since Teams names people by their Entra ID object id, which the directory must know.

## 3. The chat

| Chat | What | Fills |
| --- | --- | --- |
| Matrix | a5s's application service, registered on the organisation's homeserver, as [`deploy/matrix`](../deploy/matrix) registers it on the test stack's | `matrix.homeserver`, `matrix.serverName`, and the Secret's `matrix-as-token` and `matrix-hs-token` |
| Teams | A bot for each agent, the assistant and the watcher, so each talks to people as itself: a single-tenant bot registration in the tenant's Entra ID, with Teams turned on, whose messaging endpoint is `https://<host>/channels/teams/messages`, made a Teams app in the personal and group chat scopes, but not a team's, which a5s turns away | `teams.tenantId`, `teams.bots: [{agent: assistant, appId: <its id>}, {agent: watcher, appId: <its id>}]`, and the Secret's `teams-secret-assistant` and `teams-secret-watcher` |
| The web chat | Nothing more: the core serves it, at `https://<host>/chat/` | |

A bot's secret expires: put its date in the on-call calendar, since a bot whose secret has expired can't answer.

## 4. The cluster, Postgres and locked storage

**The cluster** needs a network plugin that enforces network policies, since they're how the workers reach the gateway alone, and an ingress for the channels. In a cloud, its workload identity lets the copier sign in to the locked storage with no key. Fills: `ingress: {enabled: true, className: <the ingress controller's class>, host: <host>, tlsSecret: <the certificate's Secret>}`.

**Postgres 16,** a managed one or one of the organisation's own, whose administrator needn't be a superuser, which is one of the checks. Each part keeps up to 10 connections open, so a server that takes 50 is too small. It takes connections from the cluster alone, over TLS. Fills: the Secret's `database-admin-url`, and `networkPolicies.database`: its pods' labels, if it's in the cluster, or its addresses.

**Locked storage for the ledger's copies:** a store where the copier locks each copy for a year, in compliance mode or the like, so nobody, its administrators included, can change or delete it before then. Fills: `anchor.store`, and the copier's right to write there.

| Where | Cluster | Postgres | `anchor.store` | The copier's right to write there |
| --- | --- | --- | --- | --- |
| AWS | EKS | RDS or Aurora for PostgreSQL | `s3://<bucket>/<prefix>`, a bucket made with Object Lock | `serviceAccounts.annotations.anchor: {eks.amazonaws.com/role-arn: <a role that may write the bucket>}` |
| Azure | AKS | Azure Database for PostgreSQL | `azure://<account>/<container>/<prefix>`, a container with version-level immutability | `serviceAccounts.annotations.anchor: {azure.workload.identity/client-id: <its identity>}`, and `podLabels.anchor: {azure.workload.identity/use: "true"}`, which AKS needs on the pod as well |
| Google Cloud | GKE | Cloud SQL for PostgreSQL | `gs://<bucket>/<prefix>`, a bucket with object retention | `serviceAccounts.annotations.anchor: {iam.gke.io/gcp-service-account: <a service account that may write the bucket>}` |
| On premises, or anywhere else | Any | Any Postgres 16 | `s3://<bucket>/<prefix>` on a store with S3's object lock, such as MinIO, with `anchor.s3Endpoint` and `anchor.s3Region` | The Secret's `anchor-s3-access-key-id` and `anchor-s3-secret-access-key` |

## 5. The deployment's own image: the sample, with the test accounts

The directory finds each person by the id the provider sends, so the sample's made-up ids give way to the test accounts'. That makes the sample's folder the deployment's own, which goes in an image built on the release's, so the release this deployment approves covers it ([agent model](agent-model.md)):

```sh
mkdir -p deployment/scenario/keys
cp scenarios/sample/data.yaml scenarios/sample/settings.* deployment/scenario/
cp scenarios/sample/keys/*.pub deployment/scenario/keys/  # public keys only, never a .key
# ...and in deployment/scenario/data.yaml, each test account's id in place of the made-up
# one, as the provider sends it, such as identities: ["entra:<its object id>"]
cat > deployment/Dockerfile <<'EOF'
FROM ghcr.io/sreent/a5s@sha256:<the release's digest>
COPY scenario /app/scenarios/test
ENV A5S_SCENARIO_DIR=/app/scenarios/test
EOF
docker build -t <the organisation's registry>/a5s:0.1.0-test deployment
docker push <the organisation's registry>/a5s:0.1.0-test
```

Fills: `image.repository: <the organisation's registry>/a5s` and `image.digest`, from the push's output.

The sample's settings stay signed by its made-up people, whose private keys are in the repository: fine for a test with made-up data, and the reason the team's own scenario, in stage 2, has its own approvers, each with a key of their own (`a5s keygen`).

## 6. Install

The Secret, each part's key apart, as [`deploy/helm/test.sh`](../deploy/helm/test.sh) makes it. The setup job gives each part's role its password:

```sh
random() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32; }
db="<the server's host>:5432/a5s?sslmode=require"
set -- --from-literal=database-admin-url="postgresql://<its administrator>:<password>@$db"
for part in gateway channels scheduler anchor; do
  password=$(random)
  set -- "$@" --from-literal=database-$part-url="postgresql://a5s_$part:$password@$db" \
    --from-literal=database-$part-password="$password"
done
kubectl create namespace a5s
kubectl -n a5s create secret generic a5s "$@" \
  --from-literal=service-token="$(random)" --from-literal=seal-keys="$(random)" \
  --from-literal=deepseek-api-key="<for the sample's made-up data only>"
  # and the chat's keys, from step 3, and the store's, from step 4, if it takes keys
helm install a5s deploy/helm/a5s -n a5s -f test-values.yaml  # the values from steps 2 to 5
```

The core opens no run until the release is approved here, as [the chart's README](../deploy/helm/README.md#install) says: `a5s release show` in the gateway prints it, the sample's release approvers sign it (`a5s release sign`), and a ConfigMap of their signatures, named in `release.approval`, is recorded at the next `helm upgrade`. Then `kubectl -n a5s exec deploy/a5s-gateway -- a5s release status` ends "Approved here.", and `a5s status` reports.

## 7. The four checks

| Check | How | Passes when |
| --- | --- | --- |
| Signing in | As Ana's test account, open `https://<host>/chat/`, and say hello to the assistant. Then approve new settings: `a5s propose` asks her, in her chat | She's answered by name, the ledger names her, and the approval page asks her to sign in afresh, with her second factor, and is sealed and applied |
| The chat | In the chat, as Ana, write to each agent. Add the assistant to a group chat with Ben and mention it; in Teams, try it in a team's channel too | Each agent answers as itself; in the group, it knows who's there; a team's channel is turned away with a reason |
| The cluster | Read the setup job's log; let the copier run an hour, then try to delete a copy with the store's own tools; run the worker's reach check from [`deploy/helm/test.sh`](../deploy/helm/test.sh) against the cluster | The migrations ran as the server's administrator; the copy is there and its deletion is refused; the worker reaches the gateway and nothing else |
| What they sent | Save a token from the web chat, a message from the chat as it reached the channels, and an approval's answer | They're kept in the suite, with the test accounts' ids replaced by made-up ones and their signatures by the tests' keys, so CI checks the real shapes from then on |

What each check showed goes in [phase 1's progress](phase-1.md#progress) and [stage 0](pilot.md#stages), and what didn't work goes in the runbooks, before stage 1 starts.

## A worked example: Azure, Entra ID and Teams

Every command for one combination, run by the platform owner with the Azure CLI (`az`), `kubectl` and `helm`, with the test tenant's administrator for the app registrations. It fills the same values as the steps above. Another cloud or provider fills them its own way.

**People's sign-in** (step 2). The redirect URIs are a public client's ("Mobile and desktop applications"): Entra ID refuses PKCE with no secret for a single-page application's URIs (AADSTS9002327), and asks a web app's for a secret (AADSTS7000218).

```sh
host=a5s-test.example.org
tenant=$(az account show --query tenantId -o tsv)
az group create --name a5s-test --location uksouth  # [TBC: the region]
web=$(az ad app create --display-name "a5s" --sign-in-audience AzureADMyOrg \
  --public-client-redirect-uris https://$host/chat/ https://$host/approve/ https://$host/decide/ \
    https://$host/grade/ https://$host/notebook/ https://$host/settings/ https://$host/officer/ \
    https://$host/studio/ https://$host/tasks/ https://$host/audit/ https://$host/admin/ \
  --optional-claims '{"idToken": [{"name": "auth_time", "essential": false},
                                   {"name": "amr", "essential": false}]}' \
  --query appId -o tsv)
az ad app update --id $web --set groupMembershipClaims=ApplicationGroup  # if groups give roles
az ad group show --group "a5s billing owners" --query id -o tsv  # a group's id, for the settings
```

Fills: `people.oidcIssuer: https://login.microsoftonline.com/<tenant>/v2.0`, `people.webchatClientId: <web>`, `people.oidcPersonClaim: oid`, `people.oidcDirectoryPrefix: entra`, `people.publicUrl: https://<host>` and `people.oidcMfa: amr:mfa`, with a Conditional Access policy that requires multifactor authentication for the `a5s` app. Assign each group the settings name to the app's enterprise application; Privileged Identity Management can then make someone an auditor, say, for a fortnight, which a5s counts from their next sign-in.

**A bot for each agent** (step 3). For the assistant, and likewise the watcher:

```sh
app=$(az ad app create --display-name "a5s assistant" --sign-in-audience AzureADMyOrg \
  --query appId -o tsv)
az ad sp create --id "$app" > /dev/null
secret=$(az ad app credential reset --id "$app" --display-name a5s --years 1 --query password -o tsv)
az bot create --resource-group a5s-test --name a5s-assistant --app-type SingleTenant \
  --appid "$app" --tenant-id "$tenant" --endpoint https://$host/channels/teams/messages
az bot msteams create --resource-group a5s-test --name a5s-assistant
```

Keep `$secret` for the Secret's `teams-secret-assistant`. Then make each bot a Teams app in the [Developer Portal](https://dev.teams.microsoft.com), with the bot as its one feature, and publish it to the test tenant, or upload its package as a custom app.

**The cluster, Postgres and locked storage** (step 4):

```sh
az aks create --resource-group a5s-test --name a5s-test --node-count 2 \
  --enable-oidc-issuer --enable-workload-identity \
  --network-plugin azure --network-policy calico --enable-app-routing --generate-ssh-keys
az aks get-credentials --resource-group a5s-test --name a5s-test
issuer=$(az aks show --resource-group a5s-test --name a5s-test \
  --query oidcIssuerProfile.issuerUrl -o tsv)

admin=$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
az postgres flexible-server create --resource-group a5s-test --name a5s-test-db --version 16 \
  --tier Burstable --sku-name Standard_B2s --storage-size 32 \
  --admin-user a5sadmin --admin-password "$admin" --public-access None
az postgres flexible-server db create --resource-group a5s-test --server-name a5s-test-db \
  --database-name a5s
out=$(az network public-ip show --query ipAddress -o tsv --ids "$(az aks show \
  --resource-group a5s-test --name a5s-test \
  --query 'networkProfile.loadBalancerProfile.effectiveOutboundIPs[0].id' -o tsv)")
az postgres flexible-server firewall-rule create --resource-group a5s-test --name a5s-test-db \
  --rule-name cluster --start-ip-address "$out" --end-ip-address "$out"

account=a5stestledger  # [TBC: unique across Azure]
az storage account create --resource-group a5s-test --name $account --sku Standard_ZRS \
  --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false \
  --allow-shared-key-access false
az storage account blob-service-properties update --resource-group a5s-test \
  --account-name $account --enable-versioning true
az storage container-rm create --resource-group a5s-test --storage-account $account \
  --name ledger --enable-vlw true
az identity create --resource-group a5s-test --name a5s-anchor
copier=$(az identity show --resource-group a5s-test --name a5s-anchor --query clientId -o tsv)
az role assignment create --assignee "$copier" --role "Storage Blob Data Owner" \
  --scope "$(az storage account show --resource-group a5s-test --name $account \
    --query id -o tsv)/blobServices/default/containers/ledger"
az identity federated-credential create --resource-group a5s-test --identity-name a5s-anchor \
  --name a5s-anchor --issuer "$issuer" --subject system:serviceaccount:a5s:a5s-anchor \
  --audiences api://AzureADTokenExchange
```

The Burstable B2s server takes enough connections, where B1ms's 50 are too few. Here it takes connections only from the cluster's outbound address, over TLS, which the test's made-up data allows: a deployment with real data reaches it privately, through the cluster's network. The copier's identity has the container alone, as Storage Blob Data Owner, since locking a copy needs more than a contributor may do.

Fills: `ingress.className: webapprouting.kubernetes.azure.com`; the Secret's `database-admin-url`, `postgresql://a5sadmin:<admin>@a5s-test-db.postgres.database.azure.com:5432/a5s?sslmode=require`, and `networkPolicies.database.cidrs: [<the server's address>/32]`, from `getent hosts a5s-test-db.postgres.database.azure.com`; `anchor.store: azure://<account>/ledger/a5s-test`, `serviceAccounts.annotations.anchor: {azure.workload.identity/client-id: <copier>}` and `podLabels.anchor: {azure.workload.identity/use: "true"}`.

**The deployment's own image** (step 5), in a registry the cluster pulls from:

```sh
az ad user show --id ana@<test tenant>.onmicrosoft.com --query id -o tsv  # her object id
az acr create --resource-group a5s-test --name a5stest --sku Basic  # [TBC: unique]
az acr build --registry a5stest --image a5s:0.1.0-test deployment
az aks update --resource-group a5s-test --name a5s-test --attach-acr a5stest
```

Fills: `image.repository: a5stest.azurecr.io/a5s` and `image.digest`. In the check of the cluster, `az storage blob delete` tries to delete a copy, and is refused.
