# a5s on Azure

**Status:** Written for review, and not yet applied: it waits for a subscription. CI checks it with `terraform fmt` and `terraform validate` on every push.

Terraform for a5s's test environment on Azure, the first of the three clouds. A person applies it, after reviewing its plan. GitHub Actions then deploys each release's image to it, signing in with its own OpenID Connect token, so no cloud key is stored anywhere.

## What it makes

| Part | On Azure | As in compose |
| --- | --- | --- |
| The gateway, the channels, the scheduler, the ledger's copier, the worker | Container Apps, one replica each, in an environment in its own subnet. Only the channels take traffic from the internet; the gateway and the worker take it only from inside the environment | `gateway`, `channels`, `scheduler`, `anchor`, `worker` |
| Setting up the schema and applying the signed settings | A Container Apps job, run before each new image takes over | `setup` |
| Postgres | A Flexible Server, PostgreSQL 16, in its own subnet, which nothing outside the network reaches, with a database `a5s`. Each part connects as its own role, as the setup job makes them | `postgres` |
| Secrets | Key Vault, with Entra ID's roles. Each part has its own identity, which reads only its own secrets | Environment variables |
| The ledger's locked copies | Blob Storage with version-level immutability: the copier locks each copy for `anchor_retain_days`, and nobody, its own identity included, can shorten or delete it | `A5S_ANCHOR_STORE` |
| Teams | An Azure Bot for each agent, single-tenant, in the test tenant, sending to the channels | The fake Bot Framework |
| Deploys | An identity GitHub Actions signs in as, from this repository's `azure-test` environment alone, which may change the apps and the job and nothing else | The release workflow |
| Spending | A monthly budget, telling `budget_emails` at 80% and 100% | |

## Before the first apply

1. **A subscription for test**, and someone who may make role assignments in it, such as its owner.
2. **A storage account for Terraform's state**, made by hand, which only the people who apply this may read, since the state holds the passwords Terraform makes. Copy `backend.hcl.example` to `backend.hcl` and fill it in.
3. **People's sign-in.** In the Entra ID tenant people sign in with, register a single-page application for a5s's pages, with these redirect addresses on the channels' address, which the first plan shows as `channels_url`: `/chat/`, `/approve/`, `/decide/`, `/grade/` and `/settings/`. Its client id is `webchat_client_id` and `oidc_audience`, and the directory names people by their Entra ID object id, such as `entra:<oid>`.
4. **Teams, when the test tenant is ready.** In it, register an application for each agent's bot, single-tenant, with a client secret, and give its id in `teams_bots`.
5. Copy `test.tfvars.example` to `test.tfvars`, and fill it in. The image is a release's, by its digest.

## Apply

```sh
terraform init -backend-config=backend.hcl
terraform plan -var-file=test.tfvars -out plan
terraform apply plan
```

Role assignments take a few minutes to reach Key Vault, so the first apply may stop when an app can't read its secrets yet: apply again.

Then set the secrets Terraform doesn't make, in Key Vault, from a file or the portal, never pasted into a chat: `deepseek-api-key` and `qwen-api-key`, each bot's `teams-secret-<agent>`, and `registry-password` if the image's package on ghcr.io is private (set `registry_username` too). Run the setup job once (`az containerapp job start -g <resource group> -n caj-<name>-setup`), and restart the apps.

## Deploys

In the repository's settings, make an environment called `azure-test`, with the variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` and `A5S_NAME` from Terraform's outputs. Then run the `deploy-azure` workflow with a release's image digest. It runs the setup job with the new image, and only once that succeeds moves each app to it.

## What it costs

Roughly 60 to 150 a month in the subscription's currency for test, before what the models cost. Most of it goes on the five apps, each always running one replica, and on Postgres's smallest burstable size. Check Azure's pricing calculator for your region before applying.

## Still to decide, or to check on the first apply

- **The worker shares the apps' environment.** Container Apps has no network policy for each app, so unlike compose, the worker could reach the channels' and the gateway's addresses inside the environment, and the internet. It holds no secrets and no database password. For production: the worker in an environment and subnet of its own, whose network security group lets it reach only the gateway, which needs the core's environment to be internal, with Application Gateway in front of the channels.
- **Key Vault and the ledger's storage take requests from the internet**, with Entra ID's roles alone, so the person applying, and the deploys, reach them. For production: private endpoints, and applying and deploying from inside the network.
- **Azure's Postgres has no superuser.** Its administrator may make roles, so a5s's migrations take the parts' roles as they make them, and a5s's own suite runs every migration as such an administrator. The first setup on Azure is still the real test.
- **The bots' tenant.** The Azure Bot resources are in the subscription's tenant, and the bots' applications in the test Microsoft 365 tenant. If Azure won't take a single-tenant application from another tenant, register the bots in the subscription's tenant instead.
- **One replica of each part**, on the environment's own address, with no domain of the organisation's own. For production: a custom domain with its certificate, and more replicas of the gateway and the channels.
- **The providers' versions.** Commit `.terraform.lock.hcl` from the first `terraform init`, so every later init gets the same ones.
