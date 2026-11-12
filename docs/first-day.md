# The first day on Azure and Teams

**Status:** Draft, for stage 0 of the [pilot](pilot.md) · **Under:** [Pilot](pilot.md)

The first day puts a5s in a Microsoft 365 test tenant and an Azure subscription, and makes the four checks in [phase 1's first day](phase-1.md#progress), which only the real services can make: signing in with Entra ID, Teams, Azure's own Postgres, locked storage and network policies, and what they send, kept as fixtures. It runs the sample scenario, with test accounts in place of the sample's made-up people, so no real data reaches a model, and DeepSeek takes only the sample's made-up records.

Most of the week is waiting on accounts. The commands below are for the Azure CLI (`az`), `kubectl` and `helm`, run by the platform owner, with the test tenant's administrator for step 2. Each step says which of the chart's values or the Secret's keys it fills: they come together in step 5. Never paste a secret into a chat, an issue or a commit: each goes straight from the command that makes it into the Secret.

## Before the day

| What | Who | Why |
| --- | --- | --- |
| An Azure subscription in the test tenant, with a monthly budget and an alert at 80% (Cost Management, Budgets) | The platform owner | One directory for the bots, people's sign-in and the resources keeps the first day simple. [TBC: the budget] |
| Teams turned on in the test tenant, and leave to upload custom apps (Teams admin center, Setup policies) | The tenant's administrator | The agents' bots are custom apps |
| A test account for each sample person who'll sign in: at least Ana, an instance approver, and Ben | The tenant's administrator | Teams and Entra ID name people by their object id, which the directory must know |
| A host name, such as `a5s-test.example.org`, and a TLS certificate for it | The platform owner | Teams reaches the bots, and people the pages, only over HTTPS |
| `DEEPSEEK_API_KEY` and `QWEN_API_KEY` in the repository's secrets (Settings, Secrets and variables, Actions) | The repository's administrator | The release runs each agent's regression suite against them, on the sample's made-up data only |

## 1. The release

Once `main` is green, tag it. The release workflow runs the suites, each agent's own against its model, builds the image, smoke-tests it, pushes it with its provenance signed, and publishes the release with the image's digest:

```sh
git tag v0.1.0 && git push origin v0.1.0
gh attestation verify oci://ghcr.io/sreent/a5s@sha256:<digest> --owner sreent  # from the release's notes
```

## 2. The test tenant: people's sign-in, and a bot for each agent

**People's sign-in.** One app registration for the pages. Its redirect URIs are those of a public client ("Mobile and desktop applications"), since the core redeems the code with PKCE and no secret: Entra ID refuses that for a single-page application's URIs (AADSTS9002327) and asks a web app's for a secret (AADSTS7000218). The pages that approve, decide and grade ask for a fresh sign-in, and need its time in the token (`auth_time`), an optional claim:

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
```

Fills: `people.oidcIssuer: https://login.microsoftonline.com/<tenant>/v2.0`, `people.webchatClientId: <web>`, `people.oidcPersonClaim: oid`, `people.oidcDirectoryPrefix: entra` and `people.publicUrl: https://<host>`. `people.oidcMfa` stays `amr:mfa`, so approvals, decisions, grades and the officer's requests count only from a sign-in with a second factor. A Conditional Access policy that requires multifactor authentication for the `a5s` app makes every sign-in to it show one, which `amr` then holds as `mfa` ([administration](administration.md)).

**Roles from groups, if the deployment gives any.** For the settings to give groups roles, such as billing's owners or the auditors, the app registration sends the groups assigned to it, by their object ids, in `groups`: past 200, Entra ID sends none, and a5s gives nothing it can't see. Assign each group the settings name to the app's enterprise application, and name it in the settings by its object id ([administration](administration.md)):

```sh
az ad app update --id $web --set groupMembershipClaims=ApplicationGroup
az ad group show --group "a5s billing owners" --query id -o tsv  # its id, for the settings
```

`people.oidcGroupsClaim` stays `groups`. Privileged Identity Management can then make someone an auditor, say, for a fortnight: a5s counts it from their next sign-in.

**A bot for each agent,** the assistant and the watcher, so each talks to people as itself: a single-tenant app registration with a secret, and an Azure Bot whose messaging endpoint is the channels' Teams endpoint, with Teams turned on. For the assistant:

```sh
app=$(az ad app create --display-name "a5s assistant" --sign-in-audience AzureADMyOrg \
  --query appId -o tsv)
az ad sp create --id "$app" > /dev/null
secret=$(az ad app credential reset --id "$app" --display-name a5s --years 1 --query password -o tsv)
az bot create --resource-group a5s-test --name a5s-assistant --app-type SingleTenant \
  --appid "$app" --tenant-id "$tenant" --endpoint https://$host/channels/teams/messages
az bot msteams create --resource-group a5s-test --name a5s-assistant
```

Keep `$secret` for the Secret in step 5, and put its expiry in the on-call calendar: a bot whose secret has expired can't answer. Then make each bot a Teams app in the [Developer Portal](https://dev.teams.microsoft.com): a new app, with the bot as its one feature, by its app id, in the personal and group chat scopes but not a team's, which a5s turns away, and publish it to the test tenant, or download its package and upload it as a custom app.

Fills: `teams.tenantId: <tenant>`, `teams.bots: [{agent: assistant, appId: <app>}, {agent: watcher, appId: <its app>}]`, and the Secret's `teams-secret-assistant` and `teams-secret-watcher`.

## 3. Azure: the cluster, Postgres and locked storage

**The cluster,** with workload identity, so the copier signs in with no key, a network plugin that enforces network policies, and the application routing add-on for the ingress:

```sh
az aks create --resource-group a5s-test --name a5s-test --node-count 2 \
  --enable-oidc-issuer --enable-workload-identity \
  --network-plugin azure --network-policy calico --enable-app-routing --generate-ssh-keys
az aks get-credentials --resource-group a5s-test --name a5s-test
issuer=$(az aks show --resource-group a5s-test --name a5s-test \
  --query oidcIssuerProfile.issuerUrl -o tsv)
```

Fills: `ingress: {enabled: true, className: webapprouting.kubernetes.azure.com, host: <host>, tlsSecret: <the certificate's Secret>}`.

**Postgres 16,** whose administrator isn't a superuser, which is one of the checks. Each part keeps up to 10 connections open, so Burstable B1ms, with 50, is too small. Here it takes connections only from the cluster's address, over TLS, which the test's made-up data allows: a deployment with real data reaches it privately, through the cluster's network.

```sh
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
```

Fills: the Secret's `database-admin-url`, `postgresql://a5sadmin:<admin>@a5s-test-db.postgres.database.azure.com:5432/a5s?sslmode=require`, and `networkPolicies.database.cidrs: [<the server's address>/32]`, from `getent hosts a5s-test-db.postgres.database.azure.com`.

**Locked storage for the ledger's copies:** an account that takes no shared keys, with versioning, and a container with version-level immutability, where the copier locks each copy for a year. Its identity has the container alone, as Storage Blob Data Owner, since locking a copy needs more than a contributor may do, and trusts the copier's service account in the cluster:

```sh
account=a5stestledger  # [TBC: unique across Azure]
az storage account create --resource-group a5s-test --name $account --sku Standard_ZRS \
  --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false \
  --allow-shared-key-access false
az storage account blob-service-properties update --resource-group a5s-test \
  --account-name $account --enable-versioning true
az storage container-rm create --resource-group a5s-test --storage-account $account \
  --name ledger --enable-vlw true  # or, in the portal, the container's access policy
az identity create --resource-group a5s-test --name a5s-anchor
copier=$(az identity show --resource-group a5s-test --name a5s-anchor --query clientId -o tsv)
az role assignment create --assignee "$copier" --role "Storage Blob Data Owner" \
  --scope "$(az storage account show --resource-group a5s-test --name $account \
    --query id -o tsv)/blobServices/default/containers/ledger"
az identity federated-credential create --resource-group a5s-test --identity-name a5s-anchor \
  --name a5s-anchor --issuer "$issuer" --subject system:serviceaccount:a5s:a5s-anchor \
  --audiences api://AzureADTokenExchange
```

Fills: `anchor.store: azure://<account>/ledger/a5s-test`, `serviceAccounts.annotations.anchor: {azure.workload.identity/client-id: <copier>}` and `podLabels.anchor: {azure.workload.identity/use: "true"}`, which AKS needs on the pod as well.

## 4. The deployment's own image: the sample, with the test accounts

The directory finds each person by the object id Entra ID and Teams send, so the sample's made-up ids give way to the test accounts'. That makes the sample's folder the deployment's own, which goes in an image built on the release's, so the release this deployment approves covers it ([agent model](agent-model.md)):

```sh
mkdir -p deployment/scenario/keys
cp scenarios/sample/data.yaml scenarios/sample/settings.* deployment/scenario/
cp scenarios/sample/keys/*.pub deployment/scenario/keys/  # public keys only, never a .key
az ad user show --id ana@<test tenant>.onmicrosoft.com --query id -o tsv
# ...and in deployment/scenario/data.yaml, each test account's id in place of the
# made-up one: identities: ["entra:<its object id>"]
cat > deployment/Dockerfile <<'EOF'
FROM ghcr.io/sreent/a5s@sha256:<the release's digest>
COPY scenario /app/scenarios/test
ENV A5S_SCENARIO_DIR=/app/scenarios/test
EOF
az acr create --resource-group a5s-test --name a5stest --sku Basic  # [TBC: unique]
az acr build --registry a5stest --image a5s:0.1.0-test deployment
az aks update --resource-group a5s-test --name a5s-test --attach-acr a5stest
```

Fills: `image.repository: a5stest.azurecr.io/a5s` and `image.digest`, from the build's output.

The sample's settings stay signed by its made-up people, whose private keys are in the repository: fine for a test tenant with made-up data, and the reason the team's own scenario, in stage 2, has its own approvers, each with a key of their own (`a5s keygen`).

## 5. Install

The Secret, each part's key apart, as [`deploy/helm/test.sh`](../deploy/helm/test.sh) makes it. The setup job gives each part's role its password:

```sh
random() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32; }
db=a5s-test-db.postgres.database.azure.com:5432/a5s?sslmode=require
set -- --from-literal=database-admin-url="postgresql://a5sadmin:$admin@$db"
for part in gateway channels scheduler anchor; do
  password=$(random)
  set -- "$@" --from-literal=database-$part-url="postgresql://a5s_$part:$password@$db" \
    --from-literal=database-$part-password="$password"
done
kubectl create namespace a5s
kubectl -n a5s create secret generic a5s "$@" \
  --from-literal=service-token="$(random)" --from-literal=seal-keys="$(random)" \
  --from-literal=teams-secret-assistant="$secret" \
  --from-literal=teams-secret-watcher="<the watcher's>" \
  --from-literal=deepseek-api-key="<for the sample's made-up data only>"
helm install a5s deploy/helm/a5s -n a5s -f test-values.yaml  # the values from steps 2 to 4
```

The core opens no run until the release is approved here, as [the chart's README](../deploy/helm/README.md#install) says: `a5s release show` in the gateway prints it, the sample's release approvers sign it (`a5s release sign`), and a ConfigMap of their signatures, named in `release.approval`, is recorded at the next `helm upgrade`. Then `kubectl -n a5s exec deploy/a5s-gateway -- a5s release status` ends "Approved here.", and `a5s status` reports.

## 6. The four checks

| Check | How | Passes when |
| --- | --- | --- |
| Signing in with Entra ID | As Ana's test account, open `https://<host>/chat/`, and say hello to the assistant. Then approve new settings: `a5s propose` sends her a card | She's answered by name, the ledger names her, and the approval page asks her to sign in afresh, and is sealed and applied |
| Teams | In Teams, as Ana, write to each agent's app. Add the assistant to a group chat with Ben and mention it, then try it in a team's channel | Each agent answers as itself; in the group, it knows who's there by their object ids; the channel is turned away with a reason |
| Azure | Read the setup job's log; let the copier run an hour, then try to delete a copy (`az storage blob delete`); run the worker's reach check from [`deploy/helm/test.sh`](../deploy/helm/test.sh) against the cluster | The migrations ran as `a5sadmin`; the copy is there and its deletion is refused; the worker reaches the gateway and nothing else |
| What they sent | Save a token from the web chat, a Bot Framework activity with its token, and a card's answer | They're kept in the suite, with the test accounts' ids replaced by made-up ones and their signatures by the tests' keys, so CI checks the real shapes from then on |

What each check showed goes in [phase 1's progress](phase-1.md#progress) and [stage 0](pilot.md#stages), and what didn't work goes in the runbooks, before stage 1 starts.
