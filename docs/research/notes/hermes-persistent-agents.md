# Hermes Agent and persistent, long-lived agents (as of 27 October 2026)

Scope note: "Hermes" here means **Hermes Agent** by Nous Research (github.com/NousResearch/hermes-agent), the open-source, self-hosted, always-on personal agent. Repository facts below were read directly from a shallow clone of `main` at commit `e5ea5fd` (committed 27 Oct 2026). Release dates come from the repo's git tag metadata. Docs pages are cited by their GitHub path; the same pages are published under https://hermes-agent.nousresearch.com/docs/.

---

## 1. Hermes Agent: maker, releases, licence, architecture, memory, skills, scheduling, gateways, subagents, execution, models, security, limitations

### Takeaway
Hermes Agent is Nous Research's MIT-licensed personal agent. Secondary sources date its launch to February 2026, and the latest stable release is v0.22.5 (23 Oct 2026). It is designed to "live" rather than run once. One long-running **gateway** process per profile, installable as a systemd or launchd service, hosts every chat surface. Conversations never auto-reset. The agent keeps a small, curated memory file pair, has full-text search over every past session, writes and refines its own skills, which a curator prunes, and runs cron jobs, webhook-triggered jobs, per-session heartbeats and loops. Nous's own security policy says that **the only real security boundary is OS-level isolation**: approvals, scanners and allow-lists are heuristics. The project has accumulated a long list of CVEs and audit findings since launch.

### Cited Findings

**Name disambiguation**
- "Hermes" is also the name of Nous Research's open-weight LLM family. Hermes 4 (405B and 70B, built on Llama 3.1) was released in August 2025 and is separate from the agent — [Nous forum: Hermes 4](https://forum.nousresearch.com/t/nous-research-presents-hermes-4-our-latest-line-of-open-source-models/270); [Hermes 4 tech report](https://arxiv.org/abs/2508.18255)
- Meta's "Hermes" JavaScript engine for React Native is an unrelated product with the same name — [facebook/hermes](https://github.com/facebook/hermes)
- The official agent site is hermes-agent.nousresearch.com. A separate domain, hermes-agent.org, also turns up in search results; it is not the Nous-hosted site — [Hermes Agent official site](https://hermes-agent.nousresearch.com/); [hermes-agent.org/about](https://hermes-agent.org/about/)

**Maker, licence, launch, versions, traction**
- The README calls it "The self-improving AI agent built by Nous Research", with "a built-in learning loop". It "creates skills from experience, improves them during use, nudges itself to persist knowledge, searches its own past conversations, and builds a deepening model of who you are across sessions" — [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)
- The licence is MIT. `pyproject.toml` has `license = "MIT"` and `authors = [{ name = "Nous Research" }]` — [pyproject.toml](https://github.com/NousResearch/hermes-agent/blob/main/pyproject.toml); [official site](https://hermes-agent.nousresearch.com/)
- Launch: secondary sources say "launched in February 2026". I could not find Nous's own launch post. The earliest release tag in the repo is `v2026.3.12` (12 Mar 2026) — [agentic-ai.readthedocs: Hermes Agent](https://agentic-ai.readthedocs.io/en/latest/AgentPlatforms/hermes-agent/); [repo tags](https://github.com/NousResearch/hermes-agent/tags)
- Versioning:
  - Releases were tagged with CalVer from `v2026.3.12` to `v2026.9.24` (24 Sep 2026). Package versions in 0.x SemVer ran in parallel, for example "fixed in 0.19.0 and 2026.7.20".
  - The release doc says SemVer is now "seeded at `0.21.5` (the last legacy CalVer release, v2026.9.24)". The committed version on `main` is always `0.0.0`, and release jobs stamp the real version.
  - Stable SemVer tags since then: v0.21.6 (8 Oct 2026), v0.22.0 (14 Oct 2026) and v0.22.5 (23 Oct 2026, the latest stable as of 27 Oct 2026).
  - Nightly `+canary` prerelease tags also exist, for example `v0.22.5+canary.20261027T070237Z`.
  - Sources: [stable-releases.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/stable-releases.md); [tag v0.22.5](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.5); [NeuralTrust, 26 Oct 2026](https://neuraltrust.ai/blog/hermes-agent-security)
- Traction: about 214,000 GitHub stars and nearly 40,000 forks (July 2026). TechCrunch, citing unnamed sources, reported funding talks at a $1.5B valuation; Nous did not comment — [Trending Topics, 15 Jul 2026](https://www.trendingtopics.eu/hermes-nous-research/)
- Distribution and hosting:
  - Install options are a terminal install script, Hermes Desktop apps (macOS 12+, Windows 10/11), and optional cloud deployment through Nous Portal.
  - Nous Portal plans: Free $0, Plus $20, Super $100 and Ultra $200 per month, each including model credits.
  - Sources: [official site](https://hermes-agent.nousresearch.com/); [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)

**Process model (always-on gateway)**
- README: "Telegram, Discord, Slack, WhatsApp, Signal, and CLI — all from a single gateway process… cross-platform conversation continuity". It is "not tied to your laptop — talk to it from Telegram while it works on a cloud VM" — [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)
- Running as a service:
  - `hermes gateway install` installs a user service (systemd on Linux, launchd on macOS). `sudo hermes gateway install --system` installs a boot-time system service, recommended for a VPS or headless host.
  - The systemd unit uses `Restart=always`. There is an opt-in `systemd_watchdog_seconds` that restarts a wedged event loop.
  - Source: [messaging/index.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/index.md)
- `hermes chat` "no longer runs the agent inside your terminal process". It discovers or starts the profile's gateway, then creates or resumes the session there over a local WebSocket. "Closing the terminal detaches (`Detached; accepted work continues at the gateway.`); it does not cancel the turn" — [cli.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/cli.md)
- Session continuity: "Gateway conversations do not reset after inactivity or at a daily boundary. Use `/new` or `/reset`…" Legacy idle and daily reset policies were removed from core and are now an optional plugin, `hermes-session-reset-policy` — [sessions.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/sessions.md)
- On messaging platforms a chat is "one continuous session that survives restarts, gateway crashes, and machine reboots… a chat can run for weeks as a single session: convenient, but it grows expensive". The docs advise running `/new` at natural boundaries so the memory loop can work — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- Data persists in the Hermes home directory, `~/.hermes`. "Stopping a local agent ends its process but keeps its saved data. Tasks needing an active agent won't run while it's stopped" — [official site](https://hermes-agent.nousresearch.com/)

**Memory and user modelling**
- Memory is two bounded files in `~/.hermes/memories/`:
  - `MEMORY.md` holds the agent's own notes, up to 2,200 characters (about 800 tokens).
  - `USER.md` holds the user profile, up to 1,375 characters (about 500 tokens).
  - Both are injected into the system prompt as a frozen snapshot at session start, to preserve the prefix cache. Writes made mid-session only appear in the next session.
  - Source: [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- The `memory` tool supports add, patch and remove; there is no read action and no `replace`. Memory "does not auto-compact": a write that would exceed the limit returns an error, and the agent must consolidate entries before retrying — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- "Memory entries are scanned for injection and exfiltration patterns before being accepted… Content matching threat patterns… or containing invisible Unicode characters is blocked" — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- Write approval: `memory.write_approval` defaults to `false`. When set to `true`, foreground writes in the CLI prompt inline. Writes from messaging, scripts and the **background self-improvement review** are staged for `/memory pending` / `approve` / `reject`. Approval is pinned to the exact entry, so it is refused if the entry has changed since the write was staged — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- A background review "after a turn… may quietly save a memory or update a skill". Chat notifications are configurable (`off`, `on`, `verbose`), and the review can run on a cheaper auxiliary model — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- Session search: all CLI and messaging sessions are stored in SQLite (`~/.hermes/state.db`) with FTS5. `session_search` returns actual messages (about 20 ms per query) and lets the agent "find things it discussed weeks ago" — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- `/journey` shows a timeline of learned skills and memories and lets the user delete or edit nodes. Deleted skills are archived and can be restored — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- One writer per memory store: "Don't point two agent processes at the same Hermes home directory… two writers sharing one home will compound each other's entries into state neither of them (nor you) authored." Memory is scoped per profile; use an external provider for shared memory — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- User modelling and external memory:
  - README: "Honcho dialectic user modeling".
  - Pluggable external memory providers include Honcho, OpenViking, Mem0, Hindsight, Holographic, RetainDB, ByteRover, Supermemory and Memori.
  - Sources: [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md); [memory-providers.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory-providers.md)
- Known failure mode, per the docs: memory only persists when the model actually calls the tool. "Small local models (roughly under 30B parameters) and models with weak tool-calling" often claim to have saved something without doing it — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)

**Self-improving skills**
- Skills live in `~/.hermes/skills/`, follow the agentskills.io standard, and load by progressive disclosure. "The agent can modify or delete any skill." There is a Skills Hub with sources including official skills and ClawHub, and installs go through a security scan — [skills.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
- The `skill_manage` tool is "the agent's procedural memory". The system prompt tells the agent to save a skill when it works out a multi-step workflow, finds a working path after errors, or is corrected by the user. An advisory linter warns about incident-log-shaped skills, reference sprawl and oversized bodies, but never blocks a write — [skills.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
- Curator (background maintenance of agent-created skills):
  - It runs when 7 days have passed since the last run and the agent has been idle for at least 2 hours.
  - Skills unused for 14 days become `stale`; skills unused for 30 days are archived.
  - Pinned skills and skills referenced by any cron job are exempt.
  - An LLM consolidation and patching pass ("patches drift") is opt-in (`curator.consolidate: false` by default) and typically makes 50–100 API calls.
  - The first pass is deferred by one interval, and `--dry-run` is available.
  - Source: [curator.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/curator.md)

**Scheduling, heartbeats, loops, goals**
- Cron jobs:
  - A single `cronjob_manage` tool lets the agent itself create, pause, edit and remove jobs in natural language.
  - Jobs can be one-shot or recurring, can attach skills, and deliver results to the originating chat, files or platforms.
  - Each run happens in a fresh session.
  - A **no-agent mode** runs a script with no LLM involved.
  - Source: [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md)
- Event-driven firing: webhook routes can set `cron_job` to fire an existing job "the moment something happens… instead of waiting for the next scheduled tick". Routes have HMAC auth, rate limiting, idempotency and an at-most-once claim. The stored prompt is never mutated; the payload is injected as transient context — [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md); [webhooks.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/webhooks.md)
- Guardrail: "Cron-run sessions cannot recursively create more cron jobs… to prevent runaway scheduling loops" — [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md)
- Durability of cron runs: a run keeps its fire identity until a durable delivery handoff is recorded, and the scheduler reconciles unfinished receipts after a restart. "An interrupted execution… stays paused for operator review", and paused jobs are never auto-resumed — [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md)
- The model for a cron run is chosen at fire time: a per-job pin first, then `cron.model`, then the current main model. Per-job reasoning effort can also be pinned — [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md)
- `/heartbeat every <interval> <prompt>` sets one recurring prompt per session that re-enters the same conversation:
  - It fires only when the session is idle (minimum interval 60 s), and user messages take priority.
  - Missed ticks coalesce into one, and the state survives restarts.
  - It can reply with a `NO_REPLY` / `[SILENT]` marker, and a "don't-invent-work guard" tells the agent to stop when nothing has changed.
  - It can be paused or cleared. The docs credit Prime-Agent for the idea.
  - Source: [heartbeat.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/heartbeat.md)
- `/loop` is a timer-driven in-session re-run modelled on Claude Code's `/loop`. `/goal` is a judge-model "Ralph loop" inspired by Codex CLI's `/goal`, which keeps working until the goal is met. For unattended work the docs say to use cron instead — [loops.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/loops.md); [goals.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/goals.md)
- Kanban is a "durable SQLite-backed task board" shared across profiles. "Every worker is a full OS process with its own identity", with iteration budgets and a consecutive-failure circuit breaker — [kanban.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md)

**Messaging gateways**
- The README names Telegram, Discord, Slack, WhatsApp, Signal and CLI; the official site adds Email. The docs `messaging/` folder has adapter pages for:
  - Consumer chat: Telegram, Discord, Slack, WhatsApp (and WhatsApp Cloud), Signal, LINE, iMessage via BlueBubbles, SimpleX.
  - Workplace: Microsoft Teams (and Teams meetings), Google Chat, Matrix, Mattermost, IRC, DingTalk, Feishu, WeCom, Weixin.
  - Other channels: email, SMS, Home Assistant, ntfy, Open WebUI, generic webhooks, a Microsoft Graph webhook, A2A, and others.
  - Sources: [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md); [messaging docs folder](https://github.com/NousResearch/hermes-agent/tree/main/website/docs/user-guide/messaging)
- A separate guide covers giving the agent its own mailbox, operated through a bundled IMAP/SMTP skill: "never hand it your personal inbox" — [agent-email-address.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/agent-email-address.md)

**Subagents and parallel work**
- `delegate_task` spawns child agents with isolated context and their own terminal sessions; only the child's summary returns to the parent. It runs up to 10 concurrent subagents by default (configurable). Top-level delegations run in the background and post back on completion. Python scripts can call tools over RPC — [delegation.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/delegation.md); [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)

**Tool execution environments**
- Six built-in terminal backends: local, Docker, SSH, Modal, Daytona and Vercel Sandbox, plus plugins such as Singularity/Apptainer. "Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand" — [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)
  - Conflict: the marketing site still lists "five" backends (local, Docker, SSH, Singularity, Modal) — [official site](https://hermes-agent.nousresearch.com/)
- Checkpoints use shadow git snapshots before destructive operations, with `/rollback`. They are opt-in and off by default — [checkpoints-and-rollback.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/checkpoints-and-rollback.md)

**Model support**
- "Use any model you want — Nous Portal, OpenRouter, OpenAI, your own endpoint, and many others… Switch with `hermes model`" — [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)
- The docs include provider guides for AWS Bedrock, Azure Foundry, Google Vertex and Gemini, xAI, MiniMax, local Ollama and local models on Mac — [guides folder](https://github.com/NousResearch/hermes-agent/tree/main/website/docs/guides)
- Nous Portal paid tiers list "200+ models" on the official site; a July 2026 article says "over 300" — [official site](https://hermes-agent.nousresearch.com/); [Trending Topics](https://www.trendingtopics.eu/hermes-nous-research/)

**Security model**
- SECURITY.md describes "a single-tenant personal agent". "**The only security boundary against an adversarial LLM is the operating system.** Nothing inside the agent process constitutes containment — not the approval gate, not output redaction, not any pattern scanner, not any tool allowlist" — [SECURITY.md](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)
- Terminal-backend isolation confines shell and file tools only. It does **not** confine code execution, MCP subprocesses, plugins, hooks or skill loading. Whole-process wrapping (Hermes's Docker image or NVIDIA OpenShell) is "the supported posture when the agent ingests content from surfaces the operator does not control — the open web, inbound email, multi-user channels, untrusted MCP servers" — [SECURITY.md](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)
- Credentials: provider and gateway keys are stripped from the environment passed to subprocesses and cron scripts. "This reduces casual exfiltration. It is not containment." Plugins and skills run with full agent privileges, and the control for them is operator review before install. There is no bug bounty — [SECURITY.md](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)
- security.md lists eight layers: user authorization (allow-lists, DM pairing), dangerous-command approval, file-write safety, container isolation, MCP credential filtering, context-file injection scanning, cross-session isolation and input sanitization — [security.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md)
- Approval settings:
  - `approvals.mode` is `smart` by default: an auxiliary LLM auto-approves low-risk commands, auto-denies dangerous ones and escalates uncertain ones. The alternatives are `manual` and `off` (`off` is equivalent to `--yolo`).
  - `cron_mode`, `single_query_mode` and `unattended_mode` (webhook, Graph webhook and API-server sessions) all default to `deny`, because no human is present.
  - Approvals time out after 300 s.
  - There is a permanent allow-list, and `hermes approvals suggest` mines approval history.
  - Source: [security.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md)
- Floors that ignore yolo and "allow always":
  - A hardline blocklist that cannot be overridden (`rm -rf /`, fork bombs, `mkfs`/`dd` on disks, piping untrusted URLs to `sh`).
  - User-defined `approvals.deny` globs, which apply before yolo.
  - Content checks flag secrets in `curl`/`wget` bodies and invisible or bidirectional Unicode.
  - Source: [security.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md)
- Docker, Modal, Daytona and Vercel backends **skip** the dangerous-command check, on the basis that the "container is boundary" — [security.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md)
- Context files (AGENTS.md, .cursorrules, SOUL.md) are scanned for prompt injection. "These patterns are heuristics, not semantic intent detection." The user's own SOUL.md in HERMES_HOME is loaded with a warning rather than blocked — [security.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md)

**Limitations and criticisms**
- External audit (CSA research note, 4 May 2026): researcher @Anic888 (GitHub issue #7826, 11 Apr 2026) reported 4 Critical and 9 High findings in the **default configuration** of v0.8.0.
  - Critical: shell execution guarded only by bypassable regex checks; file reads with no deny list; approval checks skipped in containers; skill files that persist across sessions.
  - High: YOLO mode; prompt-injectable auto-approval; an opt-in write sandbox; unsandboxed hooks and plugins; unpinned git dependencies.
  - Source: [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-hermes-agent-cves-20260504-csa-styled/)
- CVE list (NeuralTrust, 26 Oct 2026): 12 CVEs.
  - CVE-2026-82021 is a supply-chain flaw in the MCP catalog (a mutable branch reference), scored CVSS v4 9.0 and fixed in 0.19.0 / 2026.7.20.
  - CVE-2026-10223 is an injection in memory-content scanning, and CVE-2026-9353 an injection in Skills Guard threat patterns, both fixed in 0.15.0.
  - CVE-2026-53870 left files world-readable, exposing conversation history and HMAC secrets.
  - CVE-2026-7112 and CVE-2026-7113 are missing or flawed authentication on the API server and webhooks.
  - CVE-2026-53869 is DNS rebinding on WebSocket endpoints.
  - Source: [NeuralTrust](https://neuraltrust.ai/blog/hermes-agent-security)
- CVE-2026-11461 is a session-lookup authorization bypass (up to 0.12.0) that can expose other users' sessions. A public PoC exists, and the vendor reportedly did not respond — [SentinelOne](https://www.sentinelone.com/vulnerability-database/cve-2026-11461/)
- Architectural criticism: poisoned memory "can persist across sessions"; self-created skills run with full privileges; terminal sandboxing does not cover code execution, MCP, plugins, hooks or skills; network endpoints should stay off the public internet — [NeuralTrust](https://neuraltrust.ai/blog/hermes-agent-security); [Repello threat model](https://repello.ai/blog/hermes-agent-security)

### Inferences
- Hermes's "lives and interacts" quality comes from five mechanisms working together, not from the model: (a) a supervised, always-running gateway process; (b) conversations that never time out; (c) durable SQLite state for sessions, cron jobs, heartbeats and the kanban board; (d) a small always-in-context memory plus searchable episodic history; (e) self-scheduling through tools the agent can call itself.
- Hermes is explicitly **single-tenant** and assumes a trusted operator. Its own policy says its in-process controls are not boundaries. Enterprise multi-user use is outside its stated security posture unless the whole process is wrapped in a sandbox.

### Gaps
- I did not find Nous Research's own launch announcement, so the exact February 2026 launch date is unverified. The earliest repo tag is 12 Mar 2026.
- I did not verify that all 12 CVEs listed by NeuralTrust are fixed in v0.22.5, nor the current status of CVE-2026-11461. The GitHub API was not reachable from this session, so I did not check the advisory list directly.
- Star and fork counts and the funding reports come from secondary press, not from Nous.

---

## 2. Comparable persistent agents and frameworks (OpenClaw, Letta, LangChain ambient agents, LangGraph/LangSmith Deployment)

### Takeaway
The same design pattern recurs across these systems:
- an always-on gateway or server;
- small always-loaded memory files, plus searchable history and consolidation that runs in the background;
- skills used as procedural memory;
- periodic "heartbeat" turns, cron jobs or event triggers;
- an inbox or owner DM through which humans supervise.

OpenClaw popularised this model and also exposed its security costs: tens of thousands of internet-exposed gateways, a malicious-skill supply-chain campaign, persistence through HEARTBEAT.md injection, and a critical heartbeat sandbox bypass. LangChain provides the primitives (threads/checkpoints, a long-term store, cron jobs, TTLs, interrupts, an Agent Inbox) but not a packaged always-on agent.

### Cited Findings

**OpenClaw (formerly Warelay → Clawdbot → Moltbot)**
- History: first published as Warelay (November 2025), then Clawdbot. It was renamed Moltbot (about 27 Jan 2026) after Anthropic objected to the trademark, and then OpenClaw (30 Jan 2026). The creator is Peter Steinberger, who later joined OpenAI; OpenAI did not acquire OpenClaw. Wikipedia lists the OpenClaw Foundation as developer — [MorphLLM history](https://www.morphllm.com/clawdbot); [Verdent](https://www.verdent.ai/guides/openclaw/founder); [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)
- Heartbeat, original model: a periodic main-session agent turn, by default every 30 minutes (1 hour with Anthropic OAuth), driven by a short `HEARTBEAT.md` checklist in the workspace. An empty file skips the model calls — [OpenClaw HEARTBEAT.md template](https://docs.openclaw.ai/reference/templates/HEARTBEAT.md)
- Heartbeat, current docs: "Heartbeat monitors are retired. Each former monitor becomes an editable automation job." Setup creates one "Proactive check" job for the ambient owner, every 30 minutes by default.
  - Jobs support `activeHours`, `NO_REPLY` for silence, and `payload.skipIfScratchEmpty` to skip calls.
  - `delivery.target: "owner"` sends to an explicitly identified owner DM.
  - Imported `HEARTBEAT.md` files are archived.
  - Source: [OpenClaw heartbeat migration doc](https://docs.openclaw.ai/gateway/heartbeat)
- Automation model: a built-in scheduler handles one-shot, interval, cron and inbound-webhook triggers. **Hooks** (`HOOK.md`) run on lifecycle events. **Standing orders** in `AGENTS.md` are injected into every session.
  - "Inferred commitments", where follow-ups extracted from conversations were delivered via heartbeat, were **removed in v2026.8.1**. The Tasks ledger and the TaskFlow API were also removed.
  - Source: [OpenClaw automation docs](https://docs.openclaw.ai/automation)
- Memory is plain Markdown in the workspace ("The model only remembers what gets saved to disk"):
  - `MEMORY.md` holds curated long-term facts, loaded at session start. `memory/YYYY-MM-DD.md` daily notes are indexed for search; today's and yesterday's notes load on `/new`. There is also an optional `USER.md` and `DREAMS.md`.
  - `memory_search` combines vector and keyword search.
  - A silent "memory flush" turn runs before compaction.
  - "Dreaming" is a scheduled consolidation job that promotes recall-scored items into `MEMORY.md`.
  - Source: [OpenClaw memory docs](https://docs.openclaw.ai/concepts/memory)
- OpenClaw memory safety controls:
  - Provenance: untrusted files are excluded from context.
  - Taint gating: untrusted candidates "never reach the consolidation prompt or durable promotion".
  - "Memory records context but doesn't enforce rules"; hard controls belong in approvals or sandboxing.
  - Action-sensitive notes should record "expiry, source authority, and safe-to-act timing".
  - Memory imported from Hermes, Codex or Claude Code is kept in a separate folder.
  - Source: [OpenClaw memory docs](https://docs.openclaw.ai/concepts/memory)
- Exposure: Censys counted over 30,000 internet-accessible instances as of 8 Feb 2026. The gateway bound to `0.0.0.0:18789` by default — [The Hacker News, 8 Feb 2026](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html)
  - Later scans reported far higher counts (about 65k on Shodan and 180k on ZoomEye in May 2026); these figures come from a search summary I did not open — [Conscia](https://conscia.com/blog/the-openclaw-security-crisis/)
- Skills supply chain:
  - ClawHub skills are now scanned with VirusTotal, and all active skills are re-scanned daily. OpenClaw says this is "not a silver bullet".
  - Snyk found 283 of 3,984 skills (7.1%) had critical flaws exposing credentials.
  - Malicious skills exfiltrated data and installed stealers.
  - Source: [The Hacker News](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html)
  - Koi Security's "ClawHavoc" audit found 341 malicious skills out of 2,857 — [eSecurity Planet](https://esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub)
- Persistence through heartbeat: "an indirect prompt injection on a web page could make OpenClaw append attacker instructions to HEARTBEAT.md". Other reported issues include a one-click RCE that leaked the auth token through the Control UI (since patched), cleartext credential storage (OX Security), and full system access by default unless Docker sandboxing is enabled (HiddenLayer) — [The Hacker News](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html)
- CVE-2026-41329, "Heartbeat context inheritance bypasses sandbox via senderIsOwner escalation": Critical (CVSS v4 9.0), affects versions ≤ 2026.3.28, patched in 2026.3.31, published 31 Mar 2026 — [GitHub Advisory GHSA-g5cg-8x5w-7jpm](https://github.com/advisories/GHSA-g5cg-8x5w-7jpm)
- Nine OpenClaw CVEs were disclosed 18–21 Mar 2026. They include CVE-2026-22172 (CVSS 9.9), which lets an authenticated user grant itself admin scopes during the WebSocket handshake — [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-hermes-agent-cves-20260504-csa-styled/)
- Microsoft Agent 365 added preview policy controls and runtime blocking for managed agents (June 2026), with **initial support for OpenClaw via Intune** — [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)

**Letta**
- Memory blocks are "structured sections of the agent's context window that persist across all interactions". Each has a label, description, value and character limit.
  - The agent edits them with memory tools.
  - Blocks can be `read_only`, which suits shared policies.
  - Several agents can attach the same block, and the last write wins.
  - Source: [Letta memory blocks docs](https://docs.letta.com/guides/agents/memory-blocks)
- Sleep-time agents are background agents that update the primary agent's memory blocks every N steps (default 5) — [Letta sleep-time agents docs](https://docs.letta.com/guides/agents/sleep-time-agents)
- Strategy shift, 16 Mar 2026:
  - Letta Code (an "open, model-agnostic agent harness with persistent memory") became the flagship.
  - Memory is moving to git-backed files, called "context repositories" or MemFS, edited with general tools such as bash. Legacy memory tools such as `core_memory_replace` will be removed.
  - Server-side sleep-time agents will be replaced by client-side subagents.
  - Skills replace server-side MCP. Identities move to the application layer as tags.
  - Agent lifespans should "far exceed that of any underlying model".
  - Source: [Letta "Our next phase"](https://www.letta.com/blog/our-next-phase)

**LangChain ambient agents and Agent Inbox**
- "Introducing ambient agents" (Harrison Chase, 14 Jan 2025, older but foundational):
  - Ambient agents "listen to an event stream and act on it accordingly".
  - Three human-in-the-loop patterns: **notify**, **question** and **review**.
  - The Agent Inbox is a UI modelled on email and ticketing that shows "all open lines of communication". LangChain tried Slack first, but notifications got lost.
  - LangGraph supplies persistence, `interrupt`, a long-term memory store and cron jobs.
  - The reference implementation is an email assistant.
  - Source: [LangChain blog](https://www.langchain.com/blog/introducing-ambient-agents)

**LangGraph / LangSmith Deployment primitives for long-running agents**
- Cron jobs, in LangSmith Deployment (formerly LangGraph Platform):
  - **Thread-bound** crons (`create_for_thread`) run against an existing thread; **stateless** crons create a new thread for each run.
  - All schedules are in UTC.
  - For stateless crons, `on_run_completed="delete"` (the default) or `"keep"` controls whether the thread is kept.
  - The docs warn that unused crons should be deleted because they "can generate unwanted LLM API charges".
  - Source: [LangSmith cron jobs docs](https://docs.langchain.com/langsmith/cron-jobs)
- TTLs:
  - Checkpointer TTL uses a strategy of `delete` (the default) or `keep_latest`. Store TTL has `refresh_on_read` (default true). The sweep interval defaults to 5 minutes.
  - "If omitted, threads do not expire by default" and store "items do not expire by default".
  - Source: [LangSmith configure TTL](https://docs.langchain.com/langsmith/configure-ttl)
- Deep Agents memory:
  - Memory is filesystem-backed (`memory=["/memories/AGENTS.md"]`, `skills=["/skills/"]`), with `/memories/` routed to a persistent StoreBackend.
  - Scopes: agent-scoped (the assistant ID, a "persistent identity over time"; needs `deepagents>=0.5.0`), user-scoped (the recommended default) and org-scoped (typically read-only).
  - Optional background consolidation ("sleep-time compute") is triggered by cron, and the cron interval must match the lookback window.
  - It warns that shared writable memory allows a malicious user to "inject instructions". Mitigations: user scope, read-only shared memory, and human approval via interrupts before writes to sensitive paths.
  - Source: [Deep Agents memory docs](https://docs.langchain.com/oss/python/deepagents/memory)

### Inferences
- OpenClaw retired its dedicated heartbeat in favour of ordinary scheduled jobs with owner-only delivery and skip-if-empty, and removed "inferred commitments" in v2026.8.1. This suggests the most autonomous "proactive" features were the hardest to keep reliable and safe.
- LangGraph/LangSmith already provides every durable primitive a weeks-long Deep Agent needs (threads, checkpoints, store, crons, TTL, interrupts). The always-on gateway, channel adapters, owner identity and inbox are what Hermes and OpenClaw add on top.

### Gaps
- The OpenClaw release that turned heartbeat monitors into automation jobs is not stated in the page I fetched.
- Counts of malicious ClawHub skills vary widely between sources (341 to over 1,000). I relied on the Koi/eSecurity Planet figure without opening Koi's original post.
- The "Letta (formerly MemGPT)" lineage was not re-verified from a Letta page in this pass.
- I did not fetch LangSmith docs on background runs or double-texting.

---

## 3. How the cloud platforms handle long-lived agents versus sessions

### Takeaway
The cloud platforms separate **compute sessions**, which are bounded, from **identity and memory**, which persist.
- AWS: AgentCore Runtime sessions run in per-session microVMs with a 15-minute idle default and 8-hour lifetime default (configurable up to 14 days). Continuity comes from session storage and AgentCore Memory.
- Google: Agent Runtime runs agents for up to 7 days, and Memory Bank, Agent Identity and an Inbox cover persistence and supervision.
- Microsoft: persistence is modelled as **identity**. Entra agent identities have sponsors, optional user accounts with mailboxes (Frontier preview), and Agent 365 governance (GA 1 May 2026). Copilot Studio autonomy comes from event triggers that run on the maker's credentials.

### Cited Findings

**Microsoft Copilot Studio (autonomous agents and triggers)**
- Event triggers let agents "act autonomously in response to the defined event occurring". Examples include a new SharePoint item, a new OneDrive file, a completed Planner task and a **Recurrence** trigger. They require generative orchestration and depend on DLP policy (doc dated 9 Sep 2026) — [Copilot Studio event triggers](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about)
- Billing: each trigger payload counts as a message, so "a recurrence trigger set to activate every 10 minutes sends a trigger payload as a message… every 10 minutes". Frequent triggers can exceed quotas and cause throttling — [Copilot Studio event triggers](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about)
- Credentials: "Event triggers can only use the agent maker's credentials… This might allow users of an agent to… access data and systems using that same authorization." To run autonomously, every action must use maker authentication. Admins can block triggers via data policies — [Copilot Studio event triggers](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about)

**Microsoft Agent 365 and Entra Agent ID**
- Agent 365 has been **GA since 1 May 2026** for the Commercial segment. It costs USD 15 per user per month, or is included in Microsoft 365 E7, and its pillars are observe, govern and secure, built around a central registry — [Agent 365 overview](https://learn.microsoft.com/en-us/microsoft-agent-365/overview); [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- GA versus preview, as of the 1 May 2026 post:
  - GA: delegated-access agents and "own-access agents operating behind the scenes".
  - Public preview: own-access agents in team workflows, registry sync with AWS Bedrock and Google Cloud, and Windows 365 for Agents.
  - "Basic lifecycle actions such as start, stop, and delete are planned but not yet available" for synced agents.
  - Source: [Microsoft Security blog](https://www.microsoft.com/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- Identity model:
  - An **agent identity blueprint** is a template that holds credentials and inheritable permissions.
  - An **agent identity** is a service principal with its own sponsor.
  - An optional **agent's user account** lets the agent have "a mailbox and OneDrive storage, appear in directory… and be reached through Teams, Outlook, Word comments, and email". It is available **only to Frontier preview tenants**.
  - Source: [Agent 365 identity](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/identity)
- Execution modes:
  - **S2S**: the agent acts as itself, "for scheduled tasks, monitoring, and background processing".
  - **OBO**: the agent acts for a signed-in user.
  - **Agentic-User**: the agent acts as its own user account, for example to read its own mailbox. Requires Frontier.
  - Source: [Agent 365 identity](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/identity)
- Lifecycle: every agent identity and blueprint needs at least one **sponsor**. Sponsors "might be asked to decide whether an agent should be retained or disabled". A blueprint lets an admin "disable every agent of that kind in one operation". Agent identities cannot use MFA and are governed by Conditional Access instead — [Agent 365 identity](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/identity)

**AWS Bedrock AgentCore**
- Each Runtime session gets a dedicated microVM. "After session completion, the entire microVM is terminated and memory is sanitized." AgentCore "does not enforce session-to-user mappings"; the client backend has to — [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- Lifecycle:
  - A session stops on inactivity (default 15 minutes), on reaching maximum lifetime (default 8 hours), on `StopRuntimeSession`, or when it fails health checks.
  - The next invoke provisions new compute. "The session itself remains valid until the AgentCore Runtime ARN is deleted."
  - Background work is signalled by returning a `HealthyBusy` ping status.
  - "Sessions last up to 8 hours for each lifecycle on microVMs, or up to 14 days on Instances."
  - Source: [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- `LifecycleConfiguration`: `idleRuntimeSessionTimeout` defaults to 900 s and `maxLifetime` to 28,800 s. The current API reference gives a valid range of 60–1,209,600 s (14 days) for both — [AgentCore LifecycleConfiguration API](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_LifecycleConfiguration.html)
  - Conflict: some CloudFormation reference copies still list a 60–28,800 s maximum — [CloudFormation LifecycleConfiguration](https://docs.aws.eu/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrockagentcore-runtime-lifecycleconfiguration.html)
- Continuity: by default "compute… is ephemeral". **Session storage** keeps the filesystem across stop/resume cycles. For data that must outlive the session, the docs say to "use AgentCore Memory" — [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- AgentCore Memory:
  - Short-term memory is turn-by-turn within a session. Long-term memory automatically extracts preferences, facts and summaries across sessions.
  - The docs give "invoice approval… track the status of each step" as a workflow use case.
  - Strategies can be built-in, built-in with overrides, or self-managed. Without a strategy, no long-term records are extracted.
  - Sources: [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html); [Memory strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html)

**Google (Vertex AI Agent Engine, now Gemini Enterprise Agent Platform)**
- Gemini Enterprise long-running agents were announced 22 Apr 2026 (Cloud Next). They run "from hours to days" in Google's cloud sandboxes.
  - An **Inbox** is the "central command location to monitor, guide, and securely manage all of your agent activity", with categories "Needs your input", "Errors" and "Completed".
  - It includes human-in-the-loop checkpoints and **Agent Identity**: "unique digital IDs… least privilege for every agent".
  - Features were to roll out "over the coming months".
  - Source: [Google Cloud blog, 22 Apr 2026](https://cloud.google.com/blog/products/ai-machine-learning/whats-new-in-gemini-enterprise)
- The 29 Jul 2026 Agent Platform announcement made these "newly generally available":
  - **Agent Runtime**, which "runs continuously for up to 7 days" (multi-day async work).
  - **Agent Memory Bank**, which keeps preferences, past decisions and account history.
  - **Agent Identity**, which binds access to the runtime and "automatically manages identity lifecycles to eliminate dormant credentials".
  - **Agent Gateway**, with Model Armor against prompt injection and tool poisoning.
  - **Agent Registry**.
  - **Agent Evaluation**, which detects "behavioral drift".
  - Source: [Google Cloud blog, 29 Jul 2026](https://cloud.google.com/blog/products/ai-machine-learning/whats-new-in-gemini-enterprise-agent-platform)
- Release notes:
  - Memory Bank memory profiles GA (15 Jul 2026); IngestEvents API GA (8 Jul 2026); global endpoints for Memory Bank and Sessions GA (17 Jun 2026).
  - Agent Identity API **Preview** (18 Jun 2026); Managed Agents API **Preview** (19 May 2026).
  - A "Deferred tier" **Preview** (2 Sep 2026) queues background agent work for off-peak hours at a 50% token discount.
  - Source: [Agent Platform release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes)
- Older: Vertex AI Agent Engine Sessions and Memory Bank became GA on 17 Dec 2025, with charging from 28 Jan 2026. This comes from the search summary of the release notes — [Vertex AI Agent Builder release notes](https://docs.cloud.google.com/agent-builder/release-notes)
- Memory Bank supports VPC Service Controls, CMEK, data residency, IAM Conditions and memory revisions — [Memory Bank overview](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview)

### Inferences
- None of the hyperscalers offers a Hermes-style "process that lives forever". The longest single compute lifetimes are 7 days (Google Agent Runtime) and 14 days (AgentCore, per the current API maximum and on "Instances"). Agents that live for weeks are expected to be rebuilt from durable memory, storage and identity on each wake-up, triggered by schedules or events.
- Microsoft's design treats the persistent "digital worker" as an identity with a sponsor and, optionally, a mailbox, rather than as a running process. The mailbox-holding agent user is still Frontier-preview only.

### Gaps
- I could not verify the reported 365-day default session TTL for Vertex Agent Engine Sessions; the fetched session pages did not mention TTL. Memory Bank TTL appeared in a search snippet of the overview page but not in my fetch.
- I found no official Gemini Enterprise feature named "scheduled actions". The closest I found are recurring tasks, the Deferred tier, and BigQuery/Pub/Sub-triggered async runs (the last from a secondary source).
- AgentCore "Instances", the 14-day compute option, was not researched further. Exact GA dates for Copilot Studio autonomous triggers were not captured.

---

## 4. Design patterns and risks specific to persistent agents

### Takeaway
Long-lived agents raise problems that one-shot agents never hit:
- Wake-ups should be event-driven where possible. Where polling is needed, use idle-only, coalescing heartbeats that can return "nothing to report" silently.
- State and scheduled fires need to be durable, at-most-once, and recoverable after a crash.
- Memory must be bounded, curated, provenance-tagged and approvable, because poisoned memory persists by design.
- Self-written skills and memories drift and can degrade safety.
- Credentials outlive sessions and need sponsors and lifecycle management.
- Cost grows with cadence and context length.
- Supervision needs an inbox, digests and approvals.
- Retiring an agent means stopping its schedules and disabling its identity, not just killing a process.

### Cited Findings

**Event-driven wake-ups versus heartbeats and polling**
- Hermes webhook routes can fire a cron job "the moment something happens… instead of waiting for the next scheduled tick", with the schedule kept only as a fallback sweep — [Hermes webhooks.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/webhooks.md)
- Hermes heartbeat rules: idle-only; missed ticks coalesce ("one heartbeat turn, not a backlog"); user messages take priority; silent `NO_REPLY`; a "don't-invent-work guard" — [Hermes heartbeat.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/heartbeat.md)
- OpenClaw: an empty `HEARTBEAT.md` skips model calls; jobs can use `skipIfScratchEmpty`, `activeHours` and `idleOnly` — [OpenClaw HEARTBEAT template](https://docs.openclaw.ai/reference/templates/HEARTBEAT.md); [OpenClaw automation](https://docs.openclaw.ai/automation)
- LangChain's framing: ambient agents act on event streams — [LangChain blog](https://www.langchain.com/blog/introducing-ambient-agents)
- Copilot Studio: triggers are external events, with Recurrence as one trigger type — [Copilot Studio triggers](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about)

**Durable state and checkpointing**
- Hermes:
  - Sessions are stored in SQLite `state.db`.
  - Heartbeat state is stored in `SessionDB.state_meta` and restored on gateway restart.
  - Cron "admission recovery" keeps fire identity until a durable delivery handoff is recorded, and interrupted runs stay paused for operator review.
  - The kanban board is durable SQLite.
  - Sources: [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md); [heartbeat.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/heartbeat.md); [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md); [kanban.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md)
- LangGraph persistence "saves agent state between steps so the agent can pause and wait for feedback" — [LangChain blog](https://www.langchain.com/blog/introducing-ambient-agents)
- AgentCore session storage persists the filesystem across stop/resume — [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)

**Memory hygiene and poisoning**
- Systematic study (Dash et al., arXiv 2606.04329, June 2026): "a single adversarial write can exert long-term influence".
  - It identifies 4 memory write channels, 9 structural vulnerabilities and 6 attack classes, and builds the MPBench benchmark.
  - "Agents designed to write and retrieve memory more aggressively are more exploitable." Existing prompt-injection defenses "do not adequately cover memory poisoning".
  - Source: [arXiv 2606.04329](https://arxiv.org/abs/2606.04329)
- OWASP's Top 10 for Agentic Applications lists Memory and Context Poisoning as ASI06. Radware disclosed "ZombieAgent" (January 2026), which planted persistent rules in an agent's long-term memory. Both come from a secondary source — [Akto](https://www.akto.io/blog/memory-poisoning-ai-agents)
- Further preprints: an empirical study of memory revocation enforcement (arXiv 2609.08258) and MemSentry (2609.08747). Per the search summary, the revocation study finds revoked memories can still be treated as authoritative — [arXiv 2609.08258](https://arxiv.org/pdf/2609.08258); [arXiv 2609.08747](https://arxiv.org/pdf/2609.08747)
- A web-page prompt injection appended attacker instructions to OpenClaw's `HEARTBEAT.md`, a file the agent re-reads every cycle — [The Hacker News](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html)
- Hermes's own memory-scanner and Skills Guard defenses have had injection CVEs (CVE-2026-10223, CVE-2026-9353) — [NeuralTrust](https://neuraltrust.ai/blog/hermes-agent-security)
- Hygiene controls in shipping products:
  - Hermes: hard character caps, write approval, staged background writes, `/journey` pruning — [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
  - OpenClaw: provenance, taint gating, expiry and source-authority notes — [OpenClaw memory](https://docs.openclaw.ai/concepts/memory)
  - Deep Agents: user scope, read-only org memory, interrupts before sensitive writes — [Deep Agents memory](https://docs.langchain.com/oss/python/deepagents/memory)
  - Letta: read-only blocks — [Letta memory blocks](https://docs.letta.com/guides/agents/memory-blocks)
  - Hermes and Letta share a single-writer or last-write-wins caveat: Hermes warns against two processes on one home, and Letta blocks are last-write-wins — [Hermes memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md); [Letta memory blocks](https://docs.letta.com/guides/agents/memory-blocks)

**Drift of self-modified skills and instructions**
- "Your Agent May Misevolve" (Shao et al., NeurIPS 2025 / ICLR 2026) studies drift in self-evolving agents across four pathways: model, memory, tool and workflow. It finds degraded safety alignment after memory accumulation, and vulnerabilities introduced by tool creation and reuse, even on top-tier models — [ICLR 2026 proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/a24cd16bc361afa78e57d31d34f3d936-Abstract-Conference.html); [Hugging Face paper page](https://huggingface.co/papers/2509.26354)
  - Decrypt reported that a coding agent's refusal rate fell from 99.4% to 54.4% after it drew on its own memory. This figure is secondary and was not verified against the paper — [Decrypt](https://decrypt.co/?p=342484)
- The audit of Hermes v0.8.0 rated "skill files that persist across sessions" as a **Critical** default-configuration issue — [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-hermes-agent-cves-20260504-csa-styled/)
- Hermes counters skill sprawl and drift with the curator (stale after 14 days, archived after 30, opt-in LLM consolidation that "patches drift", pinning) and with an advisory linter — [curator.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/curator.md); [skills.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
- Google's Agent Evaluation runs online monitors for "behavioral drift in production" — [Google Cloud blog, 29 Jul 2026](https://cloud.google.com/blog/products/ai-machine-learning/whats-new-in-gemini-enterprise-agent-platform)

**Identity and credentials that outlive a session**
- Copilot Studio triggers run on the maker's credentials, which users of the agent can then exercise — [Copilot Studio triggers](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about)
- Microsoft Entra: S2S mode for scheduled and background work; blueprint credentials are shared by every agent created from that blueprint ("treat each blueprint as a credential boundary"); a sponsor is required — [Agent 365 identity](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/identity)
- Google Agent Identity binds access to the runtime "to mitigate token theft" and "eliminate[s] dormant credentials" — [Google Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/whats-new-in-gemini-enterprise-agent-platform)
- Hermes strips credentials from subprocess and cron environments but says this "is not containment". The CSA advises rotating credentials for any deployment that ran in YOLO mode — [SECURITY.md](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md); [CSA](https://labs.cloudsecurityalliance.org/research/csa-research-note-hermes-agent-cves-20260504-csa-styled/)
- OpenClaw "stores credentials in cleartext" (OX Security) — [The Hacker News](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html)

**Cost control for always-on agents**
- Hermes:
  - Weeks-long single sessions "grow expensive" through repeated compaction.
  - The frozen memory snapshot preserves the prefix cache.
  - The background review and the curator can run on cheaper auxiliary models.
  - Cron jobs can pin a model or run in no-agent mode.
  - Daytona and Modal backends hibernate when idle.
  - Sources: [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md); [cron.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md); [README](https://github.com/NousResearch/hermes-agent/blob/main/README.md)
- Copilot Studio bills every trigger payload as a message — [Copilot Studio triggers](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-triggers-about)
- LangSmith warns that unused crons incur LLM charges — [LangSmith cron jobs](https://docs.langchain.com/langsmith/cron-jobs)
- Deep Agents: consolidating more often than users actually talk to the agent wastes tokens — [Deep Agents memory](https://docs.langchain.com/oss/python/deepagents/memory)
- Google's Deferred tier gives a 50% discount for off-peak background work — [Agent Platform release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes)
- AgentCore's idle timeout (default 15 minutes) tears down compute — [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)

**Human supervision over time**
- LangChain: notify, question and review, through the Agent Inbox — [LangChain blog](https://www.langchain.com/blog/introducing-ambient-agents)
- Gemini Enterprise Inbox, with "Needs your input", "Errors" and "Completed" categories — [Google Cloud blog, 22 Apr 2026](https://cloud.google.com/blog/products/ai-machine-learning/whats-new-in-gemini-enterprise)
- Hermes:
  - Approvals arrive in chat with native buttons (Telegram, Discord, Slack).
  - A 300 s approval timeout applies, and unattended sessions default to deny.
  - Staged memory writes are reviewed with `/memory pending`, and "💾 Memory updated" notifications report background changes.
  - Sources: [security.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md); [memory.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- OpenClaw delivers to the owner's DM only — [OpenClaw heartbeat](https://docs.openclaw.ai/gateway/heartbeat)
- Agent 365 provides a registry, sponsors and role-specific oversight — [Agent 365 overview](https://learn.microsoft.com/en-us/microsoft-agent-365/overview)

**Stopping and retiring**
- Hermes:
  - `/heartbeat pause` and `/heartbeat clear`; cron pause and remove. Leaving a conversation clears its heartbeat, and resuming the conversation does not bring it back.
  - The curator archives unused skills.
  - Stopping the gateway keeps the data on disk.
  - Sources: [heartbeat.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/heartbeat.md); [curator.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/curator.md); [official site](https://hermes-agent.nousresearch.com/)
- AWS: `StopRuntimeSession`; a session remains valid until the runtime ARN is deleted — [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- Microsoft: a sponsor decides whether to retain or disable an agent; disabling a blueprint disables every agent of that kind; registry start/stop/delete for synced agents was "planned" as of May 2026 — [Agent 365 identity](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/identity); [Microsoft Security blog](https://www.microsoft.com/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- LangSmith: `crons.delete`; thread and store TTLs, which are off by default — [LangSmith cron jobs](https://docs.langchain.com/langsmith/cron-jobs); [configure TTL](https://docs.langchain.com/langsmith/configure-ttl)

### Inferences
- Across sources, "persistence" breaks into separately governable parts:
  - a schedule or trigger registry;
  - durable conversation and checkpoint state;
  - curated semantic memory;
  - procedural memory (skills);
  - an identity with credentials and a human sponsor.

  Each has its own failure mode (runaway cost, crash replay, poisoning, drift, orphaned credentials) and its own off-switch.
- The pattern most consistently recommended by the security sources pairs agent autonomy with OS- or platform-level isolation, provenance-aware memory writes and explicit human approval for durable changes.

### Gaps
- I found no rigorous public cost data (for example tokens per day) for running Hermes or OpenClaw always-on.
- Several memory-poisoning items (OWASP ASI06 wording, ZombieAgent details, the revocation-study finding) come from secondary or search summaries; the primary papers and advisories were not opened in full.
- I found no documented, standard "agent retirement" procedure that covers memory deletion and credential revocation together on any one platform.
