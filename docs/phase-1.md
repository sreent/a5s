# Phase 1

**Status:** Steps 1 and 2 under way, step 4 built ([progress](#progress)) · **Under:** [Architecture](architecture.md)

Phase 1 builds the smallest a5s that's useful: the trusted core, conversations, and two reference agents of a5s's own, at levels 0 and 1. They're proven against a5s's sample scenario, and used first by the team that builds a5s. In phase 1, agents read, report, draft and remind. None of them changes data. Which real scenario comes first is a separate decision [TBC].

## Decide first

Decided on 28 October 2026, except where marked:

| Decision | Decided |
| --- | --- |
| Clouds | Azure, Google Cloud and AWS, all three at once, each with managed Postgres. a5s's code is the same on each, and adapters cover what differs: identity, secrets, object-lock storage and model endpoints. |
| Hosting | Each cloud's own container service, such as Azure Container Apps, Cloud Run and Amazon ECS on Fargate, not Kubernetes. On the organisation's own premises, even on a network with no way out, the same image on any container host, with compose as the reference. Decided on 29 October 2026. |
| Identity providers | Entra ID, Google Cloud Identity and Okta, through OpenID Connect. People who use Teams also have an Entra ID identity, which the directory maps to the person. Any other provider that speaks OpenID Connect works the same way, such as Keycloak on the organisation's own network, and a directory that speaks only LDAP or SAML, such as Active Directory on its own, connects through a bridge such as Keycloak or Dex. Added on 29 October 2026. |
| Channel | Teams, for organisations on Microsoft 365. Teams needs the internet, so elsewhere, and on a network with no way out, people use a web chat the core serves, which takes sign-in from any provider, or Matrix, on the organisation's own homeserver, as well as the command line. Each deployment turns on the chats its people use, any number at once. Test and development use the web chat and Matrix. Decided on 29 October 2026. |
| Settings | One signed settings store with three ways to change it: files in git, approval cards in Teams, and a simple web app |
| Roles | Held by people, assigned in each organisation's directory, never by job title. a5s checks each role's rules in code, such as the release approver being outside the team that runs a5s. Who holds the platform owner and release approver roles is each deployment's to assign. |
| Models | Any provider with an OpenAI-compatible or Anthropic-compatible API. Development and tests use DeepSeek and Qwen, whose keys are in the environment, against the fake with synthetic data only. Real data goes only to models on the organisation's approved list, for the classes of data each is approved for, such as open-weight models it hosts in its own cloud or on its own premises, with vLLM, Ollama or llama.cpp. |
| Sample scenario | a5s's own fake of every contract interface, with synthetic data: a directory, settings, a records system and a document store. It's the test bench, locally and in CI. |

## Build, in order

Each step ends with something running and its tests passing.

1. **A walking skeleton,** running locally against the fake:
   - definitions in git, and instances in Postgres;
   - a scheduler for messages, schedules and obligations, with leases and suspension;
   - `create_deep_agent` runs, each on a thread that lasts one run;
   - every call goes from the agent to a gateway, which checks Cedar policy, denying by default and failing closed, and writes the ledger in the same transaction ([a call, step by step](architecture.md#a-call-step-by-step));
   - a model gateway that speaks both API styles, tested with DeepSeek and Qwen;
   - settings as signed files in git;
   - replies through the channel gateway, in Teams, Matrix and a web chat of a5s's own;
   - a switch that suspends an instance at its next call;
   - the same build deployed to Azure, Google Cloud and AWS from the start, through one set of infrastructure code with an adapter for each.
2. **A release pipeline:** pinned dependencies, the regression suite in CI, and protected branches, with an attested build and outside approval for the trusted core, deploying to all three clouds. Releases are [proportionate](architecture.md#independence).
3. **Context:** conversations in topics, structured summaries that code checks, profiles, case briefs from records, search over past turns, promises and reminders, and the context budget for each run ([context](architecture.md#context-and-memory)). Summaries keep facts by handle, so this step also prototypes [handles](architecture.md#provenance-who-said-what) and the exact matching of typed values.
4. **The two reference agents,** against the sample scenario:
   - the assistant, at level 1: one conversation with each person, drafts on request, promises and reminders, digests and chases;
   - the watcher, at level 0: it reads the sample scenario's records on a schedule and reports what changed or fell due to whoever owns it, which tests obligations, schedules and sweeps;
   - approval cards in Teams, so the people who approve these agents can do it where they already work.
5. **Running it properly, then production:** tokens for classified values, masked traces, budgets at the model gateway, the hourly ledger anchor with assurance, dashboards, objectives, runbooks and on-call, on all three clouds ([operations](architecture.md#operations)). Then the reference agents go to production, used first by the team that builds a5s.
6. **Parts and levels:** the sample scenario gets parts with owners, and the reference agents work within them, with live settings, a level for each part, case briefs from records, and checks on what each person may see. Tools return no outside content, since the extractor comes in phase 2. With this comes the settings web app, where owners review a whole version before they sign it.

## Progress

Step 1, the walking skeleton, runs locally against the sample scenario, with DeepSeek and Qwen as models:

| Built | Where |
| --- | --- |
| Definitions in git, with a hash of the folder in each release, and each tool's whole definition pinned, its risk flags included | [`agents/`](../agents/), [`definitions.py`](../src/a5s/definitions.py) |
| Instances, runs and the ledger in Postgres. Each ledger entry is written in the same transaction as its decision and chained by hash. The database refuses to change an entry, and verification shows where a rewritten one breaks the chain. | [`core/`](../src/a5s/core/) |
| Each part connects to Postgres as its own role, with only the rights its job needs, so a compromised service can't write the core's records. The core's tables belong to a role nobody logs in as, no role may change, delete or truncate the ledger, and the schema changes through numbered migrations. | [`migrations/`](../src/a5s/migrations/) |
| Cedar policy with a5s's base pack and a schema, denying by default and failing closed | [`core/policies/`](../src/a5s/core/policies/) |
| The gateway for tools, for models in both API styles, and for outgoing messages. Outgoing text, in messages and in tools' text such as drafts, keeps only words and the scenario's record links: no images, HTML or other links in any form. Providers get only known fields and the agent's own function tools, never their own web search, and every response must report the approved version. Workers hold only a run token, never a provider's key. | [`core/gateway.py`](../src/a5s/core/gateway.py) |
| The scheduler, which takes each message from the core's queue together with its conversation's lease, and renews the lease while it works. Every minute it also asks the core what falls due, and works on each obligation and schedule under a lease of its own. A message outlives a scheduler that stops, and waits while the core can't be reached. The scheduler has no port of its own. Runs expire, and a run that outlives its time is closed and its person told. Each fresh run reads the latest turns of the conversation that fit its budget, with when each was said and what a5s told the person, so the agent can tell an old request from a new one. When an agent can't help, a5s says why and names someone who can: whoever suspended it, its owner or deputy but never the person asking, or the instance approvers. | [`services/`](../src/a5s/services/) |
| A Deep Agents worker with no credentials and no shell, whose thread ends with the run | [`worker.py`](../src/a5s/worker.py) |
| Obligations, worked out by code from the scenario's records: one for each record and person, naming the instance that acts on it. That instance reminds the person once half the time allowed has passed, in their working hours, in a run that acts for them and can write to nobody else, as the agent's own bot, in the conversation they last had with it or else the chat they last wrote in. If it's still open when due, the core escalates it itself, a step up the person's reporting line at a time, in each recipient's working hours, and no sooner than a working day after the reminder or the step before. It escalates whether or not an agent can act, so suspending or withdrawing one never silences what's owed, and it skips anyone a5s may not write to. If the records can't be read, nothing owed changes until they can. | [`core/obligations.py`](../src/a5s/core/obligations.py) |
| Schedules, which come only with a release and keep its owner's time zone. Each time fires once, even with two schedulers. A time more than an hour past is let go rather than worked through, and one that falls while the instance is suspended is recorded as skipped and isn't made up. A schedule run acts for nobody, so it writes to nobody [TBC: whose digest a schedule's findings go in]. | [`core/schedules.py`](../src/a5s/core/schedules.py) |
| Suspension that stops the next call, even in a running run. Who suspends and resumes comes from their sign-in, the first suspender's suspension stands, and only they can resume it. | [`core/registry.py`](../src/a5s/core/registry.py) |
| Signed settings: a version counts only when someone the directory names as an instance approver signs it, with their own key or on a card in their chat ([step 4](#progress)), and its serial must rise, so an older, looser version can't be replayed. The core checks the signed bytes again whenever a run opens, and refuses an instance whose record differs from them, from its release or from the last status change in the ledger, so editing the database widens nothing. A version that leaves an instance out retires it. | [`core/signing.py`](../src/a5s/core/signing.py), [`core/registry.py`](../src/a5s/core/registry.py) |
| Every tool is a call to the gateway, for subagents too. A call policy denies never runs, the agent hears why in words, and the denial is recorded. Asking the core to explain a call before making it waits for held proposals, in phase 2. | [`worker.py`](../src/a5s/worker.py) |
| Sign-in through the organisation's identity provider, with OpenID Connect, built for Entra ID, Google Cloud Identity and Okta and tested with Keycloak and a fake provider. Every message arrives at the core, which checks the token, finds the person in the directory, and records the message. A run that answers it takes its sender from there, so the token goes no further. | [`core/identity.py`](../src/a5s/core/identity.py) |
| The ledger's copies in locked storage, made every hour, with an adapter for each cloud's: S3 Object Lock, Azure's immutable Blob Storage and Google Cloud Storage's object retention. Verifying the ledger checks it against its copies, so a history rewritten with every hash recomputed shows, as do deleted entries, a replaced copy, a fork, a planted copy and copying that has stopped. A planted copy can't stop the copying, and a copier that finds the ledger rewritten stops with an error, so the platform notices. | [`core/anchor.py`](../src/a5s/core/anchor.py), [`core/stores.py`](../src/a5s/core/stores.py) |
| Teams, through the Bot Framework, with each agent its own bot. The core receives each message itself, because Teams' token doesn't cover what a message says: it checks the token, its key's endorsement for Teams, the service URL and the organisation, and finds the sender by their Entra ID. The scheduler answers from the core's queue, and replies and a5s's own notices reach Teams only through the core, which alone holds the bot's credentials. An agent writes first only to people who've added its app, which Teams tells its bot. | [`core/teams.py`](../src/a5s/core/teams.py) |
| A web chat, a page the core serves, where people sign in with their organisation's provider and talk to the agents through the core's local channel, as the command line does. Sign-in is the authorization code flow with PKCE: the core passes the code on to the provider and gives the page only the ID token, never the provider's access token. The page runs only its own script, shows only text, and keeps the sign-in for its tab alone. It's on only where people can sign in to it, or in development. | [`core/webchat/`](../src/a5s/core/webchat/), [`core/inbox.py`](../src/a5s/core/inbox.py) |
| Matrix, as an application service on the organisation's own homeserver, with each agent its own bot. The homeserver proves each delivery with its token, and vouches for its own people, whom the directory names by their Matrix ids. a5s joins a direct chat when someone the directory knows invites an agent's bot, and turns away people on other servers, rooms with more people and encrypted messages, saying why. Replies and reminders reach Matrix only through the core, which alone holds the token that speaks as the bots. An agent that writes to someone first starts a direct chat as its own bot, never another agent's, and a5s stops writing in a chat the person leaves or turns down. | [`core/matrix.py`](../src/a5s/core/matrix.py) |
| Each deployment turns on the chats its people use by setting each one's settings, any number at once, and compose passes them on from its environment | [`deploy/compose.yaml`](../deploy/compose.yaml) |
| The sample scenario, with nine people in two time zones, including the team that runs a5s and the people outside it who approve its releases, customer questions with owners and due dates, and a store for drafts. a5s serves whichever scenario its configuration names, and keeps none of a scenario's people in its own definitions. | [`scenarios/sample/`](../scenarios/sample/) |
| One container image that runs as the gateway, the scheduler or a worker, and a compose stack whose networks enforce the design: a worker holds no secrets and reaches only the gateway, never the database or the internet. A smoke test runs the stack in CI with stand-ins for the model, the identity provider, a Matrix homeserver and locked storage: Keycloak and Synapse, with the sample's people, and LocalStack, whose S3 enforces object lock as Amazon's does. | [`Dockerfile`](../Dockerfile), [`deploy/`](../deploy/) |
| 296 tests against a real Postgres and a scripted model, fakes of the Bot Framework, a Matrix homeserver and an identity provider, and the web chat and the approval page in Chromium, with a clock the tests set, with emulators for Azure's and Google's storage, and live tests through DeepSeek's and Qwen's OpenAI-compatible APIs and DeepSeek's Anthropic-compatible one, including a reminder, the watcher's reports, and a reminder offered and confirmed | [`tests/`](../tests/) |

Step 2, the release pipeline, has started:

| Built | Where |
| --- | --- |
| Releases that each organisation approves for its own deployment. A release's manifest lists every file a5s runs and what each agent and model may do, and the people its changes need sign it with their own keys, anywhere and offline: the release approver, from outside the team that runs a5s and its reporting line, and assurance, for the trusted core or what its image is built from; the release approver for the scenario, or anything that widens what an agent or a model may do; the agent's owner and a second engineer for instructions alone; an engineer for the services alone, or for a security fix that changes only dependencies. The core checks the signatures against the directory, and opens no run until the release has what it needs, so a change to the trusted core can't run without the outside approval. An image whose code isn't what it was built with doesn't run. | [`core/releases.py`](../src/a5s/core/releases.py) |
| A release pipeline. On a version tag, the full suite runs, then the image is built, smoke-tested, pushed with its provenance signed, and published with the manifest it was built with. Base images, actions and test images are pinned by digest or commit, and a test fails if any isn't. The smoke test shows the core refusing a release nobody approved, then running it once the sample's people have signed. | [`.github/workflows/`](../.github/workflows/) |
| Rules that protect the main branch and release tags, ready for the repository's settings: changes through reviewed pull requests with the suite passing, and tags nobody can move or delete | [`.github/rulesets/`](../.github/rulesets/) |

Still to do in step 2:

- deploying each release to the three clouds, which waits for step 1's infrastructure code;
- applying the rules to the repository, which needs a second maintainer to review changes: `gh api --method POST repos/<owner>/a5s/rulesets --input .github/rulesets/main.json`, and the same for `releases.json`;
- each agent's own regression suite, run against real models, which grows with the reference agents in step 4.

Step 4, the reference agents, is built:

| Built | Where |
| --- | --- |
| The watcher, at level 0, which reads and changes nothing. Each working day, in each person's digest, it tells each person it serves what changed in the records they own since it last told them, and what fell due. The first time, it tells them what's open. Code works the facts out from the records and from the obligations the core keeps, so the model only puts them into words, and a day with nothing new starts no model at all. Each report acts for its person alone, goes once a day, and is skipped, not made up, while the watcher is suspended, so what changed waits for the next one. People can also ask it about their records, and it writes to them only as its own bot. | [`agents/watcher/`](../agents/watcher/), [`core/reports.py`](../src/a5s/core/reports.py) |
| The scenario contract gives each person's records as they stand, for reports | [`contract.py`](../src/a5s/contract.py) |
| The assistant's promises and reminders. It offers a reminder, or to follow something up, with a5s's own typed tools, and a5s keeps it only once the person says yes, in a later message of their own: a reminder is theirs alone, set only in answer to their own message, and never by a run that has read content from outside. On the day, the assistant reminds them, checking the record first, and if it can't act, the core reminds them itself. People can list and cancel theirs, and say what they're waiting on for one of their records, which pauses reminders about it until the date they give, and tells whoever an escalation reaches why. | [`core/reminders.py`](../src/a5s/core/reminders.py) |
| Digests: one message a day for each person from all the agents together, at a time they choose, the start of their working day unless they ask an agent for another. Chases, reports and reminders for a day wait for it, and the agents' work for it is done when its time comes, so nothing in it is stale: what comes up after it waits for the next. One item goes as its agent's own message; more go as one from a5s, each under its agent. Answers, escalations and reminders for a particular time go at once. | [`core/digests.py`](../src/a5s/core/digests.py) |
| Approval cards, for the people who approve these agents. A version of the settings can be proposed to the instance approvers, rather than signed with their keys. Each gets a card in Teams, or a link in Matrix, the web chat or on the command line, saying what the version changes in words code works out, and which changes widen what agents do. The card only opens the core's own page, where they decide, apart from the conversation. There they sign in afresh at the identity provider, with a nonce that commits to approving that version, so the provider's signature covers the decision, and each sign-in approves once. The core seals each approval it has checked with a key only it holds, so the approval outlasts the provider's keys and editing the database approves nothing. It checks the seal again at every run, as it checks signatures made with keys, and applies the version once an instance approver has approved it. Releases are still signed with keys, offline. | [`core/approvals.py`](../src/a5s/core/approvals.py), [`core/webchat/approve.js`](../src/a5s/core/webchat/approve.js) |

Approval cards reach Teams through the fake Bot Framework until a5s's bots are registered in your tenant, as the rest of Teams does (step 1). The smoke test approves new settings with a real sign-in at Keycloak, from a request in a Matrix chat.

Still to do in step 1:

- registering a5s's bots in your Entra ID tenant and adding them to Teams, which needs your tenant. Until then, Teams is tested against a fake of the Bot Framework, and people use the web chat, Matrix or the command line;
- reading encrypted rooms in Matrix. Until then, people turn encryption off in their chats with a5s;
- the infrastructure code that deploys the image to Azure, Google Cloud and AWS with managed Postgres, which needs your accounts there to test. The containers run locally with compose, and each cloud will run them on its own container service.

## Done means

- a5s's own suite passes on all three clouds, against the sample scenario in CI and in test. Among its tests: every call is in the ledger; calls are denied when policy, the settings or the ledger is down; a suspended instance's next call is denied; a change to the trusted core can't deploy without the outside approval; and a person who comes back a week later picks up where they left off.
- The measures have a baseline from the first users: promises and reminders met on time, time from something falling due to it being done, people who come back to an agent, and cost per run.

## Later

| Phase | Adds | Because |
| --- | --- | --- |
| 2 | The extractor, with handles for the values it reads. Held proposals, counts, signed decisions, and level 2 with samples and sequential tests. | They're needed only once agents read outside content or act |
| 3 | Group conversations, a notebook of what agents learn from records, agent to agent over A2A, and adapters for managed runtimes | Each builds on phase 2's evidence |

## Costs

| Cost | How it's worked out | Estimate |
| --- | --- | --- |
| Build | The six steps above | [TBC: about three engineers for two quarters for one cloud. Running on three at once adds two more clouds' adapters, deployments and operations.] |
| Models | Runs × model calls per run × tokens per call × price | About $0.50 a run before caching: 5 calls of 30,000 tokens in and 1,000 out, at an illustrative $3 and $15 per million. 1,000 runs a month is about $500. Sweeps start no model when nothing has changed. |
| Platform | Postgres, workers, gateways, object-lock storage and telemetry, on each of the three clouds | [TBC: from each cloud's prices] |
| People | Agent owners' time, and the outside approver for widening and core releases. From phase 2, graders. | Graders: about 100 items a quarter for each type of action at level 2, at about 3 minutes each, is 5 hours a quarter |
