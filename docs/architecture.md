# Architecture

**Status:** Draft v0.1 · **Under:** [a5s](../README.md)

a5s runs agents the way an operating system runs programs. It installs them, gives each one an identity and only the rights it needs, wakes it when there's work, checks every call it makes, and keeps a record of what happened.

| An operating system has | a5s has |
| --- | --- |
| Programs | Agent definitions, released as tested versions |
| User accounts | An identity for each agent instance, with a named owner |
| Processes | Runs: one piece of work, on the thread it belongs to |
| A scheduler | Triggers: messages, events, schedules and obligations falling due |
| System calls and permissions | Tool and model calls, each checked against policy |
| Memory and files | Scratch space for each run, the agent's conversations and notes, and shared knowledge that agents only read |
| Drivers | Tool servers, over MCP, for the systems agents use |
| Messages between processes | A2A between agents, and channels to people |
| An audit log | The evidence ledger |

The [agent model](agent-model.md) defines definitions, releases, instances, threads and runs, and the terms used here: parts and their owners, grants, types of action, settings, governed processes, the decision surface, and whom an agent acts for. The [critique](critique.md) records the loopholes found in this design and how it answers each one.

## The kernel

| Component | Does | Built on |
| --- | --- | --- |
| Register | Holds definitions and their releases in git, and instances, with their identities, status and any approval the scenario's settings don't hold, in its database [TBC]. Every change goes in the ledger. | Git, copied to the host's registry for discovery only |
| Identity | Gives each instance its own identity, and gets short-lived credentials for each call. The model never sees them. | The host's agent identity ([hosting](#hosting)) |
| Policy | Decides each tool and model call: allow, hold for a person, or deny. Reads the scenario's settings live for every call. | Cedar [TBC] |
| Gateways | The only routes from an agent to systems and to models. They ask policy for every call, hold the credentials, tag what comes back with its source, record held calls, and strip what mustn't leave. | MCP, and the host's gateway where it has one |
| Approvals | Gets a person's decision on each held call, on the decision surface, has the gateway make the call once it's approved, and follows the requests agents hand to governed processes | Its own store, of calls the gateway signed |
| Scheduler | Wakes instances on triggers, works out what they owe people, runs them within budget, tells them when decisions arrive, and stops them when they're suspended | Its own code, with threads kept by LangGraph's checkpointer |
| Context | Keeps each instance's conversations, what it knows about the people it works with, and its notebook, with sources, masking and expiry | LangGraph threads and store, and Deep Agents' summarisation |
| Channels | Lets agents talk to people inside the organisation, under one identity per agent, within contact rules counted per person | Teams or email [TBC] |
| Ledger | Records every action, append-only, where the team that runs a5s can't change it | Immutable storage [TBC], OpenTelemetry |
| Assurance | Tests each release, measures how people review proposals, and samples work as the evidence for each agent's level | LangSmith evaluations and annotation queues |

## Policy

Every call meets three lines, so that no single failure lets an agent do what it mustn't:

1. **Rights.** An instance's identity holds only its grant. Actions the scenario forbids, such as approving or confirming in the lean scenario, are never granted, so no instruction can talk an agent into them.
2. **The gateways.** Tool calls go through the tool gateway and model calls through the model gateway, which ask policy for every call. They hold even if the agent's own code is bypassed. Rules copied into a host's own policy engine can only add restrictions.
3. **The middleware.** a5s's LangChain middleware asks the same policy first, on the agent and on every subagent, including Deep Agents' built-in general-purpose one, so the agent gets a clear reason and can change course.

Policy answers **allow**, **hold** or **deny**, from:

- **who:** the instance, and the people it acts for. Acting for people, an agent sees and shares only what all of them may see.
- **what:** the tool or model, its risk attributes (reads, writes, sensitive, destructive, sends outside) and the type of action.
- **on what:** the fields it touches, the parts they belong to, their classes of data, and where each value came from. An action that touches fields in several parts needs each part's approval, and works at the lowest of their levels.
- **context:** the instance's levels, the actions counted so far, the run's budget, and the scenario's switches, such as the lean scenario's switch for each request type until it moves to the unified app.

Policy denies by default, and fails closed:

- If policy can't be reached, every call is denied.
- If the settings can't be read, every call that touches a part is denied.
- If the counts can't be read, every counted call is denied: drafts, requests and level-2 actions.
- If the ledger can't be written, every call is denied.

A run stopped this way ends, and its trigger waits in the queue ([when things fail](#when-things-fail)).

**Settings** are read live and never copied, because a stale copy is a setting nobody approved. A cache is allowed only if a change to the settings clears it at once. a5s acts only on settings whose approval carries their owner's own authenticated sign-off, and the ledger records the version of the settings that decided each call.

**Counts.** Drafts, requests and level-2 actions are all counted, per piece of work and across all their types of action. Code decides what a piece of work is, never the model: the source document or conversation for drafts, and the check or issue on the data platform for a clean-up. Each count is checked and reserved in the same step as the policy decision, so parallel calls can't overshoot it, and it's reconciled against the governed process's own log. As a backstop, an instance's actions in each part are also counted over a window [TBC], up to the same limit. When a piece of work reaches a limit the scenario sets, such as the lean framework's mass-change size, a5s stops it and sends the rest to whoever approves that limit, as one piece of work. Work planned to go past the limit goes to them from the start.

**Packs.** A base pack holds what a5s always enforces, including these fail-closed rules, and each scenario adds a pack that can only add restrictions. Packs change like the rest of the enforcement ([independence](#independence)), and the ledger records the version that decided each call.

## Provenance: who said what

Many loopholes come down to one question: whose words is the agent acting on? a5s answers it in code, never by asking the model.

- **Every value carries its source.** The gateway tags what tools return with the system, the field and who last wrote it. Channels tag messages with their sender, and the extractor tags what it extracts. The tags travel with the value into summaries, notes, drafts and requests, and the model can't remove them.
- **Outside words never reach an agent raw.** Documents, email from outside the organisation, and free text that an outside party wrote, such as a comment on a supplier portal request, go only through the extractor. A run that has seen outside content stays marked: it can't write the notebook, and what it drafts or raises says so to whoever decides.
- **Outside values can't steer verification.** By default, policy refuses a value from outside as a contact for verifying a change, as a recipient or as a link. A request carries each value's source, and the governed process never approves a value from a document automatically.
- **Facts that decide are computed.** Anything a person relies on to decide, such as which contact to call back, whether a check was done, whether two changes match, or which items go in a sample, is computed by code from records and shown by the decision surface. An agent can explain these facts, but it can't assert them.
- **Acting for people.** A run acts for everyone whose words it serves: whoever sent the message, set the reminder, or wrote the reply or note that a request came from, and everyone in a group conversation. They're named on what the agent drafts or raises, none of them may decide it, and a request that came from a person's words never goes through at level 2.
- **Who can talk to an agent.** Only people inside the organisation, identified by their directory ID. Email starts a run only from an internal sender that passes DMARC and matches the directory, and the agent never answers a Reply-To address or recipients someone added. Any other email goes to the extractor as a document. A reused address never inherits a former owner's conversation.

## Proposals and approvals

At level 1 an agent prepares and people decide. Its work reaches a person in one of three ways:

| Way | When | Who decides | What a5s does |
| --- | --- | --- | --- |
| Draft | The agent prepares something for a person to use, such as a pre-filled request or a case pack. No governed data changes. | The person who uses it, or doesn't | Allows it, and records it |
| Request | The action belongs to a governed process, such as a request in the unified app | The process routes it to a person, and makes the change if they approve | Allows it. The process checks the instance's level and status with a5s before approving anything automatically, and refuses if it can't check. a5s follows the decision through events, for the measures. |
| Held proposal | The action has no governed process of its own | The owner of the fields it touches, or a delegate where the scenario allows, on the decision surface | Holds the call, gets the decision, and makes exactly that call once it's approved |

A held proposal never pauses the agent. A colleague who's waiting for sign-off gets on with other work, and so does an agent:

1. When policy answers hold, the gateway records the exact call, signed, instead of making it, and the agent is told it's waiting for a decision. The agent carries on, and can tell the people it's working with.
2. The approvals service posts the proposal to the decision surface. It shows the actual call and its arguments, with the agent's evidence and summary beside them, never instead of them.
3. The decider approves, edits or rejects it there. The service checks who they are, and refuses a decision from anyone the scenario forbids, such as the people the agent acted for, or the agent's owner and deputy. Edited arguments go through policy again.
4. On approval, the gateway makes the stored call as the instance, after policy checks it again with the approval as an input, and only if the records it changes haven't changed since. a5s records the decision, the decider and the timings, and tells the agent the outcome on the thread the proposal came from.
5. If nobody decides in time, the proposal is chased, then escalated along the chain the scenario sets, and in the end it expires as rejected [TBC: timings]. Suspending the instance, or moving it to another release, withdraws its pending proposals.

Because a5s makes the approved call itself, the agent can't change it after approval, and nothing waits inside a LangGraph run. That avoids two of LangGraph's interrupt behaviours: an interrupted step runs again when it resumes, and Deep Agents' batched interrupts match decisions to calls by position.

- **Withdrawals.** When an instance is suspended, or a part owner withdraws its approval, a5s asks each governed process to withdraw or flag the instance's open requests there, and the suspension is complete only when each one confirms. Drafts nobody has used yet are flagged.
- **Handoffs.** When an agent hands work to a person, such as a draft the requester submits or a question it routes to a delegate, it attaches a handoff note, and any flags it raised go on the request itself, so whoever decides sees them. Flags that keep recurring become checks in the governed process.
- **Where decisions happen.** Decisions on proposals are taken only on the decision surface, never in a chat with the agent. At level 2, actions of an approved type run, through the governed process where there is one, and are reported. The agent owner can reverse them through the scenario's own process, never by rewinding the agent.

## How an agent lives

An instance lives in records: its identity, its register entry, its obligations, its triggers and its context. Compute is the only temporary part. Each piece of work goes like this:

1. **Wake.** A trigger arrives: a message from a person, an event from a system, a schedule, an obligation falling due, a sweep, or a decision on a held proposal. Every agent can be talked to, because every release includes a message trigger, acting for the sender. A sweep is a fallback schedule that runs only while the instance is idle, and starts no model when nothing has changed.
2. **Prepare.** The scheduler checks that the instance is active and that the thread the work belongs to has no other run active, and reserves the run's budget. Then it works out what has fallen due, and gathers the context: the thread, the people's profiles, a brief of the case built from records, and the notebook.
3. **Build.** It creates the agent with `create_deep_agent` on that thread: the person's conversation, the case's thread, or a new one for a sweep. The release's instructions and skills load read-only, as part of the system prompt, never through Deep Agents' editable memory files. The agent gets only the granted tools, its context, and a5s's policy, ledger, masking and budget middleware.
4. **Work.** The agent plans, reads, drafts and hands parts to subagents, which run within the same run. Every call passes policy in the middleware and again at a gateway. The agent's file tools write only to a scratch area that's wiped after the run, and attachments go only to the extractor.
5. **Propose or act.** Drafts and requests go to people as they're made, and held calls go to the approvals service. A level-2 action runs and is reported.
6. **Remember.** The agent updates profiles and its notebook through typed tools, which check sources, size and masking.
7. **Sleep.** The run ends. Its credentials expire, its sandbox is discarded, and its obligations and contact log are updated. The thread stays, for next time.

- **Obligations** are worked out by code from the scenario's records, such as cases past their turnaround time or exceptions near expiry, never inferred by the model. Each has a due time from the governed process, an escalation chain and a contact log, and the scheduler wakes the instance when one falls due. There's one obligation per record and person, whichever agents are involved, so two agents never chase the same thing. The model drafts and summarises. It doesn't decide what's owed.
- **Waiting on.** A person can tell an agent what they're waiting for, such as a call-back from a supplier. The agent offers a "waiting on" note, the person confirms it with a button, and it goes on the case: chases to them pause until the date they give, and any escalation shows it. A chase about a sensitive change says that verification comes first.
- **Reminders** that people ask for go through a typed tool. The agent offers one, and the person confirms it with a control the model can't use, such as a button in the chat client. It must be of a type the release lists, and content from outside the organisation can't set one.
- **Triggers and schedules** are part of the release, and an agent can't create its own.
- **One active run for each thread.** An agent can talk to many people at once, but each conversation or case runs one thing at a time, and new messages and triggers for it queue behind the active run. Policy reads the settings and the instance's status live at every call.
- **Repeats are safe.** If a run crashes, LangGraph re-runs the step it was in, so tools are idempotent, with keys made from the piece of work, the record and the change. A call that times out tells the model it's pending, not failed, so it isn't retried as a new call. A scheduled run fires at most once, and a run that's cut off releases its thread and waits for review.

## Context and memory

An agent is only a colleague if it remembers. a5s keeps five kinds of context, each governed in proportion to its risk:

| Context | What it is | Written by | Checked by |
| --- | --- | --- | --- |
| Conversations | One ongoing conversation with each person, whichever channel they use, organised in topics, such as one per request | The conversation itself | The person, who can see all of it, summaries included |
| Profiles | What the agent knows about each person it works with: their role, parts, preferences and open topics, in about a page | The agent, only from what that person says or does | The person, who can see, correct or delete it |
| Case briefs | The state and history of each case, request or exception, built fresh for every run | Code, from the scenario's records | Nobody needs to: the records are the source |
| Notebook | What the instance has learned doing its job, such as the usual causes of a recurring failure, each entry with its sources | The agent, only from records and tool results | The agent owner, by sampling. Entries expire [TBC: 90 days]. |
| Instructions and skills | How the agent works | Only a release | The release approver |

- **A conversation never runs out of room.** It never resets: when it nears the model's limit, older turns are summarised and it carries on, so people can keep talking to an agent for months. Each turn sends the summary, the recent turns, the case brief, the profile and what a search of the history finds, within a cap [TBC], so a long conversation stays affordable.
- **Topics keep things apart.** Each request or case a person discusses gets its own topic, so details don't blur together in a summary. The agent keeps an index of topics, can bring an old one back, and the person can start a topic afresh.
- **Summaries are open.** Summaries keep the source tags of what they summarise, and outside content stays as a reference rather than a paraphrase. They're versioned, and the person can see and correct them.
- **Group conversations** each have their own thread, which draws only on that thread, records and what members choose to bring in. The agent shares only what everyone present may see, and posts links rather than values, because people who join later can read earlier posts.
- **Profiles come only from the person themselves.** An agent never records what others say about someone. Each release lists the preferences people can set, such as how they like fixes grouped, and they're kept in the profile. Profiles hold no classified values, writes to them go through one writer, so a parallel run can't undo a person's correction, and they're deleted when the person leaves [TBC: with the data protection officer].
- **The notebook can't carry one person's words to another.** Notes come only from records and tool results, never from a conversation or a marked run. Each note takes the highest class of data among its sources, and loads only for runs whose people may all see that class. What a person says stays in their own conversation and profile.
- **Records beat recollection.** Commitments, decisions and obligations live in records, never only in a conversation, so summarising can't lose them. When the agent's recollection and a record disagree, the record wins.
- **Notes aren't instructions.** A note that would change how the agent works becomes a proposal for its next release.
- **Classified values are tokenised** at the gateway, so the model sees a raw value only where its work needs one. Values are shown back only in fields code fills in, to people who may see them. Conversations are kept for [TBC], and archived when a person leaves.
- **Versions.** Each run reads fixed versions of the profiles, the notebook and the summaries, and the ledger records which, so a poisoned entry can be traced and removed.

Rich context is safe enough because a5s's controls don't live in it. However a conversation or note is poisoned, the agent still can't approve, confirm or reach data outside its grant, every call is still checked outside the model, outside words keep their tags, and its drafts and requests still go to people. The worst a poisoned context can do is mislead: a poor draft, a misleading message, or at level 2 a wrong change of an approved type within its limits, all recorded and reversible.

## Channels

Each agent talks to people under one identity, such as its own mailbox or bot account, never a person's, whichever of its instances does the work, and it says it's an AI agent. Messages route to the right instance by record. The scenario sets the contact rules and the escalation chain, and a release can tighten them but not loosen them.

- **Contact is counted per person.** Each person gets at most one digest a day from all the agents together, within one limit across them all. Urgent items go at once to someone in the escalation chain who's at work, using people's time zones and holiday calendars, and escalation pauses outside working hours. a5s measures whether messages are read, not just sent.
- **What a message can carry.** Text, and links to records that the governed process builds. Every other link, image and piece of HTML is stripped, and nothing goes to anyone outside the organisation. A message takes the classification of what it quotes, so it links to records instead of quoting classified values.
- **When an agent can't help.** If an agent is suspended, out of budget or stopped by an outage, the channel service replies in code, names who to ask instead, and hands urgent obligations to the next person in the chain.
- Replies continue the conversation.

## Data protection

- **Classes come from the scenario.** Each field's class comes from the scenario's settings, and decides what's masked and which models may see it.
- **Masking.** The ledger, the context, traces and evaluation sets hold masked or tokenised values with their record keys, so evidence stays usable without holding restricted data outside live systems.
- **Models are pinned.** Each approved model names its provider, deployment, region and dated version, and the model gateway checks every call and response against it, including those inside managed features such as summarisation. It refuses any failover or reroute to a model that isn't approved for the same classes of data, so fixing an outage can't send data somewhere new. An instance reaches only the models approved for the classes of data it's granted.
- **Workers are closed.** Workers and sandboxes hold no credentials for any system, and can reach only the gateways and a5s's own trace collector, which masks before anything is stored. Turning on tracing can't send data elsewhere.
- **Outside content.** The extractor has no tools, and fixed schemas with no free-text fields. It reads a document as it appears on the page, and flags any difference from the text hidden underneath. For questions about an outside document, such as what a contract says about price reviews, it can also answer in free text, marked as outside content, shown to the person, and never used as an instruction or a field value. Classifiers such as Prompt Shields, Model Armor or Bedrock Guardrails add signals. They're never the boundary.
- **Tool servers and skills.** The gateway refuses requests from tool servers to ask people for input or to run the agent's model. Skills are copied into the release and pinned by hash, never loaded from elsewhere.

## Independence

a5s is built and run by a team whose own work it partly checks, so it doesn't rely on that team's word.

- **Enforcement changes like agents do.** A change to the kernel, a gateway, a policy pack, masking, or a tool a governed process offers agents is a release like an agent's. Someone outside the team that runs a5s, and outside its manager's reporting line, approves it [TBC: who], after assurance re-runs the scenario's tests on what's deployed.
- **Overrides are emergency access.** Switching off a fail-closed rule, editing a thread's saved state by hand, or resuming an instance someone else suspended counts as emergency access, which the scenario's assurance reviews.
- **The ledger is anchored outside.** Each day, the ledger's latest hash is lodged with assurance, in a store the team that runs a5s doesn't administer, so a rewritten history shows.
- **Graders and deciders are independent.** Nobody from the team that built an agent grades its samples or decides its proposals. Code draws the samples, and the ledger records what they were drawn from, and how.

## When things fail

The governed processes work without agents, so when a5s can't run safely it stops, says so, and people carry on in those processes.

- **Runs end and wait.** A run whose dependency fails ends, and its trigger goes back in the queue. A circuit breaker pauses new runs while the dependency is down, and tells the people affected to work in the governed process directly.
- **Budgets are kept apart.** Budgets are kept per source of triggers and per person, reserved before a run starts, with a share kept for obligations, so one person or a flood of outside requests can't starve the rest. Outside parties are rate-limited.
- **Releases are kept safe.** A failed drift test lowers an agent's cap. A security advisory withdraws every release that pins the affected version. Releases include tested migrations of thread state, both ways, so moving between releases doesn't strand conversations, and only the runtime writes that state.

## Evidence

For every action, the ledger records the instance and its release, the people it acted for, the trigger, the tool or model and its masked arguments, the policy decision, the policy and settings versions, any approval with its decider and review time, the versions of the profiles, notebook and summaries it read, a hash of the thread state it started from, and the outcome. Entries are append-only and hash-chained, kept where the team that runs a5s can't change them, and readable by whoever assures the scenario, such as internal controls. Because the ledger holds tokens rather than personal data, deleting a token's mapping when its retention ends removes the data without breaking the chain.

The same events go out as OpenTelemetry spans, using the GenAI conventions (`invoke_agent`, `execute_tool`), plus a5s attributes for what those lack, such as the people acted for and the policy decision. The conventions are still at Development stability, so a5s pins a version. Traces are for debugging and are kept briefly. They aren't the evidence.

## Assurance

- **Release tests.** Each release passes its regression suite, including the scenario's tests and attempted injections, before it's approved.
- **Measures.** For each instance, type of action and reviewer: work handled, proposals, acceptance and edit rates, review times, chases and escalations, and cost. Almost no rejections with very short reviews flags rubber-stamping. Review times are weighted by the size of what was reviewed, graders' times are measured too, and requester–confirmer pairs on sensitive changes are watched.
- **Samples.** Code draws stratified samples from all of an instance's work, per part and type of action, and people the scenario names grade them, never anyone from the team that built the agent. The results are the evidence for moving it up a level, and they set its cap ([autonomy](agent-model.md#autonomy)).
- **Drift.** Long-lived instances re-run their suite on a schedule, because models change under them. A failure lowers the cap.

## What comes from Deep Agents, and what a5s adds

| a5s needs | Deep Agents and LangGraph give | a5s adds |
| --- | --- | --- |
| The agent loop | `create_deep_agent`: a virtual filesystem, subagents, skills, summarisation, and planning if wanted | Instructions and skills loaded read-only, file tools that write only to a scratch area, attachments sent to the extractor, and subagents that run within the run |
| Context that lasts | Threads kept by a Postgres checkpointer, a store, summarisation and offloading of large results, and `AGENTS.md` memory | One conversation per person across channels, in topics, profiles people can see and correct, case briefs from records, and a notebook with sources and expiry |
| Proposals that wait for days | Interrupts, which park a run until it's resumed | Held calls kept outside the run, so nothing parks and the agent can't change an approved call |
| A check on every call | Middleware hooks such as `wrap_tool_call`, and filesystem permissions that allow by default | Policy that denies by default, on every agent and subagent, and again at the gateways |
| Durable state | A Postgres checkpointer and store, which run anywhere | One active run for each thread, with the rest queued, and a hash of the state in the ledger |
| Tools | The MCP client in `langchain` 1.4 and later | Registered tool servers, pinned tool definitions, risk attributes, and no requests from tool servers for input or sampling |
| Tracing and evaluation | LangSmith and OpenTelemetry | The ledger, measures and samples |
| Personal data | PII middleware, with five built-in regex types | Masking by class, from the scenario's settings |

The LangGraph Agent Server adds cron jobs, versioned assistants, sign-in handlers and an A2A endpoint, but only where it runs, and a self-hosted one needs a LangSmith licence. a5s doesn't depend on them. It has its own scheduler, releases, identity and A2A, so it runs the same on every host, with or without the Agent Server.

Deep Agents is still before 1.0 and releases several times a week, so a5s pins its versions and treats each upgrade as a release. It needs deepagents 0.7.25 or later, which fixed a way around its approval rules.

## Agent to agent

Agents call each other over A2A, only between registered instances, with typed requests. The people the caller acts for travel with the call, by token exchange, and the agent called works only within what it, the caller and those people may all do. Its answers are filtered by class of data. Authority doesn't pass from caller to callee, a marked run's mark travels with its calls, and the ledger links both runs.

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
- Let an agent assert a fact that someone relies on to decide, such as that a call-back was done.
- Give a model or a sandbox credentials.
- Take decisions on proposals anywhere but the decision surface, whether in a vendor's inbox or a chat with the agent.
- Let an agent act without telling anyone. There's no level above 2.
- Write to a system of record except through its own governed process.
