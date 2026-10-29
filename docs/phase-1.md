# Phase 1

**Status:** Plan, nothing built · **Under:** [Architecture](architecture.md)

Phase 1 builds the smallest a5s that's useful: the trusted core, conversations, and two reference agents of a5s's own, at levels 0 and 1. They're proven against a5s's sample scenario, and used first by the team that builds a5s. In phase 1, agents read, report, draft and remind. None of them changes data. Which real scenario comes first is a separate decision [TBC].

## Decide first

Decided on 28 October 2026, except where marked:

| Decision | Decided |
| --- | --- |
| Clouds | Azure, Google Cloud and AWS, all three at once, each with managed Postgres. a5s's code is the same on each, and adapters cover what differs: identity, secrets, object-lock storage and model endpoints. |
| Identity providers | Entra ID, Google Cloud Identity and Okta, through OpenID Connect. People who use Teams also have an Entra ID identity, which the directory maps to the person. |
| Channel | Teams only, for now |
| Settings | One signed settings store with three ways to change it: files in git, approval cards in Teams, and a simple web app |
| Roles | Held by people, assigned in each organisation's directory, never by job title. a5s checks each role's rules in code, such as the release approver being outside the team that runs a5s. Who holds the platform owner and release approver roles is each deployment's to assign. |
| Models | Any provider with an OpenAI-compatible or Anthropic-compatible API. Development and tests use DeepSeek and Qwen, whose keys are in the environment, against the fake with synthetic data only. Real data goes only to models on the organisation's approved list, for the classes of data each is approved for, such as open-weight models it hosts in its own cloud. |
| Sample scenario | a5s's own fake of every contract interface, with synthetic data: a directory, settings, a records system and a document store. It's the test bench, locally and in CI. |

## Build, in order

Each step ends with something running and its tests passing.

1. **A walking skeleton,** running locally against the fake:
   - definitions in git, and instances in Postgres;
   - a scheduler for messages, schedules and obligations, with leases and suspension;
   - `create_deep_agent` runs, each on a thread that lasts one run;
   - every call goes from the middleware to a gateway, which checks Cedar policy, denying by default and failing closed, and writes the ledger in the same transaction ([a call, step by step](architecture.md#a-call-step-by-step));
   - a model gateway that speaks both API styles, tested with DeepSeek and Qwen;
   - settings as signed files in git;
   - replies in Teams through the channel gateway;
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
| Definitions in git, with a hash of the folder in each release and tools' schemas pinned | [`agents/`](../agents/), [`definitions.py`](../src/a5s/definitions.py) |
| Instances, runs and the ledger in Postgres. Each ledger entry is written in the same transaction as its decision and chained by hash. The database refuses to change an entry, and verification shows where a rewritten one breaks the chain. | [`core/`](../src/a5s/core/) |
| Cedar policy with a5s's base pack and a schema, denying by default and failing closed | [`core/policies/`](../src/a5s/core/policies/) |
| The gateway for tools, for models in both API styles, and for outgoing messages, which keep only the scenario's record links. Workers hold only a run token, never a provider's key. | [`core/gateway.py`](../src/a5s/core/gateway.py) |
| The scheduler, with a lease per conversation, and conversations that each fresh run reads | [`services/`](../src/a5s/services/) |
| A Deep Agents worker with no credentials and no shell, whose thread ends with the run | [`worker.py`](../src/a5s/worker.py) |
| Suspension that stops the next call, even in a running run, and resuming only by whoever suspended | [`core/registry.py`](../src/a5s/core/registry.py) |
| Signed settings: a version counts only when someone the directory names as an instance approver signs it, and its serial must rise, so an older, looser version can't be replayed. A run won't open for an instance whose settings nobody signed. | [`core/signing.py`](../src/a5s/core/signing.py), [`core/registry.py`](../src/a5s/core/registry.py) |
| The middleware that asks the gateway to explain a tool call before making it. A call policy would deny never runs, the agent hears why in words, and the denial is recorded. It reaches subagents too. | [`worker.py`](../src/a5s/worker.py) |
| The sample scenario, with three people, customer questions and a store for drafts | [`scenarios/sample/`](../scenarios/sample/) |
| One container image that runs as the gateway, the scheduler or a worker, and a compose stack whose networks enforce the design: a worker holds no secrets and reaches only the gateway, never the database or the internet. A smoke test runs the stack in CI with a stand-in model. | [`Dockerfile`](../Dockerfile), [`deploy/`](../deploy/) |
| 49 tests against a real Postgres and a scripted model, and live tests through DeepSeek's and Qwen's OpenAI-compatible APIs and DeepSeek's Anthropic-compatible one | [`tests/`](../tests/) |

Still to do in step 1:

- the Teams channel, which needs a bot registered in your Entra ID tenant. With it, the core checks each message's sender against the channel's signed identity. Until then, the local channel trusts the scheduler's word for who sent a message, so it's for development only;
- deploying the image to Azure, Google Cloud and AWS, on each one's container service with managed Postgres, which needs your accounts there.

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
