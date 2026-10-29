# Vendor-neutral standards and reference frameworks for an enterprise "agent OS" (state as of 27 Oct 2026)

Scope note: these notes cover open protocols, identity/authorization, policy-as-code, telemetry, security frameworks, governance/regulation, autonomy taxonomies, and the "agent OS" concept. Every dated item carries its date. Items older than 2026 are marked "(older)" where that matters. Where only secondary sources were found, this is stated.

---

## 1. Model Context Protocol (MCP): version, authorization, registry, elicitation/HITL, governance, security issues

### Takeaway
MCP's current spec revision is **2026-07-28** (released 28 Jul 2026). It made the protocol core **stateless**: no initialize handshake and no `Mcp-Session-Id`. It replaced server-initiated requests with **Multi Round-Trip Requests**, where the server returns `input_required`. Authorization is an **OAuth 2.1 resource-server model**. The MCP server MUST publish **RFC 9728 Protected Resource Metadata**, clients MUST send **RFC 8707 resource indicators**, and RFC 9207 `iss` checks apply. Client ID Metadata Documents are preferred and Dynamic Client Registration is deprecated. Token passthrough is explicitly forbidden. MCP has been governed under the Linux Foundation's **Agentic AI Foundation (AAIF)** since **9 Dec 2025**. The official MCP Registry was still described as **preview** in the sources found.

### Cited Findings
**Version and release**
- The current MCP spec revision is **2026-07-28**, released on 28 July 2026 alongside updated Tier 1 SDKs. The release post describes MCP as "transforming from a bidirectional stateful protocol into a request/response stateless protocol." — [MCP blog: The 2026-07-28 Specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/); [MCP versioning page](https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning)
- Stateless core: the `initialize`/`initialized` handshake and the `Mcp-Session-Id` header are retired (SEP-2575, SEP-2567). Each request carries the protocol version, client identity and capabilities in `_meta`. An optional `server/discover` RPC exists. Requests can hit any instance behind a round-robin load balancer. State is kept through explicit handles passed as tool arguments. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **Multi Round-Trip Requests (MRTR, SEP-2322)** replace server-initiated `elicitation/create`, `sampling/createMessage` and `roots/list`. The server returns `resultType: "input_required"` and the client retries with `inputResponses`. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **Header-based routing (SEP-2243):** Streamable HTTP requests must carry `Mcp-Method` and `Mcp-Name` headers, so gateways can route and meter without parsing JSON bodies. **Cacheable list results (SEP-2549):** responses carry `ttlMs`/`cacheScope`. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **Tasks (SEP-2663)** moved out of the experimental core into the `io.modelcontextprotocol/tasks` extension, with `tasks/get` polling, `tasks/update`, and a single `subscriptions/listen` stream. A formal **extensions framework** now covers Tasks, **MCP Apps** and **Enterprise Managed Authorization (EMA)**. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **Deprecations:** Roots, Sampling and Logging are deprecated (SEP-2577) but keep working for at least 12 months. The legacy HTTP+SSE transport is deprecated with a year-long offramp. A formal deprecation policy sets a 12-month minimum window. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **SDKs:** TypeScript, Python, Go and C# support 2026-07-28; Rust is in beta. Microsoft shipped the official MCP C# SDK v2.0 implementing 2026-07-28. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/); [.NET Blog](https://devblogs.microsoft.com/dotnet/announcing-v20-of-the-official-mcp-csharp-sdk/)
- **Previous revision (older): 2025-11-25.** It added URL-mode elicitation (SEP-1036), Client ID Metadata Documents as the recommended registration method (SEP-991), OpenID Connect Discovery for AS discovery, icons, and incremental scope consent via `WWW-Authenticate` (SEP-835). — [MCP 2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)
- 2026-07-28 removed `notifications/elicitation/complete` and `elicitationId` from URL-mode elicitation. Under MRTR, clients learn the outcome by retrying, and servers correlate retries with their own `requestState`. — [MCP 2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)

**Authorization model (2026-07-28)**
- Authorization is OPTIONAL. HTTP transports SHOULD conform. STDIO transports SHOULD NOT and should take credentials from the environment instead. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Standards basis: OAuth 2.1 draft (draft-ietf-oauth-v2-1-13), RFC 6750, RFC 8414, RFC 7591 (DCR), RFC 8707, RFC 9728, RFC 9207, draft-ietf-oauth-client-id-metadata-document-00, and OIDC Discovery/Registration. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Roles: the MCP server is an **OAuth 2.1 resource server** and the MCP client is an OAuth 2.1 client. The authorization server's implementation is out of scope. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- MCP servers **MUST** implement RFC 9728 Protected Resource Metadata, and clients **MUST** use it for AS discovery. The AS MUST offer RFC 8414 or OIDC Discovery, and clients MUST support both. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Client registration: Client ID Metadata Documents are SHOULD. Pre-registration is allowed. **DCR is MAY and "deprecated and retained for backwards compatibility."** — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Clients **MUST** use PKCE and **MUST** send the RFC 8707 `resource` parameter (the canonical MCP server URI) in both the authorization and token requests. Clients MUST record the expected issuer and validate `iss` per RFC 9207 before redeeming a code. This defends against mix-up attacks. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Servers **MUST** validate that tokens were issued for them as audience. "MCP servers MUST NOT accept or transit any other tokens." Clients MUST NOT send tokens from any AS other than the server's own. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Scope model: the server sends a `scope` in the `WWW-Authenticate` 401 challenge. At runtime it returns **403 `insufficient_scope`** for **step-up authorization**, and the client unions old and new scopes. Clients acting on a user's behalf SHOULD attempt step-up. `client_credentials` clients MAY. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- Authorization extensions (optional, additive, composable) live in the `modelcontextprotocol/ext-auth` repo. — [MCP Authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)

**Elicitation / human-in-the-loop**
- Elicitation has a **form mode** (structured data with a restricted flat JSON schema) and a **URL mode** (out-of-band, for sensitive interactions such as credentials, payments and third-party OAuth). Servers **MUST NOT** use form mode for passwords, API keys, tokens or payment credentials. — [MCP Elicitation spec](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
- In 2026-07-28, elicitation is delivered inside an `InputRequiredResult` and answered by retrying the request. Responses use a three-action model: `accept` / `decline` / `cancel`. Clients MUST show which server is asking and offer decline and cancel. For URL mode, clients MUST show the full URL, MUST NOT prefetch it, and MUST get consent before opening it in a way that keeps the LLM from inspecting the page. — [MCP Elicitation spec](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
- URL-mode elicitation lets an MCP server act as an OAuth client to a third-party API. Third-party credentials MUST NOT transit the MCP client. The server MUST NOT reuse the client's token, because that would be passthrough. The server MUST verify that the user completing the flow is the one who started it (anti-phishing). — [MCP Elicitation spec](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)

**Registry**
- The official MCP Registry (registry.modelcontextprotocol.io) launched in **preview on 8 Sep 2025 (older)**. It acts as an upstream source of truth for public and private **sub-registries**, which can add metadata via `_meta`. — [MCP blog: registry preview](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)
- The registry terms state it is "currently in preview," that breaking changes or data resets may occur before GA, and that there are no uptime or durability guarantees. — [MCP Registry terms](https://modelcontextprotocol.io/registry/terms-of-service)
- A third-party tracker cites a 17 Oct 2026 snapshot of the official registry with 44,805 distinct server names. This is secondary and unverified. — [APITracker MCP statistics](https://apitracker.io/mcp-statistics)

**Governance**
- On **9 Dec 2025** the Linux Foundation announced the **Agentic AI Foundation (AAIF)**, anchored by Anthropic's **MCP**, Block's **goose** and OpenAI's **AGENTS.md**. — [Linux Foundation press release](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)
- A 2026 AAIF post on the MCP 2026-07-28 migration is hosted on aaif.io, which indicates MCP is maintained under AAIF. — [AAIF blog: MCP 2026-07-28](https://aaif.io/blog/mcp-2026-07-28-whats-changing-and-how-to-migrate)
- Spec changes go through numbered **SEPs** (Spec Enhancement Proposals), for example SEP-2575, SEP-2322 and SEP-2663. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

**Known security issues**
- **Confused deputy:** MCP proxy servers that use a static client ID with a third-party AS, plus DCR and consent cookies, can leak auth codes to attackers. Mitigation: proxies **MUST** implement per-client consent, exact `redirect_uri` matching and single-use `state`. — [MCP Security Best Practices](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices)
- **Token passthrough** is "explicitly forbidden." Its risks are security-control circumvention, broken audit trails and trust-boundary violations. — [MCP Security Best Practices](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices)
- Other enumerated attacks include: SSRF via OAuth metadata URLs (block private IP ranges, use egress proxies); **state-handle hijacking**, the stateless replacement for session hijacking (bind handles to the token's `sub`); local MCP server compromise (show the exact command, sandbox it); malicious authorization URLs (`javascript:`, shell injection); stdio proxy escalation; mix-up attacks; localhost redirect impersonation with CIMD; and scope minimization. — [MCP Security Best Practices](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices)
- **Tool poisoning** (Invariant Labs, **April 2025, older**) hides instructions in tool descriptions, for example telling the model to read SSH keys and pass them in an argument. **Tool shadowing** means one server's description alters how the agent uses another trusted server. **Rug pull** means a tool definition changes after approval via `notifications/tools/list_changed`. Invariant released MCP-Scan (11 Apr 2025), which pins tool definitions by hash. — [Invariant Labs](https://invariantlabs.ai/blog/mcp-security-notification); [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-tool-poisoning-ai-agent-exfiltration-2/)
- CVE-2025-54136 (July 2025) showed tool approvals did not survive later server-side changes, a rug-pull pattern. OWASP lists tool poisoning as **MCP03:2025** in its MCP Top 10. — [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-tool-poisoning-ai-agent-exfiltration-2/)
- The MCP spec's own security doc does not address tool-description poisoning or prompt injection as attacks. Its scope is auth and transport. — [MCP Security Best Practices](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices)

### Inferences
- An agent OS that fronts MCP servers through a gateway can use the new `Mcp-Method`/`Mcp-Name` headers for routing and per-tool authorization without body parsing. The stateless core suits horizontally scaled gateways.
- Human-in-the-loop in MCP is now a "return `input_required`, retry with answers" pattern. This maps naturally onto checkpoint/resume (e.g., LangGraph interrupts) but needs a durable store for `requestState`.
- Clients built against 2025-era MCP (sessions, server-initiated sampling/elicitation, DCR) face a migration. The deprecation window is at least 12 months from Jul 2026.
- Tool-description integrity (pinning or hashing tool definitions, re-approval on change) is not specified by MCP. A platform must provide it.

### Gaps
- No confirmation found that the MCP Registry reached GA or a frozen v1 API by Oct 2026. The latest primary source still says "preview."
- The date form-mode elicitation was first introduced (believed to be 2025-06-18) was not verified in this session.
- The contents of the Enterprise Managed Authorization (EMA) extension were not retrieved.

---

## 2. Agent2Agent (A2A): version, Agent Cards, discovery, task lifecycle, auth, governance, adoption

### Takeaway
**A2A v1.0** is the first stable release (March 2026). It brought multi-protocol bindings (JSON-RPC, gRPC, HTTP+JSON/REST), version negotiation, multi-tenancy and **signed Agent Cards**. The task lifecycle has explicit interrupted states, **`INPUT_REQUIRED`** and **`AUTH_REQUIRED`**, for human or credential input. Google donated A2A to the Linux Foundation in **June 2025**, and A2A **joined AAIF on 17 Aug 2026**, putting it under the same roof as MCP. AWS (AgentCore), Microsoft (Azure AI Foundry, Agent Framework), Google Cloud, SAP, Salesforce, ServiceNow and LangChain (LangGraph Agent Server) support it.

### Cited Findings
- Timeline: Google announced A2A on **9 Apr 2025**. It was donated to the Linux Foundation on **23 Jun 2025**, and **v1.0** was released in **March 2026** as "the first stable, fully production-ready version." — [Google Open Source Blog (16 Apr 2026)](https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html)
- Exact v1.0 day conflicts across sources. Secondary sources say **12 Mar 2026**, with v1.0.1 as a later patch. Another says 9 Apr 2026. — [TestMu AI blog](https://www.testmuai.com/blog/a2a-protocol-v1/); contradicted by [Agora Intelligence](https://agora-intelligence.com/en/blog/leon-a2a-protocol-production-2026)
- The spec site lists the latest released version as **1.0.0**, with prior 0.3.0, 0.2.6 and 0.1.0. The normative source is the protobuf file `spec/a2a.proto`. Renamed fields stay deprecated until the next major version. — [A2A specification](https://a2a-protocol.org/latest/specification/)
- **Bindings:** JSON-RPC (§9), gRPC (§10), HTTP+JSON/REST (§11) and custom bindings (§12). — [A2A specification](https://a2a-protocol.org/latest/specification/)
- **Task states:** `SUBMITTED`, `WORKING`; interrupted `INPUT_REQUIRED`, `AUTH_REQUIRED`; terminal `COMPLETED`, `FAILED`, `CANCELED`, `REJECTED`. — [A2A specification](https://a2a-protocol.org/latest/specification/)
- **Agent Card** includes `supportedInterfaces` (each with binding, URL and protocol version), `capabilities` (`streaming`, `pushNotifications`, `extendedAgentCard`), `skills` (AgentSkill), `securitySchemes`/`security`, and `signatures` (AgentCardSignature, with signing rules in §8.4). An **Extended Agent Card** is returned after authentication. — [A2A specification](https://a2a-protocol.org/latest/specification/)
- In v1.0, `supportedInterfaces` replaces v0.3's single URL, so an agent can advertise several versions during migration. — [TestMu AI blog](https://www.testmuai.com/blog/a2a-protocol-v1/)
- **Auth:** security schemes cover API key, HTTP auth, OAuth 2.0 (authorization code, client credentials, device code), OpenID Connect and mutual TLS. §7 covers server identity, client authentication and in-task authorization. Push notifications are HTTP POST webhooks. — [A2A specification](https://a2a-protocol.org/latest/specification/)
- **Discovery:** the well-known path in practice is `/.well-known/agent-card.json`. LangGraph Agent Server exposes it per assistant at `GET /.well-known/agent-card.json?assistant_id=...` (requires `langgraph-api >= 0.4.21`; supports `message/stream`, `tasks/get`). — [LangChain docs: A2A endpoint in Agent Server](https://docs.langchain.com/langsmith/server-a2a)
- Older `/.well-known/agent.json` naming persists. LiteLLM tries `agent-card.json`, then `agent.json`, then `/agentCard/v1.0`. — [LiteLLM docs](https://docs.litellm.ai/docs/a2a_agent_card)
- **AAIF move:** on **17 Aug 2026** A2A joined AAIF as a hosted project, moving from the LF's broader portfolio. More than 150 organizations back it. IBM's Agent Communication Protocol (ACP) merged into A2A in Aug 2025. A2A has cloud support in Google Cloud, Microsoft Azure AI Foundry and AWS Bedrock AgentCore. v1.0 added multi-protocol bindings, version negotiation, multi-tenancy and signed agent cards. — [AAIF blog: A2A joins AAIF](https://aaif.io/blog/a2a-joins-aaif); [Axios (17 Aug 2026)](https://axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards)
- The founding supporters named by Google were AWS, Cisco, Microsoft, Salesforce, SAP and ServiceNow. The "A2Family" of extensions includes AP2 (payments), A2UI (agent-to-UI) and UCP (Universal Commerce Protocol). Google positions A2A as complementary to MCP: MCP for internal tool integration, A2A for external coordination. — [Google Open Source Blog](https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html)
- AWS AgentCore Runtime documents hosting A2A agents with `/.well-known/agent-card.json`. — [AWS AgentCore A2A docs (KR locale)](https://docs.aws.amazon.com/ko_kr/bedrock-agentcore/latest/devguide/runtime-a2a.md)
- Microsoft Agent Framework 1.0 reached GA on **3 Apr 2026**. "A2A 1.0 support coming soon" was noted at GA. By late Aug 2026 a Python "channel" system exposed one agent via MCP, A2A, OpenAI Responses and Telegram. These details come from secondary sources. — [AgenticWire](https://www.agenticwire.news/article/microsoft-agent-framework-1-0-workflows-mcp); [ADTmag (27 Aug 2026)](https://adtmag.com/articles/2026/08/27/microsoft-agent-framework-adds-support.aspx)

### Inferences
- A2A's `INPUT_REQUIRED`/`AUTH_REQUIRED` states and MCP's `input_required` result are now structurally similar. An agent OS can expose one internal "awaiting human/credential" state that maps to both protocols.
- Signed Agent Cards plus the extended (authenticated) card give a standard hook for a catalogue or registry that verifies agent provenance.

### Gaps
- The exact v1.0 release day (12 Mar vs. others) and v1.0.1 contents were not verified from a2a-protocol.org release notes.
- No primary source was found for SAP-specific A2A product integrations beyond "founding supporter."
- Whether open-source LangGraph or Deep Agents (not just the commercial Agent Server) natively speaks A2A was not confirmed.

---

## 3. Other agent-ecosystem standards and bodies (AAIF projects, AGENTS.md, Agent Skills, Agent Protocol, Agent Spec, registries/ANS)

### Takeaway
AAIF is now the main neutral home for agent standards. It launched with 3 projects (Dec 2025) and hosts **10 projects as of 22 Oct 2026**: MCP, A2A, AGENTS.md, goose, Agent Router, agentgateway, **Agent Skills**, **Open Responses**, OpenEnv and OpenSandbox. Outside AAIF, LangChain's **Agent Protocol** (serving API: runs, threads, store) and Oracle's **Open Agent Specification** (declarative portable agent definitions) are relevant to portability. Agent naming and registry standards (**ANS**) remain individual IETF drafts with no consensus.

### Cited Findings
- AAIF founding (**9 Dec 2025**): Platinum members are AWS, Anthropic, Block, Bloomberg, Cloudflare, Google, Microsoft and OpenAI. Gold members include Cisco, IBM, JetBrains, Oracle and SAP. Sources differ on the full gold/silver lists. — [Linux Foundation press release](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)
- Axios reported AAIF membership at more than 250 organizations in Aug 2026. — [Axios](https://axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards)
- **22 Oct 2026:** AAIF added four projects. **Agent Skills** (from Anthropic) is an open format packaging instructions, scripts and resources that agents load on demand. **Open Responses** (from OpenAI) is an open multi-provider LLM interface spec based on the OpenAI Responses API. **OpenEnv** (from Hugging Face) is an RL environment framework exposing MCP and Gym interfaces. **OpenSandbox** (from Alibaba) is a sandbox platform with lifecycle and execution APIs on Docker and Kubernetes runtimes. The existing projects listed were A2A, Agent Router, agentgateway, AGENTS.md, goose and MCP, for 10 projects in total. — [LF/AAIF press release (22 Oct 2026)](https://www.linuxfoundation.org/press/agentic-ai-foundation-announces-four-new-projects-agent-skills-open-responses-openenv-and-opensandbox)
- AGENTS.md is a guidance file for coding agents. Block reported 20,000+ open-source projects using it at launch. Another source cites 60,000. — [Block](https://block.xyz/inside/block-anthropic-and-openai-launch-the-agentic-ai-foundation); [IntuitionLabs](https://intuitionlabs.ai/articles/agentic-ai-foundation-open-standards)
- Agent Skills format: a folder with `SKILL.md` (YAML front matter with at least `name` and `description`, then instructions) plus optional `scripts/`, `references/` and `assets/`. It shipped for Claude on 16 Oct 2025 and was published as an open standard at agentskills.io on 18 Dec 2025. It was reportedly adopted by OpenAI Codex, Microsoft VS Code, Gemini CLI, Cursor, JetBrains, goose and others by early 2026. These details are secondary. — [MindStudio](https://www.mindstudio.ai/blog/agent-skills-open-standard-claude-openai-google)
- **Agent Protocol (LangChain):** framework-agnostic APIs for serving agents. It covers **Runs** (stateless `/runs/wait`, `/runs/stream`, plus background runs), **Threads** (persistent multi-turn state, history, one active run per thread), **Store** (long-term memory by namespace and key), agent introspection, and SSE/WebSocket streaming. LangGraph Platform "implements a superset of this protocol." No version or date is stated. — [GitHub langchain-ai/agent-protocol](https://github.com/langchain-ai/agent-protocol)
- **Open Agent Specification (Agent Spec, Oracle):** a framework-agnostic declarative language (JSON/YAML) for Agents (ReAct-style) and Flows (workflows). It has a Python SDK (pyagentspec), a TypeScript SDK, the WayFlow reference runtime, and adapters for LangGraph, CrewAI and AutoGen. Licensed Apache-2.0 or UPL-1.0. — [arXiv 2510.04173](https://arxiv.org/abs/2510.04173)
- **Agent Name Service (ANS):** draft-narajala-ans-00 (May 2025, older) proposed a DNS-based, PKI-verified agent directory. It was replaced by draft-narajala-courtney-ansv2 (three-part names, dual certificates, transparency log, discovery separated from the Registration Authority). This is an individual, experimental submission. — [IETF Datatracker: ANS](https://datatracker.ietf.org/doc/draft-narajala-ans/); [ANSv2 text](https://ietf.potaroo.net/all-ids/draft-narajala-courtney-ansv2-00.txt)
- A different "ANS," draft-hood-agtp-discovery-00 (Mar 2026, Nomotic Inc.), defines discovery for the AGTP protocol with trust-score thresholds. It is unrelated to the narajala ANS. — [IETF Datatracker](https://datatracker.ietf.org/doc/draft-hood-agtp-discovery/)
- A2A's Signed Agent Cards and the MCP Registry with sub-registries are the two protocol-native catalogue mechanisms (see §1 and §2). — [A2A spec](https://a2a-protocol.org/latest/specification/); [MCP registry preview](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)

### Inferences
- For a LangChain Deep Agents-based OS, the most portable "packaging" surfaces are AGENTS.md and Agent Skills (now both AAIF-governed), MCP for tools, A2A for remote agents, and Agent Protocol for serving.
- Open Responses entering AAIF suggests a neutral model-API schema that could reduce provider lock-in at the LLM call layer. Its adoption by Microsoft, AWS and Google was not verified.
- No standard agent-registry format has consensus. Registry designs today compose MCP Registry `server.json` entries, A2A Agent Cards and an internal metadata layer.

### Gaps
- No primary source found for "Agent Router" or "agentgateway" project scope or contributor (agentgateway is associated with Solo.io per [Solo.io blog](https://www.solo.io/blog/aaif-announcement-agentgateway), but this was not fetched).
- No evidence found of an "Open Agent Schema" standard under that exact name. The nearest equivalents are Oracle Agent Spec and the A2A Agent Card.
- ITU-T was reported to have agent-related work items (an agent platform framework and an agentic identity data model), but these were not verified from ITU primary pages.

---

## 4. Agent identity and delegated authorization (IETF, OpenID Foundation, SPIFFE, NIST; Entra Agent ID, AgentCore Identity, Google agent identity)

### Takeaway
The IETF consolidated its agent-auth work into **draft-ietf-wimse-aims-00** ("AI Identity Management System," WIMSE WG, **15 Sep 2026**, Informational). It builds no new protocols; it composes existing ones:
- **WIMSE/SPIFFE** workload identity for the agent
- short-lived key-bound credentials
- OAuth authorization code for user delegation
- **RFC 8693 token exchange** for down-scoping
- **transaction tokens** inside the call graph
- **identity chaining/ID-JAG** across domains
- **CIBA** for out-of-band human approval
- **Shared Signals (CAEP/RISC)** for revocation

The OpenID Foundation's whitepaper (Oct 2025) frames the same problems. NIST (Feb 2026) launched an AI Agent Standards Initiative and an NCCoE agent identity project. All three hyperscalers now issue first-class agent identities:
- **Google:** SPIFFE IDs with certificate-bound tokens
- **Microsoft:** Entra Agent ID, specialized service principals with blueprints and sponsors
- **AWS:** AgentCore Identity, a workload identity plus token vault with inbound JWT and outbound OAuth

### Cited Findings
**IETF**
- **draft-ietf-wimse-aims-00**, published 15 Sep 2026 and expiring 19 Mar 2027. It is an Informational, active WIMSE WG draft that replaces draft-klrc-aiagent-auth. Authors are from Defakto Security, AWS, Zscaler, Ping Identity, OpenAI and Okta. — [IETF Datatracker: draft-ietf-wimse-aims](https://datatracker.ietf.org/doc/html/draft-ietf-wimse-aims)
- AIMS content:
  - **Identity:** each agent has exactly one WIMSE identifier (may be a SPIFFE ID) that is stable for the workload's lifetime.
  - **Credentials:** WIMSE WIT/WIC and SPIFFE X.509-SVID/JWT-SVID, short-lived and key-bound. Static API keys are an "antipattern." **The LLM must never have access to agent or tool credentials.**
  - **Delegation:** OAuth authorization code for user delegation; client credentials or JWT grant for the agent's own authority; **RFC 8693 token exchange** for exchange and down-scoping. Tokens carry the agent as `client_id` and the user as `sub`.
  - **Within the call graph:** transaction tokens between internal services. Forwarding agent tokens is an anti-pattern.
  - **Cross-domain:** OAuth identity chaining and ID-JAG.
  - **Human approval:** **CIBA** for out-of-band approval ("local UI confirmation alone is explicitly not sufficient").
  - **Monitoring:** Shared Signals (CAEP/RISC); tamper-evident audit logs recording agent ID, delegated subject, resource, decision, timestamp and risk state; versioned policy-as-code.
  
  — [IETF Datatracker: draft-ietf-wimse-aims](https://datatracker.ietf.org/doc/html/draft-ietf-wimse-aims)
- AIMS lists gaps:
  - CIBA covers only client-initiated flows, so mid-execution confirmation is unsolved.
  - Mapping a broad user "mission" into concrete authorizations is out of scope.
  - Application-layer authentication lacks channel binding.
  - Attestation formats are not standardized.
  - Policy formats are left to implementers.
  
  — [IETF Datatracker: draft-ietf-wimse-aims](https://datatracker.ietf.org/doc/html/draft-ietf-wimse-aims)
- The predecessor draft-klrc-aiagent-auth reached -03 (6 Jul 2026) and is now marked Replaced. — [IETF Datatracker: draft-klrc-aiagent-auth](https://datatracker.ietf.org/doc/draft-klrc-aiagent-auth/)
- Other individual OAuth-for-agents drafts (none WG-adopted per search):
  - **draft-oauth-ai-agents-on-behalf-of-user-02**: `requested_actor` and `actor_token` parameters; expired. — [Datatracker](https://datatracker.ietf.org/doc/draft-oauth-ai-agents-on-behalf-of-user/)
  - **draft-mishra-oauth-agent-grants-02** (Aug 2026): a delegated agent authorization profile with sender-constrained, resource-bound tokens. — [IETF archive](https://www.ietf.org/archive/id/draft-mishra-oauth-agent-grants-02.html)
  - **draft-mcguinness-oauth-ai-agent-instance-00** (Jul 2026): client-instance assertions for many concurrent agent instances. — [Datatracker](https://datatracker.ietf.org/doc/html/draft-mcguinness-oauth-ai-agent-instance-00)
  - **draft-rosenberg-oauth-aauth-00** (2025, older): an Agent Authorization Grant. — [IETF archive](https://www.ietf.org/archive/id/draft-rosenberg-oauth-aauth-00.html)

**OpenID Foundation**
- The *Identity Management for Agentic AI* whitepaper was published **7 Oct 2025 (older)** by the OIDF AI Identity Management Community Group, with Tobin South as lead author. It names these problems: agent identity fragmentation, user impersonation, consent fatigue, recursive delegation, and browser agents bypassing API controls. It recommends interoperable identity profiles, explicit on-behalf-of delegation and programmatic verification. — [OpenID Foundation](https://openid.net/new-whitepaper-tackles-ai-agent-identity-challenges/); [arXiv 2510.25819](https://arxiv.org/abs/2510.25819)

**NIST**
- The **AI Agent Standards Initiative** was launched **17 Feb 2026** by CAISI with ITL and NSF. It has three pillars: industry-led standards, community open-source protocols, and agent security and identity research. Deliverables were a CAISI RFI on agent security (due 9 Mar 2026), the NCCoE *Software and AI Agent Identity and Authorization* concept paper (comments due 2 Apr 2026), and sector listening sessions from April 2026. — [NIST news](https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure); [NCCoE project](https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization)
- The NCCoE concept paper proposes adapting OAuth 2.0/2.1, OIDC and SPIFFE/SPIRE for agent workloads. No final NIST agent standard had been published per the sources found. These details are secondary. — [NIST AI Agent Standards Initiative guide (Akto)](https://www.akto.io/blog/nist-caisi-ai-agent-standards-initiative); [CSA research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-nist-ai-agent-standards-20260416-csa-style/)

**Vendor implementations**
- **Microsoft Entra Agent ID:**
  - Agent identities are "specialized identity constructs" in Entra ID for AI agents, designed for scale and ephemerality, unlike long-lived service principals. They support autonomous access (Graph permissions, Azure RBAC, directory and app roles), **delegated (on-behalf-of) access**, and authentication of inbound calls from users and other agents.
  - Agent identities can be paired one-to-one with special "agent user" accounts.
  - Copilot Studio agents get an agent identity automatically, with the creator recorded as **sponsor**.
  - "Agent ID is available for all Microsoft Entra customers." Extending Entra security features (e.g., Conditional Access) to agents requires a **Microsoft Agent 365** licence (included in M365 E7, add-on to E5).
  - Page updated 15 Jun 2026.
  
  — [Microsoft Learn: What are agent identities](https://learn.microsoft.com/en-us/entra/agent-id/identity-platform/what-is-agent-id)
- **Google (Vertex AI Agent Engine / GKE):**
  - Each agent gets a **SPIFFE ID** (`spiffe://TRUST_DOMAIN/resources/...`) and a matching IAM `principal://` identity, with an auto-provisioned x509 certificate.
  - A Google-managed Context-Aware Access policy requires mTLS so **certificate-bound tokens** only work from the intended runtime.
  - Agent identity integrates with IAM, Principal Access Boundary and VPC-SC.
  - The identity derives from the resource ID, so a redeployment gets a new principal.
  
  — [Google Cloud: Agent Engine agent identity](https://docs.cloud.google.com/agent-builder/agent-engine/agent-identity); [Google IAM agent identity overview](https://docs.cloud.google.com/iam/docs/agent-identity-overview); [GKE agent identity](https://docs.cloud.google.com/kubernetes-engine/security/about-agent-identity)
- **AWS AgentCore Identity:**
  - Inbound auth is either IAM SigV4 or JWT bearer (OIDC discovery URL, allowed audiences and clients), but not both per runtime.
  - Outbound auth uses a **token vault** for OAuth 2.0 tokens, client credentials and API keys. It supports 2-legged and 3-legged OAuth, KMS encryption, and binding to agent-user pairs. A user ID header lets an agent fetch per-user OAuth tokens.
  - The AWS doc page retrieved was still labelled preview.
  
  — [AWS AgentCore inbound/outbound auth docs](https://docs.aws.amazon.com/ko_kr/bedrock-agentcore/latest/devguide/runtime-oauth.html); [AgentCore Identity announcement (repost)](https://aihub.hkuspace.hku.hk/2025/08/15/introducing-amazon-bedrock-agentcore-identity-securing-agentic-ai-at-scale/)
- AgentCore reportedly went GA on 13 Oct 2025. This is secondary. — [usecarly](https://www.usecarly.com/blog/agent-identity/)
- A third-party critique argues Cognito, the default AS in AgentCore examples, lacks CIBA, DCR and out-of-band approval. This is vendor opinion. — [Descope](https://www.descope.com/blog/post/amazon-agentcore-identity)
- **Windows:** at Ignite (18 Nov 2025, older) Microsoft introduced an on-device Agent ID "distinct from the user ID that makes it possible to audit every action taken by the agent." — [Microsoft Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- Commentators separate **workload identity** (which workload is calling) from **agent identity** (which logical agent, acting for whom). SPIFFE alone does not govern what an agent may do after authentication. — [Solo.io](https://www.solo.io/blog/what-is-agent-identity-human-workload-a-new-layer); [Promptise](https://docs.promptise.com/blog/spiffe-vs-entra-vs-aws-iam-for-ai-agents/)

### Inferences
- A cloud-neutral agent OS identity layer aligned with AIMS would be:
  - a SPIFFE/WIMSE workload identity per agent runtime
  - OAuth/OIDC with `client_id` = agent and `sub` = user
  - RFC 8693 exchange for down-scoped downstream tokens
  - transaction tokens internally
  - CIBA or URL-mode elicitation for approvals
  - CAEP/RISC for kill-switch revocation
- Google's model is closest to SPIFFE. Entra Agent ID is OAuth/Entra-native. AgentCore centres on a credential vault. Federation between them would run over OIDC/OAuth (and SPIFFE JWT-SVID where supported).

### Gaps
- Exact GA dates for Entra Agent ID and Google agent identity were not confirmed from primary release notes. The Google docs page recommended test-environment use at some point; its current status is unclear.
- Whether any draft (e.g., AAuth, OBO-for-agents) has been WG-adopted in the OAuth WG was not confirmed. Evidence suggests none had.
- Status of the OIDF AI Identity Management CG deliverables after Oct 2025 was not retrieved.

---

## 5. Policy as code for agents (Cedar, OPA/Rego) gating tool calls

### Takeaway
**Cedar** has become the de facto policy language for gating agent tool calls in managed platforms. **AWS AgentCore Policy** evaluates Cedar on every MCP `tools/list` and `tools/call` at the AgentCore Gateway, default-deny (GA reportedly 3 Mar 2026). Cedar joined the **CNCF Sandbox** (reported Jan 2026). Docker's and Stacklok's MCP gateways also use Cedar. **OPA/Rego** remains the more expressive, widely integrated alternative. IETF AIMS recommends "versioned, reviewable policy-as-code" but leaves the format open.

### Cited Findings
- AgentCore Policy is a Cedar policy engine attached to an AgentCore Gateway. It evaluates each `tools/list` and `tools/call` before the tool is reached. It is **default-deny** once associated, and policies can be written in Cedar or generated from natural language. LOG_ONLY mode is recommended before ENFORCE. It only covers traffic routed through the Gateway. GA was 3 Mar 2026 across 13 regions per a secondary source. — [AWS docs: Getting started with Policy in AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-getting-started.html); [hidekazu-konishi guide](https://hidekazu-konishi.com/entry/amazon_bedrock_agentcore_policy_implementation_guide.html)
- AWS published its rationale for choosing Cedar for agent workflows. — [AWS Security Blog](https://aws.amazon.com/blogs/security/why-policy-in-amazon-bedrock-agentcore-chose-cedar-for-securing-agentic-workflows/); [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/secure-ai-agents-with-policy-in-amazon-bedrock-agentcore/)
- Cedar joined the **CNCF as a Sandbox project**. It was originally built by AWS and supports RBAC, ABAC and ReBAC. Its language spec is formally verified in **Lean**, and its validator checks policies against a schema before deployment. — [InfoQ (Jan 2026)](https://infoq.com/news/2026/01/cedar-joins-cncf-sandbox/)
- Stacklok ToolHive models MCP authorization in Cedar as principal/action/resource, e.g., `Action::"call_tool"` on `Tool::"weather"`. — [Stacklok ToolHive docs](https://docs.stacklok.com/toolhive/concepts/cedar-policies)
- Docker's MCP gateway evaluates Cedar policies, default-deny. — [Docker docs: MCP policy reference](https://docs.docker.com/ai/sandboxes/governance/reference/mcp-policy/)
- OPA/Rego (a Datalog-derived language) is described as a CNCF graduated project, more expressive with richer integrations. Cedar is described as more analyzable. — [Permit.io](https://docs.permit.io/integrations/policy-engines/overview); [Natoma comparison](https://natoma.ai/blog/mcp-access-control-opa-vs-cedar-the-definitive-guide)
- IETF AIMS puts policy format out of scope but says implementers should use versioned, reviewable policy-as-code. — [draft-ietf-wimse-aims](https://datatracker.ietf.org/doc/html/draft-ietf-wimse-aims)
- MCP 2026-07-28 added `Mcp-Method`/`Mcp-Name` headers so gateways can route and authorize per tool without parsing bodies. — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

### Inferences
- A gateway-enforced, default-deny Cedar (or OPA) check on `tools/call` keyed on agent identity, user, tool and arguments is the common pattern across AWS, Docker and Stacklok. It is portable because Cedar and OPA are both open-source CNCF projects.
- The enforcement point matters more than the language. The control only binds if all tool traffic is forced through the gateway, as AWS notes.

### Gaps
- No Microsoft- or Google-native Cedar or OPA tool-call gating product was found in this session. Microsoft and Google use their own policy systems (e.g., Entra Conditional Access, Google IAM/PAB).
- OPA's CNCF graduation date was not verified from CNCF directly.

---

## 6. Observability: OpenTelemetry GenAI semantic conventions for agents and tools

### Takeaway
OTel GenAI conventions define agent spans and MCP spans:
- agent spans: `create_agent`, `invoke_agent` (CLIENT or INTERNAL), `invoke_workflow`, `plan`, `execute_tool`
- MCP spans: `{mcp.method.name} {target}`, mergeable with `execute_tool`

As of 2026 **all GenAI conventions remain "Development" (not stable)** and have moved to a dedicated `semantic-conventions-genai` repo. Microsoft Agent Framework, Google ADK (≥1.17) with Cloud Trace, and AWS AgentCore (via ADOT/CloudWatch) emit or ingest them. OpenInference is a competing convention.

### Cited Findings
- Agent span types in the `semantic-conventions-genai` repo:
  - `create_agent {gen_ai.agent.name}` (CLIENT)
  - `invoke_agent {name}` (CLIENT for remote, INTERNAL for in-process)
  - `invoke_workflow {gen_ai.workflow.name}` (INTERNAL)
  - `plan {name}` (INTERNAL)
  
  All are **Development** stability. — [OTel semantic-conventions-genai: agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- Key attributes:
  - `gen_ai.provider.name` (required on create/invoke client)
  - `gen_ai.agent.name`, `.description`, `.id` (a provider-assigned stable ID for hosted agents), `.version`
  - `gen_ai.conversation.id` (do not invent a fallback)
  - `gen_ai.data_source.id`
  - `gen_ai.tool.definitions` (opt-in, sensitive)
  - errors via `error.type` (Stable), with `_OTHER` fallback
  
  — [OTel agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- MCP conventions:
  - Span name `{mcp.method.name} {target}`, e.g., `tools/call get-weather`; `mcp.method.name` is required.
  - MCP tool spans are compatible with GenAI `execute_tool` spans. If outer instrumentation already traces the tool, MCP instrumentation SHOULD add attributes to that span rather than create a new one. `gen_ai.operation.name = execute_tool` is recommended.
  - Tool arguments and results (`gen_ai.tool.call.arguments`/`.result`) are opt-in and sensitive.
  - Status: Development.
  
  — [OTel semconv: MCP](https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp)
- "Every single gen_ai.* attribute, span, metric, and event" carries Development stability. The GenAI conventions were deprecated in the main repo and moved to `semantic-conventions-genai`. — [DEV Community (2026)](https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke)
- MCP conventions were added in semconv v1.39, and v1.41 made `execute_tool` span naming require the tool name. The GenAI SIG began in April 2024. These details are secondary. — [Greptime (9 May 2026)](https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions)
- **Microsoft Agent Framework** "emits traces, logs, and metrics according to the OpenTelemetry GenAI Semantic Conventions." — [Microsoft Learn: Agent Framework observability](https://learn.microsoft.com/agent-framework/agents/observability)
- **Google ADK** has built-in OTel from v1.17.0. Google recommends opting into the latest experimental GenAI convention and exporting via the Telemetry (OTLP) API. Cloud Trace auto-extracts GenAI events from spans that conform to the conventions. — [Google Cloud: Instrument ADK with OTel](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk); [Google Cloud: Observability for AI agents](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-overview)
- **AWS AgentCore Observability:** ADOT auto-instruments agent frameworks and captures GenAI semantic-convention spans to the CloudWatch OTLP endpoint. It can monitor on-prem and multi-cloud agents, and can be disabled to send standard OTLP elsewhere. — [AWS ML blog repost (14 Aug 2026)](https://aihub.hkuspace.hku.hk/2026/08/14/monitor-on-premises-and-multi-cloud-ai-agents-with-agentcore-observability/); [OpenObserve docs](https://openobserve-website-preview.openobserve.ai/docs/integration/ai/frameworks/amazon-bedrock-agentcore/)
- OpenInference (Arize) has broader auto-instrumentation for ADK, Strands and LangChain and richer retrieval detail. OTel GenAI is the "community default." Both ride on OTel. — [Arthur.ai comparison](https://www.arthur.ai/column/openinference-vs-opentelemetry-genai-conventions-agent-tracing)

### Inferences
- Emitting OTel GenAI spans (`invoke_agent` → `chat` → `execute_tool`, with MCP attributes) from a Deep Agents runtime makes traces ingestible by CloudWatch, Cloud Trace, Azure Monitor and third-party backends. Pin a semconv version, because names can still change.
- The spans carry `gen_ai.agent.id` and `gen_ai.conversation.id`, but there is no standard attribute yet for the *delegated user* or *policy decision*. An agent OS will need custom attributes for audit (AIMS lists agent ID, delegated subject, decision and risk state as audit fields).

### Gaps
- LangSmith/LangChain native emission of OTel GenAI conventions (vs. LangSmith's own format) was not confirmed from LangChain primary docs.
- The exact `execute_tool` attribute list and the `OTEL_SEMCONV_STABILITY_OPT_IN` value were not retrieved (page truncated).
- No announced date for GenAI conventions reaching Stable was found.

---

## 7. Security frameworks (OWASP Agentic Top 10 2026, OWASP LLM Top 10, MITRE ATLAS, CSA, Google SAIF, lethal trifecta, prompt-injection design patterns)

### Takeaway
The main reference set is:
- the **OWASP Top 10 for Agentic Applications 2026** (ASI01 to ASI10, published 9 Dec 2025)
- the **OWASP LLM Top 10 2025** (LLM01 Prompt Injection, LLM06 Excessive Agency)
- **MITRE ATLAS**, which added agentic techniques through 2026
- **CSA MAESTRO** (7-layer agentic threat model)
- **Google's agent security principles**: well-defined human controllers, limited powers, observable actions and planning
- **AWS's Agentic AI Security Scoping Matrix** (4 scopes)

For agents that read untrusted content, the consensus design guidance is architectural rather than detection-based. Avoid the **lethal trifecta** (private data + untrusted content + external communication). Use **plan-then-execute**, **dual-LLM** or **CaMeL**-style control/data-flow separation.

### Cited Findings
**OWASP Top 10 for Agentic Applications (2026)**, published 9 Dec 2025:

| ID | Risk | Example cited by OWASP |
|---|---|---|
| ASI01 | Agent Goal Hijack | EchoLeak |
| ASI02 | Tool Misuse | Amazon Q |
| ASI03 | Identity & Privilege Abuse | – |
| ASI04 | Agentic Supply Chain Vulnerabilities | poisoned MCP/A2A components; GitHub MCP exploit |
| ASI05 | Unexpected Code Execution | AutoGPT RCE |
| ASI06 | Memory & Context Poisoning | Gemini memory attack |
| ASI07 | Insecure Inter-Agent Communication | – |
| ASI08 | Cascading Failures | – |
| ASI09 | Human-Agent Trust Exploitation | – |
| ASI10 | Rogue Agents | Replit incident |

- Companion OWASP resources: the Agentic AI Threats & Mitigations taxonomy v1.1, an Agentic Threat Modelling Guide, cheat sheets on MCP and Agentic Identity, and the AI Vulnerability Scoring Standard (AI-VSS). — [OWASP GenAI Security Project](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)
- **OWASP LLM Top 10 (2025 edition)**: LLM01 Prompt Injection (direct or via retrieved documents and tool outputs) and LLM06 **Excessive Agency** (too much autonomy, permissions or functionality). Mitigations: minimize the extensions an agent can call, limit their functionality, require human approval. — [Promptfoo: OWASP LLM Top 10](https://promptfoo.dev/docs/red-team/owasp-llm-top-10/); [Invicti](https://www.invicti.com/blog/web-security/owasp-top-10-risks-llm-security-2025)

**MITRE ATLAS**
- The first 2026 update expanded agentic coverage, adding e.g. AI Service API technique AML.T0096 and the SesameOp case study AML.CS0042 (Assistants API used as C2). — [Zenity](https://zenity.io/blog/current-events/zenitys-contributions-to-mitre-atlas-first-2026-update)
- ATLAS v5.4.0 (Feb 2026) added agentic techniques. — [Vectra](https://vectra.ai/topics/mitre-atlas)
- A Sep 2026 post describes release v2026.09 with 16 tactics and many techniques tagged "Agentic AI." Counts conflict across sources. — [Speakeasy](https://www.speakeasy.com/blog/mitre-atlas-explained)

**Cloud Security Alliance**
- **MAESTRO** (Multi-Agent Environment, Security, Threat, Risk & Outcome), Feb 2025 (older), by Ken Huang. It is a seven-layer agentic threat-modelling framework extending STRIDE, PASTA and LINDDUN. — [CSA blog](https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro); [CSA MAESTRO site](https://labs.cloudsecurityalliance.org/maestro/)
- A CSA article (16 Dec 2025) proposes extending AWS's Scoping Matrix to separate *agency* from *autonomy*. — [CSA](https://cloudsecurityalliance.org/blog/2025/12/16/enhancing-the-agentic-ai-security-scoping-matrix-a-multi-dimensional-approach)
- A CSA whitepaper and research notes cover MCP tool poisoning and rug pulls (May 2026). — [CSA whitepaper](https://labs.cloudsecurityalliance.org/research-rb/csa-whitepaper-mcp-security-tool-poisoning-20260506-csa-styl/)

**Google**
- *Google's Approach for Secure AI Agents* (Díaz & Olive, 2025, older) gives three principles: agents must have **well-defined human controllers**, their **powers must be carefully limited**, and their **actions and planning must be observable**. It recommends a hybrid of deterministic controls and reasoning-based defenses. — [Google Research](https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/)
- Claims that "SAIF 2.0" extends SAIF to agents were found only in secondary sources. — [VerifyWise](https://verifywise.ai/ai-governance-library/agentic-security/agent-google-saif-2-agents-2025)

**AWS**
- The **Agentic AI Security Scoping Matrix** has four scopes: 1 No Agency, 2 Prescribed Agency, 3 Supervised Agency, 4 Full Agency. Controls are mapped across dimensions including identity context, data protection, audit/logging and orchestration. — [AWS Security Blog](https://aws.amazon.com/blogs/security/the-agentic-ai-security-scoping-matrix-a-framework-for-securing-autonomous-ai-systems); [AWS scoping matrix page](https://aws.amazon.com/ai/security/agentic-ai-scoping-matrix/)

**Lethal trifecta and design patterns**
- **Lethal trifecta** (Simon Willison, **16 Jun 2025**, older): access to private data + exposure to untrusted content + ability to communicate externally. "We still don't know how to 100% reliably prevent this." A 95% guardrail detection rate is "a failing grade." MCP "encourages users to mix and match tools from different sources," which makes the trifecta easy to assemble. — [Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- *Design Patterns for Securing LLM Agents against Prompt Injections* (2025, older; ETH Zurich, Google, IBM, Microsoft and others) gives six patterns. Examples:
  - **Plan-then-execute:** tool sequence fixed before reading untrusted data; "control-flow integrity," but injected data can still alter arguments.
  - **Dual LLM:** a quarantined LLM with no tools processes untrusted data; the privileged LLM handles only symbolic references.
  
  Core rule: once an agent has ingested untrusted input, it must be constrained so that input cannot trigger consequential actions. — [arXiv 2506.08837](https://arxiv.org/abs/2506.08837); [Simon Willison review](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/)
- **CaMeL** (*Defeating Prompt Injections by Design*, Google/DeepMind/ETH, arXiv 2503.18813, Mar 2025, older):
  - Extracts control and data flow from the trusted user query, so untrusted data "can never impact the program flow."
  - A privileged LLM writes the plan as code, and a quarantined LLM parses untrusted data.
  - A custom Python interpreter tracks **capabilities** (provenance metadata) on values and enforces data-flow policies.
  - It reported 67% of AgentDojo tasks solved with provable security; a later version reports 77%.
  
  — [Simon Willison on CaMeL](https://simonwillison.net/2025/Apr/11/camel/); [arXiv 2503.18813](https://arxiv.org/abs/2503.18813)
- A critique: the patterns stop injected text from choosing *actions* but not from shaping *values*. — [Signals/Aktagon](https://signals.aktagon.com/articles/2026/02/design-patterns-for-securing-llm-agents-against-prompt-injection-attacks/)

### Inferences
- The frameworks converge on these controls:
  - least privilege/"least agency" per tool
  - identity per agent (ASI03)
  - supply-chain integrity for MCP/A2A components (ASI04)
  - sandboxed code execution (ASI05)
  - memory provenance (ASI06)
  - authenticated inter-agent messaging, e.g., signed Agent Cards and mTLS (ASI07)
  - circuit breakers (ASI08)
  - approval UX that resists rubber-stamping (ASI09)
  - kill switches and monitoring (ASI10)
- For an agent OS, the lethal-trifecta rule can be enforced as a policy invariant: no single session/plan holds all three capabilities without human approval. CaMeL-style taint or capability tracking is the strongest published design, but it has no standard implementation in LangChain or the cloud platforms per the sources found.

### Gaps
- Google SAIF primary pages (saif.google) were not fetched. SAIF-for-agents details beyond the 2025 Google paper are secondary only.
- CSA's AI Controls Matrix (AICM) and any CSA agentic IAM publication were not found in this session.
- Exact MITRE ATLAS version and technique counts as of Oct 2026 are inconsistent across sources.
- Whether OWASP issued a "2026" LLM Top 10 update was hinted at on the OWASP site but not confirmed.

---

## 8. Governance standards and regulation (ISO/IEC 42001, NIST AI RMF and agent work, EU AI Act dates) and levels-of-autonomy taxonomies

### Takeaway
- **EU AI Act:** the **Digital Omnibus on AI, Regulation (EU) 2026/1744**, was published in the OJ on **24 Jul 2026** and in force since **27 Jul 2026**. It deferred Annex III high-risk obligations from 2 Aug 2026 to **2 Dec 2027** and Annex I to **2 Aug 2028**. **Article 50 transparency obligations still apply from 2 Aug 2026**, including telling users they are interacting with AI. GPAI obligations have applied since 2 Aug 2025; prohibitions and AI literacy since 2 Feb 2025.
- **ISO/IEC 42001:2023** remains the certifiable AI management-system standard. No dedicated SC 42 agentic work item was found.
- **NIST** has no final agent profile yet. Its work is the AI Agent Standards Initiative (Feb 2026) and COSAIS SP 800-53 overlays for single- and multi-agent systems, in development.
- **Autonomy taxonomies:** Feng/McDonald/Zhang's five user-role levels (Knight First Amendment Institute, 2025) and AWS's four-scope matrix.

### Cited Findings
**EU AI Act**
- Omnibus timeline: proposal 19 Nov 2025; provisional agreement 6 May 2026; Member State confirmation 13 May 2026. — [Gibson Dunn](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/)
- New and unchanged dates:
  - Annex III high-risk deferred from 2 Aug 2026 to **2 Dec 2027**.
  - Annex I (product-embedded) deferred from 2 Aug 2027 to **2 Aug 2028**.
  - **Article 50 transparency stays at 2 Aug 2026**. Art. 50(2) machine-readable marking has a grace period to **2 Dec 2026** for systems placed on the market before 2 Aug 2026.
  - GPAI (Arts 51–56) has applied since **2 Aug 2025**.
  - Art. 4 AI literacy (since 2 Feb 2025) is softened to "support" literacy.
  - Art. 5 prohibitions have applied since 2 Feb 2025. A new prohibition on non-consensual intimate imagery/CSAM generators has a transition to 2 Dec 2026.
  - Member State sandboxes are moved to 2 Aug 2027.
  
  — [Gibson Dunn](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/)
- The final act is **Regulation (EU) 2026/1744 of 8 July 2026**, published in the OJ **24 Jul 2026** and in force **27 Jul 2026**. It is the first amendment to Regulation (EU) 2024/1689. — [EUR-Lex 2026/1744](https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng); [Law & Technology EU](https://lawandtechnology.eu/en/digital-omnibus-on-ai-official-journal-regulation-2026-1744/); [White & Case](https://www.whitecase.com/insight-alert/eu-ai-omnibus-enters-force-amending-ai-act)
- Sources disagree on how much substance changed beyond the dates. One says only four dates moved. White & Case cites eased requirements and added prohibitions. — [Law & Technology EU](https://lawandtechnology.eu/en/digital-omnibus-on-ai-official-journal-regulation-2026-1744/); contrasted with [White & Case](https://www.whitecase.com/insight-alert/eu-ai-omnibus-enters-force-amending-ai-act)
- The AI Act does not define "AI agent." An arXiv legal analysis (Apr 2026) examines how agents map onto the Act. — [arXiv 2604.04604 "AI Agents Under EU Law"](https://arxiv.org/pdf/2604.04604)

**ISO/IEC**
- ISO/IEC 42001 (published Dec 2023, older) is the only certifiable standard in the AI family. As of summer 2026, **SC 42 had not initiated a dedicated standalone agentic AI work item**. Agent requirements are expected to be folded into existing standards, and a revision of ISO/IEC 22989 terminology may address agents. — [ANSI USNC newsletter, Summer 2026](https://share.ansi.org/Shared%20Documents/Standards%20Activities/International%20Standardization/IEC/USNC%20Current/Vol.%2021%20No.%202%20Summer%202026.pdf); [arXiv 2604.04604](https://arxiv.org/pdf/2604.04604)

**NIST**
- AI Agent Standards Initiative (17 Feb 2026): see §4. — [NIST](https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure)
- **COSAIS** (Control Overlays for Securing AI Systems; concept paper Aug 2025) adapts SP 800-53. Its planned use cases include "Using AI Agent Systems – Single Agent" and "– Multi-Agent." The agent overlays were still in development as of Mar 2026. — [CSA research note on NIST](https://labs.cloudsecurityalliance.org/research/csa-research-note-nist-ai-agent-standards-federal-framework/); [Redmond Mag (Aug 2025)](https://redmondmag.com/Articles/2025/08/26/NIST-Outlines-Cybersecurity-Framework-for-AI-System.aspx)
- No agent-specific NIST AI RMF profile was found. The relevant RMF documents remain AI RMF 1.0 (NIST AI 100-1, Jan 2023) and the Generative AI Profile (NIST AI 600-1, Jul 2024); these are older and were not re-fetched this session. — [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)

**Levels of autonomy**
- *Levels of Autonomy for AI Agents* by K. J. Kevin Feng, David W. McDonald and Amy X. Zhang (University of Washington), for the Knight First Amendment Institute. arXiv 2506.12469, v1 14 Jun 2025, v2 28 Jul 2025 (older).
  - Autonomy is treated as a **design decision separate from capability**.
  - The five levels are defined by the user's role: **L1 Operator, L2 Collaborator, L3 Consultant, L4 Approver, L5 Observer**.
  - The paper proposes "AI autonomy certificates" for governing agents.
  
  — [arXiv 2506.12469](https://arxiv.org/abs/2506.12469); [Knight Columbia](https://knightcolumbia.org/content/levels-of-autonomy-for-ai-agents-1)
- AWS Agentic AI Security Scoping Matrix: Scope 1 No Agency → Scope 4 Full Agency (see §7). — [AWS](https://aws.amazon.com/ai/security/agentic-ai-scoping-matrix/)
- Critique: agency (permissions) and autonomy (approval requirements) vary independently, so a 2-D matrix is proposed. — [CSA](https://cloudsecurityalliance.org/blog/2025/12/16/enhancing-the-agentic-ai-security-scoping-matrix-a-multi-dimensional-approach); [WitnessAI](https://witness.ai/blog/aws-agentic-ai-security-scoping-matrix/)

### Inferences
- For enterprise agents in the EU in late 2026, the binding near-term obligations are Article 50 transparency (since 2 Aug 2026), AI literacy, the prohibitions, and GPAI duties if the enterprise is a GPAI provider. High-risk (Annex III) agent use cases have until 2 Dec 2027.
- An agent OS could tag each agent with an autonomy level (Feng et al. L1–L5) and an agency scope (AWS 1–4), and use those as policy inputs for approval gates. This is a design choice; no standard mandates it.

### Gaps
- The EUR-Lex text of 2026/1744 was not read directly. Substantive changes beyond the dates are disputed among secondary sources.
- No Microsoft- or Google-published "levels of autonomy" taxonomy for agents was found in this session.
- The NIST COSAIS agent overlays' current status (Oct 2026) and any NIST AI RMF agent profile were not confirmed.

---

## 9. The "agent OS" concept: how vendors and research use the term and what components they include

### Takeaway
The term is used in three ways:
1. **Research:** AIOS (Rutgers et al.) treats an "LLM agent operating system" as a kernel that schedules LLM calls and manages context, memory, storage, tools and access for many agents.
2. **Microsoft Windows "agentic OS"** (term used Nov 2025, with backlash): OS-level primitives, namely MCP support, an **On-Device Registry (ODR)** of MCP "agent connectors," isolated **Agent Workspace** sessions, a separate **Agent ID** for audit, and Intune/Entra/Group Policy controls. These were preview at Ignite 2025.
3. **Cloud platforms:** an agent control plane comprising identity, registry, gateway, policy, observability and runtime (see §4–§6).

### Cited Findings
- **AIOS: LLM Agent Operating System** (arXiv 2403.16971, first posted Mar 2024, older, later revised). An AIOS kernel isolates LLM and OS-style services from agent apps. Modules include an **agent scheduler** (FIFO/Round-Robin dispatch of LLM requests), a **memory manager** (per-agent short-term memory with eviction to disk) and a **tool manager** (external API calls and conflict resolution). — [arXiv 2403.16971](https://arxiv.org/abs/2403.16971); [Moonlight review (secondary)](https://www.themoonlight.io/review/aios-llm-agent-operating-system)
- On **10 Nov 2025**, Windows head Pavan Davuluri posted that Windows is "evolving into an agentic OS." The post drew 400+ mostly negative replies. He later said Windows will serve both humans and agents and that Microsoft is building OS "primitives" for agent security, identity, governance, observability and performance. — [TechRadar](https://www.techradar.com/computing/windows/windows-11-users-rebel-as-top-microsoft-exec-says-operating-system-is-evolving-into-an-agentic-os); [GeekWire (2026)](https://www.geekwire.com/2026/microsoft-2-5-evp-pavan-davuluri-wants-to-remake-windows-for-both-human-and-agent-users/)
- Ignite 2025 (18 Nov 2025) Windows announcements:
  - **public preview of native MCP on Windows**
  - **public preview of the Windows On-Device Registry (ODR)**, a managed repository of agent connectors (MCP servers)
  - **private preview of Agent Workspace**, a separate policy-controlled desktop where agents run
  - **Agent ID** distinct from user ID, for auditing
  - IT management via **Intune, Entra and Group Policy**, with "advanced controls planned for 2026"
  - built-in connectors for File Explorer and System Settings
  
  — [Microsoft Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/); [Windows Developer Blog (18 Nov 2025)](https://blogs.windows.com/windowsdeveloper/2025/11/18/ignite-2025-furthering-windows-as-the-premier-platform-for-developers-governed-by-security/)
- Insider build 26220.7344 (Dec 2025) shipped native MCP, ODR and agent workspaces as experimental, opt-in features. — [Paperclipped](https://www.paperclipped.de/en/blog/windows-on-device-registry-ai-agents-mcp/)
- Microsoft's Entra docs define an agent's components as **model, orchestration layer, memory and tools**. They argue agents need distinct identities because they are dynamic and ephemeral. — [Microsoft Learn: agent identities](https://learn.microsoft.com/en-us/entra/agent-id/identity-platform/what-is-agent-id)
- IETF AIMS frames an "AI Identity Management System" as a conceptual set of functions (identifier, credentials, attestation, authentication, authorization, monitoring and audit, policy) that one or several systems can implement. It is the closest standards-body decomposition of an agent control plane's identity layer. — [draft-ietf-wimse-aims](https://datatracker.ietf.org/doc/html/draft-ietf-wimse-aims)
- AAIF's 22 Oct 2026 project set covers further agent-OS building blocks: sandboxing (OpenSandbox), skills packaging (Agent Skills), a model API (Open Responses) and a gateway (agentgateway). — [LF/AAIF press release](https://www.linuxfoundation.org/press/agentic-ai-foundation-announces-four-new-projects-agent-skills-open-responses-openenv-and-opensandbox)

### Inferences
- Across AIOS, Windows and the cloud platforms, the recurring "agent OS" components are:
  - scheduler/runtime and isolation (workspace, sandbox)
  - context and memory management
  - tool and connector registry (ODR, MCP Registry)
  - agent identity (Agent ID, SPIFFE, Entra Agent ID)
  - policy and consent (Intune/Group Policy, Cedar)
  - observability and audit (OTel)
  - inter-agent protocol (A2A)
  
  Most of these now have an open standard or AAIF project to anchor to.
- Windows ODR suggests that the MCP-server registry is treated as an OS-level primitive, not just a cloud catalogue.

### Gaps
- The full, current module list of AIOS (context, storage and access managers in later versions) was not re-verified from the arXiv full text in this session. Its institutional affiliation (Rutgers) was not confirmed from the sources fetched.
- No GA announcement for Windows Agent Workspace or ODR was found as of Oct 2026.
- No other commercial "agent operating system" products were investigated in depth in this session.
