# Amazon Bedrock AgentCore and AWS's enterprise agent offering (state as of 27 Oct 2026)

Scope note: These notes were compiled on 2026-10-27. Most facts come from the AgentCore developer guide's release notes, quotas, pricing and FAQ pages, which were current in October 2026. Each date is the date AWS published the item. "Preview" means public preview and "GA" means generally available. One quirk of the source: the AgentCore release-notes page has a broken "June 2026" heading that shows up inside the July 2026 section, as "== June 2026" after the ActiveSessionCount entry. The items that follow that marker are therefore dated June 2026 below ([Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)).

## 1. What each AgentCore service does, how it is designed, and its status

### Takeaway
AgentCore launched in preview on 16 July 2025 and reached GA on 13 October 2025. By October 2026 it was a set of separately usable services, all billed by consumption: Runtime, Memory, Gateway, Identity, Policy, Evaluations, Observability, Code Interpreter and Browser are all GA. Newer pieces have joined them. A managed "harness" (an agent loop defined by configuration) is GA. AWS Agent Registry is GA. Payments is in preview. A set of "optimization" features (recommendations, batch evaluation, A/B tests) is mostly GA, with Failure Insights still in preview. Runtime runs each session in its own microVM. A session lasts at most 8 hours, and payloads can be up to 100 MB. Runtime can host any framework and speaks HTTP, MCP, A2A, AG-UI and WebSocket bidirectional streaming. A new "Instances" compute type runs on EC2 in the customer's account and supports sessions of up to 14 days.

### Cited Findings

**Platform timeline and overall status**
- Preview launched 16 July 2025 at AWS Summit New York with seven services: Runtime, Memory, Observability, Identity, Gateway, Browser and Code Interpreter. AWS said they "can be used individually and are optimized to work together" and that AgentCore supports "any framework and model, hosted on Amazon Bedrock or elsewhere" — [AWS News Blog, 16 Jul 2025](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/)
- GA came on 13 October 2025 in nine Regions. With GA, every service supported VPC, PrivateLink, CloudFormation and tagging. Runtime added A2A. Memory added self-managed strategies. Gateway added MCP-server targets and IAM authorization. Identity added a vault for refresh tokens. Observability became OTEL-compatible and could export to Dynatrace, Datadog, Arize Phoenix, LangSmith and Langfuse. Named frameworks: CrewAI, LangGraph, LlamaIndex, Google ADK and OpenAI Agents SDK, used with any model inside or outside Bedrock — [What's New, 13 Oct 2025](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available/)
- At re:Invent on 2 December 2025, AWS put Policy and Evaluations into preview and added the episodic memory strategy and Runtime bidirectional streaming. Customers named: PGA TOUR, Workday (Code Interpreter) and Grupo Elfa (Observability) — [AWS News Blog, 2 Dec 2025](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/); [What's New Dec 2025](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-bedrock-agentcore-policy-evaluations-preview)
- Policy went GA on 3 March 2026 in 13 Regions, and Evaluations went GA on 31 March 2026 — [AWS News Blog (updated)](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/); [What's New, 31 Mar 2026](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available)
- By October 2026 the FAQ lists 15 Regions across the Asia Pacific, Canada, Europe, South America and the US. AgentCore is HIPAA eligible, and FedRAMP "is being pursued". The Bedrock SLA applies. AWS lists AgentCore features still in preview as Payments and optimization insights; Agent Registry and the managed harness also carry preview labels on the FAQ page, but the release notes record both as GA (Registry in August 2026, harness in June 2026) — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- Other platform milestones:
  - February 2026: ISO and CSA STAR certification.
  - May 2026: GA in AWS GovCloud (US-West).
  - June 2026: in scope for SOC 1, 2 and 3.
  - May 2026: the CDK L2 constructs became stable (the Policy submodule is still alpha).
  - AgentCore CLI: preview in February 2026, GA (v0.4.0) in March 2026, and v1.0 in October 2026.
  - Source for all of the above: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

**Runtime (GA since Oct 2025)**
- **Isolation.** Each session "runs in a dedicated microVM with completely isolated CPU, memory, and filesystem resources." When a session ends, "the entire microVM is terminated and memory is sanitized." Session state is ephemeral, so AWS tells you to use AgentCore Memory for durability — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- **Session lifecycle.**
  - States are Active, Idle and Terminated.
  - The default idle timeout is 15 minutes, set by `idleRuntimeSessionTimeout`.
  - The maximum lifetime is 8 hours, set by `maxLifetime`. Both values are configurable through LifecycleConfiguration.
  - Source: [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html); [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Hard limits.**

  | Limit | Value |
  |---|---|
  | Synchronous request timeout | 15 min |
  | Maximum payload (request/response) | 100 MB |
  | Streaming chunk | 10 MB |
  | Streaming / WebSocket connection maximum | 60 min |
  | Async job maximum | 8 h |
  | WebSocket frame | 64 KB |
  | Hardware per session | 2 vCPU / 8 GB |
  | Docker image | 2 GB |
  | Direct-code zip | 250 MB compressed / 750 MB uncompressed |
  | Session storage | 1 GB |

  Default quotas:
  - 5,000 active sessions in us-east-1 and us-west-2, and 2,500 elsewhere.
  - Data-plane API rate: 1,000 TPS per account (shared).
  - New-session creation: 25 TPS per account (shared).
  - 1,000 agents.

  Source: [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Protocols.**
  - HTTP (REST request/response).
  - MCP (Runtime can host MCP servers).
  - A2A, "for multi-agent communication and discovery".
  - WebSocket bidirectional streaming.
  - Source: [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)

  Protocol additions by date:
  - December 2025: bidirectional streaming over WebSocket.
  - March 2026: AG-UI protocol support, OAuth for browser WebSocket clients, and stateful MCP (elicitation, sampling, progress notifications).
  - May 2026: custom header passthrough.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Hosting any framework.** You can define agents with "popular frameworks like LangGraph, CrewAI, or Strands Agents" through the AgentCore Python SDK, or add "the required HTTP endpoints using the AgentCore SDK or custom implementation". Agents deploy as container images in ECR — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
  - Direct code deployment from a zip archive arrived in November 2025 for Python and in April 2026 for Node.js — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - The FAQ lists CrewAI, LangGraph, LlamaIndex, Google ADK, OpenAI Agents SDK, Claude Agents SDK and Strands — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- **Versions and endpoints.**
  - Every configuration change creates a new immutable version.
  - Endpoints (aliases) point at versions. The `DEFAULT` endpoint follows the latest version.
  - You can create custom dev/test/prod endpoints, and rolling back means re-pointing an endpoint.
  - Inbound auth is either IAM SigV4 or OAuth 2.0 / JWT, with a discovery URL plus allowed audiences and clients.
  - Source: [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- **Platform V2.** V2 starts the agent from a snapshot, so cold starts stay consistent regardless of image size. It bills on active use and reclaims memory. It is available in five Regions. Trade-offs: create/update takes minutes, the container must report healthy on `/ping` within 120 seconds, and environment variables are capped at 1.5–2.5 KB — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- **Instances compute type (August 2026).**
  - Runs on AWS-managed EC2 in the customer's own account, defined by a "capacity provider".
  - Sessions can last up to 14 days.
  - GPU instance types are supported.
  - Several agents can share an instance (at most 20 agents per capacity-provider session).
  - Savings Plans and ODCRs apply, and data stays in your account.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html); [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Execution and storage features.**
  - March 2026: the InvokeAgentRuntimeCommand API for running shell commands in a session, and managed session storage in public preview (1 GB, retained 14 days).
  - May 2026: bring-your-own file systems (Amazon S3 Files and EFS) mounted into every session.
  - June 2026: interactive shells, up to 10 per session.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

**Memory (GA since Oct 2025)**
- **Two layers.** Short-term memory is raw events per actor and session, written with CreateEvent. Long-term records are extracted from those events asynchronously by "strategies". "If no strategies are specified, long-term memory records will not be extracted." — [Memory strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html)
- **Built-in strategies.** There are four: semantic, user preference, summary and episodic. Each runs some of three steps: Extraction, Consolidation (create a new record or update an existing one) and Reflection (insights across episodes) — [Built-in strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-strategies.html)
  - Episodic (December 2025) captures "context, reasoning, actions, outcomes", and a reflection agent pulls out patterns — [AWS News Blog, 2 Dec 2025](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/)
- **Customization levels.**
  - Built-in: fully managed, but highest storage cost.
  - "Built-in overrides": custom prompts, with Bedrock models invoked in your own account.
  - "Self-managed": you own the whole extraction and consolidation pipeline.
  - One memory resource can mix these types.
  - Source: [Memory strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html)
- **2026 additions.**
  - March: resource-based policies and record streaming (push notifications when records change).
  - April: structured metadata filtering.
  - August: direct ingestion into long-term memory (IngestData), JSON (non-conversational) payloads up to 100 KB, and flexible namespaces.
  - October: TTL on long-term records.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Limits.**
  - At most 6 strategies per memory and 150 memories per Region.
  - Event expiry between 7 and 365 days.
  - Extraction is capped at 150k tokens per minute per account (adjustable).
  - Source: [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)

**Gateway (GA since Oct 2025)**
- **What it is now.** AWS calls Gateway a "fully managed AI gateway" and "single, secure entry point for agentic traffic". It does three things:
  - It "converts APIs, Lambda functions, and existing services into Model Context Protocol (MCP)-compatible tools". Input types are OpenAPI, Smithy and Lambda.
  - It fronts other agents and HTTP services through passthrough targets, "including Agent-to-Agent (A2A) traffic".
  - It routes inference across model providers.
  - It also offers 1-click integrations for Salesforce, Slack, Jira, Asana and Zendesk, plus "Semantic Tool Selection" so agents "use thousands of tools while minimizing prompt size".
  - Source: [Gateway overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- **Targets by date.**
  - October 2025: MCP servers as targets.
  - December 2025: Amazon API Gateway stages.
  - April 2026: three-legged OAuth (3LO) for MCP targets GA.
  - June 2026: Runtime targets GA, HTTP passthrough targets, and inference targets.
  - June 2026: the Web Search tool GA ("Amazon-operated web index", "zero data egress").
  - October 2026: an AWS Step Functions connector, model fallback chains with a circuit breaker, Bedrock InvokeModel wire-format translation, and private-CA TLS.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **MCP features (May 2026).** Stateful MCP sessions (default 1 hour, up to 8 hours), SSE response streaming, elicitation pass-through, sampling, and progress and logging notifications — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Interceptors.** A gateway can have at most one REQUEST and one RESPONSE interceptor, both implemented as Lambda functions. They are used for "fine-grained access control over tools or MCP operations", transforming requests and responses, and "custom authorization logic". Headers are passed to interceptors only if `passRequestHeaders=true`. AWS asks for idempotent Lambdas because the gateway may retry — [Gateway interceptors](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-interceptors.html)
  - A mirror of an AWS ML Blog post says the request interceptor runs before the Cedar policy evaluation, so it can enrich the context the policy sees — [AWS ML Blog mirror](https://aihub.hkuspace.hku.hk/2026/06/02/secure-ai-agents-with-policy-and-lambda-interceptors-in-amazon-bedrock-agentcore-gateway/)
- **Rate limits (August 2026).** Customers can configure limits scoped by JWT claim, IAM principal, target, tool or model. They can cap requests per second or minute, tokens per minute and connections. Setting `rate=0` acts as an emergency block. Changes propagate within 30 seconds. The system "fails open on transient errors" — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Quotas.**
  - 100 targets per gateway and 1,000 tools per target.
  - 15-minute invocation timeout.
  - 6 MB tool payload.
  - 200 TPS for tool-call/list.
  - Search-based tool calls: 25 per minute by default.
  - All of these are adjustable.
  - Source: [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)

**Identity (GA since Oct 2025)**
- **Agent identity directory.** It acts as "a unified directory service that acts as the single source of truth for all agent identities", "similarly to Cognito User Pools". Each agent is a workload identity with an ARN of the form `.../workload-identity/directory/default/workload-identity/agent-name`. This works for agents on Runtime, self-hosted or hybrid — [Identity features](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/key-features-and-benefits.html)
  - Quota: 11,000 workload identities — [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Token vault.** It stores OAuth tokens, client credentials and API keys, "encrypted using either customer-managed or service-managed AWS KMS keys". Credentials are released only "when they present verifiable proof of workload identity", and "every access request is validated independently, even from callers within the same trust domain … to protect end-user data from malicious or misbehaving agent code" — [Identity features](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/key-features-and-benefits.html)
- **Flows.**
  - 2LO (client credentials, machine-to-machine) and 3LO (authorization code with user consent).
  - Built-in providers for Google, GitHub, Slack, Salesforce and Atlassian.
  - SDK decorators `@requires_access_token` and `@requires_api_key`.
  - Source: [Identity features](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/key-features-and-benefits.html)
  - Runtime outbound modes are "User-delegated" (on behalf of the end user) and "Autonomous" (service-level credentials) — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- **2026 additions.**
  - April: On-Behalf-Of token exchange.
  - April: VPC egress to private IdPs.
  - June: reference existing Secrets Manager secrets (customer CMKs and rotation).
  - July: Private Key JWT client authentication, with keys held in KMS and every signing logged in CloudTrail.
  - September: a hosted Consent Portal where end users approve delegated access.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

**Policy (preview 2 Dec 2025, GA 3 Mar 2026)** (details in section 4)
- Policy engines are associated with gateways. Policy "intercepts all agent traffic through Amazon Bedrock AgentCore Gateways and evaluates each request … before allowing tool access". Policies are written in Cedar, and now also in Dogwood. Natural-language authoring is validated with automated reasoning — [Policy docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)

**Evaluations (preview 2 Dec 2025, GA 31 Mar 2026)**
- **Built-in evaluators (13):** Correctness, Faithfulness, Helpfulness, Response Relevance, Conciseness, Coherence, Instruction Following, Refusal, Goal Success Rate, Tool Selection Accuracy, Tool Parameter Accuracy, Harmfulness and Stereotyping. There are two modes: online, which samples and scores live traces, and on-demand — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/); [What's New, 31 Mar 2026](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available)
- **Custom evaluators and data sources.** Custom evaluators can be an LLM judge or code running in Lambda. Ground-truth support compares against reference answers, behavioral assertions and expected tool sequences — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - Evaluations can read from an AgentCore endpoint or from the CloudWatch log group of an external agent — [AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/)
- **2026 additions.**
  - April: "agent optimization loop" in preview (recommendations, batch evaluations, A/B tests).
  - June: Recommendations, Batch Evaluation and A/B testing went GA. AWS says they work "regardless of where agents run: on AgentCore runtime, AWS Lambda, Amazon EKS, or non-AWS environments". Failure Insights entered preview.
  - July: OpenAI Agents, LlamaIndex, Google ADK and Claude Agent SDK support, plus generic OTel GenAI / OpenInference conventions.
  - August: DeepEval and AutoEval third-party evaluators, plus skill evaluators (SkillSelectionAccuracy and SkillInstructionFollowing).
  - September: TypeScript frameworks (Strands, LangGraph, OpenAI Agents, Vercel AI SDK).
  - October: `Builtin.FailureAnalysis`.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

**Observability (GA since Oct 2025)**
- Telemetry is "standardized OpenTelemetry (OTEL)-compatible". All metrics, spans and logs are stored in CloudWatch. The CloudWatch dashboard (trace visualizations, error breakdowns) covers "agent runtime data only". By default you get metrics for agents, gateways and memory, and you can instrument your own spans — [Observability docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- 2026 additions:
  - March: one-click enablement for Memory and Gateway.
  - April: cross-account monitoring (up to 5 monitoring accounts per source).
  - April: complete traces available in under 10 seconds.
  - July: a "unified span destination", so each agent's spans go to its own log group for per-agent access control and encryption (the default for agents created from 20 July 2026).
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

**Code Interpreter and Browser (GA since Oct 2025)**
- **Code Interpreter.** Sandboxed Python, JavaScript and TypeScript (Node.js support added March 2026), with support for large files via S3. Limits: 2 vCPU / 8 GB, 15-minute synchronous timeout, 100 MB payload, 8-hour async commands, 10 GB disk — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/); [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html); [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Browser.** VM-level isolation, live view, session replay, CloudTrail logging and CAPTCHA handling. Each session gets 1 vCPU / 4 GB and a 10 GB disk — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/); [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
  - Additions:
    - October 2025: Web Bot Auth in preview (cryptographically signed requests).
    - February 2026: proxies, persistent profiles and Chrome extensions.
    - March 2026: Chrome Enterprise policies and custom root CAs.
    - April 2026: OS-level interaction beyond CDP.
    - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

**Newer AgentCore services (2026)**
- **Managed harness** (preview April 2026, GA June 2026). You "declare what your agent does (model, tools, skills, instructions)" and AgentCore runs it in an isolated microVM per session, with filesystem, shell, memory and the option to switch models mid-session. It is "powered by Strands Agents" and can be exported to Strands code. There is "no separate harness charge" — [Harness docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)
  - Later additions: Step Functions integration (June 2026), lifecycle hooks (September 2026), custom OpenAI-compatible endpoints (September 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Payments** (preview May 2026). Built with Coinbase and Stripe. Supports x402 and the Machine Payments Protocol (from August 2026) and enforces a budget per session — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Managed Knowledge Base** (GA June 2026). A RAG service that agents query through Gateway, with S3, SharePoint, Confluence, Google Drive, OneDrive and web-crawler connectors — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

### Inferences
- Over 2026 AWS shipped quickly, usually with an "ingress/egress through Gateway" design, and moved up the stack. In 2025 AgentCore only hosted frameworks. In 2026 it gained its own managed agent loop (the harness, on Strands), an LLM gateway with model fallback, and a quality loop that runs from evaluations through recommendations to A/B testing.
- The microVM-per-session model has hard caps that matter for long-running "agent OS" workloads: 2 vCPU / 8 GB, 8 hours, 15-minute synchronous calls and 1 GB session storage. Instances (14 days, EC2 in your account) is AWS's answer for heavier or longer workloads.

### Gaps
- I found no exact launch date or GA/preview label for Runtime platform V2 (snapshot-based); the docs show it only as available in five Regions.
- The release date of Gateway interceptors was not confirmed. A December 2025 date appears only in secondary or mirror sources.
- The exact August 2026 day for Agent Registry GA and Runtime Instances is not on the release-notes page.
- I could not confirm the exact name and behavior of the Gateway semantic-search tool beyond "Semantic Tool Selection".

## 2. How AWS separates the agent framework from the runtime and the control plane

### Takeaway
AWS draws a hard line between agent code, which can be any framework, and the platform services, which are independent, API-addressable resources with their own IAM, quotas and pricing. The model and the agent code are treated as untrusted. Identity, credential release, tool authorization (Policy), rate limiting and content checks (Guardrails) all run at the Gateway boundary or in separate services, outside the agent process. Control-plane and data-plane APIs have separate endpoints and PrivateLink services.

### Cited Findings
- AgentCore services "can be used individually and are optimized to work together" — [AWS News Blog, 16 Jul 2025](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/). "Each service can be used independently" and is billed separately — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- **Runtime is a thin contract.** Agent code adds "required HTTP endpoints using the AgentCore SDK or custom implementation". Each agent has its own identity and immutable versions, and endpoints are routed to versions — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
  - In the LangGraph / Deep Agents example, the code change is: import `BedrockAgentCoreApp`, decorate the entry function with `@app.entrypoint`, and call `app.run()`. "The rest of the agent code stays unchanged" — [AWS ML Blog, 23 Sep 2025](https://aws.amazon.com/blogs/machine-learning/running-deep-research-ai-agents-on-amazon-bedrock-agentcore)
- **Separate control-plane and data-plane endpoints.**
  - Control plane: `bedrock-agentcore-control.<region>.amazonaws.com`, with PrivateLink service `com.amazonaws.region.bedrock-agentcore-control` (added March 2026).
  - Data plane: `com.amazonaws.region.bedrock-agentcore`.
  - Gateway data-plane URL: `https://{gateway-Id}.gateway.bedrock-agentcore.{Region}.amazonaws.com`.
  - Source: [Quotas/endpoints](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html); [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - Agent Registry has its own namespace (`agent-registry`) and separate control and data PrivateLink endpoints (August 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Enforcement outside agent code.** "By moving security controls outside of agent code … reducing the risk of policy bypass through agent manipulation." Enforcement is "at the boundary outside of agent's code - ensuring consistent, deterministic enforcement that remains reliable regardless of how the agent is implemented" — [Policy docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
  - Guardrails checks in Policy "run at the gateway layer, outside the agent's code, where the agent cannot reason around them. Because every tool and context source routes through the gateway, every new agent capability is automatically governed by the same security layer" (June 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Closing the bypass path.** Since June 2026 a Runtime can be set to "accept invocations only when they originate from your gateway". For SigV4 this uses an `aws:SourceArn` resource policy, and for JWT it uses `allowedWorkloadConfiguration` — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Credentials kept away from agent code.** The token vault releases credentials only on proof of workload identity, and it re-validates every request "to protect end-user data from malicious or misbehaving agent code" — [Identity features](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/key-features-and-benefits.html)
- **Org-level guardrails through IAM condition keys.**
  - January 2026: `bedrock-agentcore:Subnets` and `bedrock-agentcore:SecurityGroups`.
  - March 2026: `bedrock-agentcore:RuntimeAuthorizerType` and `aws:VpceOrgID`.
  - These let central teams require VPC deployment or a specific authorizer.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Evaluation and optimization work outside AgentCore Runtime.** Evaluations read external agents' CloudWatch log groups — [AWS News Blog, 2 Dec 2025](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/). Recommendations and A/B tests work for agents on Lambda, EKS or non-AWS platforms — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **The counter-trend.** The harness is a managed agent loop powered by Strands. Exporting to Strands code is the way out "when configuration isn't enough" — [Harness docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)

### Inferences
- AWS's layering can be read as three tiers:
  - Tier 1 is a framework-agnostic compute sandbox (Runtime), joined to the platform by a minimal HTTP/MCP/A2A contract.
  - Tier 2 is a mandatory egress choke point (Gateway) where identity, policy, guardrails, rate limits and audit attach.
  - Tier 3 is a set of shared services (Memory, Identity, Registry, Observability, Evaluations) reached through APIs, not in-process libraries.
- The "outside the agent" guarantee only holds when every tool call goes through Gateway. Direct SDK calls from agent code to AWS or third-party APIs skip Policy unless the network or IAM is locked down. This is why AWS added gateway-only Runtime invocation and VPC/IAM condition keys.

### Gaps
- I found no AWS architecture document that formally names "control plane" vs "data plane" for the whole AgentCore platform beyond the endpoint naming above.

## 3. Agent registry, catalogue and marketplace; how agents are inventoried and owned

### Takeaway
AWS has three inventory layers:
- The AWS Marketplace "AI Agents and Tools" category (July 2025) for buying third-party agents and tools.
- AgentCore Identity's agent identity directory (workload identities with hierarchical ARNs).
- AWS Agent Registry: preview on 9 April 2026, GA in August 2026. It is a private, governed catalogue of agents, tools, MCP servers and skills, with approval workflows, auto-discovery across AWS Organizations, RAM sharing and an MCP endpoint.

### Cited Findings
- **Marketplace.** The AWS Marketplace "AI Agents and Tools" category launched with AgentCore at AWS Summit New York (16 July 2025). It offers natural-language search, and listings show MCP or A2A support. Solutions run on AgentCore Runtime or connect through Gateway. Reported participants include Anthropic, Accenture, IBM, Salesforce, Stripe, PwC, Automation Anywhere and Perplexity — [TechTarget](https://www.techtarget.com/ai/news/366627853/AWS-launches-AgentCore-system-and-agentic-marketplace); [AWS News Blog, 16 Jul 2025](https://aws.amazon.com/blogs/aws/introducing-amazon-bedrock-agentcore-securely-deploy-and-operate-ai-agents-at-any-scale/)
  - Only one source gives a launch size of "900+ listings" — [TMCnet (single source; unverified)](https://blog.tmcnet.com/blog/rich-tehrani/ai/aws-marketplace-launches-ai-agents-tools-category-with-900-solutions-for-enterprise-deployment.html)
  - Since August 2026, Coinbase wallet use for AgentCore Payments is billed through a mandatory Marketplace subscription — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Agent Registry preview (9 April 2026).**
  - It is a "private, governed catalog" for agents, tools, MCP servers, agent skills and custom resources.
  - It supports MCP and A2A natively, plus custom schemas.
  - Records can be registered by hand or "point it to an MCP or A2A endpoint to pull details automatically".
  - Workflow: draft, then pending approval, then org-wide discoverable. Records are versioned and can be deprecated, and there are "hooks for existing approval workflows".
  - IAM controls who can register and who can discover.
  - Custom metadata can record "team ownership, compliance status, and deployment environment".
  - Search is hybrid (keyword plus semantic).
  - It can index agents hosted "including other cloud providers and on-premises environments".
  - It is reachable from the console, the API, or an MCP server (for Kiro, Claude Code and others), with IAM or OAuth (custom JWT) auth.
  - Customers: Zuora (50 agents) and Southwest Airlines.
  - Stated roadmap: extend to Amazon Quick and Kiro, auto-index on deploy, federate registries, custom taxonomies, show observability data on records, and connect to partner catalogues.
  - Source: [AWS ML Blog, 9 Apr 2026](https://aws.amazon.com/blogs/machine-learning/the-future-of-managing-agents-at-scale-aws-agent-registry-now-in-preview); [What's New](https://aws.amazon.com/about-aws/whats-new/2026/04/aws-agent-registry-in-agentcore-preview)
- **Registry GA (August 2026).**
  - "Auto-detection with AWS Organizations" catalogues AgentCore Runtimes and Gateways across member accounts "with no per-account setup" and stays in sync.
  - Customer-managed KMS keys.
  - PrivateLink.
  - Cross-account sharing through AWS RAM with four managed permissions: ReadOnly, Consumer, Publisher and Admin.
  - A required `recordType`, tagging, and new discovery APIs.
  - October 2026: expansion to Ohio, Frankfurt, London and Canada. Semantic search uses cross-region inference.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Registry pricing and limits.** Records: first 5,000 free each month, then $0.40 per 1,000. Search: first 1M free, then $0.02 per 1,000. Limit of 10 registries per account per Region. API calls include `SubmitRegistryRecordForApproval` and `UpdateRegistryRecordStatus` — [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/); [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Identity-level inventory.** The agent identity directory is "a unit of governance that allows administrators to configure policies across a common set of agent identities", with a hierarchical ARN path for group-level policies — [Identity features](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/key-features-and-benefits.html)
- **Practitioner critique of the preview.** Editing any record sets it back to DRAFT, so it must be approved again. Putting filter conditions into natural-language queries made results less precise — [Interview Kickstart write-up](https://interviewkickstart.com/blogs/articles/aws-just-launched-an-agent-registry-what-engineers-need-to-know-about-governing-ai-agents-at-scale)

### Inferences
- AWS treats agents, MCP servers and skills as one class of first-class resources, each with an owner, lifecycle state and approval gate. Discovery happens through MCP itself, so coding agents can query the catalogue.
- Registry is separate from runtime: it can catalogue agents that run elsewhere. Auto-detection, however, covers only AgentCore Runtimes and Gateways in AWS Organizations.

### Gaps
- I found no documentation showing Registry approval status gating whether Gateway or Policy will let an agent be invoked. The link between registry state and runtime enforcement is unclear.
- I found no current count of AWS Marketplace agent listings as of October 2026.

## 4. Deterministic controls the model cannot bypass (Policy + Gateway) and human-in-the-loop support

### Takeaway
AgentCore Policy is a policy engine attached to one or more Gateways. It is deny-by-default and evaluates every tool call outside the agent, using Cedar for single-request rules and Dogwood for session-aware temporal rules (Dogwood is open source, Apache-2.0, Cedar-compatible, and launched in August 2026). It can be authored in natural language and checked with automated reasoning. It has LOG_ONLY and ENFORCE modes. Policies can also consume Bedrock Guardrails signals. Human-in-the-loop support comes from several building blocks rather than one feature:
- Temporal "approval must precede action" rules.
- MCP elicitation pass-through in Gateway.
- Step Functions task-token callbacks and human-approval steps.
- Harness lifecycle hooks (Lambda allow/deny).
- Identity 3LO consent and the Consent Portal.

### Cited Findings
- **Mechanism.** You "create policy engines, create and store deterministic policies in them and associate policy engines with gateways." Policy "intercepts all agent traffic through Amazon Bedrock AgentCore Gateways and evaluates each request against defined policies … before allowing tool access." Access control can use "user identity and tool input parameters". Every decision is logged to CloudWatch — [Policy docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
- **Natural-language authoring.** Policies written in natural language are turned into candidates, "validates them against the tool schema, and uses automated reasoning to check safety conditions such as identifying policies that are overly permissive, overly restrictive, or contain conditions that can never be satisfied" — [Policy docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
  - There is also an MCP server for authoring in IDEs. Engines can enforce or only log. AWS's example is a refund tool allowed only for the `refund-agent` role and amounts under $200 — [AWS News Blog, 2 Dec 2025](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/)
- **Status.** Preview from 2 December 2025. GA on 3 March 2026 in 13 Regions — [AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/); [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - Canada Central and São Paulo were added in April 2026, and Gateway and Policy reached full Availability Zone coverage the same month — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - The CDK Policy submodule was still alpha as of May 2026 — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Dogwood (6 August 2026).** The AWS Open Source Blog post is by Marc Brooker, Joseph Tassarotti and Jean-Baptiste Tristan. Dogwood is "an open source governance language designed for agents and their tools". It is Cedar-compatible and requires no migration. It adds `when temporal { … }` clauses with `formerly`, `count_within`, `count_distinct_within`, `sum_within` and `bind`. Examples include required prior approval, per-hour transfer caps and distinct-recipient limits. The project ships a parser, validator and reference interpreter under Apache 2.0 — [AWS Open Source Blog](https://aws.amazon.com/blogs/opensource/introducing-dogwood-runtime-verification-for-ai-agents/); [GitHub repo](https://github.com/dogwood-policy/dogwood)
  - Secondary coverage says enforcement runs in a "Dogwood monitor inside AgentCore Gateway" — [The New Stack](https://thenewstack.io/aws-dogwood-agent-policies/); [InfoQ](https://infoq.com/news/2026/08/aws-dogwood-agent-policy)
- **How temporal policies work.**
  - A permit rule can use `formerly within 1h … approve_claim … output.approved: true`, matched on the same claimId, to allow `disburse_payment`.
  - Operators: `formerly within`, `since within`, `count` and `sum`.
  - History is scoped to a "policy session" whose ID the caller sends in the `x-amzn-bedrock-agentcore-policy-session-id` header.
  - Requests without a session ID fail if the engine has temporal policies.
  - Changing temporal policies invalidates open sessions (HTTP 409).
  - Only permitted actions are recorded as `response` events; denied ones are recorded as `error`.
  - Source: [Temporal policies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html)
- **Limits and caveats on temporal policies.**
  - Rate limits are per session, "the session ID is supplied by the caller", and "starting a new session begins a new count".
  - Gateway and targets must be in the same account and Region.
  - The Workload Access Token (WAT) must travel through the request chain. Non-AgentCore hops such as a third-party API gateway or Kubernetes must forward it.
  - At most 20 temporal policies per engine, 3 temporal operators per policy, and a 24-hour maximum window.
  - Not available in some Regions (e.g., Milan, N. California, Hyderabad).
  - Source: [Temporal policies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html); [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
  - Other policy limits: 1,000 policies per engine, 10 KB per policy, and a 400 KB Cedar schema per engine, generated from all tools on all associated gateways — [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Guardrails as policy inputs.** Policies can "consult information providers, such as Guardrails, that emit a signal at evaluation time — such as a content-safety or prompt-attack score — and make decisions based on the emitted score" — [Policy docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
  - This arrived in June 2026: Guardrails checks "outputs from authorized agent actions and inputs to gateway targets for prompt injection attempts, harmful content, and sensitive data exposure" — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Other gateway controls.** Lambda REQUEST and RESPONSE interceptors — [Gateway interceptors](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-interceptors.html)
  - Gateway rate limits can be scoped by JWT `sub`, IAM principal, tool or model, and `rate=0` acts as a kill switch. But "the system fails open on transient errors" — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - The FAQ also mentions per-user cost limits on requests, tokens and connection duration, and Web ACLs — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- **Human-in-the-loop building blocks.**
  - (a) Temporal policies that require an approval event before an action — [Temporal policies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html). The FAQ also mentions "one-time approvals" — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
  - (b) Gateway MCP elicitation pass-through (May 2026). In form mode the server can ask, for example, "Confirm you want to proceed with this refund?". In URL mode it can send the user to an OAuth consent page. AWS describes this as "human-in-the-loop workflows through a managed gateway" — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - (c) Step Functions: harnesses can be wrapped "with human approval, error handling, or conditional routing steps" (June 2026). The Step Functions connector's "task-token operations support human-in-the-loop callbacks" (October 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - (d) Harness lifecycle hooks at `before_tool_call` and similar points call a Lambda that returns a synchronous allow or deny. SNS and EventBridge targets can receive non-blocking notifications (September 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - (e) Identity 3LO user consent, OBO token exchange (April 2026) and the hosted Consent Portal (September 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Strands' own view.** The Strands project describes in-framework "steering" (evaluating responses and asking the model to retry) as a soft control, and positions AgentCore Policy as the harder backstop for tool access — [Strands blog](https://strandsagents.com/blog/strands-agents-with-agent-control/) (summary from search results; the full text was not fetched)

### Inferences
- AWS's governance design has three layers, all outside the model: deterministic authorization at the tool boundary (Cedar/Dogwood), probabilistic content checks (Guardrails) fed into that deterministic engine as signals, and workflow-level human approval (Step Functions, elicitation).
- The temporal-policy rules show the trade-offs of keeping state at the boundary: sessions are caller-supplied, limited to one account and Region, capped at 24-hour windows, and invalidated when policies change.

### Gaps
- I found no documented native "pause and wait for approver" primitive inside Policy itself, such as a decision value that escalates. Human approval is modelled as a prior approved tool call or handed off to Step Functions or MCP elicitation.
- I found no independent benchmark of Policy latency. The FAQ only says "thousands of requests per second".

## 5. Data protection: Guardrails, VPC/PrivateLink, residency, no-training commitments and customer-managed keys

### Takeaway
Bedrock commits that customer data "is not shared with model providers, and is not used to improve the base models". Model providers have no access to Bedrock's model deployment accounts. AgentCore supports VPC and PrivateLink for nearly every control-plane and data-plane API, and customer-managed KMS keys for the token vault, Gateway data and Registry. The main residency caveat is that Memory extraction, Policy natural-language authoring and evaluation, Evaluations, and Registry semantic search use cross-region inference. That inference is usually bounded to a geography, but some source Regions route globally. Guardrails offers prompt-attack, PII, contextual grounding and Automated Reasoning checks, and can be applied at the Gateway.

### Cited Findings
- **Bedrock commitments.** "Your data is not shared with model providers, and is not used to improve the base models"; data is "encrypted in transit and at rest". Keys can be managed in KMS, and PrivateLink is supported. Bedrock is in scope for ISO, SOC and CSA STAR Level 2, is HIPAA eligible, can be used in compliance with GDPR, and is FedRAMP High in GovCloud (US-West) — [Bedrock security & compliance](https://aws.amazon.com/bedrock/security-compliance/)
  - Bedrock runs one model deployment account per provider per Region. "Model providers don't have any access to those accounts … they don't have access to Amazon Bedrock logs or to customer prompts and completions" — [Bedrock data protection](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html)
- **AgentCore Gateway specifics.** Data is stored in DynamoDB and S3, "encrypted either with a service key or a customer-managed KMS key". "Customer content is not used to provide and maintain the AgentCore Gateway service." — [AgentCore data protection](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/data-protection.html)
  - Token vault: "customer-managed or service-managed AWS KMS keys" — [Identity features](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/key-features-and-benefits.html)
  - Registry supports customer-managed keys (August 2026). Private Key JWT keys stay in KMS (July 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Cross-region inference.** For Memory, Policy and Evaluations, requests stay within the source geography (for example, US stays in US). "Your input prompts and output results may move outside of your primary region", while data is stored only in the primary Region — [Cross-region inference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/cross-region-inference.html)
  - Global routing to any commercial Region applies to Policy from ca-central-1, sa-east-1, ap-south-2, ap-southeast-5 and ap-southeast-7 (effective 30 April). It applies to Evaluations from ap-south-2, ap-southeast-5, ap-northeast-2 and ap-southeast-7 — [Cross-region inference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/cross-region-inference.html)
  - "CloudWatch and AWS CloudTrail logs won't specify the AWS Region in which data inference occurs." — [Cross-region inference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/cross-region-inference.html)
  - Opt-outs: for Memory, use a built-in-with-overrides strategy. For Evaluations, use custom evaluators. GovCloud data "never leaves the partition" — [Cross-region inference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/cross-region-inference.html)
  - Agent Registry semantic search also uses cross-region inference — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Network isolation by date.**
  - September 2025: VPC support for Runtime and Memory.
  - October 2025 (GA): VPC and PrivateLink for all services.
  - January 2026: IAM condition keys for VPC subnets and security groups.
  - March 2026: control-plane PrivateLink for all services except the Identity control plane.
  - April 2026: managed VPC egress for Identity, Gateway and Runtime.
  - July 2026: PrivateLink for Evaluations and Optimizations.
  - August 2026: PrivateLink for Registry.
  - Source: [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Bedrock Guardrails safeguards.**
  - Content filters (Hate, Insults, Sexual, Violence, Misconduct, Prompt Attack).
  - Denied topics and word filters.
  - Sensitive-information filters that "block or mask" PII, plus custom regex.
  - Contextual grounding checks for RAG hallucinations.
  - Automated Reasoning checks against logical rules.
  - Guardrails can be applied to any content through the `ApplyGuardrail` API, without invoking a model. The Standard tier extends detection to code elements.
  - Source: [Guardrails docs](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
  - Automated Reasoning checks went GA on 6 August 2025 — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/08/automated-reasoning-checks-amazon-bedrock-guardrails)
  - AWS says they do not protect against prompt injection and should be paired with content filters — [AR checks docs](https://docs.aws.eu/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Compliance.** AgentCore is HIPAA eligible, holds ISO, SOC, PCI and C5 among others, and is pursuing FedRAMP — [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)

### Inferences
- Teams with strict residency needs (for example EU-only processing) should check every AgentCore feature that calls an LLM inside the service: memory extraction, policy natural-language authoring, evaluators and registry search. Those calls can leave the primary Region, and logs do not record where inference happened.

### Gaps
- I found no AgentCore-wide statement as explicit as Bedrock's no-training commitment covering Memory, Runtime or Evaluations content. The only explicit AgentCore-specific "not used" statement is the Gateway one.
- I did not verify per-service customer-managed key support for Memory, Runtime session storage, Evaluations results or Policy. The FAQ says Memory storage is encrypted but does not mention customer-managed keys.

## 6. Pricing model

### Takeaway
Everything is billed by consumption with no minimums. Runtime, Browser and Code Interpreter bill per second for active vCPU, and CPU is free during I/O wait. Gateway, Identity, Policy, Memory, Evaluations and Registry bill per call, per token or per record. Observability is billed at CloudWatch rates. There is no separate charge for the harness. Two pricing changes landed in October 2026: short-term Memory moved to per-GB billing on 6 October 2026, and committed-baseline Runtime rates were "launching by October 2026".

### Cited Findings
- **Runtime, microVMs.** All rates from [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/):

  | | CPU (per vCPU-hour) | Memory (per GB-hour) |
  |---|---|---|
  | V1 | $0.0895 | $0.00945 |
  | V2 | $0.1276 | $0.0169 |
  | V2 committed baseline | $0.0997 | $0.0132 |

  - Billing is per second, with a 1-second minimum and a 128 MB memory minimum.
  - CPU drops to zero during I/O wait, and V2 reclaims idle memory after 120 seconds.
  - Managed session storage is not charged during the public preview.
- **Runtime, Instances.** EC2 cost plus an AgentCore management fee calculated as a percentage of the On-Demand price. AWS's examples use 12%, or 7.8% for G-series — [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Browser and Code Interpreter.** $0.0895 per vCPU-hour and $0.00945 per GB-hour. Browser Profiles incur S3 storage charges from 15 April 2026 — [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Gateway.**

  | Item | Price |
  |---|---|
  | API calls | $0.005 per 1,000 |
  | Search API | $0.025 per 1,000 |
  | Tool indexing | $0.02 per 100 tools per month |
  | Egress to customer VPC | $0.006 per GB |
  | Web Search | $7.00 per 1,000 queries |

  Source: [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Identity.** $0.010 per 1,000 token or API-key requests for non-AWS resources, and no charge when used through Runtime or Gateway — [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Memory.** Short-term memory was $0.25 per 1,000 events until 5 October 2026. From 6 October 2026 it is $1.00 per GB ingested, $0.20 per GB retrieved and $0.10 per GB-month stored. Long-term memory:

  | Item | Price |
  |---|---|
  | Records, built-in strategies | $0.75 per 1,000 per month |
  | Records, self-managed / override strategies | $0.25 per 1,000 per month |
  | Retrievals | $0.50 per 1,000 |

  Source: [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Policy.** $0.000025 per authorization request and $0.13 per 1,000 input tokens for natural-language authoring. The first 100 temporal policies per engine are free of authorization charges. Guardrails are billed separately — [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Evaluations.** Built-in evaluators cost $0.0024 per 1,000 input tokens and $0.012 per 1,000 output tokens. Custom evaluators cost $1.50 per 1,000 evaluations plus model usage. Batch evaluations are 25% cheaper — [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- **Other.**
  - Observability: CloudWatch pricing.
  - Optimization Insights: free during preview.
  - Payments: no AgentCore fee (the wallet provider charges).
  - New AWS customers: up to $200 in Free Tier credits.
  - Source: [Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
  - Harness: "There is no separate harness charge" — [Harness docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)

### Inferences
- Charging nothing while CPU waits on I/O suits agents that mostly wait on LLM calls. The real cost drivers are likely to be model tokens (billed separately), CloudWatch telemetry volume, long-term memory records and evaluation tokens.

### Gaps
- I found no published figure for what an "average" agent session costs, and no independent cost comparison as of October 2026.

## 7. Deploying LangGraph / LangChain Deep Agents on AgentCore, and the AWS–LangChain relationship

### Takeaway
AWS has documented Deep Agents on AgentCore since September 2025 (a Runtime deployment). In April 2026 AWS's release notes recorded an "Integrations: LangChain Deep Agents Partnership". Under it, AgentCore Code Interpreter became "the first AWS-native sandbox provider" for Deep Agents, through the `langchain-agentcore-codeinterpreter` package published under the LangChain organization and a `--sandbox agentcore` CLI flag. LangGraph state and memory can persist to AgentCore Memory through `langgraph-checkpoint-aws` (AgentCoreMemorySaver and AgentCoreMemoryStore). AgentCore Evaluations supports LangGraph in both Python and TypeScript.

### Cited Findings
- **First Deep Agents example (23 September 2025).** "Running deep research AI agents on Amazon Bedrock AgentCore" calls Deep Agents "a recently introduced framework built on LangGraph".
  - Deployment: wrap the agent with `BedrockAgentCoreApp` and `@app.entrypoint`, then use the Starter Toolkit to configure, launch and invoke. Deployment takes about 2–3 minutes.
  - The toolkit generates a Python 3.13-slim container with OpenTelemetry. Each session runs in "its own fresh AgentCore Runtime microVM".
  - The post describes no formal partnership.
  - Source: [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/running-deep-research-ai-agents-on-amazon-bedrock-agentcore)
- **Partnership note (April 2026).** "AgentCore Code Interpreter is now the first AWS-native sandbox provider in LangChain's Deep Agents framework. New PyPI package `langchain-agentcore-codeinterpreter` published under the LangChain org with documentation live on the LangChain site. Native CLI support via `--sandbox agentcore`." — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - LangChain's docs show `AgentCoreSandbox` wrapping a `CodeInterpreter` and being passed to `create_deep_agent` — [LangChain docs: AWS sandbox](https://docs.langchain.com/oss/python/integrations/sandboxes/aws); [LangChain docs: remote sandboxes](https://docs.langchain.com/oss/python/deepagents/code/remote-sandboxes)
- **Research-agent example (15 June 2026).** "Build context-rich research agents with Deep Agents and Bedrock AgentCore" uses `langchain_aws` (ChatBedrockConverse, `create_browser_toolkit`, `create_code_interpreter_toolkit`) and `deepagents.create_deep_agent`.
  - Each browser subagent gets its own AgentCore Browser microVM. An analyst subagent uses Code Interpreter. Memory holds insights across sessions. Part 2 deploys the agent to Runtime with the AgentCore CLI.
  - Tracing goes to CloudWatch through ADOT or to LangSmith.
  - Caveats: the sample sets `checkpointer=None`, so resuming a session needs AgentCoreMemorySaver. Browser sessions expire after 1 hour and interpreter sessions after 15 minutes.
  - No LangChain co-authors are listed.
  - Source: [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/build-context-rich-research-agents-with-deep-agents-and-bedrock-agentcore/)
- **LangGraph and AgentCore Memory.** AgentCoreMemorySaver stores checkpoints (messages, graph state, metadata). AgentCoreMemoryStore handles long-term memory. Both are configured with just a Memory ID — [AWS docs: Memory with LangChain/LangGraph](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-integrate-lang.html)
  - The same `langgraph-checkpoint-aws` package also ships a DynamoDBSaver — [AWS Database Blog](https://aws.amazon.com/blogs/database/build-durable-ai-agents-with-langgraph-and-amazon-dynamodb/)
- **Tooling.** The AgentCore CLI scaffolds LangChain projects (preview February 2026, GA March 2026). Evaluations supports LangGraph in Python and, since September 2026, TypeScript — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - Observability exports to LangSmith — [What's New, 13 Oct 2025](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available/)
- **Competitive context.** LangChain itself reportedly launched a managed Deep Agents service in August 2026, bundling LangSmith Deployments, Sandboxes and Context Hub — [secondary news summary, unverified against LangChain primary source](https://news.baeke.info/articles/langchain-launches-managed-deep-agents-service)

### Inferences
- The only formal AWS–LangChain integration I could document is at the sandbox layer (Code Interpreter) plus memory checkpointing. Hosting LangGraph on Runtime uses the generic entrypoint wrapper and needs no LangChain-specific support.
- Runtime's 8-hour session cap and ephemeral microVM state mean long-running Deep Agents must checkpoint externally (AgentCoreMemorySaver, DynamoDB, or S3 Files/EFS mounts).

### Gaps
- I found no joint AWS–LangChain press release or LangChain-authored blog post about the April 2026 "partnership". The only primary source is AWS's release-notes entry.
- I found no AWS example of deploying LangGraph Platform or LangSmith Deployments on AgentCore Runtime.

## 8. Other AWS agent offerings, viewed through their governance approach

### Takeaway
AWS's other agent products reuse the same governance patterns:
- Agents act only with the end user's existing permissions (Quick).
- Coding and ops agents run as long-lived "frontier agents".
- Strands is the open-source framework underneath the managed harness, and Strands treats AgentCore Policy as the hard backstop.
- The AgentCore MCP server and Registry are meant to be used from Kiro and other IDEs.

Public governance detail for frontier agents is thin.

### Cited Findings
- **Strands Agents.** AWS's open-source framework, and the engine behind the AgentCore harness ("powered by Strands Agents"). Harness configurations can be exported to Strands code — [Harness docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)
  - Strands describes "steering" (evaluate and retry) and hooks as in-framework controls, and positions AgentCore Policy as the harder backstop — [Strands blog](https://strandsagents.com/blog/strands-agents-with-agent-control/) (search summary)
- **Amazon Quick (Quick Suite).** Quick agents can only reach resources the user already has access to, and the admin or owner decides what each agent may do. "Mission Control" provides monitoring, run history and KPIs across agents — [Quick docs: agents](https://docs.aws.amazon.com/quick/latest/userguide/agents-desktop.html); [Quick docs: Mission Control](https://docs.aws.amazon.com/quick/latest/userguide/mission-control-desktop.html) (search summaries)
  - Quick is a named client of the AWS for SAP MCP Server — [What's New, 1 May 2026](https://aws.amazon.com/about-aws/whats-new/2026/05/aws-sap-mcp-amazon-bedrock/)
  - Extending the Registry to Quick and Kiro is on the stated roadmap — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/the-future-of-managing-agents-at-scale-aws-agent-registry-now-in-preview)
- **Frontier agents (re:Invent, December 2025).** Kiro autonomous agent, AWS Security Agent and AWS DevOps Agent (preview), described as "autonomous, scalable, and work for hours or days without constant intervention" — [Amazon press release](https://press.aboutamazon.com/2025/12/aws-unveils-frontier-agents-a-new-class-of-ai-agents-that-work-as-an-extension-of-your-software-development-team); [SiliconANGLE](https://siliconangle.com/aws-puts-ai-agents-work-truly-autonomous-software-development)
- **Kiro and other coding agents as AgentCore clients.** The official AgentCore MCP server in `awslabs/mcp` (April 2026) lets Kiro, Claude Code, Cursor and others create Runtime, Browser, Code Interpreter and Memory resources — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **AG-UI.** CopilotKit named AgentCore its recommended deployment target for AG-UI agents (April 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)

### Inferences
- AWS is converging its own agent products (Quick, Kiro, frontier agents) and customer-built agents on shared primitives: Registry, Gateway/Policy and Identity. The Registry roadmap names Quick and Kiro.

### Gaps
- I found no public documentation of permission models, approval gates or audit trails for the Kiro autonomous agent, AWS Security Agent or AWS DevOps Agent.
- I did not research AWS Transform's agent governance. It is not covered here.
- Strands 1.0 release details and Quick admin governance settings were not verified from primary sources.

## 9. Relevance to SAP (SAP on AWS agent integrations, Joule, A2A)

### Takeaway
AWS's main SAP integration is the AWS for SAP MCP Server, GA on 1 May 2026. It runs on AgentCore Runtime with AgentCore Identity and lets agents perform create, read, update and delete operations on S/4HANA and ECC business objects over OData. Named clients are SAP Joule, Amazon Quick and Strands agents. On the SAP side, A2A is the preferred protocol between agents and MCP is used for tools. SAP's BTP guidance lists AWS Bedrock as a platform that can delegate SAP tasks to Joule agents. AgentCore Runtime hosts A2A servers (since October 2025), and Gateway can front A2A traffic through passthrough targets (since June 2026).

### Cited Findings
- **AWS for SAP MCP Server (GA 1 May 2026).** CRUD on sales orders, purchase orders, materials and finance documents in SAP S/4HANA and SAP ECC through OData. It runs on AgentCore Runtime with "dual-layer authentication" via AgentCore Identity (OAuth 2.0), session isolation, private connectivity and CloudWatch telemetry. It deploys from CloudFormation as a free container image. Clients: Amazon Quick, Strands agents and SAP Joule — [What's New, 1 May 2026](https://aws.amazon.com/about-aws/whats-new/2026/05/aws-sap-mcp-amazon-bedrock/)
- **SAP's protocol stance.** SAP's reference architecture calls A2A its preferred standard for multi-agent and vendor-to-vendor collaboration. Joule acts as an A2A client to external agents, and MCP is used for tools — [SAP Architecture Center: A2A and MCP on BTP](https://architecture.learning.sap.com/docs/ref-arch/76ec36)
  - SAP's BTP guidance lists "Google Vertex AI, Microsoft Copilot Studio and AWS Bedrock" as platforms that "can delegate SAP-specific tasks to Joule Agents" — [SAP Architecture Center: build AI agents](https://architecture.learning.sap.com/docs/golden-path/ai-golden-path/build-and-deliver/build-ai-agents)
  - Joule Studio agents "will natively support MCP and A2A protocols" — [SAP Sapphire 2026 innovation guide](https://www.sap.com/topics/events/sapphire/innovation-news-guide-2026)
- **AWS side of A2A.** AgentCore Runtime supports the A2A protocol "for multi-agent communication and discovery" — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html). This has been GA since 13 October 2025 — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available/)
  - Gateway HTTP passthrough targets can front "application-to-application (A2A) agents" with unified auth, policy and observability (June 2026) — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Unverified claim.** One non-primary blog says Joule Studio 2.0 adds bidirectional A2A with GA in Q4 2026 — [blckalpaca.at (unverified)](https://blckalpaca.at/en/knowledge-base/ai-agents/future-of-agentic-ai/a2a-adoption-prognose)

### Inferences
- The documented AWS–SAP integration path is MCP, with AWS hosting the SAP tool server. A Joule-to-AgentCore A2A exchange is architecturally possible because both sides support A2A, but I found no AWS or SAP primary document showing an end-to-end Joule-to-AgentCore A2A integration.

### Gaps
- I found no documentation of how SAP user identity is propagated through the SAP MCP Server, for example SAP principal propagation versus a technical user. The announcement says only "dual-layer authentication".
- I found no AWS-published guide on Joule interoperating with AgentCore over A2A.

## 10. Notable limitations and practitioner criticisms

### Takeaway
Practitioner reports from 2026 focus on:
- State durability across the 8-hour session cap and across version deploys.
- Debugging and observability setup friction.
- MCP transport mismatches.
- Cold starts.
- Hard platform quotas.

Several 2025 preview-era complaints have since been fixed: no IaC, no A2A, and no way to inspect memory. Documented design caveats include rate limits that fail open, temporal-policy sessions supplied by the caller, and cross-region inference for features that call LLMs inside the service.

### Cited Findings
- **Honeycomb (6 July 2026).** Routing a session to a new Runtime version starts it in a fresh environment, so "we were losing history on every deploy". Their workaround is a new endpoint per version, with an internal gateway pinning each session to the endpoint it started on.
  - They cite the 8-hour session cap.
  - Managed session storage "doesn't survive version updates", so they mount history from S3 Files, which adds operational complexity.
  - They hit "surprising deployment and CI gotchas".
  - They found long-term Memory "relatively turnkey".
  - Source: [Honeycomb blog](https://www.honeycomb.io/blog/prototype-production-aws-agentcore)
- **Laura Salinas (AWS) on DEV, 10 September 2025, preview era.** You must enable CloudWatch Transaction Search or invocations fail with "hard to debug" errors. Finding and editing the execution role's IAM permissions was "particularly tricky". The samples "need some sharpening" — [DEV Community](https://dev.to/aws/first-impressions-with-amazon-bedrock-agentcore-5dje)
- **Rackspace, preview era (2025).** The service lacked IaC support (CDK, CloudFormation, Terraform), had poor tooling for inspecting memory contents, and could not host A2A servers — [Rackspace review](https://www.rackspace.com/blog/amazon-bedrock-agentcore-preview-agentic-ai-platform)
  - These were later addressed: CloudFormation in September 2025, A2A at GA in October 2025, CDK stable in May 2026, and Agent Inspector memory browsing in April 2026 — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- **Cold starts and MCP transport.** One vendor selling a cloud-agnostic alternative reports 8–12-second initial connections after idle periods, and mismatches between FastMCP's default transport and what AgentCore expects — [Apigene blog (vendor; weigh accordingly)](https://apigene.ai/blog/aws-mcp-gateway)
  - Platform V2 snapshot restore is AWS's stated answer to cold-start variance — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- **Hard limits that constrain "agent OS" designs.**
  - Per Runtime session: 2 vCPU / 8 GB, 15-minute synchronous requests, 60-minute streaming connections, 8-hour lifetime and 1 GB session storage.
  - Gateway: 25 search-based tool calls per minute by default.
  - Policy: at most 20 temporal policies per engine, a 24-hour temporal window, and a 400 KB Cedar schema per engine.
  - Source: [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- **Documented design caveats.**
  - Gateway rate limiting "fails open on transient errors" — [Release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
  - Temporal rate limits reset when a caller starts a new session. They do not cross accounts or Regions, and non-AgentCore hops must forward the WAT — [Temporal policies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-temporal.html)
  - Cross-region inference Regions are not logged — [Cross-region inference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/cross-region-inference.html)
  - Platform V2 adds create and update times of several minutes and smaller environment-variable limits — [Runtime: how it works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
  - The CloudWatch dashboard covers "agent runtime data only" — [Observability docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- **Registry friction.** Edits reset records to DRAFT, so they need approval again — [Interview Kickstart](https://interviewkickstart.com/blogs/articles/aws-just-launched-an-agent-registry-what-engineers-need-to-know-about-governing-ai-agents-at-scale)

### Inferences
- The most consistent practitioner pain point is state continuity. Runtime microVMs are deliberately ephemeral and tied to a version, so any agent OS hosted on AgentCore needs its own durable checkpoint and session-routing layer, or must use Memory, S3 Files or EFS. Honeycomb built exactly that.

### Gaps
- Several Medium and blog posts (for example cloudshim, gunjanvi, octoco, hidekazu-konishi) discuss vendor lock-in (IAM, CloudWatch, Lambda coupling), roughly 5% X-Ray trace sampling and about 10 minutes of dashboard indexing lag. Search tools surfaced these claims, but I could not tie each one to a specific URL, so they are not cited as findings.
- I found no independent, current (2026) benchmark of AgentCore Runtime cold-start latency on V1 versus V2.
