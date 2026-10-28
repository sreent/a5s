# Phase 1

**Status:** Plan, nothing built · **Under:** [Architecture](architecture.md)

Phase 1 builds the smallest a5s that's useful: the trusted core, conversations, and three low-risk agents from the [lean scenario](../scenarios/lean-framework.md) working for real people, at levels 0 and 1. In phase 1, agents read, report, draft and chase. None of them changes data.

## Decide first

| Decision | Starting proposal |
| --- | --- |
| Cloud and identity provider | The ones the organisation's identity estate already runs on, with Postgres |
| Channel | Teams |
| Settings store | a5s's own, with signed versions [TBC: edited through a simple app, or in git] |
| Outside approver | Information security, for releases that widen an agent and changes to the trusted core |
| Model | One approved model, pinned by provider, deployment, region and version |
| The lean contract | Interfaces for the directory, settings, tools and records, and a fake of each. That includes where the exception register and the ownership settings live during the transition [TBC]. |

## Build, in order

Each step ends with something running and its tests passing.

1. **A walking skeleton,** running locally against the fake:
   - definitions in git, and instances in Postgres;
   - a scheduler for messages, schedules and obligations, with leases and suspension;
   - `create_deep_agent` runs, each on a thread that lasts one run;
   - every call goes from the middleware to a gateway, which checks Cedar policy, denying by default and failing closed, and writes the ledger in the same transaction ([a call, step by step](architecture.md#a-call-step-by-step));
   - replies in Teams through the channel gateway;
   - a switch that suspends an instance at its next call.
2. **A release pipeline:** pinned dependencies, the regression suite in CI, and protected branches, with an attested build and outside approval for the trusted core. Releases are [proportionate](architecture.md#independence).
3. **Context:** conversations in topics, structured summaries that code checks, profiles, case briefs from records, search over past turns, promises and reminders, and the context budget for each run ([context](architecture.md#context-and-memory)).
4. **The first two agents,** against the fake and then the real systems in test:
   - the governance coordinator at level 1, with no parts. Its obligations come from the exception register, and it sends digests and chases and drafts the owner review pack;
   - the change reconciler at level 0. It only reads, matches by code and reports to internal controls, which makes it a cheap test of the plumbing, watched by the team whose job is checking.
5. **Running it properly, then production:** tokens for classified values, masked traces, budgets at the model gateway, the hourly ledger anchor with assurance, dashboards, objectives, runbooks and on-call ([operations](architecture.md#operations)). Then the first two agents go to production.
6. **The owner assistant, for one part,** at level 1: live settings, a level for each part, case briefs and chasing. Its part has no Restricted fields, and its tools return no outside content, since the extractor comes in phase 2. Alongside it, a prototype of [handles](architecture.md#provenance-who-said-what), the first test of value provenance.

## Done means

- The lean scenario's phase-1 tests pass ([passing the baseline](../scenarios/lean-framework.md#passing-the-baseline)), against the fake in CI and against the real systems in test.
- a5s's own suite passes. Among its tests: every call is in the ledger; calls are denied when policy, the settings or the ledger is down; a suspended instance's next call is denied; a change to the trusted core can't deploy without the outside approval; and a person who comes back a week later picks up where they left off.
- The measures have a baseline for phase 2 to beat: exceptions reminded before they expire, cases chased within their turnaround, time to prepare the owner review pack, people who come back to an agent, and cost per run.

## Later

| Phase | Adds | Because |
| --- | --- | --- |
| 2 | The extractor and value provenance, then the request assistant. Held proposals, counts, signed decisions, level 2 with samples and sequential tests, and the quality agent. | They're needed only once agents read outside content or act |
| 3 | Group conversations, a notebook of what agents learn from records, agent to agent over A2A, and adapters for managed runtimes | Each builds on phase 2's evidence |

## Costs

| Cost | How it's worked out | Estimate |
| --- | --- | --- |
| Build | The six steps above | [TBC: about three engineers for two quarters, to confirm once the decisions are made] |
| Models | Runs × model calls per run × tokens per call × price | About $0.50 a run before caching: 5 calls of 30,000 tokens in and 1,000 out, at an illustrative $3 and $15 per million. 1,000 runs a month is about $500. Sweeps start no model when nothing has changed. |
| Platform | Postgres, workers, gateways, object-lock storage and telemetry | [TBC: from the cloud's prices, once it's chosen] |
| People | Agent owners' time, and the outside approver for widening and core releases. From phase 2, graders. | Graders: about 100 items a quarter for each type of action at level 2, at about 3 minutes each, is 5 hours a quarter |
