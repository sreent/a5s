# Architecture

**Status:** Draft v0.1 · **Under:** [a5s](../README.md)

a5s runs agents the way an operating system runs programs. It installs them, gives each one an identity and only the rights it needs, wakes it when there's work, checks every call it makes, and keeps a record of what happened.

| An operating system has | a5s has |
| --- | --- |
| Programs | Agent definitions, released as tested versions |
| User accounts | An identity for each agent instance, with a named owner |
| Processes | Runs: one piece of work, started fresh from the agent's records |
| A scheduler | Triggers: events, schedules, sweeps and messages |
| System calls and permissions | Tool calls, each checked against policy |
| A file system | Scratch space for each run, memory for each instance, and shared knowledge that agents only read |
| Drivers | Tool servers, over MCP, for the systems agents use |
| Messages between processes | A2A between agents, and channels to people |
| An audit log | The evidence ledger |

The [agent model](agent-model.md) defines definitions, instances, runs, scopes and autonomy.

## The kernel

| Component | Does | Built on |
| --- | --- | --- |
| Register | Holds every definition and instance, its owner and deputy, its approved release and its status | Git for definitions, copied to the host's registry for discovery |
| Identity | Gives each instance its own identity, and gets short-lived credentials for each call. The model never sees them. | The host's agent identity ([hosting](#hosting)) |
| Policy | Decides each tool call: allow, propose or deny. Reads autonomy live from the scenario's settings. | Cedar [TBC] |
| Tool gateway | The only route from an agent to a system. Checks policy again and holds the credentials. | MCP, and the host's gateway where it has one |
| Approvals | Turns each proposal into a decision by the right person, where the scenario decides things, and resumes the run | LangGraph interrupts |
| Scheduler | Wakes instances on triggers, works out what they owe people, runs them within budget, and stops them when they're suspended | LangGraph checkpointer and cron jobs |
| Memory | Keeps each instance's memory, versioned, masked and reviewed | Deep Agents store backend |
| Channels | Lets agents talk to people, under the agent's own identity and contact rules | Teams or email [TBC] |
| Ledger | Records every action, append-only, where the team that runs a5s can't change it | Immutable storage [TBC], OpenTelemetry |
| Assurance | Tests each release, measures how people review proposals, and samples work for moving an agent up or down a level | LangSmith evaluations and annotation queues |

## Policy

Every tool call meets three lines, so that no single failure lets an agent do what it mustn't:

1. **Rights.** An instance's identity holds only the rights its grant lists. Actions the scenario forbids, such as approving or confirming in the lean scenario, are never granted, so no instruction can talk an agent into them.
2. **The tool gateway.** It checks each call against policy outside the agent, before the call reaches the system. This line holds even if the agent's own code is bypassed.
3. **The agent's middleware.** A LangChain `wrap_tool_call` middleware asks the same policy first, so the agent gets a clear reason and can change course.

Policy answers **allow**, **propose** or **deny**, from:

- **who:** the instance, and the person it acts for, if any;
- **what:** the tool, its risk attributes (reads, writes, sensitive, destructive, sends outside) and the type of action;
- **on what:** the record, its scope and the classes of data involved;
- **context:** the instance's autonomy for that type of action, earlier actions counted across runs, the run's budget, and the scenario's switches.

Policy denies by default. If it can't be reached, the call is denied. If the scenario's settings or the counts can't be read, the instance works at level 1 at most, so any action becomes a proposal.

- **Autonomy** is read live from the scenario's settings for every run, and never copied, because a stale copy is a setting nobody approved.
- **Counts** run across runs: actions are counted per instance and type of action over a window [TBC], so a large change can't be split into small runs.
- **Packs.** A base pack holds what a5s always enforces, and each scenario adds its own. Both are part of a release, and the ledger records the version that decided each call.

## Approvals

When policy answers propose, the run pauses with a per-call LangGraph interrupt, and the checkpointer parks it for as long as the decision takes.

1. The approvals service posts the proposal to the scenario's decision surface, for the scope owner or their delegates. It shows the actual tool call and its arguments, with the agent's evidence and summary beside them, never instead of them.
2. The decider approves, edits or rejects it there. The service checks who they are, and refuses a decision from anyone the scenario forbids, such as the person the agent acted for, or the agent's own owner.
3. Edited arguments go through policy again.
4. The service records the decision, the decider, and when the proposal was shown and decided, then resumes the run with that one decision.
5. A proposal that isn't decided in time escalates along the scope's chain, and in the end expires as rejected [TBC: how long].

A run with no person present, such as a scheduled one, never approves anything: it proposes and stops. A level-2 action runs without a proposal, and the agent owner can reverse it through the scenario's own process, never by rewinding the agent.

## How an agent lives

An instance lives in records: its identity, its register entry, its obligations, its triggers and its memory. Compute is the only temporary part. Each piece of work goes like this:

1. **Wake.** A trigger arrives: an event from a system, a message from a person, a schedule, or a sweep. A sweep is a fallback schedule that runs only while the instance is idle, and starts no model when nothing has changed.
2. **Prepare.** The scheduler checks that the instance is active, has budget left and has no other run going. Then it works out what has fallen due, resolves autonomy, and loads the instance's latest memory snapshot.
3. **Build.** It creates the agent with `create_deep_agent` on a fresh thread: the release's instructions and skills, only the granted tools, the memory snapshot to read, and the policy, ledger, masking and budget middleware.
4. **Work.** The agent plans, reads, drafts and hands parts to subagents. Every tool call passes policy twice.
5. **Propose or act.** A proposal pauses the run until a person decides. A level-2 action runs and is reported.
6. **Remember.** The agent can propose memory entries. a5s masks them and holds them for review before they join the next snapshot.
7. **Sleep.** The run ends. Its credentials expire, its sandbox is discarded, and its obligations and contact log are updated.

- **Obligations** are worked out by code from the scenario's records, such as cases past their turnaround time or exceptions near expiry, never inferred by the model. Each has a due time, an escalation chain and a contact log. The model drafts and summarises. It doesn't decide what's owed.
- **Triggers and schedules** are part of the release, and an agent can't create its own. People can ask an agent for something within its job, such as a reminder on Friday, which becomes an obligation. Nobody changes an agent's job by talking to it.
- **One run at a time** for each instance. Tools are idempotent, because LangGraph re-runs the code before an interrupt when a run resumes. A scheduled run fires at most once, and a run that's cut off waits for review instead of restarting.

## Memory

| Store | Holds | Kept for | Written by |
| --- | --- | --- | --- |
| Scratch | Working files for one run | The run | The agent |
| Memory | What the instance has learned: preferences, patterns and open threads | The instance's life, each entry until it expires | a5s, from entries the agent proposes and a reviewer approves [TBC: the agent owner] |
| Knowledge | The scenario's documents and settings | As their owners decide | Their owners, in their own systems. Agents only read it. |
| History | What the instance did and said | As the ledger is kept | The ledger and contact log. The instance can search its own. |

Memory entries are structured: what, why, source, class of data and expiry. They hold record keys, never classified values. Each run reads a frozen, versioned snapshot, and the ledger records which one, so a poisoned entry can be traced and removed. An agent recalls what it said weeks ago by searching its history, not by keeping one conversation open for weeks.

## Channels

Each instance talks to people under its own identity, such as its own mailbox or bot account, never a person's, and says it's an AI agent. The scenario sets the contact rules: by default one digest a day rather than a stream, working hours, a limit per person per day, and the escalation chain. A message takes the classification of what it quotes, so it links to records instead of quoting classified values. Replies wake the agent.

## Data protection

- **Classes come from the scenario.** Each field's class comes from the scenario's settings, and decides what's masked and which models may see it.
- **Masking.** The ledger, memory, traces and evaluation sets hold masked or tokenised values with their record keys, so evidence stays usable without holding restricted data outside live systems.
- **Models by class.** Each class of data has approved models and environments, and policy checks the model before data reaches it. That includes models inside managed features, such as memory extraction or evaluation.
- **Outside content.** Documents and messages from outside the organisation go through an extractor that has no tools. It returns typed fields tagged with their source, and policy can refuse to use a value for a purpose because of where it came from. Classifiers such as Prompt Shields, Model Armor or Bedrock Guardrails add signals. They're never the boundary.

## Evidence

For every action, the ledger records the instance and its release, the person it acted for, the trigger, the tool and its masked arguments, the policy decision and policy version, any approval with its decider and review time, the model, the memory snapshot and the outcome. Entries are append-only and hash-chained, kept where the team that runs a5s can't change them, and readable by whoever assures the scenario, such as internal controls.

The same events go out as OpenTelemetry spans, using the GenAI conventions (`invoke_agent`, `execute_tool`), plus a5s attributes for what those lack, such as the person acted for and the policy decision. Traces in LangSmith or elsewhere are for debugging and are kept briefly. They aren't the evidence.

## Assurance

- **Release tests.** Each release passes its regression suite, including the scenario's tests and attempted injections, before it's approved.
- **Measures.** For each instance, type of action and reviewer: work handled, proposals, acceptance and edit rates, review times, chases and escalations, and cost. Almost no rejections with very short reviews flags rubber-stamping.
- **Samples.** People grade stratified samples of each instance's proposals and actions. The results are the evidence for moving it up a level, or down.
- **Drift.** Long-lived instances re-run their suite on a schedule, because models change under them.

## What comes from Deep Agents, and what a5s adds

| a5s needs | Deep Agents and LangGraph give | a5s adds |
| --- | --- | --- |
| The agent loop | `create_deep_agent`: a virtual filesystem, subagents, skills, summarisation, and planning if wanted | Nothing. It's used as it is. |
| Proposals that wait for days | Per-call interrupts (langchain 1.4.6 and later) and a checkpointer | Routing, the decider's identity, who may decide, timings, escalation and expiry |
| A check on every tool call | `wrap_tool_call` middleware, and filesystem permissions that allow by default | Policy that denies by default, checked again at the gateway |
| Memory | `StoreBackend`, `CompositeBackend` and `AGENTS.md` memory | One writer, review, masking, expiry and versioned snapshots |
| Schedules | Agent Server cron jobs | Triggers from the release, obligations, sweeps, and runs that fire at most once |
| Durable state | A Postgres checkpointer and store | One run at a time for each instance, and idempotent tools |
| Tools | The MCP client in `langchain` (1.4 and later) | Registered tool servers, pinned tool definitions and risk attributes |
| Agent to agent | The Agent Server's A2A endpoint (v1.0, JSON-RPC) | Registered peers only, and no borrowed authority |
| Versions | Assistants, which are versioned configurations | Releases, with tests and approval |
| Sign-in | `@auth.authenticate` and `@auth.on` handlers. A self-hosted server has no authentication by default. | Identity adapters, and the decider's identity bound to each resume |
| Tracing and evaluation | LangSmith and OpenTelemetry | The ledger, measures and samples |
| Personal data | PII middleware, with five built-in regex types | Masking by class, from the scenario's settings |

Deep Agents is still before 1.0 and releases several times a week, so a5s pins its versions and treats each upgrade as a release. It needs deepagents 0.7.25 or later, which fixed a way around its approval rules, and per-call interrupts, because the default batched mode matches decisions to tool calls by position.

## Agent to agent

Agents call each other only over A2A, and only between registered instances. The agent called treats a request like any other: within its own job, grants and autonomy. Authority doesn't pass from caller to callee, and the ledger links both runs.

## Hosting

The kernel is the same everywhere, and adapters connect it to the host:

| Host | Runs on | Identity | Gateway | Notes |
| --- | --- | --- | --- | --- |
| Self-hosted | LangGraph Agent Server, with Postgres and Redis | The organisation's identity provider, or SPIFFE [TBC] | An MCP gateway such as agentgateway, with a5s policy | The most control, and the most to run |
| AWS | AgentCore Runtime | AgentCore Identity: a workload identity and token vault | AgentCore Gateway and Policy, which also uses Cedar | The best-documented home for Deep Agents. Sessions last 8 hours by default. |
| Microsoft | Foundry hosted agents | Entra Agent ID: a blueprint for each definition, an agent identity for each instance, and the owner as sponsor | The a5s gateway | Fits a Microsoft 365 estate, with Purview audit |
| Google | Agent Runtime | Agent Identity: a certificate that lasts 24 hours, with tokens bound to it | Agent Gateway, managed only for Agent Runtime so far | The strongest identity. Sessions last up to 7 days. |

Each host's registry gets a copy of the register, for discovery and gateway rules. The register in git stays the source.

## Standards

| For | Standard |
| --- | --- |
| Tools | MCP, specification 2026-07-28 |
| Agent to agent | A2A v1.0 |
| Skills and instructions | Agent Skills and `AGENTS.md` |
| Identity and delegation | OAuth 2.1 and token exchange, with the agent as the client and the person as the subject, following the IETF's WIMSE work |
| Policy | Cedar [TBC] |
| Telemetry | OpenTelemetry GenAI conventions |

## What a5s won't do

- Let an agent change its own instructions, skills, tools, schedules or memory rules in production.
- Let a model approve an action. A person does, or a policy rule with a fixed answer.
- Give a model credentials.
- Record decisions in a vendor's inbox instead of the scenario's decision surface.
- Let an agent act without telling anyone. There's no level above 2.
- Write to a system of record except through its own governed process.
