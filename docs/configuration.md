# Configuration

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md)

What a deployment sets for a5s, where each thing lives, who decides it, and how to check and see what a running part uses.

## Where each value lives

a5s keeps each value with whoever decides it, so the default can be the safe one, and nobody can loosen what isn't theirs to decide.

| Layer | Who decides | What's in it | Where |
| --- | --- | --- | --- |
| The deployment's configuration | The team that runs a5s | Addresses, the database, timeouts, workers, channels, sign-in, publishing: what differs between one deployment and another | `A5S_` environment variables, from compose or the chart. Every one is below |
| The signed settings | Part owners, instance approvers and the data protection officer, each for what's theirs | What agents may do and the rules for people's data: levels, limits, thresholds, classes of data, the roles groups give | Versions people sign and approve, which the ledger records ([administration](administration.md)) |
| An agent's definition | The agent's owner, through a release | Its model, tools, schedules, context and budgets | `agent.yaml` in the agent's folder, checked with bounds, released and signed |
| People's preferences | Each person | What an agent offers them to set, with it | Their own, in the chat |
| a5s's code | A release, which its approvers sign, assurance among them | The starting values nobody needs to change between deployments, and the rules that keep a5s safe | [Starting values](starting-values.md) lists each, with its owner |

Some rules stay out of every layer, whoever asks: level 2 comes only from the signed settings, agents speak only as their own bots, and SQL is only ever text in the code. A setting for one of those would be a way to turn it off.

## Checked as each part starts

Every setting a5s reads is in one list, [`a5s/config.py`](../src/a5s/config.py), with what it takes and its default, which is written there alone. The table below is made from it. Each part reads a setting only through that list, as it needs it, never as a module is imported.

Each part checks all of them as it starts. It won't start with any of these, and it lists every one it finds, not only the first:

- A value it can't use, such as `A5S_DB_POOL_SIZE=ten`. The message names the variable and what it takes, and never shows a secret's value.
- A setting missing beside another that needs it, such as Teams's tenant beside its app.
- An `A5S_` name that isn't a setting, such as a misspelling of `A5S_OIDC_MFA`. Ignored, it would do nothing, so a second factor nobody is asked for would go unnoticed. Where it looks like a setting, the message says which.
- A setting that has moved, such as to the signed settings. The message says where it went.

The command line, which serves nothing, warns of a name that isn't a setting rather than stopping. Names a5s uses for its tests (`A5S_TEST_`), and those compose and the deployment scripts read, are listed as not being settings.

## Seeing what a part runs with

- `a5s config` lists every setting, by its area. For each, it shows the value, whether the environment sets it or it's a5s's default, and what it sets. Secrets are masked, and so is a database address's password. Run it in a part's own container, such as `kubectl exec deploy/a5s-gateway -- a5s config`, to see exactly what that part has. `--set` shows only what's set, and `--json` gives the same to a script. It exits with an error, listing them, where a part would refuse to start, so it can check a deployment's configuration before it rolls out.
- Each part's first log line says what it starts with: every setting its environment sets, masked as above. Everything else is at a5s's default.
- The core's status, `a5s status` and its `/status`, says what the core runs with, in the same way.

The tests check that every `A5S_` name anywhere in the repository is a setting, or said not to be one, and that this page's table is the code's.

## Every setting

<!-- a5s config --markdown -->
### The core and its parts

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_ROOT` | none | a folder | The folder a5s's own files are in: its agents, config and scenarios |
| `A5S_SERVICE_TOKEN` | none, or `.a5s/service-token` under `A5S_ROOT` | a token | The token a5s's parts call the core with |
| `A5S_SEAL_KEYS` | none, or `.a5s/seal-key` under `A5S_ROOT` | keys, by commas | The core's own keys, sealing what people approve, decide and grade: the first seals, the others are ones it's moving from |
| `A5S_GATEWAY_URL` | `http://127.0.0.1:8700` | an http(s):// address | Where the other parts reach the core |
| `A5S_CHANNELS_URL` | `http://127.0.0.1:8703` | an http(s):// address | Where people's messages reach the core's channels |
| `A5S_PUBLIC_URL` | none | an http(s):// address | Where people reach the channels, for links, if not A5S_CHANNELS_URL |
| `A5S_TEAM` | `platform` | text | The directory's team that runs a5s: its approvals of a release count as an engineer's, never as the release approver's |
| `A5S_PROVIDER_TIMEOUT` | `180` | seconds, from 5 to 900 | Seconds the core waits for a model provider's answer |

### The database

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_DATABASE_URL` | `postgresql://a5s@127.0.0.1:54329/postgres` | a postgresql:// address | The part's database, as its own role |
| `A5S_DB_POOL_SIZE` | `10` | a whole number from 1 to 200 | Connections each part keeps open to its database |
| `A5S_DB_CONNECT_TIMEOUT` | `2` | a whole number of seconds from 1 to 60 | Seconds a part waits to connect to its database before failing |

### Workers

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_WORKER_URL` | none | an http(s):// address | The shared worker pool, for every agent without a pool of its own |
| `A5S_WORKER_URLS` | none | agent=address pairs, by commas | Each agent's own worker pool, by its name |
| `A5S_WORKER_SLOTS` | none | agent=number pairs, by commas | How many of an agent's runs the scheduler works on at once in its pool |
| `A5S_WORKER_AGENTS` | none | agents, by commas | In a worker: the agents its pool runs, if it's their own |
| `A5S_WORKER_POOLED` | none | agents, by commas | In the shared pool: the agents with pools of their own, which it refuses |
| `A5S_WORKER_TIMEOUT` | `240` | seconds, from 10 to 3,600 | Seconds a worker waits for the core, and for a model through it |
| `A5S_WORKER_WAIT` | `600` | seconds, from 10 to 7,200 | Seconds the scheduler waits for a worker to finish a run |

### Signing in

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_DEVELOPMENT` | `False` | true or false | Without an identity provider, take people's word for who they are: for development alone |
| `A5S_OIDC_ISSUER` | none | an http(s):// address | The identity provider people sign in with, exactly as its tokens name it, as Entra ID's v1 ends in a slash |
| `A5S_OIDC_AUDIENCE` | `a5s` | names, by commas | The audiences a5s takes tokens for |
| `A5S_OIDC_PERSON_CLAIM` | `preferred_username` | text | The claim that says who someone is, as the directory knows them |
| `A5S_OIDC_METADATA_URL` | none | an http(s):// address | Where the provider's metadata is, if not where the issuer says |
| `A5S_OIDC_DIRECTORY_PREFIX` | none | text | What to take off the person claim to find someone in the directory |
| `A5S_OIDC_MFA` | none | claim:value,value, such as amr:mfa | The second factor what counts needs a sign-in to show, as the claim and the values that show it |
| `A5S_OIDC_GROUPS_CLAIM` | `groups` | text | The claim sign-ins show groups in, for the roles the settings give them; set empty for none |
| `A5S_WEBCHAT_CLIENT_ID` | none | text | The web chat's client at the identity provider, a public one |

### Teams

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_TEAMS_APP_ID` | none | text | One bot's registration in Entra ID, for Teams |
| `A5S_TEAMS_APP_SECRET` | none | its secret | That bot's secret |
| `A5S_TEAMS_AGENT` | `assistant` | text | The agent that bot speaks for |
| `A5S_TEAMS_BOTS` | none | a JSON list | Several bots, one for each agent, instead: a JSON list of {agent, app_id, secret_env} |
| `A5S_TEAMS_TENANT_ID` | none | text | The organisation's tenant: messages from any other are refused |
| `A5S_TEAMS_SERVICE_HOSTS` | `smba.trafficmanager.net` | hosts, by commas | The hosts a5s sends Teams replies to, and no other |

### Matrix

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_MATRIX_HOMESERVER` | none | an http(s):// address | The organisation's Matrix homeserver, which turns Matrix on |
| `A5S_MATRIX_SERVER_NAME` | none | text | Its people's domain, as in @ana:<it> |
| `A5S_MATRIX_AS_TOKEN` | none | a token | A5s's token there, to speak as its bots |
| `A5S_MATRIX_HS_TOKEN` | none | a token | The homeserver's, which comes with every delivery |

### The ledger's locked copies

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_ANCHOR_STORE` | none | s3://, azure://, gs:// or file://, such as s3://bucket/a5s | Where the ledger's locked copies go |
| `A5S_ANCHOR_RETAIN_DAYS` | `365` | a whole number of days from 1 to 36,500 | Days each copy stays locked |

### The studio, its sandbox and publishing

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_SANDBOX_URL` | none | an http(s):// address | The sandbox, where the studio tries the agents people are making |
| `A5S_SANDBOX_TOKEN` | none | a token | The token the studio and the sandbox share |
| `A5S_SANDBOX_DATABASE_URL` | none | a postgresql:// address | In the sandbox: its own database, as its administrator |
| `A5S_SANDBOX_DIR` | none | a folder | In the sandbox: the folder it keeps people's tries in |
| `A5S_GITHUB_CLIENT_ID` | none | text | A5s's GitHub App, by its client id, a public thing, for publishing drafts as pull requests |
| `A5S_GITHUB_REPO` | none | owner/name | The agents' repository, as owner/name |
| `A5S_GITHUB_BASE` | `main` | text | The branch pull requests go to |
| `A5S_GITHUB_URL` | `https://github.com` | an http(s):// address | GitHub, or a GitHub Enterprise server |
| `A5S_GITHUB_API_URL` | `https://api.github.com` | an http(s):// address | Its API, such as https://<it>/api/v3 |

### What the data protection officer has agreed to

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_STUDIO_NAMES` | `False` | true or false | The studio's pages name whom each run acted for |
| `A5S_AUDIT_NAMES` | `False` | true or false | The auditors' page names whom agents acted for, and exports the ledger there |
| `A5S_FLAG_RUBBER_STAMPS` | `False` | true or false | The status names deciders whose approvals are graded wrong far more often than others' |

### The scenario

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_SCENARIO` | `a5s.sample:SampleScenario` | module:Class | The scenario a5s serves, as module:Class |
| `A5S_SCENARIO_DIR` | none | a folder | The scenario's folder, if not scenarios/sample |
| `A5S_AGENTS_DIR` | none | a folder | The agents' folders, if not agents |

### The command line

| Variable | Default | Takes | What it sets |
| --- | --- | --- | --- |
| `A5S_TOKEN` | none | a token | The token the identity provider gave the person using the command line, where a5s uses one |

### Families

| Variables | What they set |
| --- | --- |
| `A5S_DB_<PART>_PASSWORD` | Each part's database password, which setup gives its role |
| `A5S_TEAMS_SECRET_<AGENT>` | A bot's secret, where A5S_TEAMS_BOTS names it |
<!-- end of a5s config --markdown -->

The libraries a5s uses read some variables of their own: OpenTelemetry's `OTEL_EXPORTER_OTLP_ENDPOINT`, for where traces and figures go, and each cloud's own sign-in for the ledger's store, such as `AWS_REGION` or `AZURE_STORAGE_CONNECTION_STRING`. A model's key is in the variable `config/models.yaml` names for it, such as `DEEPSEEK_API_KEY`.
