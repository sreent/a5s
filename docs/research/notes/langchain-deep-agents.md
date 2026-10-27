# LangChain Deep Agents and the LangChain / LangGraph / LangSmith stack as a foundation for a self-built enterprise "agent OS" (state as of 27 October 2026)

Method note: these notes rely mainly on primary sources. Those are the live docs.langchain.com pages (fetched 27 Oct 2026 as Markdown), PyPI and npm release metadata, LangChain changelogs and blog posts, GitHub security advisories, and AWS, Microsoft and Google docs. Release dates come from PyPI first-upload timestamps unless stated otherwise. Docs pages carry no "last updated" date, so a feature claim sourced only from a docs page reflects the docs as of 27 Oct 2026. The page says when a version gate exists (e.g. "requires deepagents>=0.6.8"), and PyPI dates for those versions are given where useful. The whole stack moves fast. deepagents shipped 25 patch releases between 20 Aug and 23 Oct 2026, so expect details to drift.

---

## Q1. Current architecture of Deep Agents: versions, planning, filesystem and backends, subagents, context management, skills, memory, CLI, and the LangChain 1.x middleware model

### Takeaway
Deep Agents (`deepagents`, MIT, still pre-1.0 at Python 0.7.32 as of 23 Oct 2026) is an "agent harness" built on LangChain `create_agent` and middleware, with LangGraph as the durable runtime. It ships a virtual filesystem with pluggable backends (state, store, local disk, local shell, Context Hub, composite, sandbox) and declarative filesystem permissions. It also provides subagents (sync, forked and async), automatic offloading and summarization, Agent-Skills-standard skills, AGENTS.md memory, and HITL via `interrupt_on`. Planning (`write_todos`) has been opt-in since v0.7 (Jul 2026). The old `deepagents-cli` is deprecated. The terminal agent is now "Deep Agents Code" (`dcode`), and LangChain now steers production users to "Managed Deep Agents" (public beta).

### Cited Findings

**Versions and release dates**
- `deepagents` (Python) latest is 0.7.32, uploaded 2026-10-23. Minor-line first releases: 0.0.1 on 2025-07-29, 0.1.0 on 2025-10-17, 0.2.0 on 2025-10-28, 0.3.0 on 2025-12-08, 0.4.0 on 2026-02-10, 0.5.0 on 2026-04-07, 0.6.0 on 2026-05-12, 0.7.0 on 2026-07-29. PyPI summary: "Production-ready, extensible agent harness with a built-in filesystem and context management, sub-agent delegation, skills, and long-term memory." — [PyPI deepagents](https://pypi.org/project/deepagents/#history)
- The JS/TS `deepagents` npm package is at 1.16.0, published 2026-10-26. 1.11.0 shipped 2026-07-16 and 1.15.0 on 2026-10-13. — [npm deepagents](https://www.npmjs.com/package/deepagents)
- Underlying libraries: `langchain` 1.0.0 shipped 2025-10-17, 1.4.0 on 2026-09-03, latest 1.4.7 on 2026-10-21. `langgraph` 1.0.0 shipped 2025-10-17, 1.2.0 on 2026-05-12, latest 1.2.18 on 2026-10-26. — [PyPI langchain](https://pypi.org/project/langchain/#history); [PyPI langgraph](https://pypi.org/project/langgraph/#history)
- Deep Agents 0.6 was announced at LangChain's Interrupt conference (post dated 14 May 2026) with "code interpreter, typed streaming, and DeltaChannel". — [LangChain Interrupt 2026 overview](https://langchain.com/blog/interrupt-2026-overview)
- Release notes from late Oct 2026 include 0.7.30 (22 Oct): async subagent follow-ups can queue without interrupting, and `AsyncSubAgent` gained `notify_parent` and `webhook`. 0.7.31 (23 Oct) added execution output retention metadata to tracing. 0.7.32 (23 Oct) lazy-loads provider SDKs. — [GitHub deepagents releases](https://github.com/langchain-ai/deepagents/releases)
- The docs describe Deep Agents as "the agent harness for complex, multi-step work. It adds planning, a virtual filesystem for context, subagent spawning, and long-term memory on top of LangChain and LangGraph". The library "uses the LangGraph runtime for durable execution, streaming, human-in-the-loop". — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- The docs organize the harness into four components: the execution environment (tools, virtual filesystem, filesystem permissions, code execution), context management (skills, memory, summarization and offloading, prompt caching), delegation (task planning, subagents) and steering (HITL). — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)

**Planning (`write_todos`)**
- "Starting in v0.7 task planning is opt-in only. In earlier versions, task planning middleware was included by default." It is enabled by passing `TodoListMiddleware()`, which gives the agent a `write_todos` tool. Task statuses are `pending`, `in_progress` and `completed`, persisted in agent state. — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- A third-party review (Wavect, 23 Aug 2026) says maintainers' evals found default planning "added cost and latency without improving performance". It credits the 0.7 release with a 65% cut in base prompt and tool-description tokens. This is a vendor-blog claim and has not been verified against LangChain release notes. — [Wavect review](https://wavect.io/blog/langchain-deep-agents-review/)

**Virtual filesystem and backends**
- Built-in file tools: `ls`, `read_file` (multimodal for images, video, audio, PDF and PPT), `write_file`, `edit_file`, `delete` (requires deepagents>=0.7), `glob`, `grep`. `execute` is available only with sandbox backends or LocalShellBackend. — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview); [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- Backends:
  - `StateBackend` (default): thread-scoped files stored in LangGraph state and persisted through the checkpointer. It is shared between the supervisor and its subagents.
  - `FilesystemBackend`: real disk under `root_dir`.
  - `LocalShellBackend`: disk plus host shell with "no sandboxing".
  - `StoreBackend`: cross-thread durable storage via a LangGraph `BaseStore` such as Postgres or Redis.
  - `ContextHubBackend`: files stored in a LangSmith Context Hub repo.
  - Sandbox backends: LangSmith, AgentCore, Daytona and others.
  - `CompositeBackend`: routes by path prefix, longest prefix wins, typically `/memories/` to the store and everything else to state.

  — [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- Custom backends implement `BackendProtocol`. To support `execute`, they implement `SandboxBackendProtocol`. "For custom validation logic beyond path-based allow/deny rules (rate limiting, audit logging, content inspection), enforce enterprise rules by subclassing or wrapping a backend" (backend "policy hooks"). — [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- `StoreBackend` namespace factories receive a LangGraph `Runtime` with `context` (e.g. `user_id`), `server_info` (assistant ID, graph ID, authenticated user) and `execution_info` (thread, run and checkpoint IDs). This requires deepagents>=0.5.2. Without a namespace factory, "the legacy default uses the `assistant_id`… all users of the same assistant share the same storage." — [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- Declarative filesystem permissions (deepagents>=0.5.2) are ordered rules of `{operations: read|write, paths: globs, mode: allow|deny|interrupt}`, evaluated first-match-wins. "If no rule matches, the call is **allowed** (permissive default)." The rules apply only to built-in filesystem tools: "Custom tools and MCP tools that access the filesystem are not covered", and they "do not apply to sandbox backends". `mode="interrupt"` (deepagents>=0.6.8) turns a matching write into an HITL approval. Subagents inherit the parent's rules unless overridden. — [Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)
- Since deepagents>=0.7, a `tools` allowlist on `FilesystemMiddleware` can expose a subset of file tools, for example a read-only agent. Removing `FilesystemMiddleware` entirely "is intentionally rejected". — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)

**Code execution**
- There are two modes. Sandbox backends add an `execute` shell tool. "Interpreters" add an `eval` tool that runs JavaScript in a scoped QuickJS runtime, with "no shell access, package installs, or filesystem and network access". Interpreters are used for loops, batching and programmatic tool calling. — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview); [Interpreters](https://docs.langchain.com/oss/python/deepagents/interpreters)

**Subagents**
- A built-in `task` tool spawns ephemeral subagents. They are isolated by default (`mode: "isolated"`), and `mode: "fork"` inherits the parent's history. A default `general-purpose` subagent exists. Subagents run autonomously, return one final report, and are "stateless". — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview); [Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
- Async subagents run in parallel, and the supervisor can launch, check, update and cancel them. They "communicate with any server that implements the Agent Protocol", meaning LangSmith Deployment or a self-hosted Agent Protocol server, over ASGI in-process or remote HTTP. Task notifications and the `waiting` status require deepagents>=0.7.26 and are marked **beta**. — [Async subagents](https://docs.langchain.com/oss/python/deepagents/async-subagents)
- "Dynamic subagents" use interpreters to dispatch and orchestrate subagents from code. — [docs index entry: Dynamic subagents](https://docs.langchain.com/oss/python/deepagents/dynamic-subagents)

**Summarization and context management**
- Every `create_deep_agent` includes compression. Tool inputs or results over 20,000 tokens are offloaded to the backend and replaced with a file pointer and a 10-line preview. Old write and edit tool calls are truncated once context passes 85% of the window. — [Context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- `SummarizationMiddleware` triggers at 85% of the model profile's `max_input_tokens` and keeps 10% as recent context. Without a model profile it falls back to a 170,000-token trigger with 6 messages kept. On `ContextOverflowError` it immediately summarizes and retries. An optional `compact_conversation` tool allows on-demand compaction. — [Context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- "Unused built-in tools still send their full schemas on every turn". `excluded_tools` (harness profiles) removes them. — [Context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- Prompt caching is applied automatically for Anthropic and Bedrock (Claude or Nova) models. — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)

**Skills**
- Skills follow the Agent Skills standard (agentskills.io). Each is a directory with `SKILL.md` (YAML frontmatter `name` and `description`) plus optional `scripts/`, `references/` and `assets/`. They load by progressive disclosure: metadata at startup, the full SKILL.md when invoked, and resources as needed. Skill tools require deepagents>=0.7.22 and skill reloading deepagents>=0.7.16. Skills can be pinned, selected by context, and loaded from remote backends. — [Skills](https://docs.langchain.com/oss/python/deepagents/skills)

**Long-term memory (AGENTS.md, LangGraph Store)**
- Memory uses `AGENTS.md` files passed through `memory=`. Unlike skills, memory files are always loaded, and they are stored in the configured backend (State, Store or Filesystem). The agent can update memory with `edit_file`. — [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview); [Memory](https://docs.langchain.com/oss/python/deepagents/memory)
- Memory scopes are agent-scoped (namespace `(assistant_id,)`, shared across all users), user-scoped (`(user_id,)`) and organization-level. "Organization memory is typically **read-only** to prevent prompt injection via shared state". The docs also cover episodic memory via thread search and recommend "background consolidation" by a separate consolidation agent run on cron. — [Memory](https://docs.langchain.com/oss/python/deepagents/memory)
- LangGraph persistence uses checkpointers for short-term, per-thread state and stores for cross-thread long-term memory. — [docs index: Persistence](https://docs.langchain.com/oss/python/langgraph/persistence); [Stores](https://docs.langchain.com/oss/python/langgraph/stores)

**CLI and terminal agent**
- `deepagents-cli` latest is 0.3.0, uploaded 2026-08-24. Its PyPI summary reads "DEPRECATED: Deployment tooling for Deep Agents. Use Managed Deep Agents (`uv tool install managed-deepagents`, `mda`) instead". — [PyPI deepagents-cli](https://pypi.org/project/deepagents-cli/)
- The terminal coding agent is now **Deep Agents Code** (`dcode`, PyPI `deepagents-code`). It first shipped on 2026-04-30 and the latest is 0.2.2 (2026-10-26). 0.2.0 requires Python 3.14. — [PyPI deepagents-code](https://pypi.org/project/deepagents-code/); [GitHub releases](https://github.com/langchain-ai/deepagents/releases)
- dcode features: remote sandboxes, goals and rubrics, subagents, memory, compaction, HITL, hooks (`hooks.json`), plugins and marketplaces, and MCP tools. — [Deep Agents Code overview](https://docs.langchain.com/oss/deepagents/code/overview)
- Other protocol adapters: ACP for editors (`deepagents-acp`, first release 2026-02-06, latest 0.0.13 on 2026-10-12) and AG-UI. — [PyPI deepagents-acp](https://pypi.org/project/deepagents-acp/); [ACP docs](https://docs.langchain.com/oss/python/deepagents/acp); [AG-UI docs](https://docs.langchain.com/oss/python/deepagents/ag-ui)

**LangChain 1.x middleware model (`create_agent`)**
- Prebuilt provider-agnostic middleware: Tool error (langchain>=1.3.14), Tool retry, Model retry, Model fallback, Summarization, Human-in-the-loop, Model call limit ("to prevent excessive costs"), Tool call limit, PII detection, To-do list, LLM tool selector, Provider tool search, Shell tool, Filesystem, Subagent, Rubric grading (**Beta**), File search, Context editing, and LLM tool emulator. — [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- `PIIMiddleware` built-in types are `email`, `credit_card` (Luhn), `ip`, `mac_address` and `url`. Custom types can be detected by regex or function. Strategies are `redact`, `mask`, `hash` and `block`. It applies to input by default. Output and tool results are opt-in, and with `apply_to_output=True` it redacts streamed output (langchain>=1.3.2). — [Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails); [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- Guardrails are custom `before_agent` / `after_agent` / model-wrap / tool-wrap middleware, either deterministic (regex or keyword) or model-based. The guardrails page lists "Detecting and blocking prompt injection attacks" as a use case but ships only PII and HITL as built-in guardrails. — [Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
- `MCP` support moved into LangChain itself as `langchain.mcp`, built on FastMCP, with `MCPAdapter` replacing `MultiServerMCPClient`. It requires `langchain[mcp]>=1.4.0` (1.4.0 shipped 2026-09-03). — [Migrate from langchain-mcp-adapters](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters); [PyPI langchain](https://pypi.org/project/langchain/#history)

### Inferences
- The harness covers most of the "agent loop" layer of an agent OS: planning, filesystem context, delegation, memory, skills and compaction. Its safety primitives are library-level and opt-in, though. Filesystem permissions are allow-by-default and cover only built-in file tools. PII detection is regex-based with five built-in types.
- deepagents is still 0.x and ships about 2–3 patch releases a week, and 0.7 changed defaults (planning). A platform built on it needs a pinning and upgrade-testing process, since the API surface keeps moving.
- Backend policy hooks are the natural extension point for an enterprise policy decision point on filesystem operations. Tool-level policy (MCP or custom tools) has to be implemented as `wrap_tool_call`-style middleware.

### Gaps
- I did not retrieve the full 0.6.x and 0.7.0 changelog text (the GitHub releases page shows only the latest 10 of 34 pages), so the exact contents of each minor release are not itemized here.
- I found no official LangChain statement of a deepagents 1.0 or stability commitment.

---

## Q2. Human-in-the-loop: interrupts, approve/edit/reject, checkpointing and time travel, and how they could implement "propose, a person approves" autonomy levels

### Takeaway
LangGraph interrupts plus a durable checkpointer let a run pause indefinitely before a tool call and resume later, even in another process. The reviewer's decision is one of approve, edit, reject or respond. Tools can be gated per tool, by an argument-level `when` predicate, or by filesystem path rule. Per-call interrupts with JSON response schemas are new (langchain>=1.4.6, Oct 2026). Time travel (replay or fork) works from any checkpoint. All of this is scoped to a thread. Only LangSmith Fleet (a SaaS no-code product) offers a cross-agent approvals inbox, so multi-approver, delegated or out-of-thread approval workflows are not provided by the OSS stack or the Agent Server.

### Cited Findings
- The HITL flow: the model proposes tool calls, the middleware checks `interrupt_on` and pauses with an interrupt, and "the checkpointer saves the agent's state, so the run can stop and resume later, even in another process". The application collects decisions and resumes with `Command(resume=...)`. — [HITL concepts](https://docs.langchain.com/oss/python/concepts/human-in-the-loop)
- There are four decision types: `approve`, `edit` (modify args), `reject` (skip and return feedback) and `respond` (a synthetic tool result for "ask user" tools). The docs warn against using `respond` to deny side-effecting tools, "because its message may be treated by the model as a successful tool result". — [Deep Agents HITL](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)
- There are two modes. In **batched** mode, the current default and the one Deep Agents uses, there is one interrupt per model turn and decisions are matched by position. In **per-call** mode (langchain>=1.4.6) there is one interrupt per call, keyed by interrupt ID, with a `response_schema`. "Use per-call mode for new agents. LangChain plans to make it the default in the next major release." langchain 1.4.6 was uploaded 2026-10-14. — [HITL concepts](https://docs.langchain.com/oss/python/concepts/human-in-the-loop); [PyPI langchain](https://pypi.org/project/langchain/#history)
- Documented batched-mode hazards include positional mismatches, where "A reviewer means to approve `write_file` and reject `execute_sql`, but sends `[reject, approve]`. The `DELETE` runs". A wrong number of decisions raises `ValueError` and "the thread stays stuck". Edited args are not validated. — [HITL concepts](https://docs.langchain.com/oss/python/concepts/human-in-the-loop)
- Conditional interrupts: a `when` predicate on `InterruptOnConfig` receives the `ToolCallRequest` and returns True or False to gate on arguments (langchain>=1.3.3). `allowed_decisions` restricts the options per tool. Subagents can have their own `interrupt_on`, and tools can call `interrupt()` directly. — [Deep Agents HITL](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)
- Filesystem permission rules with `mode="interrupt"` (deepagents>=0.6.8) raise the same HITL interrupt for writes to protected paths. They merge with `interrupt_on`. — [Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)
- Interrupt mechanics: a checkpointer is required, and `thread_id` is the "persistent cursor". On resume, "the node restarts from the beginning of the node where the interrupt was called… any code before the interrupt runs again". Typed `response_schema` validation requires langgraph>=1.2.12 (2026-09-21). — [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts); [PyPI langgraph](https://pypi.org/project/langgraph/#history)
- Time travel: **Replay** re-executes from a prior checkpoint ("LLM calls, API requests, and interrupts fire again and may return different results"). **Fork** uses `update_state` on a past checkpoint, which "does not roll back a thread. It creates a new checkpoint that branches". — [Use time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- The production guide describes indefinite interrupts ("pause for minutes or days") and says checkpoints "provide an audit trail and a recovery point" for payments and other irreversible actions. — [Going to production](https://docs.langchain.com/oss/python/deepagents/going-to-production)
- The Agent Server API exposes thread state, history, state at a checkpoint, and copy-thread endpoints, which together support time travel over the API. — [docs index: Agent Server API threads](https://docs.langchain.com/langsmith/agent-server-api/threads/get-thread-history)
- On A2A, the Agent Server maps an interrupted graph to the A2A `input-required` state, and resume works through a `command` parameter. Interrupts' `response_schema` is now included in thread state, run outputs and A2A artifacts. — [Agent Server changelog](https://docs.langchain.com/langsmith/agent-server-changelog)
- **LangSmith Fleet** provides "a central inbox for reviewing agent actions across all your agents", where users approve, edit or reject. Fleet's comparison page says "No other platform in this comparison offers a single centralized approvals inbox spanning all agents" (a vendor claim). — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight); [Fleet comparison](https://docs.langchain.com/langsmith/fleet/comparison)
- Managed Deep Agents supports "agent-owned interrupts" that post a Slack form from a tool, pause the run, and resume when the user submits. — [docs index: Prompt Slack users with agent-owned interrupts](https://docs.langchain.com/langsmith/python/managed-deep-agents-agent-owned-interrupts)
- Deep Agents Code has autonomy tiers: **Manual** (approve every gated action, the default), **Auto** (routine actions auto-approved, the model reviews uncertain ones, falls back to the human after repeated denials) and **YOLO** (no review). Gated actions include writes and deletes, `execute`, web requests and `task` delegation. The docs warn that "Auto is an authorization heuristic… **not** sandbox containment". — [Approval modes](https://docs.langchain.com/oss/deepagents/code/approval-modes)
- On Microsoft Foundry hosted agents, `ResponsesHostServer` surfaces LangGraph interrupts as a `function_call` item or an `mcp_approval_request` item, and resumes from `function_call_output` or `mcp_approval_response`. — [Microsoft Learn: Host LangGraph agents as Foundry hosted agents](https://learn.microsoft.com/azure/foundry/how-to/develop/langchain-hosted-agents)

### Inferences
- "Propose, a person approves" autonomy levels map directly onto these primitives:
  - L0 observe-only: a read-only `FilesystemMiddleware` tools allowlist with no side-effecting tools.
  - L1 propose: `interrupt_on` for every side-effecting tool.
  - L2 conditional: `when` predicates on amount, recipient domain or path.
  - L3 autonomous: no interrupt, but call limits apply.

  dcode's Manual/Auto/YOLO is a working precedent for tiering, but it is local-only.
- What an enterprise must still build:
  - An approval service outside the thread: routing to the right approver, multi-party or quorum sign-off, SLAs and escalation, delegation, and expiry or auto-reject of stale interrupts.
  - Binding the approver's identity to the resume command and authorizing it. On the Agent Server, a resume is a run creation on the thread, so this falls to custom `@auth.on` handlers.
  - Re-validating edited arguments, at least in batched mode.
  - Idempotency for tools re-executed on replay or node restart.
- The Fleet inbox is evidence that LangChain treats cross-agent approvals as a product feature. It sits in the proprietary Fleet layer, though, not in the OSS harness or Agent Server.

### Gaps
- I found no documentation of an Agent Server-level approval queue API, approver role model, or interrupt timeout/expiry policy. Their absence is inferred from the docs reviewed, not explicitly stated.

---

## Q3. Deployment and operations: LangSmith Deployment / Agent Server, Managed Deep Agents, Fleet (formerly Agent Builder), and LangSmith governance features

### Takeaway
LangSmith Deployment (formerly LangGraph Platform) runs graphs on the "Agent Server". It is available as Cloud (Plus plan or above), Hybrid, BYOC (Enterprise, GA on AWS), fully self-hosted with a control plane (Enterprise) or a standalone server. The server provides assistants (versioned configs), threads, runs, crons, a store, custom AuthN/AuthZ handlers, and `/mcp` and `/a2a` endpoints. On top of it sit Managed Deep Agents (public beta, 7 Aug 2026, LangSmith Cloud) and LangSmith Fleet, a no-code product that was "Agent Builder" until March 2026. Governance features are real but mostly Enterprise-gated or beta: RBAC and custom roles, tag-based ABAC, audit logs (400-day retention, OCSF), SCIM and SSO, agent-based workspaces (Cloud only), and the LLM Gateway (beta) with spend, rate, model-access and PII/secret-redaction policies.

### Cited Findings

**Deployment topologies**
- LangSmith Deployment options:
  - **Cloud**, "Fully managed by LangChain on AWS and GCP… Requires a Plus plan or above".
  - **Self-hosted with control plane**, which needs the Enterprise plan.
  - **Hybrid**, a LangChain-managed control plane with Agent Servers in your infrastructure.
  - **Standalone server**: "Bring your own PostgreSQL, Redis, and LangSmith license; no control plane".

  All use the same Agent Server runtime. — [LangSmith Deployment](https://docs.langchain.com/langsmith/deployment)
- LangSmith Deployment is "framework-agnostic". It can deploy LangGraph/LangChain, Google ADK, and "Claude Agent SDK, Strands, CrewAI, AutoGen" via the Functional API or `deployments-wrap-sdk`. — [LangSmith Deployment](https://docs.langchain.com/langsmith/deployment)
- BYOC is "only available for customers on the Enterprise plan" and is "generally available (GA) on AWS. Support for additional cloud providers is planned for the second half of 2026." However, the LangSmith Cloud changelog for 12–19 Oct 2026 announces "Create BYOC data planes on GCP" via `POST /orgs/current/data-planes`. The BYOC docs page may be stale. — [BYOC](https://docs.langchain.com/langsmith/byoc); [LangSmith Cloud changelog](https://docs.langchain.com/langsmith/changelog)
- Self-hosted LangSmith is "an add-on to the Enterprise plan". The base install includes observability, evals, prompts, Insights and Chat. Optional components:
  - Sandboxes, which need KVM-capable nodes and JuiceFS.
  - Engine.
  - Fleet (self-hosting in **beta**).
  - LLM Gateway (**beta**, Helm 0.17.1 or later).
  - LangSmith Deployment (KEDA, ingress, control and data plane).

  Terraform modules exist for AWS, Azure and GCP, and FIPS images are available. — [Self-hosted LangSmith](https://docs.langchain.com/langsmith/self-hosted); [docs index: products & setup](https://docs.langchain.com/_llms/products-and-setup/lang-smith-setup.txt)
- Agent Server release cadence: `langgraph-api` has daily `latest`, three-weekly `rc` and three-weekly `stable` streams. Deployments auto-update to the newest stable on each new revision unless pinned. As of 27 Oct 2026 the stable line is 0.16.x (0.16.7 on 2026-10-26) and 0.17 is RC. — [Agent Server changelog](https://docs.langchain.com/langsmith/agent-server-changelog); [PyPI langgraph-api](https://pypi.org/project/langgraph-api/#history)

**Agent Server primitives**
- Assistants are versioned configurations (prompt, model, tools) on a graph. "Editing an assistant creates a new version, and you can promote or roll back to any version." A default assistant is created per graph. — [Assistants](https://docs.langchain.com/langsmith/assistants)
- Cron jobs run on a schedule. Each run creates a new thread with the given assistant and input, "All cron schedules are interpreted in **UTC**". — [Cron jobs](https://docs.langchain.com/langsmith/cron-jobs)
- Other documented features: the store (with semantic search and TTLs), double texting, webhooks, per-user store isolation, a custom store, AES or custom encryption at rest, IAM auth for data stores, and RemoteGraph. — [docs index: deploy pages](https://docs.langchain.com/_llms/agent-development-lifecycle/deploy.txt); [Semantic search](https://docs.langchain.com/langsmith/semantic-search); [TTLs](https://docs.langchain.com/langsmith/configure-ttl); [Isolate store data per user](https://docs.langchain.com/langsmith/store-auth); [Encryption at rest](https://docs.langchain.com/langsmith/encryption)

**Auth**
- AuthN is an `@auth.authenticate` handler that runs on every request and returns user info, which is exposed to the graph as `langgraph_auth_user`. AuthZ is `@auth.on` handlers at global, resource (`threads`, `assistants`, `crons`, store) and action (`threads.create`, etc.) granularity, most specific wins. Handlers can tag metadata, return filter dicts (`$eq`, `$contains`) or deny. — [Authentication & access control](https://docs.langchain.com/langsmith/auth)
- Defaults: LangSmith-hosted deployments use LangSmith API keys (`x-api-key`). "Self-hosted: No default authentication". "Custom auth **is supported** for all plans". `auth.allow_langsmith_api_keys` (Agent Server v0.14.0rc2+) accepts both. — [Authentication & access control](https://docs.langchain.com/langsmith/auth)
- "Agent authentication": values returned from `@auth.authenticate` flow into run context, "giving agents user-scoped credentials" to call MCP servers, databases or other agents on the user's behalf. — [Authentication & access control](https://docs.langchain.com/langsmith/auth)
- A tutorial ("Make conversations private") tags resources with `owner` and filters on it so users see only their own threads. — [Resource auth](https://docs.langchain.com/langsmith/resource-auth)
- A potentially breaking change in a recent Agent Server release: `POST /runs` now authorizes the attached assistant via the `assistants.read` auth event. An Oct 2026 fix (0.16/0.17 line) made the server apply request mutations from JS/TS custom auth handlers, "including the store namespace rewrite used to scope items per user. This fixes cross-user store isolation". — [Agent Server changelog](https://docs.langchain.com/langsmith/agent-server-changelog)

**Protocols: Agent Protocol, MCP, A2A**
- MCP: the Agent Server exposes `/mcp` (Streamable HTTP) so deployed agents appear as MCP tools, named after the agent with its input schema. It requires langgraph-api>=0.2.3. "The current LangGraph MCP implementation does not support sessions. Each `/mcp` request is stateless". It uses the same auth as the rest of the API and can be disabled with `disable_mcp`. — [MCP endpoint in Agent Server](https://docs.langchain.com/langsmith/server-mcp)
- A2A: the endpoint is `/a2a/{assistant_id}`. It speaks "A2A **v1.0** JSON-RPC binding and also accepts the v0.3 method names". `SubscribeToTask` and push-notification config are "Not yet". "Only the JSON-RPC binding is available. gRPC and HTTP+JSON are not implemented." The agent card is at `/.well-known/agent-card.json`. — [A2A endpoint](https://docs.langchain.com/langsmith/server-a2a); [Agent Server changelog](https://docs.langchain.com/langsmith/agent-server-changelog)
- `A2A_ALLOWED_TOOL_CALL_RESULTS` restricts which tool results are exposed over A2A, and error messages in streams and A2A responses are sanitized. — [Agent Server changelog](https://docs.langchain.com/langsmith/agent-server-changelog)
- The Agent Protocol (github.com/langchain-ai/agent-protocol) is the server contract used by async subagents. — [Async subagents](https://docs.langchain.com/oss/python/deepagents/async-subagents)

**Managed Deep Agents (MDA)**
- MDA was introduced in **private beta** on 13 May 2026 (Victor Moreira) and moved to **public beta** on 7 Aug 2026. The public-beta post says: LangSmith Cloud, **US region only**, CLI-first while the API is finalized, no self-hosted or BYOC, Python and TypeScript, and "basic" OIDC identity with "more advanced auth and credential flows" planned. It suggests using LangSmith Deployment directly for custom routes, auth logic, or persistence control. — [Introducing Managed Deep Agents](https://langchain.com/blog/introducing-managed-deep-agents); [MDA public beta](https://langchain.com/blog/managed-deep-agents-is-now-in-public-beta)
- A project is a directory:
  - `agent.py` (model)
  - `instructions.md`
  - `skills/` and `tools/` (including `tools/mcp.py`)
  - `middleware/`
  - `sandbox/`
  - `memory.py`
  - `identity.py`
  - `channels/` (Slack, HTTP)
  - `schedules/` (managed cron)
  - `evals/` (Harbor)

  MDA "runs the open source Deep Agents harness rather than a second framework". `define_deep_agent` returns a definition that the `mda` CLI compiles on the managed runtime. Instructions, skills and memory live in Context Hub. — [Managed Deep Agents overview](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
- The `managed-deepagents` PyPI package runs from 0.1.1 (2026-06-05) to 0.9.0 (2026-10-07). Its README says both "Public beta" and "Private beta: dev releases only… no stable version yet", so the README is internally inconsistent. — [PyPI managed-deepagents](https://pypi.org/project/managed-deepagents/)
- MDA identity options:
  - A LangSmith API key, the default. "Anyone with the key can reach the deployment… does not give each end user private threads".
  - Supabase.
  - Another JWT provider ("Auth0, Okta, Clerk, or Microsoft Entra ID").
  - Your own backend.

  Caveat: "A caller with API access to the LangSmith workspace can read and search every thread in the deployment… Per-user privacy therefore holds against your end users, not against members of your LangSmith workspace." — [MDA identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity)
- Parallel says MDA v0.8 (Sept 2026) shipped with built-in Parallel web search. — [Parallel blog](https://parallel.ai/blog/langchain-managed-deep-agents-parallel-search); [MDA search docs](https://docs.langchain.com/langsmith/python/managed-deep-agents-search)

**LangSmith Fleet (formerly Agent Builder): no-code agents built on Deep Agents**
- Timeline:
  - Agent Builder launched in **private preview** during the week of 27–31 Oct 2025.
  - A central tool registry and chat agent were added 16–20 Feb 2026.
  - "Agent Builder is now LangSmith Fleet" in the week of 16–20 Mar 2026.

  — [Fleet changelog](https://docs.langchain.com/langsmith/fleet/changelog)
- Fleet agents can be exported to code via Deep Agents (MIT), and Fleet self-hosting is in **beta**. — [Fleet comparison](https://docs.langchain.com/langsmith/fleet/comparison); [Fleet overview](https://docs.langchain.com/langsmith/fleet/index)
- Agent identity has two modes. "Fixed credentials ('Claws')" means one set of credentials for everyone, and channels and schedules require it. "User credentials ('Assistants')" use per-user OAuth. "Once an agent identity is set, it cannot be changed." — [Fleet agent identity](https://docs.langchain.com/langsmith/fleet/agent-identity)
- Fleet RBAC permissions: `fleet-agents:read/invoke/create/update/delete`, `fleet-skills:*`, `mcp-servers:read/invoke/create/update/delete`, `deployments:*`, and `fleet:read-admin-config` / `fleet:write-admin-config` for usage limits. Custom roles are Enterprise-only, and self-hosted Fleet RBAC needs LangSmith 0.17.44 or later. — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight)
- Tool access control (Enterprise) works in layers, evaluated in this order:
  1. Workspace integration policy (enable or disable built-in integrations).
  2. ABAC deny.
  3. RBAC.
  4. ABAC allow.

  ABAC applies to the `mcp_server` and `fleet_integration` resource types. — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight)
- Recent Fleet changes (12–19 Oct 2026):
  - Every Fleet agent is now an **MCP server** (`/v1/fleet/agents/{id}/mcp` with `send_message`, `respond_to_interrupt`, `get_thread`, `cancel_run`) and an **A2A server**.
  - New per-user and per-agent USD cost endpoints.
  - Workspace "tool credential profiles" (agents call tools with an `X-LangSmith-Profile` header "instead of acting as a user").
  - In OIDC SSO orgs, Fleet runs "now receive your identity provider access token, including scheduled and triggered runs".
  - "Tool kits replace MCP gateways."

  — [Fleet changelog](https://docs.langchain.com/langsmith/fleet/changelog)

**LangSmith governance features**
- The "Govern" area covers users and access (RBAC, ABAC, authentication), organization administration, audit logs and compliance. Runtime governance is described as LLM Gateway spend and data policies, sandboxes and human approval. — [Govern overview](https://docs.langchain.com/langsmith/govern-overview)
- RBAC "is an Enterprise feature… Other plans default to using the Admin role for all users". Custom workspace roles are Enterprise-only. Organization roles (Admin, Operator, User, Viewer) are fixed. — [RBAC](https://docs.langchain.com/langsmith/rbac)
- ABAC (Enterprise) adds tag-based conditions on resources, but "currently only supports `resource_tag_key` as an `attribute_name`". It is configured via API. — [ABAC](https://docs.langchain.com/langsmith/abac)
- Audit logs (Enterprise) are a "tamper-resistant record of administrative and configuration actions". In agent-based workspaces, "agents are audited too". Retention is up to **400 days**. The API returns OCSF v1.7.0 API Activity (class 6003). SIEM forwarding works by polling (e.g. Lambda every hour). — [Audit logs](https://docs.langchain.com/langsmith/audit-logs)
- Agent-based workspaces make the agent "the unit a workspace is organized around". Each agent has an immutable identifier and four fixed environments (Production, Staging, Development, Local), and traces, alerts, evaluators and dashboards attach to them. This is **LangSmith Cloud only, not self-hosted**, and existing workspaces are migrated on an unpublished schedule. — [Agents](https://docs.langchain.com/langsmith/agents); [Agent environments](https://docs.langchain.com/langsmith/agent-environments); [How agent-based workspaces differ](https://docs.langchain.com/langsmith/migrate-to-agent-based-workspaces)
- Trace data retention on self-hosted defaults to 14 days for `shortlived` and 400 days for `longlived` TTLs, with extended retention configurable per workspace for Enterprise. — [Self-host TTL](https://docs.langchain.com/langsmith/self-host-ttl)
- Trace masking: `hide_inputs`/`hide_outputs`, rule-based regex masking, Presidio or Amazon Comprehend anonymizers, secret redaction, and redaction via an OTel gateway. — [Mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs); [Redact secrets](https://docs.langchain.com/langsmith/redact-secrets); [OTel gateway redaction](https://docs.langchain.com/langsmith/otel-gateway-trace-redaction)
- Tracing-only API keys scoped to workspaces were added 12–19 Oct 2026. — [LangSmith Cloud changelog](https://docs.langchain.com/langsmith/changelog)
- **LLM Gateway** (**beta**) offers one LangSmith key across providers in Chat Completions, Messages or Responses format. It traces every call and applies spend limits, rate limits and data policies. It runs on Cloud, BYOC and self-hosted. — [LLM Gateway](https://docs.langchain.com/langsmith/llm-gateway)
  - It was "In private beta today" at Interrupt on 14 May 2026. — [Interrupt 2026 overview](https://langchain.com/blog/interrupt-2026-overview)
  - An aggregator reports it entered public beta in Aug 2026, but I did not verify this against a LangChain primary source. — [AI Toolly](https://aitoolly.com/ai-news/article/2026-08-27-langchain-august-2026-update-managed-deep-agents-and-llm-gateway-enter-public-beta-with-aws-byoc-sup)
- Gateway spend policies apply by organization, workspace, API key ("maps to a service or agent") or user, over monthly, weekly, daily or hourly windows. Requests that would exceed the cap are blocked with HTTP `402`. Narrower scopes can only tighten. Policies can also be split by a custom header (e.g. `X-Gateway-Customer-Id`). — [Spend policies](https://docs.langchain.com/langsmith/llm-gateway-spend-policies)
- Gateway data policy: it can redact PII and secrets before requests reach the provider and rehydrate them on the response. PII rules cover emails, US phone numbers and US SSNs by regex, plus names, locations and nationality/religious/political groups via Presidio. "PII redaction is off by default and enabled for selected organizations". Trace content capture is off by default. — [Data policy](https://docs.langchain.com/langsmith/llm-gateway-data-policy)
- Separate gateway pages cover model access policies, rate limit policies, model fallbacks, per-customer header policies, an LLM auth proxy and setup for coding agents. — [docs index: LangSmith setup](https://docs.langchain.com/_llms/products-and-setup/lang-smith-setup.txt)

### Inferences
- The Agent Server covers much of the runtime plane an agent OS needs: durable threads and runs, versioned assistants, cron, a store, an auth hook, MCP and A2A. Its authorization model is resource metadata filtering for end users, though. It is not a policy engine over tool calls, and self-hosted servers have no default auth.
- The strongest governance features (RBAC custom roles, ABAC, audit logs, BYOC, self-hosting, tool access control) sit behind the Enterprise plan or are in beta (LLM Gateway, self-hosted Fleet). Agent-based workspaces, the closest thing to an agent inventory, are Cloud-only.
- MDA is the path LangChain recommends, but it is Cloud-only (US) and in beta, and workspace members can read all end-user threads. A regulated enterprise building its own agent OS on the OSS SDK would most likely use self-hosted or Hybrid LangSmith Deployment, or a third-party runtime.

### Gaps
- Pricing for MDA, LLM Gateway and Fleet usage was not retrieved.
- I could not confirm the current GA or beta stage of LLM Gateway beyond the docs' "beta" label, or whether MDA has expanded beyond US Cloud since 7 Aug 2026.
- No information was found on SLAs for Agent Server or MDA.

---

## Q4. Observability and evaluation: LangSmith tracing (incl. OpenTelemetry), online and offline evals, annotation queues, Insights, Engine, and deep-agent-specific evals

### Takeaway
LangSmith is a mature trace, eval and monitoring product. It supports OTel both ways (ingests OTLP and GenAI semconv attributes, can fan out to other backends), and offers online evaluators (LLM-judge, code, composite, multi-turn, decision-model), Insights (GA Oct 2025), alerts and dashboards. LangSmith Engine (public beta, May 2026) clusters production failures and proposes fixes as PRs. For Deep Agents there are subagent-level trace filters, a trajectory view, Harbor-based evals for MDA and a rubric-grading middleware (beta). Agent-environment scoping is Cloud-only.

### Cited Findings
- Deep Agents tracing: the Trajectory view shows a simplified conversation, and every subagent run carries the `lc_agent_name` metadata key for filtering. — [Trace Deep Agents](https://docs.langchain.com/langsmith/trace-deep-agents)
- OTel support:
  - `LANGSMITH_OTEL_ENABLED` turns on OTel for LangChain and LangGraph apps.
  - Non-LangChain agents send OTLP to `https://api.smith.langchain.com/otel` (self-hosted: `/api/v1/otel`).
  - Collector fanout sends to multiple destinations.
  - "Agent addressing" headers (`Langsmith-Agent-Id`, `Langsmith-Agent-Environment`) route traces to agents, and return 403 on self-hosted.

  — [Trace with OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry)
- OTel span attributes outside the LangSmith schema are now stored in run metadata in all production regions (5–12 Oct 2026). GenAI cache-token attributes are priced at cache rates (12–19 Oct 2026). — [LangSmith Cloud changelog](https://docs.langchain.com/langsmith/changelog)
- Online evaluator types: LLM-as-a-judge, code, composite, multi-turn, decision model, and "LangChain Tuned Evaluators". Alerts and dashboards are also available. — [docs index: Monitor](https://docs.langchain.com/_llms/agent-development-lifecycle/monitor.txt); [Multi-turn online evaluators](https://docs.langchain.com/langsmith/online-evaluations-multi-turn); [Alerts](https://docs.langchain.com/langsmith/alerts)
- Insights analyzes traces for usage patterns and failure modes via hierarchical categorization. It needs the Plus or Enterprise plan and a model configuration. The "Insights Agent is now generally available for Plus and Enterprise plans" (changelog week of 20–24 Oct 2025). — [Insights](https://docs.langchain.com/langsmith/insights); [LangSmith Cloud changelog](https://docs.langchain.com/langsmith/changelog)
- Annotation queues exist as audited resources, with create, populate, export, reviewer management and pairwise queues. — [Audit logs tracked operations](https://docs.langchain.com/langsmith/audit-logs)
- LangSmith Engine was "Available now in public beta" at Interrupt (14 May 2026). It detects issues in traces, gives diagnoses with evidence, proposes code or prompt fixes, opens PRs (now ready-for-review rather than drafts, Oct 2026), creates offline dataset examples from failing traces and learns from triage feedback. It became available on BYOC data planes in Oct 2026. — [Interrupt 2026 overview](https://langchain.com/blog/interrupt-2026-overview); [Engine issues](https://docs.langchain.com/langsmith/engine-issues); [LangSmith Cloud changelog](https://docs.langchain.com/langsmith/changelog)
- MDA evals "run in Harbor". `mda evals init` and `mda evals compile` prepare tasks that the user runs locally in Docker. — [PyPI managed-deepagents README](https://pypi.org/project/managed-deepagents/); [MDA public beta blog](https://langchain.com/blog/managed-deep-agents-is-now-in-public-beta)
- Rubric grading middleware (**Beta**) applies "LLM-as-a-judge grading so agents self-evaluate and iterate until a rubric is satisfied". — [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in); [Grading rubrics](https://docs.langchain.com/oss/python/deepagents/rubric)
- A CI/CD example covers LangSmith Deployment combined with evaluation. — [CI/CD pipeline example](https://docs.langchain.com/langsmith/cicd-pipeline-example)

### Inferences
- LangSmith already covers the "agent observability and eval" pillar of an agent OS well, including OTel interoperability with an enterprise SIEM or APM. The main design questions are data residency (self-hosted or BYOC are Enterprise), trace retention versus audit needs, and the fact that agent-centric features (agent addressing, environment-scoped alerts and Insights) are Cloud-only.

### Gaps
- Offline experiment and annotation-queue doc pages were not read in detail. No independent assessment of Engine's accuracy was found.

---

## Q5. Tools and integrations: MCP adapters, A2A, sandbox providers, and running Deep Agents on AWS AgentCore, Google Vertex AI Agent Engine and Microsoft Foundry

### Takeaway
MCP client support is now built into `langchain` (>=1.4.0, Sept 2026) and replaces `langchain-mcp-adapters`. Bearer, OAuth 2.1 and per-user credential auth are supported. The Agent Server and Fleet expose agents as MCP and A2A servers. Sandbox backends cover LangSmith Sandboxes (GA May 2026), AgentCore Code Interpreter, Daytona, E2B, Modal, Runloop and Vercel. Deep Agents runs as an ordinary LangGraph graph on AWS AgentCore Runtime (AWS blog, Sept 2025), on Microsoft Foundry hosted agents (explicitly documented, Aug 2026), and on Google's agent runtime through the LangGraph template. Each of those clouds adds its own identity, memory and observability around it.

### Cited Findings
- `langchain.mcp` (FastMCP-based `MCPAdapter`) replaces `langchain-mcp-adapters` and requires `langchain[mcp]>=1.4.0`. The migration guide says to stop and ask if code uses "prompts, resources, sampling, roots, SSE/WebSocket transports, `to_fastmcp`, or any API the guide marks as not supported or protocol-deprecated". — [Migrate from langchain-mcp-adapters](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters)
- The last standalone `langchain-mcp-adapters` release was 0.3.2 on 2026-08-06. — [PyPI langchain-mcp-adapters](https://pypi.org/project/langchain-mcp-adapters/#history)
- MCP auth options are bearer tokens, OAuth 2.1 and per-user credentials. — [docs index: MCP Authentication](https://docs.langchain.com/oss/python/langchain/mcp/auth)
- A Fleet changelog entry (Oct 2026) notes compatibility fixes for MCP clients on "the 2026-07-28 protocol revision". — [Fleet changelog](https://docs.langchain.com/langsmith/fleet/changelog)
- Sandbox providers documented for Deep Agents are AgentCore, Daytona, E2B, Modal, Runloop and Vercel. LangSmith Sandboxes are first-party. A provider only has to implement `execute()`. — [Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)
- Sandbox lifecycle can be thread-scoped (the default) or assistant-scoped. Assistant-scoped sandboxes "accumulate in-sandbox state over time", so TTLs or snapshots are needed. — [Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)
- LangSmith Sandboxes became GA at Interrupt (14 May 2026). They are GA in GCP US, EU and APAC, AWS US and BYOC, and became available to Azure production orgs in Oct 2026. Egress is restricted by default for non-Enterprise orgs. An auth proxy can inject credentials into outbound sandbox requests. — [Interrupt 2026 overview](https://langchain.com/blog/interrupt-2026-overview); [LangSmith Sandboxes](https://docs.langchain.com/langsmith/sandboxes); [LangSmith Cloud changelog](https://docs.langchain.com/langsmith/changelog); [Going to production](https://docs.langchain.com/oss/python/deepagents/going-to-production)
- **AWS AgentCore Runtime**: AWS published "Running deep research AI agents on Amazon Bedrock AgentCore" on 23 Sep 2025. Deep Agents is wrapped with `BedrockAgentCoreApp`/`@app.entrypoint` and deployed via the starter toolkit (Docker to ECR to Runtime). Each session runs in a dedicated microVM, executions can last up to 8 hours, and AgentCore Memory, Gateway (MCP), Identity, and CloudWatch/X-Ray integration are available. The post does not discuss LangGraph checkpointing or HITL. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/running-deep-research-ai-agents-on-amazon-bedrock-agentcore)
- AWS integration packages:
  - `langgraph-checkpoint-aws` provides `AgentCoreMemorySaver` (checkpointer) and `AgentCoreMemoryStore`. — [AWS docs: Integrate AgentCore Memory with LangChain/LangGraph](https://docs.aws.amazon.com/pt_br/bedrock-agentcore/latest/devguide/memory-integrate-lang.html); [langchain-aws GitHub](https://github.com/langchain-ai/langchain-aws)
  - `langchain-agentcore-codeinterpreter` (0.0.1 on 2026-03-20, 0.0.5 on 2026-06-23) provides an AgentCore Code Interpreter sandbox backend "for Deep Agents". — [PyPI langchain-agentcore-codeinterpreter](https://pypi.org/project/langchain-agentcore-codeinterpreter/); [LangChain AWS sandbox docs](https://docs.langchain.com/oss/python/integrations/sandboxes/aws)
  - A second AWS post, "Build context-rich research agents with Deep Agents and Bedrock AgentCore", is mirrored with a 15 Jun 2026 date. I took that date from the mirror, not AWS. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/build-context-rich-research-agents-with-deep-agents-and-bedrock-agentcore/)
- **Microsoft Foundry**: `langchain-azure-ai[hosting]>=1.2.9` provides `ResponsesHostServer` (`/responses`) and `InvocationsHostServer` (`/invocations`). "Deep Agents are hosted in the same way as other LangGraph agents." Foundry "manages the hosted runtime, sessions, scale, identity, and protocol endpoints". Existing `langgraph.json` projects run unchanged via `python -m langchain_azure_ai.agents.hosting.run`. Deployment requires the Foundry Project Manager role. The page's ms.date is 2026-08-31. — [Microsoft Learn](https://learn.microsoft.com/azure/foundry/how-to/develop/langchain-hosted-agents)
  - `langchain-azure-ai` latest is 1.2.12 (2026-10-22). — [PyPI langchain-azure-ai](https://pypi.org/project/langchain-azure-ai/)
  - The Learn page does not state preview or GA status for hosted agents. A third-party guide says Hosted Agents are in Preview. — [Medium guide](https://medium.com/@arnaud.tincelin/deploy-hosted-agents-on-microsoft-foundry-complete-guide-0de13e4f835f)
- **Google**: the "Develop an agent" page (updated 2026-10-26) lists templates for ADK, Agent2Agent, LangChain, LangGraph, AG2, LlamaIndex and custom. It now uses "Agent Runtime" / "Agent Platform" naming rather than "Agent Engine". Listed services are Sessions, Memory Bank, Code Execution sandbox, IAM agent identity, Cloud Trace/Logging, Agent Gateway and Private Service Connect. Deep Agents is not mentioned. — [Google Cloud: Develop an agent](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/develop/overview?hl=en)
  - The `LanggraphAgent` template class sits in `vertexai.preview.reasoning_engines`, a preview namespace, with checkpointing off by default. — [Vertex AI reference: LanggraphAgent](https://docs.cloud.google.com/python/docs/reference/vertexai/latest/vertexai.preview.reasoning_engines.LanggraphAgent)
- Interop protocols in Deep Agents: ACP (editors) and AG-UI (frontends). — [ACP](https://docs.langchain.com/oss/python/deepagents/acp); [AG-UI](https://docs.langchain.com/oss/python/deepagents/ag-ui)

### Inferences
- Because a deep agent is just a compiled LangGraph graph, it is portable across LangSmith Deployment, AgentCore Runtime, Foundry hosted agents and Google's runtime. On the hyperscalers the enterprise inherits that cloud's identity (IAM or Entra) and isolation (microVM per session on AgentCore), but must bring its own durable checkpointer for interrupts and HITL. The Foundry doc says to use a durable checkpointer, and the AgentCore sample shows none. It then loses LangSmith-native features such as assistants, cron and the store, unless it re-creates them.

### Gaps
- Official Google documentation showing Deep Agents specifically on Agent Runtime or Agent Engine was not found.
- The GA or preview status of the LangGraph template on Google, and of Foundry hosted agents, as of Oct 2026, was not confirmed from a primary source.

---

## Q6. Gaps vs enterprise agent-governance platforms (Microsoft Agent 365 / Entra Agent ID, AWS AgentCore Identity/Policy, Google Gemini Enterprise): what the LangChain stack does not provide out of the box

### Takeaway
The LangChain stack provides end-user authN/authZ hooks, per-agent credential modes (Fleet), tool-level RBAC and ABAC (Fleet, Enterprise), model-call spend and PII policies (LLM Gateway, beta), HITL and audit logs of admin actions. It does not provide:
- a directory-backed per-agent workload identity, as Entra Agent ID or AgentCore Identity do;
- a cross-platform agent registry;
- a deterministic central policy engine evaluated on every tool call with arguments, like AgentCore Policy (Cedar, GA 3 Mar 2026);
- enterprise DLP or data classification integration;
- built-in prompt-injection detection;
- approval workflows outside a thread (except the Fleet inbox);
- whole-run cost budgeting beyond model spend and call counts.

### Cited Findings
- **Per-agent identity.** Agent Server auth authenticates the *caller* via custom handlers and passes user info into the run. Agents act "on behalf of the user" with user-scoped credentials. — [Authentication & access control](https://docs.langchain.com/langsmith/auth)
  - Fleet offers per-agent "fixed" vs "user" credential modes, immutable once set, plus workspace tool credential profiles (Oct 2026). — [Fleet agent identity](https://docs.langchain.com/langsmith/fleet/agent-identity); [Fleet changelog](https://docs.langchain.com/langsmith/fleet/changelog)
  - MDA "identity" is caller authentication (API key, Supabase, JWT provider or backend). — [MDA identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity)
  - By contrast, Microsoft says Agent 365 becomes the unified registry and control plane for agents, while Entra provides the identity foundation via Agent ID. — [Microsoft Learn: agent registry convergence](https://learn.microsoft.com/en-us/entra/agent-id/agent-registry-convergence)
  - Google's agent runtime lists "IAM agent identity". — [Google Cloud: Develop an agent](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/develop/overview?hl=en)
- **Agent registry and inventory.** LangSmith agent-based workspaces give each agent an immutable ID and environments, but only on LangSmith Cloud. — [Agents](https://docs.langchain.com/langsmith/agents)
  - Fleet keeps its own agent list with sharing permissions. — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight)
  - No docs page describes a registry for agents running outside LangSmith (e.g. on AgentCore or Foundry) or lifecycle states such as approved, retired or quarantined.
- **Central policy enforcement on tool calls.** In OSS, the mechanisms are middleware (custom guardrails), HITL `interrupt_on`/`when`, model and tool call-limit middleware, and filesystem permissions. The permissions are allow-by-default and limited to built-in file tools, "Custom tools and MCP tools… are not covered", and they do not apply to sandboxes. — [Permissions](https://docs.langchain.com/oss/python/deepagents/permissions); [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
  - Fleet's tool access control (Enterprise) gates which MCP servers and integrations a user or role may read or invoke via RBAC, ABAC tags and a workspace integration policy. — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight)
  - AWS, by comparison, says AgentCore Policy (GA 3 Mar 2026) attaches Cedar policies to AgentCore Gateway, which "intercepts agent-to-tool traffic and evaluates each request against the policies". — [AWS What's New (Mar 2026)](https://aws.amazon.com/de/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/); [AWS What's New preview (Dec 2025)](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-bedrock-agentcore-policy-evaluations-preview)
- **DLP and data classification.** `PIIMiddleware` covers 5 built-in regex types plus custom detectors. — [Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
  - LLM Gateway data policy redacts PII and secrets on model calls only. It is beta, and PII is an opt-in entitlement. — [Data policy](https://docs.langchain.com/langsmith/llm-gateway-data-policy)
  - Trace masking is available for logs. — [Mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs)
  - No integration with sensitivity labels or data classification systems (e.g. Purview-style labels) was found in LangChain docs.
- **Prompt-injection defences.** No built-in injection classifier middleware is listed among the prebuilt middleware. The guardrails page frames injection blocking as something to implement with custom middleware. — [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in); [Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
  - The docs' mitigations are architectural: no secrets in sandboxes, a credential-injecting proxy, read-only shared memory, and treating sandbox output as untrusted. — [Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes); [Going to production](https://docs.langchain.com/oss/python/deepagents/going-to-production)
- **Approval workflows outside a thread.** OSS and Agent Server HITL is per thread (interrupt plus resume on the same `thread_id`). — [Deep Agents HITL](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)
  - Cross-agent approvals exist only in Fleet's central inbox. — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight)
- **Cost controls.** Model call limit and tool call limit middleware are documented. — [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
  - LLM Gateway spend policies (beta) apply hard caps by org, workspace, API key or user, but only for traffic routed through the gateway. — [Spend policies](https://docs.langchain.com/langsmith/llm-gateway-spend-policies)
  - Fleet has usage limits and per-user and per-agent cost reporting. — [Fleet changelog](https://docs.langchain.com/langsmith/fleet/changelog)
  - Fleet's own comparison rates its spend limits "⚠️ Managed at workspace level". — [Fleet comparison](https://docs.langchain.com/langsmith/fleet/comparison)
- **Audit.** LangSmith audit logs cover administrative and configuration actions (and agents in agent-based workspaces), with 400-day retention and pull-based OCSF export. — [Audit logs](https://docs.langchain.com/langsmith/audit-logs)
  - Fleet treats LangSmith traces as the "audit trail" of agent actions. — [Fleet access & oversight](https://docs.langchain.com/langsmith/fleet/access-and-oversight)
  - Self-hosted short-lived trace TTL defaults to 14 days. — [Self-host TTL](https://docs.langchain.com/langsmith/self-host-ttl)

### Inferences
An enterprise building an "agent OS" on Deep Agents would need to build or integrate the following itself:
1. **Agent identity.** Each agent needs a workload identity distinct from the end user, such as a service principal or SPIFFE ID, or an Entra Agent ID or AgentCore Identity if hosted there. It also needs token exchange or on-behalf-of flows for MCP and tools. Agent Server only gives a caller-auth hook.
2. **An agent registry.** This covers ownership, purpose, risk tier, allowed tools and models, environment, version (Agent Server assistants are versioned, but there is no org registry), and approval and decommission lifecycle across all runtimes.
3. **A policy decision point on every tool and MCP call.** It needs argument-aware, deny-by-default, centrally managed rules, and can be implemented as `wrap_tool_call` middleware plus backend policy hooks calling an external engine such as OPA or Cedar, mirroring AgentCore Policy.
4. **DLP and classification.** This must go beyond regex PII, including tool-result and file scanning, plus egress controls for sandboxes and agents.
5. **Prompt-injection detection and provenance tagging** of untrusted content (tool results, files, skills, memory), with integrity controls such as signing or review for skills and shared memory.
6. **An out-of-thread approval service.** It needs routing, quorum, SLAs, escalation, approver authorization and audit of decisions.
7. **Per-run and per-agent budgets** that include tool, sandbox and model costs, with kill switches.
8. **Tamper-evident action audit** separate from traces, given trace TTLs and sampling.

Several of these exist in LangSmith only as Enterprise, Cloud-only or beta features (ABAC, audit logs, agent-based workspaces, LLM Gateway), and may not apply to a self-built runtime.

### Gaps
- I did not research Google Gemini Enterprise governance features or AgentCore Identity in primary sources (other researchers are covering those platforms). The comparisons above rely on the cited Microsoft and AWS pages only.
- No LangChain roadmap statement about agent workload identity or a central tool-call policy engine was found.

---

## Q7. Known limitations, security issues and practitioner criticisms

### Takeaway
LangChain's own docs say plainly that Deep Agents is "trust-the-LLM" by design. Sandboxes don't stop context injection or exfiltration, local backends give no isolation, and shared memory is an injection vector. Real vulnerabilities have hit the permission and approval layer (two deepagents GHSAs, Oct 2026) and the LangGraph checkpointer and deserialization layer (an RCE chain disclosed by Check Point, patched Dec 2025 to Mar 2026). Practitioners stress missing production pieces (tenancy, budgets, evals), cost from fan-out, and fast-moving pre-1.0 APIs.

### Cited Findings

**Security advisories**
- **GHSA-47w2-rfrr-wvq8** (Moderate, CVSS v4 6.0, CWE-59, published 15 Oct 2026): "Filesystem permission and approval rules may be bypassed through alternate paths". `deny` and `interrupt` rules were checked against one path form while `FilesystemBackend` resolved to another target, so an agent could read or modify blocked files or skip required approvals. It affects `deepagents` >=0.5.2,<0.7.25 and is fixed in 0.7.25 (released 2026-10-14). — [GHSA-47w2-rfrr-wvq8](https://github.com/langchain-ai/deepagents/security/advisories/GHSA-47w2-rfrr-wvq8); [PyPI deepagents](https://pypi.org/project/deepagents/#history)
- **GHSA-459r-276m-w72x** (Moderate, CVSS v4 6.0, CWE-78, published 13 Oct 2026): a shell approval bypass in `deepagents-acp`. Segments that failed to parse were dropped from the auto-approve check, so `ls && echo PWNED #'` ran without a prompt when `ls` was allow-listed. It affects >=0.0.3,<0.0.13 and is fixed in 0.0.13. — [GHSA-459r-276m-w72x](https://github.com/langchain-ai/deepagents/security/advisories/GHSA-459r-276m-w72x)
- **LangGraph RCE chain** (Check Point Research, disclosed Nov 2025, patched Dec 2025 to Mar 2026, CSA note 14 Jun 2026) chains three flaws:
  - CVE-2025-67644: SQLi in `langgraph-checkpoint-sqlite` <3.0.1, CVSS 7.3.
  - CVE-2026-28277: unsafe msgpack deserialization in `langgraph` <1.0.10, CVSS 6.8.
  - CVE-2026-27022: RediSearch injection in `@langchain/langgraph-checkpoint-redis` <1.0.2, CVSS 6.5, which can expose other users' checkpoints.

  Together these give RCE when user input reaches `get_state_history()` filters. The CSA note says LangSmith Deployment (Postgres) is not affected. — [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-langgraph-rce-chain-20260614-csa-styled/)
- Search results also mentioned Cyera research on langchain-core issues (CVE-2025-68664, deserialization, CVSS 9.3, and CVE-2026-34070, path traversal). I did not open a primary source for these, so they are **unverified** here. — [Let's Data Science summary](https://letsdatascience.com/news/researchers-find-critical-vulnerabilities-in-langgraph-b381bea1)
- An Agent Server fix in Oct 2026 corrected cross-user store isolation for JS/TS custom auth handlers. — [Agent Server changelog](https://docs.langchain.com/langsmith/agent-server-changelog)
- The deepagents-code 0.2.2 release (26 Oct 2026) included security fixes: a project `.env` "can no longer set trust", terminal links are limited to HTTP/HTTPS, and Auto mode gained a Git allowlist. — [GitHub deepagents releases](https://github.com/langchain-ai/deepagents/releases)

**Documented design limitations (vendor's own warnings)**
- `FilesystemBackend`: "the default (`virtual_mode=False`) provides no security even with `root_dir` set". Combined with network tools, "secrets may be exfiltrated via SSRF". — [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- `LocalShellBackend` uses `subprocess.run(shell=True)` "with no sandboxing" and can consume unlimited CPU, memory and disk. — [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- Sandboxes "do **not** protect against" context injection ("the agent has full control within it") or network exfiltration. "**Never put secrets inside a sandbox**… even… short-lived or scoped credentials". "A sufficiently creative enough context injection attack can bypass output filtering and HITL review." — [Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)
- "Shared memory (assistant, user, or organization scope) is a vector for prompt injection." — [Going to production](https://docs.langchain.com/oss/python/deepagents/going-to-production)
- `StoreBackend`'s legacy default namespace is `assistant_id`, so "all users of the same assistant share the same storage". — [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- MDA's default identity shares threads among API-key holders, and workspace members can read all threads. — [MDA identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity)
- Batched HITL can leave a thread "stuck" after a malformed decision list, and positional mismatches can approve the wrong call. — [HITL concepts](https://docs.langchain.com/oss/python/concepts/human-in-the-loop)
- Replay re-executes side effects. — [Use time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- dcode "Auto is… **not** sandbox containment". dcode hooks "execute arbitrary code from your configuration". — [Approval modes](https://docs.langchain.com/oss/deepagents/code/approval-modes); [Hooks](https://docs.langchain.com/oss/deepagents/code/hooks)

**Context blow-ups and cost**
- Context management depends on thresholds (85% of the window, 20k-token offload), and unused tool schemas are still sent every turn. — [Context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- In Fleet (Oct 2026), "threads known to be too large return a 422 immediately". — [Fleet changelog](https://docs.langchain.com/langsmith/fleet/changelog)
- A LangChain forum user reported "token bloat" with `create_agent` multi-agent setups. Suggested causes were verbose subagent tool descriptions and passing full parent context. — [LangChain forum](https://forum.langchain.com/t/token-bloat-when-using-create-agent/2317)

**Practitioner reviews**
- Wavect (Kevin Riedl, 23 Aug 2026, reviewing 0.7.13) calls deepagents "a fast-moving beta package" and recommends pinning. It lists missing production pieces ("authenticated users, tenant-scoped state, a checkpointer, sandbox policy…"). It says Deep Agents "provides security controls, but it does not create a security boundary by itself" and follows a "trust-the-LLM model". It names cost drivers: "Long runs, retries, summaries and subagent fan-out". It advises: "An agent must never be the only control between a model output and a payment, deletion or external message." Note that Wavect sells AI services. — [Wavect review](https://wavect.io/blog/langchain-deep-agents-review/)
- TrueFoundry argues Deep Agents is not a complete production platform and flags credential governance across many agents. I did not open this vendor blog; the claims come from a search summary. — [TrueFoundry blog](https://www.truefoundry.com/blog/langchain-deep-agents-vs-production-reality)
- Academic work (Jul 2026) on file-based memory such as AGENTS.md and CLAUDE.md in Claude Code and Codex found that payloads planted in memory files can attack current and future sessions. It also found it harder to get agents to overwrite memory from untrusted content. This research is not specific to deepagents. — [Bad Memory (arXiv 2607.14611)](https://arxiv.org/pdf/2607.14611)

### Inferences
- Both deepagents advisories hit exactly the controls an agent OS would rely on for "propose, approve": path permissions and interrupt rules, and shell auto-approval. Approval and permission enforcement therefore needs defense in depth: an external policy engine, OS or sandbox isolation, and fast patch pipelines. It should not rest on the harness alone.
- The checkpointer RCE chain shows that the persistence layer (checkpoints and the store) is part of the attack surface. A self-hosted agent OS should use hardened Postgres, never expose raw state-history filters to users, and track LangGraph security releases.

### Gaps
- I found no public reports of sandbox escapes specific to LangSmith Sandboxes or the listed providers.
- No large-scale, independent production case studies of Deep Agents were found. Hacker News and Reddit sentiment was not captured.
