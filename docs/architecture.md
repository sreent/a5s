# Architecture

**Status:** Draft v0.1 · **Under:** [a5s](../README.md)

a5s runs agents the way an operating system runs programs. It installs them, gives each one an identity and only the rights it needs, wakes it when there's work, checks every call it makes, and keeps a record of what happened.

| An operating system has | a5s has |
| --- | --- |
| Programs | Agent definitions, released as tested versions |
| User accounts | An identity for each agent instance, with a named owner |
| Processes | Runs: one piece of work, on the thread it belongs to |
| A scheduler | Triggers: events, schedules, obligations falling due, and messages |
| System calls and permissions | Tool and model calls, each checked against policy |
| Memory and files | Scratch space for each run, the agent's conversations and notes, and shared knowledge that agents only read |
| Drivers | Tool servers, over MCP, for the systems agents use |
| Messages between processes | A2A between agents, and channels to people |
| An audit log | The evidence ledger |

The [agent model](agent-model.md) defines definitions, releases, instances, threads and runs, and the terms used here: parts and their owners, grants, types of action, settings, governed processes, the decision surface, and whom an agent acts for.

## The kernel

| Component | Does | Built on |
| --- | --- | --- |
| Register | Holds definitions and their releases in git, and instances, with their identities, status and any approval the scenario's settings don't hold, in its database [TBC]. Every change goes in the ledger. | Git, copied to the host's registry for discovery only |
| Identity | Gives each instance its own identity, and gets short-lived credentials for each call. The model never sees them. | The host's agent identity ([hosting](#hosting)) |
| Policy | Decides each tool and model call: allow, hold for a person, or deny. Reads the scenario's settings live for every call. | Cedar [TBC] |
| Gateways | The only routes from an agent to systems and to models. They ask policy for every call, and hold the credentials. | MCP, and the host's gateway where it has one |
| Approvals | Holds each call that needs a person's decision, gets the decision on the decision surface, makes the call once it's approved, and follows the requests agents hand to governed processes | Its own store of held calls |
| Scheduler | Wakes instances on triggers, works out what they owe people, runs them within budget, tells them when decisions arrive, and stops them when they're suspended | Its own code, with threads kept by LangGraph's checkpointer |
| Context | Keeps each instance's conversations, what it knows about the people it works with, and its notebook, with sources, masking and expiry | LangGraph threads and store, and Deep Agents' summarisation |
| Channels | Lets agents talk to people, under the agent's own identity and the scenario's contact rules | Teams or email [TBC] |
| Ledger | Records every action, append-only, where the team that runs a5s can't change it | Immutable storage [TBC], OpenTelemetry |
| Assurance | Tests each release, measures how people review proposals, and samples work as the evidence for each agent's level | LangSmith evaluations and annotation queues |

## Policy

Every call meets three lines, so that no single failure lets an agent do what it mustn't:

1. **Rights.** An instance's identity holds only its grant. Actions the scenario forbids, such as approving or confirming in the lean scenario, are never granted, so no instruction can talk an agent into them.
2. **The gateways.** Tool calls go through the tool gateway and model calls through the model gateway, which ask policy for every call. They hold even if the agent's own code is bypassed. Rules copied into a host's own policy engine can only add restrictions. Sandboxes where agents run code have no credentials, and no network access except to the gateways.
3. **The middleware.** a5s's LangChain middleware asks the same policy first, on the agent and on every subagent, including Deep Agents' built-in general-purpose one, so the agent gets a clear reason and can change course.

Policy answers **allow**, **hold** or **deny**, from:

- **who:** the instance, and the person it acts for, if any. Acting for a person, an agent sees only what both it and that person may see.
- **what:** the tool or model, its risk attributes (reads, writes, sensitive, destructive, sends outside) and the type of action.
- **on what:** the fields it touches, the parts they belong to, and their classes of data. An action that touches fields in several parts needs each part's approval, and works at the lowest of their levels.
- **context:** the instance's levels, the actions counted so far, the run's budget, and the scenario's switches, such as the lean scenario's switch for each request type until it moves to the unified app.

Policy denies by default, and fails closed:

- If policy can't be reached, every call is denied.
- If the settings can't be read, every call that touches a part is denied.
- If the counts can't be read, every level-2 action is denied.
- If the ledger can't be written, every call is denied.

**Settings** are read live for every call and never copied, because a stale copy is a setting nobody approved.

**Counts.** Level-2 actions are counted per piece of work, such as the check or issue that started it, across all its types of action. Code, not the model, decides which piece of work each action belongs to. As a backstop, an instance's level-2 actions in each part are also counted over a window [TBC]. When a piece of work reaches a limit the scenario sets, such as the lean framework's mass-change size, a5s refuses its further level-2 actions and sends the rest to whoever approves that limit. Work planned to go past the limit goes to them from the start.

**Packs.** A base pack holds what a5s always enforces, and each scenario adds a pack that can only add restrictions. Packs are versioned and approved like releases [TBC: by whom], and the ledger records the version that decided each call.

## Proposals and approvals

At level 1 an agent prepares and people decide. Its work reaches a person in one of three ways:

| Way | When | Who decides | What a5s does |
| --- | --- | --- | --- |
| Draft | The agent prepares something for a person to use, such as a pre-filled request or a case pack. No governed data changes. | The person who uses it, or doesn't | Allows it, and records it |
| Request | The action belongs to a governed process, such as a request in the unified app | The process routes it to a person, and makes the change if they approve | Allows it, marked with the level a5s applied, so the process approves it automatically only at level 2. Follows the decision through events, for the measures. |
| Held proposal | The action has no governed process of its own | The owner of the fields it touches, or a delegate where the scenario allows, on the decision surface | Holds the call, gets the decision, and makes exactly that call once it's approved |

A held proposal never pauses the agent. A colleague who's waiting for sign-off gets on with other work, and so does an agent:

1. When policy answers hold, a5s's middleware stores the exact call with the approvals service instead of making it, and tells the agent it's waiting for a decision. The agent carries on, and can tell the person it's working with.
2. The approvals service posts the proposal to the decision surface. It shows the actual call and its arguments, with the agent's evidence and summary beside them, never instead of them.
3. The decider approves, edits or rejects it there. The service checks who they are, and refuses a decision from anyone the scenario forbids, such as the person the agent acted for, or the agent's owner and deputy. Edited arguments go through policy again.
4. On approval, a5s makes the stored call itself, through the gateway, unless the records it changes have changed since the proposal was made. It records the decision, the decider and the timings, and tells the agent the outcome on the thread the proposal came from.
5. If nobody decides in time, the proposal is chased, then escalated along the chain the scenario sets, and in the end it expires as rejected [TBC: timings]. Suspending the instance, or moving it to another release, withdraws its pending proposals.

Because a5s makes the approved call itself, the agent can't change it after approval, and nothing waits inside a LangGraph run. That avoids two of LangGraph's interrupt behaviours: an interrupted step runs again when it resumes, and Deep Agents' batched interrupts match decisions to calls by position.

When an instance is suspended, or a part owner withdraws its approval, a5s also asks each governed process to withdraw or flag the instance's open requests there, and flags its drafts that nobody has used yet.

Decisions on proposals are taken only on the decision surface, never in a chat with the agent. At level 2, actions of an approved type run, through the governed process where there is one, and are reported. The agent owner can reverse them through the scenario's own process, never by rewinding the agent.

## How an agent lives

An instance lives in records: its identity, its register entry, its obligations, its triggers and its context. Compute is the only temporary part. Each piece of work goes like this:

1. **Wake.** A trigger arrives: a message from a person, an event from a system, a schedule, an obligation falling due, a sweep, or a decision on a held proposal. A sweep is a fallback schedule that runs only while the instance is idle, and starts no model when nothing has changed.
2. **Prepare.** The scheduler checks that the instance is active and has budget left, and that the thread the work belongs to has no other run active. Then it works out what has fallen due, and gathers the context: the thread, the person's profile, a brief of the case built from records, and the notebook.
3. **Build.** It creates the agent with `create_deep_agent` on that thread: the person's conversation, the case's thread, or a new one for a sweep. The agent gets the release's instructions and skills, only the granted tools, its context, and a5s's policy, ledger, masking and budget middleware.
4. **Work.** The agent plans, reads, drafts and hands parts to subagents. Every call passes policy in the middleware and again at a gateway.
5. **Propose or act.** Drafts and requests go to people as they're made, and held proposals go to the approvals service. A level-2 action runs and is reported.
6. **Remember.** The agent updates the person's profile and its notebook through typed tools, which check sources, size and masking.
7. **Sleep.** The run ends. Its credentials expire, its sandbox is discarded, and its obligations and contact log are updated. The thread stays, for next time.

- **Obligations** are worked out by code from the scenario's records, such as cases past their turnaround time or exceptions near expiry, never inferred by the model. Each has a due time, an escalation chain and a contact log, and the scheduler wakes the instance when one falls due. The model drafts and summarises. It doesn't decide what's owed.
- **Reminders** that people ask for go through a typed tool. The agent offers one, and the person confirms it with a control the model can't use, such as a button in the chat client. It must be of a type the release lists, and content from outside the organisation can't set one.
- **Triggers and schedules** are part of the release, and an agent can't create its own.
- **One active run for each thread.** An agent can talk to many people at once, but each conversation or case runs one thing at a time, and new messages and triggers for it queue behind the active run. Policy reads the settings and the instance's status live at every call.
- **Repeats are safe.** If a run crashes, LangGraph re-runs the step it was in, so tools are idempotent and ledger entries are keyed by tool call. A scheduled run fires at most once, and a run that's cut off waits for its agent owner to review it instead of restarting.

## Context and memory

An agent is only a colleague if it remembers. a5s keeps five kinds of context, each governed in proportion to its risk:

| Context | What it is | Written by | Checked by |
| --- | --- | --- | --- |
| Conversations | One ongoing conversation with each person, whichever channel they use. Older turns are summarised as it grows, and the full history stays searchable. | The conversation itself | The person, who can see all of it |
| Profiles | What the agent knows about each person it works with: their role, parts, preferences and open topics, in about a page | The agent, only from what that person says or does | The person, who can see, correct or delete it |
| Case briefs | The state and history of each case, request or exception, built fresh for every run | Code, from the scenario's records | Nobody needs to: the records are the source |
| Notebook | What the instance has learned doing its job, such as the usual causes of a recurring failure, each entry with its source | The agent | The agent owner, by sampling. Entries expire [TBC: 90 days]. |
| Instructions and skills | How the agent works | Only a release | The release approver |

- **One conversation per person.** People pick up where they left off, a week or a month later, on Teams, email or the decision surface. In a group conversation, the agent shares only what everyone present may see.
- **Profiles come only from the person themselves.** An agent never records what others say about someone. Profiles hold no classified values, and are deleted when the person leaves [TBC: with the data protection officer].
- **Records beat recollection.** Commitments, decisions and obligations live in records, never only in a conversation, so summarising can't lose them. When the agent's recollection and a record disagree, the record wins.
- **Notes aren't instructions.** A notebook entry that would change how the agent works becomes a proposal for its next release. Entries that came from outside content are marked as such, and are never taken as instructions.
- **Classified values are tokenised** in conversations and notes at rest, and shown back only to people who may see them. Conversations are kept for [TBC].
- **Versions.** Each run reads fixed versions of the profile and the notebook, and the ledger records which, so a poisoned entry can be traced and removed.

Rich context is safe enough because a5s's controls don't live in it. However a conversation or note is poisoned, the agent still can't approve, confirm or reach data outside its grant, every call is still checked outside the model, and its drafts and requests still go to people. The worst a poisoned context can do is mislead: a poor draft, a misleading message, or at level 2 a wrong change of an approved type within its limits, all recorded and reversible.

## Channels

Each instance talks to people under its own identity, such as its own mailbox or bot account, never a person's, and says it's an AI agent. The scenario sets the contact rules and the escalation chain, and a release can tighten them but not loosen them. By default, an agent sends routine items in one digest a day and urgent ones at once, only in working hours, and within a limit per person. A message takes the classification of what it quotes, so it links to records instead of quoting classified values. Replies continue the conversation.

## Data protection

- **Classes come from the scenario.** Each field's class comes from the scenario's settings, and decides what's masked and which models may see it.
- **Masking.** The ledger, the context, traces and evaluation sets hold masked or tokenised values with their record keys, so evidence stays usable without holding restricted data outside live systems.
- **Models by grant.** An instance can reach only the models approved for the classes of data it's granted, and the model gateway enforces this by the instance's identity. Managed features that call a model, such as summarisation or evaluation, count as models too.
- **Outside content.** Documents and messages from outside the organisation go through an extractor that has no tools. It returns typed fields tagged with their source, and policy can refuse to use a value for a purpose because of where it came from. Classifiers such as Prompt Shields, Model Armor or Bedrock Guardrails add signals. They're never the boundary.

## Evidence

For every action, the ledger records the instance and its release, the person it acted for, the trigger, the tool or model and its masked arguments, the policy decision and policy version, any approval with its decider and review time, the versions of the profile and notebook it read, and the outcome. Entries are append-only and hash-chained, kept where the team that runs a5s can't change them, and readable by whoever assures the scenario, such as internal controls. Because the ledger holds tokens rather than personal data, deleting a token's mapping when its retention ends removes the data without breaking the chain.

The same events go out as OpenTelemetry spans, using the GenAI conventions (`invoke_agent`, `execute_tool`), plus a5s attributes for what those lack, such as the person acted for and the policy decision. The conventions are still at Development stability, so a5s pins a version. Traces in LangSmith or elsewhere are for debugging and are kept briefly. They aren't the evidence.

## Assurance

- **Release tests.** Each release passes its regression suite, including the scenario's tests and attempted injections, before it's approved.
- **Measures.** For each instance, type of action and reviewer: work handled, proposals, acceptance and edit rates, review times, chases and escalations, and cost. Almost no rejections with very short reviews flags rubber-stamping.
- **Samples.** People the scenario names, never the agent owner or deputy, grade stratified samples of each instance's work. The results are the evidence for moving it up a level, and they set its cap ([autonomy](agent-model.md#autonomy)).
- **Drift.** Long-lived instances re-run their suite on a schedule, because models change under them.

## What comes from Deep Agents, and what a5s adds

| a5s needs | Deep Agents and LangGraph give | a5s adds |
| --- | --- | --- |
| The agent loop | `create_deep_agent`: a virtual filesystem, subagents, skills, summarisation, and planning if wanted | Nothing. It's used as it is. |
| Context that lasts | Threads kept by a Postgres checkpointer, a store, summarisation and offloading of large results, and `AGENTS.md` memory | One conversation per person across channels, profiles people can see and correct, case briefs from records, and a notebook with sources and expiry |
| Proposals that wait for days | Interrupts, which park a run until it's resumed | Held calls kept outside the run, so nothing parks and the agent can't change an approved call |
| A check on every call | Middleware hooks such as `wrap_tool_call`, and filesystem permissions that allow by default | Policy that denies by default, on every agent and subagent, and again at the gateways |
| Durable state | A Postgres checkpointer and store, which run anywhere | One active run for each thread, with the rest queued |
| Tools | The MCP client in `langchain` 1.4 and later | Registered tool servers, pinned tool definitions and risk attributes |
| Tracing and evaluation | LangSmith and OpenTelemetry | The ledger, measures and samples |
| Personal data | PII middleware, with five built-in regex types | Masking by class, from the scenario's settings |

The LangGraph Agent Server adds cron jobs, versioned assistants, sign-in handlers and an A2A endpoint, but only where it runs, and a self-hosted one needs a LangSmith licence. a5s doesn't depend on them. It has its own scheduler, releases, identity and A2A, so it runs the same on every host, with or without the Agent Server.

Deep Agents is still before 1.0 and releases several times a week, so a5s pins its versions and treats each upgrade as a release. It needs deepagents 0.7.25 or later, which fixed a way around its approval rules.

## Agent to agent

Agents call each other over A2A, and only between registered instances. The agent called treats a request like any other, within its own job, grants and autonomy. Authority doesn't pass from caller to callee, and the ledger links both runs.

## Hosting

The kernel runs as a set of services on the host's container platform, and adapters connect it to the host. Nothing waits inside a host's session: threads live in a5s's checkpointer and held calls in its approvals store, so session limits don't matter to conversations and proposals that last for weeks.

| Host | Runs execute in | Identity | Gateways | Notes |
| --- | --- | --- | --- | --- |
| Any | a5s's own workers [TBC] | The organisation's identity provider, or SPIFFE [TBC] | An MCP gateway such as agentgateway, with a5s policy, and a model gateway [TBC] | The most control, and the most to run |
| AWS | AgentCore Runtime | AgentCore Identity: a workload identity and a token vault | AgentCore Gateway and Policy, which also uses Cedar | The best-documented home for Deep Agents. A session ends after 15 idle minutes or 8 hours, by default. |
| Microsoft | Foundry hosted agents | Entra Agent ID: an identity for each instance, with the agent owner and deputy as its owners and the platform owner as its sponsor | a5s's own | Fits a Microsoft 365 estate, with Purview audit. Microsoft documents its own check before each tool call only for Copilot Studio. |
| Google | Agent Runtime | Agent Identity: a certificate that lasts 24 hours, with tokens bound to it | Agent Gateway, managed only for Agent Runtime so far | The strongest identity. Sessions last up to 7 days. |

Each host's registry gets a copy of the register, for discovery only. a5s's register and settings stay the source.

## Standards

| For | Standard |
| --- | --- |
| Tools | MCP, specification 2026-07-28 |
| Agent to agent | A2A v1.0 |
| Skills and instructions | Agent Skills and `AGENTS.md` |
| Identity and delegation | OAuth as MCP uses it, and token exchange (RFC 8693) with the agent as the client and the person as the subject, following the IETF's WIMSE work |
| Policy | Cedar [TBC] |
| Telemetry | OpenTelemetry GenAI conventions, at a pinned version |

## What a5s won't do

- Let an agent change anything in its own release in production.
- Let a model approve an action. A person does, or a policy rule with a fixed answer.
- Give a model or a sandbox credentials.
- Take decisions on proposals anywhere but the decision surface, whether in a vendor's inbox or a chat with the agent.
- Let an agent act without telling anyone. There's no level above 2.
- Write to a system of record except through its own governed process.
