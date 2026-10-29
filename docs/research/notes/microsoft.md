# Microsoft's enterprise agent platform (state as of late October 2026)

Scope: Microsoft Agent 365, Microsoft Entra Agent ID, Copilot Studio and Microsoft 365 Copilot agents, Purview and Defender for agents, Microsoft Foundry Agent Service, Microsoft Agent Framework, Microsoft's published governance guidance, pricing and criticism, and SAP interoperability. The emphasis is on the control plane: identity, registry, policy, oversight, audit and lifecycle. Every claim below carries a URL. "Preview" covers public preview, private preview and "Frontier" early access; "GA" means generally available. Learn pages were fetched on 2026-10-27, and most showed `updated_at` dates in October 2026.

## 1. Microsoft Agent 365: what it is, timeline, capabilities, and treating agents "like users"

### Takeaway
Agent 365 is Microsoft's control plane for agents. It does not build or run them. It was announced at Ignite in November 2025 as Frontier early access and became GA for commercial customers on 1 May 2026, at $15 per user per month or inside Microsoft 365 E7. It pulls together an agent registry in the Microsoft 365 admin center, Entra Agent ID for identity, Purview for data and Defender for threats, and it can reach non-Microsoft agents through registry sync (AWS Bedrock, Google) or the framework-agnostic Agent 365 SDK. Some parts were still preview in October 2026: agents that act as "agent users" with their own mailboxes, Bedrock/Google sync, Windows 365 for Agents, and some Defender controls.

### Cited Findings

**Timeline and status**
- Ignite, 18–21 Nov 2025: "Agent 365 is available now in Microsoft 365 admin center with the Frontier program", which was early access. It brought together Defender, Entra and Purview, plus Work IQ for work context. The registry was meant to cover agents with an Agent ID, agents registered by hand, and shadow agents. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- At Ignite 2025, Entra Agent ID was "now in preview via Microsoft Agent 365", described as providing agent inventory, lifecycle governance and access protection. Defender posture management and threat protection for agents was "now available in preview as a part of Microsoft Agent 365". — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- GA came on 1 May 2026 for commercial customers, with a per-user licence. — [Agent 365 overview (Learn)](https://learn.microsoft.com/en-us/microsoft-agent-365/overview); [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- The GA blog gives a status for each agent type:
  - Agents working on behalf of users (delegated access): **GA**.
  - Agents operating behind the scenes with their own access: **GA**.
  - Agents participating in team workflows with their own access (agent users): **Public Preview**.
  - Source: [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
  - A practitioner write-up dated 8 May 2026 says the reverse for autonomous agents: only OBO agents were covered at GA, and autonomous agents, including agent-to-agent and agent-to-tool, "remain in Frontier Preview". Microsoft's own blog lists "behind the scenes (own access)" as GA, so the two disagree. — [Ragnar Heil](https://ragnarheil.de/microsoft-agent-365-what-it-cant-do-yet-limitations-you-need-to-know/)
- Frontier is Microsoft's early-access channel. Previews in it fall under customers' existing preview terms. — [Agent overview in M365 admin center](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-365-overview)

**What it is (three pillars: observe, govern, secure)**
- **Observe:** a single, centralised registry of all agents, with views of adoption, activity, health, an "Agent map", and oversight tailored to each role. — [Agent 365 overview](https://learn.microsoft.com/en-us/microsoft-agent-365/overview)
- **Govern:** lifecycle management, access control and compliance, delivered through the Agent 365 registry in the M365 admin center plus Entra and Purview. — [Agent 365 overview](https://learn.microsoft.com/en-us/microsoft-agent-365/overview)
- **Secure:** Entra for risk-based access, Purview for information protection, DLP and risk, and Defender for threat detection and real-time protection. — [Agent 365 overview](https://learn.microsoft.com/en-us/microsoft-agent-365/overview)
- Admin capabilities are listed as:
  - "Onboard and approve agents through one IT controlled flow, applying policy templates to every agent."
  - "Enforce least privilege… which users, data, and tools agents can use."
  - "rules-based agent management to automatically enforce lifecycle policies, such as flagging ownerless agents, or blocking risky agents."
  - Audit readiness.
  - Source: [Agent overview in M365 admin center](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-365-overview)

**Registry / inventory**
- The registry sits under M365 admin center > Agents > All Agents > Registry. It has four publisher types:
  - Microsoft agents
  - External partner-built agents
  - Published by your org (line-of-business)
  - Shared by creator
  - Source: [Agent Registry (Learn)](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- The same Copilot Studio agent can appear twice, as "Shared by creator" and as "Published by your org". Microsoft says this is by design: the two rows are separate lifecycle and publisher records. An org-wide listing needs the creator to submit the agent for admin approval and an admin to publish it. — [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- The summary tiles show Total agents, Agents without owners and Unmanaged agents ("created or managed outside of Agent 365, without its risk protection and observability"). The list can be filtered by status, publisher type, channel (Copilot, Teams, Outlook, M365 apps, SharePoint), platform, and data source (embedded knowledge, fine-tuned models). — [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- Ownerless agents: a shared agent becomes ownerless when its creator is deleted. A dashboard count and one-click filter support blocking or deleting such agents, and the count updates on hard deletion of users. — [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- Risk signals:
  - A "Risks" column combines high, medium and low signals from Purview, Entra and Defender, groups them per agent instance, and deep-links to each portal.
  - Counts can lag the security portals by up to an hour.
  - Viewing risks needs an E7 or Agent 365 licence.
  - Source: [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- Uploading a custom agent package (.zip):
  1. Choose who can install it ("Publish") and who has it preinstalled ("Deploy").
  2. Apply an existing policy template, a custom policy or the default policy.
  3. Review the agent's permissions.
  - Source: [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- Registry Graph APIs, in **preview**: `GET /copilot/admin/catalog/packages` (scope `CopilotPackages.Read.All`, AI Administrator role). Exports carry more than 30 fields per agent, including owner, publisher, platform and instructions. — [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)
- Admin center "Top actions" are: approve pending agent requests (All agents > Requests), assign owners to ownerless agents, remediate at-risk agents, and review agents with exceptions. Only AI Administrator or Global Administrator can approve requests or assign ownership. — [Agent overview in M365 admin center](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-365-overview)
- Agent types in the admin center:
  - Copilot Studio Declarative Agent ("MCS DA")
  - Copilot Studio Custom Engine Agent ("MCS CEA")
  - Copilot Studio business-process agent ("MCS BP")
  - Foundry LOB, Foundry non-LOB, Foundry hosted
  - Agent Builder, SharePoint, Agents Toolkit
  - "Agent instance": an agent extended with the Agent 365 SDK, which gets an Entra-backed identity, notifications, observability, governed MCP tooling and an IT-approved template.
  - Source: [Agent overview in M365 admin center](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-365-overview)
- Coverage limits in the admin center:
  - Only Copilot Studio draft agents are visible as drafts.
  - Analytics cover only Foundry "V2" agents.
  - Agent 365 licences are needed for data collection only on third-party agents.
  - Source: [Agent overview in M365 admin center](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-365-overview)
- Registry convergence: Microsoft moved agent registry experiences that used to sit in Entra and the M365 admin center under Agent 365. Agent 365 is "the unified registry and control plane", and Entra continues to provide identity through Agent ID. Viewing the inventory needs no licence, only a role (AI Reader is the least-privilege option). Applying controls needs Agent ID licensing. — [Entra: Agent Registry convergence](https://learn.microsoft.com/en-us/entra/agent-id/agent-registry-convergence)

**Third-party and non-Microsoft agents**
- At GA:
  - Agent 365 registry sync with **AWS Bedrock and Google Cloud** was in **public preview**, with basic lifecycle actions (start, stop, delete) coming "soon".
  - Local agent discovery started with **OpenClaw** on Windows devices, with GitHub Copilot CLI and Claude Code named as future additions.
  - Intune can block common OpenClaw execution paths.
  - Defender asset-context mapping of devices, MCP servers, identities and cloud resources was due to start in **June 2026**.
  - Policy-based controls, runtime blocking and alerts through Intune and Defender were due in **public preview** in June 2026.
  - Source: [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- Partner agents named as "fully configured to be managed by Agent 365": Genspark, Zensai, Egnyte, Zendesk, Kasisto, Kore, n8n. — [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- The **Agent 365 SDK and CLI** add identity, notifications, security and governed access to Microsoft 365 data to agents "built using any agent SDK or platform".
  - Named stacks: Microsoft Agent Framework, Microsoft Agents SDK, OpenAI Agents SDK, Claude Code SDK and LangChain SDK.
  - Hosting can be Azure, AWS, GCP "or any other cloud provider".
  - Quickstarts include Node.js + LangChain and Node.js + Claude Agent SDK.
  - The SDK "doesn't create or host agents".
  - Source: [Agent 365 SDK and CLI (Learn, Oct 2026)](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)
- SDK capabilities:
  - An Entra-backed agent identity, optionally with the agent's own mailbox.
  - Notifications from Teams, Outlook, Word comments and email ("just like a human participant").
  - OpenTelemetry observability covering inference events and tool usage.
  - Governed MCP servers for Mail, Calendar, SharePoint and Teams.
  - An "IT-approved blueprint system" whose policies each instance inherits.
  - Source: [Agent 365 SDK and CLI](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)
- The **Agent 365 blueprint** is an IT-approved, preconfigured definition of an agent type. It covers capabilities, required Work IQ tool access, security and compliance constraints, audit requirements, lifecycle metadata, and linked governance policy templates such as DLP, external-access limits and logging. Users ask admins for new instances of an approved blueprint in the M365 admin center, and every instance inherits the blueprint's rules. — [Agent 365 SDK and CLI](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)
- Practitioner walkthrough of a LangChain agent on AWS ECS with Bedrock (6 Oct 2026):
  - Setup: AWS IAM outbound identity federation, then a federated identity credential on the Entra blueprint (no stored secrets), then the Entra auth sidecar, then registration through the beta `copilot/agentRegistrations` endpoint.
  - Telemetry: `microsoft-opentelemetry[langchain]` exports to the M365 admin center, Purview (DSPM, Audit) and Defender advanced hunting (`CloudAppEvents`: `InvokeAgent`, `InferenceCall`, `ExecuteToolBySDK`). It needs the `Agent365.Observability.OtelWrite` app role.
  - Gotchas: LangChain instrumentation can fail to attach silently; Bedrock model calls are still authorised by AWS IAM, not Entra.
  - Contrast with registry sync: Agent 365's Bedrock/AgentCore sync gives inventory only, with no Entra identity, no caller enforcement and no per-request audit, and it relies on a long-lived AWS access key.
  - The author notes Agent ID and the Registration API were still in preview at the time.
  - Source: [Raj Penchala](https://www.rajpenchala.com/articles/governed-langchain-agent-on-aws)

**Treating agents "like users"**
- An agent can have an optional **agent's user account**. This is an Entra user "decorated as an AI agent" with a 1:1 link to its agent identity. It can hold licences, a mailbox and calendar, and can be put in administrative units and security groups "just like a human user account". — [Entra: agent identities](https://learn.microsoft.com/en-us/entra/agent-id/agent-identities); [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- Microsoft's description of agents: "Agents have unique identities. People invoke them using common gestures (such as @mentions) in apps… They demonstrate observable behaviors…, take auditable actions." — [Agent 365 SDK and CLI](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)
- Purview treats agent instances as users. They are added to DLP, IRM and eDiscovery policies "as you would a user". — [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- Foundry "Autopilot agents" (Build 2026, **public preview**) get an Entra Agent ID, an email address, Teams presence and "an org chart position", and are governed through Agent 365. — [Foundry Build 2026 blog](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- **Windows 365 for Agents** provides Cloud PCs for agent workloads, managed in Intune. It is in **public preview, US only**, and billed pay-as-you-go at $0.40 per VM-hour outside the Agent 365 licence. — [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/); [Agent 365 Licensing FAQ](https://www.microsoft.com/licensing/faqs/122)
- Licensing follows the human, not the agent:
  - "Agents do not require their own licenses."
  - OBO agents need the delegating user licensed.
  - Non-OBO agents need their owner, sponsor or manager licensed.
  - There is no fixed cap on how many agents a licensed user can oversee.
  - Multiplexing is prohibited.
  - Source: [Agent 365 Licensing FAQ](https://www.microsoft.com/licensing/faqs/122)
- Entra network controls (destination restriction, risky file-movement filtering, prompt-attack blocking) became **GA** at Agent 365 GA for Copilot Studio agents and endpoint agents, including OpenClaw. — [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)

**Renames to be aware of when reading older material**
- "Azure AI Foundry" is now "Microsoft Foundry" in current Learn and devblog content. Foundry RBAC roles were renamed from Azure AI User/Owner to Foundry User/Owner, with role IDs unchanged. — [Foundry agent identity concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)
- "Google Vertex AI" is now "Gemini Enterprise Agent Platform". — [Microsoft Security blog, 1 May 2026](https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/)
- The Entra "Agent Registry" has converged into the Agent 365 registry. — [Entra: Agent Registry convergence](https://learn.microsoft.com/en-us/entra/agent-id/agent-registry-convergence)
- Copilot Studio "messages" are now "Copilot Credits"; the Learn URL slug is still "requirements-messages-management". — [Copilot Studio billing rates](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management)
- Microsoft Agent Framework unifies Semantic Kernel and AutoGen. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)

### Inferences
- Microsoft splits the control plane in two. **Identity and access** sit in Entra and are enforced when tokens are issued. **Inventory, approval and observability** sit in Agent 365. Data and threat controls plug into both through Purview and Defender. The registry convergence page states this split explicitly.
- The **blueprint (type) vs. instance** model is the central governance pattern. Policies such as Conditional Access, permissions and disable/revoke apply to a blueprint and are inherited by every instance, including ones created later.
- "Unmanaged agents" is a first-class registry metric. Shadow agents are treated as normal, and the job is to bring them into management, not to assume none exist.

### Gaps
- Microsoft does not clearly reconcile the blog's GA claim for "own access" agents with the practitioner report that autonomous agents stayed in Frontier preview.
- I found no confirmation that Bedrock/Google registry sync, Defender local-agent controls or Windows 365 for Agents reached GA by October 2026.
- I found no detail on the content of Agent 365 "policy templates" or "security templates", or on how rules-based lifecycle automation is configured (for example inactivity thresholds).
- Availability for sovereign or government clouds was not found. EDU, charity and government SKUs were pending at GA per a secondary search summary, not verified.

## 2. Microsoft Entra Agent ID: identities, sponsors, Conditional Access, least privilege, lifecycle, authentication, non-Microsoft agents

### Takeaway
An Entra agent identity is a special service principal with no credentials of its own. A parent **agent identity blueprint** holds the credentials and acquires tokens for it. Every identity and blueprint must have a human **sponsor** for business accountability, separate from optional technical **owners**. Governance reuses Entra's existing tools: Conditional Access (including blueprint-level and attribute-based policies), ID Protection risk, access packages with expiry, and lifecycle workflows that pass sponsorship to the sponsor's manager. Agent ID reached **GA in spring 2026**: Entra's what's-new feed lists April 2026, and third parties cite 1 May. Agents built anywhere, including LangChain on AWS or GCP, can use it through an auth sidecar or workload identity federation.

### Cited Findings

**Object model**
- There are four object types: agent identity blueprint, blueprint principal, agent identity, and agent user. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)
- An agent identity "is a special service principal… It doesn't have credentials on its own. The agent identity blueprint can acquire tokens on behalf of the agent identity provided the user or tenant admin consented." Autonomous agents get app tokens; interactive agents called with a user token get user tokens where the agent is the actor. — [Entra: agent identities](https://learn.microsoft.com/en-us/entra/agent-id/agent-identities)
- Agent identities authenticate only with **federated identity credentials issued by the blueprint**. The blueprint can hold FICs, certificates or client secrets. Agent identities are always single-tenant. A blueprint can be multi-tenant and published to other tenants, where it creates identities local to that tenant. — [Entra: agent identities](https://learn.microsoft.com/en-us/entra/agent-id/agent-identities)
- The blueprint records the kind of agent: its name, publisher, the roles it offers, and the Graph permissions its agents get. Admins can "apply a conditional access policy to all Sales Assistant Agents… disable all… revoke a permission grant for all". — [Entra: agent identities](https://learn.microsoft.com/en-us/entra/agent-id/agent-identities)
- Blueprints cannot access resources themselves; "agent tasks are always performed by the agent identity". — [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)

**Sponsors, owners, managers**
- **Owners** are technical administrators: users (including guests) or service principals, not groups, and optional. They can change auth properties, credentials and owners or sponsors; they can re-enable, restore and hard-delete. — [Owners, sponsors, managers](https://learn.microsoft.com/en-us/entra/agent-id/agent-owners-sponsors-managers)
- **Sponsors** carry business accountability and are **required** when creating agent identities and blueprints.
  - Allowed: users, guests, dynamic membership groups, and assigned Microsoft 365 groups. Not allowed: role-assignable groups or assigned security groups.
  - Up to 100 sponsors, of which at most 5 can be groups.
  - Sponsors can only take nondestructive actions (disable, change sponsors, soft-delete). They cannot re-enable or restore.
  - For delegated creation, the calling user becomes sponsor by default. App-only creation must name a sponsor. Agent ID admins are not made sponsors automatically.
  - Source: [Owners, sponsors, managers](https://learn.microsoft.com/en-us/entra/agent-id/agent-owners-sponsors-managers)
- **Managers** are set on agent user accounts. They can request access packages and see "reporting" agents, but cannot modify or delete them. — [Owners, sponsors, managers](https://learn.microsoft.com/en-us/entra/agent-id/agent-owners-sponsors-managers)
- When a sponsor leaves the organisation, sponsorship transfers automatically to their manager. Lifecycle workflow templates notify co-sponsors and managers and transfer sponsorship "to prevent orphaned agents". — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview); [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Sponsors and owners can enable or disable agents in the My Account portal and request access packages for them in My Access. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)

**Least privilege and lifecycle governance**
- A new agent identity starts with limited permissions, such as delegated scopes inherited from its blueprint. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)
- Access packages can grant security group membership, OAuth API permissions (delegated and application) and Entra roles. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)
- There are three request paths: the agent requests programmatically (`accessPackageAssignmentRequest`), the sponsor requests on its behalf, or an admin assigns directly. Requests route to approvers. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)
- On expiry, the sponsor is notified as the end date approaches. They can request an extension, which may start a new approval cycle. If they do nothing, the assignment expires and the access is removed. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)
- Agent identity deletion supports automated cascade cleanup and soft-delete. — [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Foundry: a new agent identity "starts without resource permissions", and Foundry "doesn't automatically assign RBAC roles". Microsoft advises least privilege for the identity used in each tool call, scoped to a resource or resource group rather than the subscription. — [Foundry agent identity concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)

**Conditional Access for agents**
- Conditional Access is evaluated when a token is issued or refreshed. Continuous Access Evaluation gives near-real-time enforcement where the resource supports it. — [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- There are three access patterns, and policies target whoever is the token subject:
  - **OBO / delegated:** the user is the subject, so policies target users and groups. "Selecting an agent identity as the policy subject doesn't cover agent requests made on behalf of the user."
  - **App-only / autonomous:** policies target the agent identity or its blueprint.
  - **Agent user:** policies target "Agent Users". Policies scoped to "Users" don't apply to agent user accounts.
  - Source: [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- Targeting options:
  - A blueprint-level policy covers all identities from that blueprint, including future ones.
  - Custom security attributes allow attribute-driven policies ("allow approved agents").
  - Agent risk from ID Protection is evaluated, with a template to block high-risk agents.
  - An **"Agent execution environments (Preview)"** condition enables device compliance and compliant-network controls for agents on Windows 365 Cloud PCs.
  - Source: [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id); [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Limits:
  - Conditional Access does not apply when a blueprint gets Graph tokens to create identities.
  - It does not apply to intermediate token exchanges at the "AAD Token Exchange Endpoint: Public".
  - It does not apply with security defaults on.
  - It does not apply to resources reached by **API key**, which bypass Entra entirely.
  - A policy on an agent identity doesn't cover that agent's user account, and the reverse is also true. Agent users can't be scoped by group membership.
  - Source: [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- Licensing for both Conditional Access for agents and ID Governance for agents: Microsoft 365 E7, or an Agent 365 licence plus at least Entra P1 or Microsoft 365 E3. — [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id); [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview)

**How agent identities authenticate to tools and APIs**
- Supported flows are OBO (agent is the actor, user is the subject), autonomous app-only, and agent-user flows. — [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- Foundry's runtime token exchange has four steps:
  1. The blueprint credential (an FIC that Foundry provisions) authenticates.
  2. Entra issues an agent identity token.
  3. Foundry requests a token scoped to the downstream audience.
  4. The scoped token is passed to the MCP server or A2A endpoint, which checks RBAC.
  - Source: [Foundry agent identity concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)
- In Foundry, OBO by an agent identity is **preview**. Work IQ MCP supports only `AgentOnBehalfOfUser`, not app-only. — [Foundry agent identity concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)
- Hosted-agent code gets tokens for its own instance identity from a token service, and "the project managed identity isn't available to your hosted-agent code". — [Foundry agent identity concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)

**Non-Microsoft agents**
- "Configure non-Microsoft agents with Agent ID" was listed as new at GA, with patterns for AWS, GCP and n8n and step-by-step guides for Bedrock and n8n. — [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Two patterns are offered:
  - **Sidecar:** the Microsoft Entra ID Auth SDK runs as a companion container on port 7000. It suits Docker or Kubernetes, AWS Bedrock, and "Local LLMs such as Ollama with LangChain".
  - **Workload Identity Federation:** a direct exchange from AWS STS or GCP Workload Identity to Entra, with no sidecar.
  - Both support client credentials, federated identity and OBO.
  - Source: [Integrate third-party agents](https://learn.microsoft.com/en-us/entra/agent-id/configure-third-party-agents)
- Migration guides exist for moving custom app registrations and existing Copilot Studio agents to Agent ID. An "AI-guided setup" uses a coding agent to create blueprints. — [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Platforms that create Agent IDs automatically: Foundry (a per-agent blueprint and identity in the current model; a shared project identity for legacy agents), Copilot Studio (automatic for every new agent from July 2026), App Service/Functions, and the Teams Developer Portal. — [Governing agent identities](https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview); [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)

**GA date**
- Agent ID GA appears in the Entra release notes under April 2026. Some third parties cite 1 May 2026. — [Entra what's new](https://learn.microsoft.com/en-us/entra/fundamentals/whats-new) (via search summary); [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Some features remained preview after GA, for example the blueprint and identity creation wizard in the Entra admin center. — [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)

### Inferences
- In Microsoft's design, "agents as identities" means attaching agents to the IAM machinery that already exists (service principals, FICs, OBO, Conditional Access, entitlement management, lifecycle workflows), not building a parallel system. Accountability is captured as data: a mandatory sponsor plus automatic succession.
- Policy is enforced at token issuance. Any tool reached by API key or static secret is invisible to Conditional Access, which is why Microsoft keeps pushing secretless federation and sidecars.
- Each access pattern (OBO, app-only, agent-user) needs its own policy, because Conditional Access keys off the token subject. A delegated call is governed by the user's policies, not the agent's.

### Gaps
- I did not find the exact date or wording of Agent ID's original public preview announcement (believed to be Build 2025), or the precise GA date beyond "April 2026" in the release notes.
- How Entra access reviews work specifically for agent identities, beyond access-package expiry and extension, was not found in detail.
- Whether agent identities can carry verifiable credentials or signed attestations for agent-to-agent trust is not documented in the pages read.

## 3. Copilot Studio and Microsoft 365 Copilot agents: agent types, autonomy, human-in-the-loop, environments and DLP, publishing, analytics, computer use, MCP/A2A, Work/Fabric/Foundry IQ

### Takeaway
Microsoft 365 agents are either **declarative**, using Copilot's orchestrator and models with no hosting needed, or **custom engine**, bringing your own orchestrator and models. Copilot Studio can build both, along with autonomous agents and agent flows. Governance comes mostly from Power Platform: environments and environment routing, data policies (DLP) covering connectors, knowledge, triggers, HTTP and channels, plus credit caps. Admin approval and publishing happen in the M365 admin center. Human-in-the-loop is built into agent flows ("Request for information", advanced or multistage approvals). By late 2026 the following were GA: MCP (May 2025), A2A (April 2026), computer use (May 2026) and evaluations (March 2026). A new "GitHub Copilot harness" runtime has been in production-ready preview since June 2026.

### Cited Findings

**Agent types**
- Declarative agents use Microsoft's orchestrator and models with no extra hosting. Custom engine agents "bring your own orchestrator and models". — [M365 Copilot agents overview](https://learn.microsoft.com/microsoft-365/copilot/extensibility/agents-overview); [Decision guide](https://learn.microsoft.com/da-dk/microsoft-365-copilot/extensibility/decision-guide)
- In the admin center, Copilot Studio agents appear as MCS DA (declarative), MCS CEA (custom engine) or MCS BP (business process). Agent Builder and SharePoint agents are declarative. — [Agent overview in M365 admin center](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-365-overview)
- Copilot Studio now offers two runtimes, called "harnesses".
  - The **GitHub Copilot harness** reached "production-ready preview" in **June 2026**, alongside the standard harness. It adds skills (exportable as Markdown), per-user memory, Work IQ, Foundry IQ (preview) and connected agents (preview).
  - Usage-based billing in Copilot Credits for this harness was documented in **August 2026**.
  - Source: [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- Model choice includes Claude Sonnet 4.5/4.6/Opus (GA March 2026) and Claude Sonnet 5 and GPT-5.5 Chat (GA June 2026). Some external models may require processing outside the geography. — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)

**Autonomous agents and triggers**
- Autonomous agents with event triggers became **GA in March 2025**. — [What's new in Copilot Studio, March 2025](https://microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/whats-new-in-copilot-studio-march-2025)
- Message Center MC1428562 scheduled public preview for **30 Jul 2026** of autonomous-agent triggers that run on end-user credentials and can be shared with end users. This comes from a third-party mirror and its current status is unconfirmed. — [itelio mirror of MC1428562](https://www.itelio.com/en/microsoft-message-center/mc1428562)
- Data policies can govern triggers, under "Autonomous agents governance with data policies". — [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)

**Human in the loop**
- **Request for Information (RFI)** was announced in **preview** on 19 Aug 2025.
  - It pauses an agent flow and emails reviewers a form, which appears in Outlook.
  - Supported inputs are text, number, date, email and yes/no.
  - The flow resumes automatically, and responses become parameters for later steps.
  - It is available only in agent flows. It can have multiple assignees, and the first response wins.
  - Source: [Copilot blog: RFI](https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/introducing-request-for-information-in-copilot-studio-agent-flows/); [Copilot Studio what's new (Nov 2025 entry)](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- **Advanced approvals** in agent flows include multistage approvals and conditional routing, both preview, and are "available exclusively in agent flows". — [Advanced approvals (Learn)](https://learn.microsoft.com/en-us/microsoft-copilot-studio/flows-advanced-approvals) (via search summary)
- Asynchronous responses let long-running agent flows run past the two-minute limit (May 2026). — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)

**Environment strategy, managed environments, DLP**
- Data policies in the Power Platform admin center govern maker and user authentication, knowledge sources, actions, connectors and skills, HTTP requests, channel publication, App Insights and triggers. — [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)
- Other controls:
  - Environment routing gives makers a "safe space".
  - A maker welcome message.
  - Connector dependency insights.
  - Deploy-from-Git with audit trails.
  - CMK.
  - An option to disable publishing of agents that use generative AI.
  - An option to disable cross-geo data movement.
  - Customer Lockbox, which does **not** cover security audit telemetry or Agent 365 governance events.
  - Source: [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)
- Maker-side checks: an automatic security scan before publishing and a real-time risk assessment while configuring knowledge and tools. — [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)
- "Copilot Studio provides content moderation for predefined harmful-content categories, but… [there is no] tenant-configurable policy that blocks conversations based on arbitrary administrator-defined subjects." — [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)
- The Copilot Control System's management controls cover sharing limits (number of editors and viewers), approving or blocking agent deployments, connector allow/block in the M365 admin center, environment groups for applying policy in bulk, lifecycle approval, staged rollout and retirement. — [Copilot Control System management controls](https://learn.microsoft.com/en-us/microsoft-365/copilot/copilot-control-system/management-controls) (via search summary)
- CAF tells Copilot Studio teams to configure environments to separate workloads, apply DLP to control connectors per environment, and use solution pipelines and version governance. — [CAF: govern and secure AI agents](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Image rendering and embedded URLs in responses can be controlled per environment or environment group (August 2026). — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)

**Identity in Copilot Studio**
- Automatic Entra Agent ID for each agent:
  - Preview in November 2025.
  - In May 2026, used to "scope connector permissions, Conditional Access policies, and DLP governance to individual agents".
  - From **July 2026**, "Copilot Studio automatically creates a Microsoft Entra Agent ID for every new agent, and you can no longer opt out at the environment level".
  - Source: [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- Agents built before GA don't inherit Agent IDs automatically, per one practitioner. Microsoft publishes a migration guide. — [Ragnar Heil](https://ragnarheil.de/microsoft-agent-365-what-it-cant-do-yet-limitations-you-need-to-know/); [What's new in Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id)
- Tools can run with the user's credentials by default. — [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)

**Inventory, publishing, store**
- An agent inventory schema lets admins discover and audit all Copilot Studio agents from the admin center, an API or Azure Resource Graph (May 2026). — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- Publishing flow: "See agent in Microsoft 365" creates a "Shared by creator" entry. Org-wide visibility requires submission for admin approval and an admin publish. Admins can pin up to three agents for users, and changes can take up to six hours to appear. — [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)

**Analytics and evaluations**
- Agent evaluations reached **GA in March 2026**, with multi-turn tests. Earlier additions:
  - December 2025: side-by-side version comparison.
  - January 2026 (preview): activity maps on eval results.
  - April 2026: Power Automate connector triggers, and a REST API for CI/CD (preview).
  - September 2026: content-safety test method.
  - Source: [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- Other analytics: custom metrics (preview, April 2026), an Analytics Viewer role, and environment-level telemetry export to App Insights (preview, July 2026). — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)

**Computer use**
- Computer use was **preview** at Ignite 2025, running on Windows 365 for Agents. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- In January 2026 (preview) it added built-in credentials, enhanced audit logging with session replay, and Cloud PC pooling. — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- It became **GA in May 2026**. The Windows 365 for Agents MCP server became GA in June 2026. — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- Computer-using agent usage is billed at the agent-action rate and is not included in the Microsoft 365 Copilot user licence. — [Copilot Studio billing rates](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management)

**MCP and A2A**
- MCP in Copilot Studio became **GA on 29 May 2025**. It requires generative orchestration, supports streamable transport (SSE deprecated), and shows MCP tool calls in the activity map. — [Copilot blog: MCP GA](https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/model-context-protocol-mcp-is-now-generally-available-in-microsoft-copilot-studio)
- MCP server certification by Microsoft was in **preview** in July 2026. — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- A2A for connecting agents became **GA in April 2026**. Multi-agent orchestration (child or connected agents, Fabric data agents) dates from November 2025. — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)
- On the Agent 365 Tools page, admins see AI tools and MCP servers and can allow or block them. — [CAF: govern and secure AI agents](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Microsoft's registry documentation warns that "MCP implementations are susceptible to risks, such as attacks, cascading failures, and loss of human oversight" and recommends approval mechanisms. Third-party MCP data flows are the customer's responsibility. — [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview)

**Work IQ, Fabric IQ, Foundry IQ**
- Work IQ (Ignite 2025) is the intelligence layer over emails, files, meetings and chats that lets Copilot and agents learn how a person works. Foundry IQ is a fully managed knowledge system that grounds agents in Work IQ, Fabric IQ, custom apps and the web. — [Microsoft blog, 18 Nov 2025](https://blogs.microsoft.com/blog/2025/11/18/from-idea-to-deployment-the-complete-lifecycle-of-ai-on-display-at-ignite-2025/) (via search summary)
- Status at Ignite 2025: Foundry IQ and Fabric IQ were **preview**; Work IQ conversational memory was Frontier; Work IQ reasoning over SharePoint metadata was GA. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- Foundry IQ became **GA at Build (June 2026)** with an SLA-backed retrieval endpoint. Work IQ and Fabric IQ connections were still preview then. — [Foundry Build 2026 blog](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- In Copilot Studio, Work IQ tools were preview in March 2026 and Work IQ was preview again in August 2026. Fabric IQ was preview in August 2026. — [Copilot Studio what's new](https://learn.microsoft.com/en-us/microsoft-copilot-studio/whats-new)

### Inferences
- Microsoft has three governance layers for low-code agents:
  1. A **platform-policy layer**: environments, data policies on connectors, triggers and channels, and credit caps.
  2. A **tenant-catalog layer**: M365 admin approval, publishing and pinning.
  3. An **identity/security layer**: an Agent ID per agent plus Defender and Purview.
- From July 2026, every new Copilot Studio agent gets an identity by default with no opt-out. That suggests Microsoft now treats per-agent identity as non-negotiable.
- Human-in-the-loop in Copilot Studio is a **workflow primitive** (pause, collect structured input, resume), not just a yes/no gate. RFI was explicitly positioned against yes/no approvals.

### Gaps
- I did not fetch dedicated pages on Managed Environments features (sharing limits, solution checker, usage insights) or on the full agent-approval workflow in the Teams/M365 admin centers.
- I found no Learn page on "agent store" governance beyond pinning and publishing.
- Current GA status of RFI and multistage approvals (preview when found) was not confirmed.
- I found no first-party documentation of "autonomy levels" for Copilot Studio agents.

## 4. Purview and Defender: DLP, sensitivity labels, audit, DSPM for AI, prompt injection (Prompt Shields, Spotlighting), runtime protection

### Takeaway
Purview applies its existing stack to agent instances as if they were users: audit, classification, labels, DLP, IRM, communication compliance, eDiscovery, retention and Compliance Manager. Audit covers agent-to-human, human-to-agent, agent-to-tool and agent-to-agent interactions. Labels are honoured, but encrypted content must explicitly grant the agent VIEW and EXTRACT, and new content an agent creates does not inherit labels. Defender adds agent inventory, posture and threat detection through Agent 365, plus a synchronous **pre-tool-invocation webhook** for Copilot Studio that can block actions. Microsoft's prompt-injection strategy layers probabilistic defences (Spotlighting, Prompt Shields) with deterministic ones (information-flow control, blocking known exfiltration paths, consent).

### Cited Findings

**Purview for Agent 365**
- Supported for Agent 365: DSPM, auditing, data classification, sensitivity labels, DLP, IRM, communication compliance, eDiscovery, data lifecycle management and Compliance Manager. **Not supported:** encryption without sensitivity labels. — [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- A new agent instance is automatically enabled for audit, sensitive-data detection and Compliance Manager AI-regulation assessments. "For other capabilities, include the agent instance in policies as you would a user." — [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- **Audit:**
  - Prompts and responses go to the unified audit log, including the files accessed and their labels.
  - Agent instances are audited as users.
  - Coverage is "All agent-to-human, human-to-agent, agent-to-tools, and agent-to-agent interactions", searchable as "Agent 365 activities".
  - Source: [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- **Sensitivity labels:**
  - Files must be explicitly shared with the agent instance.
  - Label encryption must explicitly grant the agent instance VIEW and EXTRACT; "Add all users and groups in your organization" isn't enough.
  - "Newly created content from Agent 365 doesn't inherit sensitivity labels from the source items."
  - Source: [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- **DLP:**
  - Configured by naming agent instances, or a group containing them, in the policy.
  - Blocks or audits agent-to-human and human-to-agent interactions for Teams, OneDrive/SharePoint and email.
  - "Because an agent instance is unaware of the block action, the agent owner must actively monitor" downstream workflow impact.
  - Source: [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- **IRM:** a "Risky AI usage" template detects prompt injection and access to protected material. Signals flow into Defender XDR. — [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- **DSPM AI observability:**
  - Shows agents active in the last 30 days, ranked by IRM risk.
  - Lists top risky activities (oversharing, exfiltration, unethical behaviour).
  - Per-agent details include Entra-enabled status, owner, agent user ID, and which agent it is an instance of.
  - The **classic DSPM for AI does not support Agent 365**.
  - Source: [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365)
- At Ignite 2025, the following were announced in **preview**: DLP for Microsoft 365 Copilot prompts (blocking responses when a prompt contains sensitive data), DSPM AI observability, IRM for agents, and agents inheriting "the same protections and organizational policies as users". Audit and eDiscovery extensions to more agent interactions were **GA**. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- Copilot Studio shows the highest sensitivity label of SharePoint sources used in a response. — [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance)

**Defender for AI agents**
- Onboarding to Agent 365 automatically enables Defender's AI agent discovery, posture assessment and threat detection.
  - The Microsoft 365 connector is needed for investigation and advanced hunting.
  - Local agents on endpoints need Defender for Endpoint "AI agent runtime protection" in active mode.
  - Source: [Defender: enable security for AI agents](https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/get-started-defender-security-for-ai)
- **Copilot Studio real-time protection:**
  - Before any tool, topic or knowledge action runs, the generative orchestrator sends a webhook to Defender. The payload carries the planned action's parameters, prior orchestration outputs and user context.
  - Defender returns allow or block. Blocked actions show in activity history and raise an XDR alert.
  - Threats addressed include prompt injection, data exfiltration and reconnaissance.
  - Sources: [Microsoft Security blog, 23 Jan 2026](https://www.microsoft.com/security/blog/2026/01/23/runtime-risk-realtime-defense-securing-ai-agents/); [Defender get-started](https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/get-started-defender-security-for-ai)
- The same Copilot Studio external threat-detection mechanism accepts third-party providers and custom monitoring tools. It entered **public preview in September 2025**. — [Visual Studio Magazine, 8 Sep 2025](https://visualstudiomagazine.com/Articles/2025/09/08/Copilot-Studio-Adds-Near-Real-Time-Security-Controls-for-AI-Agents.aspx)
- Ignite 2025 reported real-time monitoring during agent runs, integrating Defender or third-party tools, as GA. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- If the Microsoft 365 connector isn't connected, real-time protection still blocks, but no alerts or incidents appear. — [Defender get-started](https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/get-started-defender-security-for-ai)
- Copilot Studio also ships default cross-prompt injection (XPIA) and user prompt injection (UPIA) defences. — [Copilot blog: near real-time protection](https://microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/strengthen-agent-security-with-near-real-time-protection-in-microsoft-copilot-studio) (via search summary)
- Defender for Cloud **AI threat protection** detects prompt manipulation and unauthorised data access, integrating with Content Safety. — [CAF: govern and secure AI agents](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)

**Prompt injection defences**
- MSRC (July 2025) describes defence in depth for indirect prompt injection:
  - **Prevention:** hardened system prompts and **Spotlighting**.
  - **Detection:** **Prompt Shields**, integrated with Defender for Cloud.
  - **Impact mitigation:** data governance, user-consent workflows, and deterministic blocking of known exfiltration methods.
  - Source: [MSRC blog, July 2025](https://www.microsoft.com/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks)
- Microsoft's Zero Trust guidance recommends combining Prompt Shields, Spotlighting, plan-drift detection and information-flow control. It notes Prompt Shields can block legitimate actions. — [Learn: defend against indirect prompt injection](https://learn.microsoft.com/en-ca/security/zero-trust/sfi/defend-indirect-prompt-injection)
- Spotlighting (datamarking and encoding of untrusted input) was added to Prompt Shields at Build 2025. — [Azure blog: Prompt Shields](https://azure.microsoft.com/en-us/blog/enhance-ai-security-with-azure-prompt-shields-and-azure-ai-content-safety/)
- The Spotlighting paper reports "negligible effects on task performance while providing robust defense against XPIA". — [arXiv 2403.14720](https://arxiv.org/pdf/2403.14720)
- Entra Internet Access offered "Real-time protection against prompt injection attacks across all generative AI apps" in **preview** at Ignite 2025. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)

### Inferences
- Microsoft's pattern is to reuse user-centric compliance policies by making an agent a policy subject equivalent to a user, rather than inventing agent-specific policy languages.
- The Defender webhook is a **synchronous policy decision point before each tool call**, sitting outside the agent and pluggable by third parties. This is the clearest Microsoft example of separating the agent runtime from the runtime guard.
- The data-path gaps are concrete: label inheritance on agent-created content, and DLP blocks the agent doesn't know about. An agent OS would need its own handling for both.

### Gaps
- Timeout and fail-open versus fail-closed behaviour of the Defender webhook was not documented in the sources read.
- I found no confirmation of whether Defender real-time protection extends beyond Copilot Studio (for example to Foundry hosted agents or SDK agents) in October 2026.
- The GA date of Purview DLP for Copilot prompts was not found.
- I did not determine whether Prompt Shields or Spotlighting run by default in Foundry Agent Service guardrails.

## 5. Foundry Agent Service and Microsoft Agent Framework: hosting, multi-agent workflows, checkpointing and HITL, observability, evaluations, LangGraph/LangChain, MCP/A2A, networking and data residency

### Takeaway
Foundry Agent Service hosts agents and is framework-agnostic. **Hosted agents** became **GA on 9 Jul 2026**, with one sandbox per session, and support Microsoft Agent Framework, LangGraph, LangChain and others. **Microsoft Agent Framework 1.0**, open source and MIT-licensed for .NET and Python, merges Semantic Kernel and AutoGen and went **GA on 3 Apr 2026**. Its graph workflows support checkpointing and request/response HITL, but critics say durability beyond checkpoints depends on Azure Durable Task. Observability uses OpenTelemetry. MCP is first-class throughout; A2A is GA in Copilot Studio, preview for incoming A2A in Foundry, and "1.0 coming soon" in Agent Framework at 1.0.

### Cited Findings

**Foundry Agent Service**
- Ignite 2025 introduced "hosted agents, built-in memory and multi-agent workflows, all in **preview**", plus support for deploying LangGraph and CrewAI custom-code agents. Also announced: a unified MCP tool catalog and Logic Apps connectors (preview), the Foundry Control Plane (preview, with observability GA), and Entra Agent ID, Defender and Purview integrations (preview). — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- Build 2026 (blog dated 2 Jun 2026):
  - Hosted agents: one sandbox per session with dedicated compute, memory and filesystem; framework-agnostic (Agent Framework, GitHub Copilot SDK, LangGraph, LangChain); deploy "without rewrites".
  - Protocols: an OpenAI-compatible Responses API and pass-through "Invocations".
  - Long-running autonomous agents (for example OpenClaw, Hermes) with durable state.
  - Routines (scheduled runs): **public preview**.
  - Toolboxes (one managed MCP endpoint): public preview.
  - Memory (user, session, and procedural): public preview.
  - Incoming A2A (expose any agent as an A2A endpoint with an agent card): **public preview**.
  - Publishing to Teams and M365 Copilot: GA in July 2026.
  - Source: [Foundry Build 2026 blog](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- **Hosted agents GA 9 Jul 2026.** Toolboxes became GA later in July/August 2026; agent skills and Tool Search stayed in public preview. — [Foundry July–August 2026](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/)
- Observability and evaluation:
  - Tracing and evaluation for hosted agents were due **GA later in June 2026** on "one OpenTelemetry pipeline" covering model calls, tools, sub-agent hops and handoffs, with evals linked to traces in Foundry Control Plane.
  - An agent optimizer (traces and evals in, ranked improvements out, with diffs, audit and rollback) was heading to public preview.
  - Also listed: Rubric (public preview), ASSERT (adversarial tests generated from policies) and the "Agent Control Specification" (turning risks into runtime guardrails). Status not stated for the last two.
  - Source: [Foundry Build 2026 blog](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- Identity: each agent in the current model gets its own blueprint and identity. Tool calls to MCP and A2A use agent-identity tokens. Identities appear in the tenant-wide Entra inventory. — [Foundry agent identity concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)
- **Networking and data residency:**
  - "Standard agent setup" stores agent state (threads, messages, metadata) in **customer-owned** Cosmos DB, Storage and AI Search, so the customer controls residency.
  - Full network isolation with VNet injection requires bring-your-own Storage, AI Search and Cosmos DB.
  - Hosted-agent VNet integration guidance appeared in July/August 2026 (status not stated).
  - Sources: [Foundry standard agent setup](https://learn.microsoft.com/en-my/Azure/foundry/agents/concepts/standard-agent-setup) (via search summary); [Foundry virtual networks](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/virtual-networks) (via search summary); [Foundry July–August 2026](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/)
- Logic Apps connectors give access to over 1,400 systems, including SAP, exposed as MCP tools (preview, Ignite 2025). — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)

**Microsoft Agent Framework (MAF)**
- **1.0 GA on 3 Apr 2026** for .NET (`Microsoft.Agents.AI`) and Python (`agent-framework`), with "stable APIs and long-term support". — [Agent Framework 1.0 devblog](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)
- **Stable** in 1.0:
  - Connectors for Foundry, Azure OpenAI, OpenAI, Anthropic Claude, Amazon Bedrock, Google Gemini and Ollama.
  - Middleware for content safety, logging and compliance.
  - Memory and context providers (Foundry memory, Mem0, Redis, Neo4j).
  - Graph workflows with branching, fan-out/fan-in, and checkpointing/hydration.
  - Orchestrations: sequential, concurrent, handoff, group chat and Magentic-One, with streaming, checkpointing, HITL approvals and pause/resume.
  - Declarative YAML agents.
  - MCP.
  - Migration assistants from Semantic Kernel and AutoGen.
  - Source: [Agent Framework 1.0 devblog](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)
- **Preview** at 1.0:
  - DevUI.
  - Hosting on Foundry or **Azure Durable Functions**.
  - Foundry observability and evals built on OpenTelemetry.
  - AG-UI adapters.
  - Skills.
  - GitHub Copilot SDK and Claude Code SDK as agents inside workflows.
  - An Agent Harness with shell, filesystem and messaging access.
  - Source: [Agent Framework 1.0 devblog](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)
- A2A: "A2A 1.0 support coming soon" (at 3 Apr 2026). — [Agent Framework 1.0 devblog](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)
- By Build 2026, the agent harness (skills, memory, middleware), the GitHub Copilot SDK and Claude Agent SDK integrations, and Magentic-One were stable. Filesystem tools, memory tools and a deep-research agent were **public preview**. — [Foundry Build 2026 blog](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- **HITL mechanics:**
  - A `RequestPort` (.NET/Go) or `ctx.request_info()` with `@response_handler` (Python) emits a `RequestInfoEvent`. The caller responds with `SendResponseAsync`, or `workflow.run(responses=...)` in Python.
  - Tool approval in orchestrations emits `ToolApprovalRequestContent` or `function_approval_request`.
  - Pending requests are saved in checkpoints and re-emitted on restore. You can resume and respond in one call with `checkpoint_id` plus `responses`.
  - The docs also show Go samples from `microsoft/agent-framework-go`.
  - Source: [Agent Framework HITL docs](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop)
- **Criticism (Diagrid, 2 Mar 2026):**
  - Resume is manual and needs a `checkpoint_id`; there is "no supervisor, no scheduler, no automatic restart".
  - There is no heartbeat or lease, so a crashed workflow looks the same as a running one.
  - Nothing stops two processes resuming the same checkpoint.
  - Checkpoints are taken per superstep, so completed parallel work is re-run.
  - There is no built-in durable retry.
  - Production-grade durability needs Azure's Durable Task Scheduler.
  - Source: [Diagrid](https://www.diagrid.io/blog/still-not-durable-how-microsoft-agent-framework-and-strands-agents-repeat-the-same-mistake)
- MAF's pause model: the workflow emits a request event and the caller runs it again with `responses=...`, optionally together with a `checkpoint_id`. — [Agent Framework HITL docs](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop)
- CAF recommends standardising on Microsoft Agent Framework plus the Foundry SDK for development. — [CAF: govern and secure AI agents](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)

**Bringing LangGraph and LangChain**
- Foundry hosted agents name LangGraph and LangChain as supported frameworks. — [Foundry Build 2026 blog](https://devblogs.microsoft.com/foundry/agent-service-build2026/); [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- The Agent 365 SDK supports the LangChain SDK on any cloud. — [Agent 365 SDK and CLI](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/)
- The Entra sidecar is documented with "Ollama with LangChain". — [Integrate third-party agents](https://learn.microsoft.com/en-us/entra/agent-id/configure-third-party-agents)
- `microsoft-opentelemetry[langchain]` instruments LangChain for Agent 365. — [Raj Penchala](https://www.rajpenchala.com/articles/governed-langchain-agent-on-aws)

### Inferences
- Microsoft separates the **harness or framework** (MAF, LangGraph, Copilot SDK, Claude SDK, all pluggable) from the **runtime** (Foundry hosted agents: per-session sandbox, token service, toolboxes) and from **governance** (Agent 365 and Entra). This is a direct precedent for running a LangChain Deep Agents harness under a separate governance layer.
- Toolboxes, a single governed MCP endpoint with auth handled outside agent code, and the hosted-agent token service both keep credentials out of agent code.
- MAF's HITL is a typed request/response model persisted in checkpoints. The criticism suggests durable execution (leases, automatic resume, exactly-once) is the part Microsoft hands off to Azure Durable Task, not to the framework.

### Gaps
- The GA status in October 2026 of Foundry multi-agent workflows, Foundry memory, incoming A2A, Foundry Control Plane (beyond observability) and MAF A2A 1.0 was not confirmed.
- I found no Foundry-specific data residency commitments (for example EU Data Boundary coverage for hosted agents).
- I did not retrieve GitHub repository metrics or release cadence for microsoft/agent-framework. A February 2026 release-candidate date appeared only in an unattributed search summary and is not verified.
## 6. Microsoft's published guidance: autonomy, responsible AI for agents, governance frameworks (CAF, Copilot Control System, failure-mode taxonomy)

### Takeaway
The most concrete guidance is the **Cloud Adoption Framework (CAF) "AI agents" track**. It requires a centralised, enforceable baseline: a registry, one identity per agent, policies that are the same across platforms, observability, cost allocation, data residency and retention, red-teaming, input/output filtering, managed identities, least privilege, MCP/A2A allow-lists and a pre-planned "kill switch". The **Copilot Control System** frames Microsoft 365 governance as security, management and measurement. The AI Red Team's **failure-mode taxonomy** (v1 April 2025, v2 June 2026) names HITL bypass as the most consistently exploited failure. It recommends tiering approvals by reversibility and blast radius, and verifying agent identity cryptographically.

### Cited Findings

**CAF: "Govern and secure AI agents across the organization" (ms.date 9 Apr 2026, updated Oct 2026)**
- The adoption process has four phases: plan, govern and secure (responsible AI, governance and security, environment preparation), build (single- vs multi-agent), and manage. — [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- "A governance and security baseline sets the minimum requirements that every agent must meet before it is allowed to operate." The four policy domains are control plane, data governance and compliance, security, and development standards. — [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Control-plane practices:
  1. Give accountability to existing cloud governance, security and compliance leaders, and "avoid creating parallel governance models".
  2. Keep an agent registry ("You can't govern agents you don't know exist"), tracking owner, purpose, platform and access scope. If Agent 365 isn't available at scale, use Entra Agent ID as the authoritative source.
  3. Give every agent a distinct identity.
  4. Enforce policies consistently across first-party, custom and third-party agents.
  5. Observe activity and tools to detect drift, using auto-instrumentation.
  6. Track and allocate costs with tags, budgets and alerts, and restrict who can create, deploy and scale agents.
  - Source: [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Data:
  - Minimise data use, audit memory stores and logs, and support deletion.
  - Ensure residency of sources, runtime and outputs.
  - Set retention for logs, memory and training data, with automated purging.
  - Isolate public agents from internal data (landing-zone "corp" vs "online" subscriptions).
  - Make agents inherit user permissions on delegated access.
  - Disclose AI involvement.
  - Name a human accountable for approving deployments.
  - Source: [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Security:
  - Training.
  - AI threat protection.
  - Infrastructure baselines.
  - Adversarial testing before release and after significant updates.
  - Input and output filtering ("treat all incoming data… as potentially hostile").
  - Managed identities instead of secrets.
  - Least privilege, with DLP on outputs.
  - Sending AI alerts to the SOC through Sentinel.
  - External integrations limited to trusted MCP servers and approved A2A entities.
  - Incident response: "decide in advance how to quickly disable an agent", preserve logs, run drills.
  - Source: [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Enforcement approach: "start with monitoring rather than immediate restrictions… audit-based model… then gradually introduce stricter controls". — [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)
- Without Agent 365, CAF says to gather signals from Entra (identity), Purview (data), Defender (AI agent inventory) and Azure Monitor. It also points to the open-source "Data Agent Governance and Security Accelerator". — [CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/governance-security-across-organization)

**Copilot Control System (CCS)**
- CCS has three pillars: security and governance, management controls, and measurement and reporting. Management controls cover licensing and metering, agent lifecycle (approve, block, staged rollout, retire), sharing limits, connector allow/block, and environment groups. — [CCS management controls](https://learn.microsoft.com/en-us/microsoft-365/copilot/copilot-control-system/management-controls) (via search summary)

**AI Red Team failure-mode taxonomy**
- v1.0 (24 Apr 2025) classifies failures as novel or existing, and as safety or security. Examples include agent compromise, injection, impersonation, flow manipulation, memory poisoning and XPIA. — [Microsoft Security blog, 24 Apr 2025](https://microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents)
- v2.0 (4 Jun 2026) adds seven failure modes:
  - Agentic supply chain compromise
  - Goal hijacking
  - Inter-agent trust escalation
  - CUA visual attacks
  - Session context contamination
  - MCP/plugin abuse
  - Capability/architecture disclosure, including exposure of HITL trigger logic
  - Source: [Microsoft Security blog, 4 Jun 2026](https://www.microsoft.com/en-us/security/blog/?p=147942)
- v2.0 recommendations:
  - "HitL bypass was the most consistently exploited failure mode."
  - Base approval prompts on the actual underlying tool calls, not the agent's description of them.
  - "Tier approvals by reversibility and blast radius", invoke HITL deterministically, and watch for consent fatigue.
  - Reject self-asserted roles at orchestrator handoffs; verify identity "cryptographically, not positionally".
  - Treat session and persistent memory as security-relevant, with provenance.
  - Include MCP servers, prompt templates and tool descriptions in SBOMs, and "treat natural-language tool descriptions as code".
  - Test full multi-step flows, because zero-click chains were achieved.
  - Source: [Microsoft Security blog, 4 Jun 2026](https://www.microsoft.com/en-us/security/blog/?p=147942)

### Inferences
- Microsoft's guidance consistently says governance is a **baseline that applies before an agent may run**, owned by existing governance functions, and phased in from audit to enforcement.
- I found no Microsoft numeric "autonomy level" scale. Autonomy is handled implicitly through access patterns (OBO, app-only, agent user), approval tiers and runtime blocking.

### Gaps
- I found no Microsoft framework of numbered autonomy levels for agents, and no agent-specific Responsible AI Standard update. The CAF Responsible AI policies page was referenced but not fetched.
- The full text of the Copilot Control System pages was not retrieved (search summary only).

## 7. Limitations, pricing model, and criticisms

### Takeaway
Pricing has three parts:
- **Per-user governance licences**: Agent 365 at $15 per user per month, or M365 E7 at $99, with no per-agent licence.
- **Consumption for building and running**: Copilot Studio Copilot Credits, Foundry Azure metering, Windows 365 for Agents at $0.40 per VM-hour.
- **Prerequisite SKUs**: E5, Entra P1/E3, and others.

Criticism focuses on cost forecasting, licensing complexity, manual onboarding of third-party and shadow agents, autonomous-agent coverage lagging behind OBO agents, and gaps in what can be monitored.

### Cited Findings

**Agent 365 licensing**
- Prices: E7 is $99 per user per month and includes E5, Agent 365, Microsoft 365 Copilot and Entra Suite. Agent 365 standalone is $15 per user per month. "There are no consumption-based costs for Agent 365 yet." — [Agent 365 Licensing FAQ](https://www.microsoft.com/licensing/faqs/122)
- Who needs a licence: users who delegate access to OBO agents, and owners, sponsors or managers of non-OBO agents. Microsoft recommends licensing everyone who interacts with or manages agents.
  - Unlicensed users' agent activity is "not entitled to Agent 365 protections".
  - Prerequisites: E5 for information workers; Defender + Purview Suite FLW for frontline workers.
  - Source: [Agent 365 Licensing FAQ](https://www.microsoft.com/licensing/faqs/122)
- Agent 365 "works best when using Microsoft E5 as a pre-requisite". — [Agent 365 overview](https://learn.microsoft.com/en-us/microsoft-agent-365/overview)
- Conditional Access and ID Governance for agents require E7, or Agent 365 plus Entra P1 or M365 E3. — [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- An Agent 365 licence does not add E5-level Purview or Defender. Conditional Access for OBO agents needs E3 per user and ID Protection needs E5 per user. — [Ragnar Heil](https://ragnarheil.de/microsoft-agent-365-what-it-cant-do-yet-limitations-you-need-to-know/) (practitioner)

**Copilot Studio Copilot Credits (Learn, ms.date 3 Aug 2026)**
- Rates per event:
  - Classic answer: 1 credit.
  - Generative answer: 2.
  - Agent action, including computer use: 5.
  - Tenant graph grounding: 10.
  - Agent flow actions: 13 per 100.
  - AI tools: basic, standard and premium tiers, with premium at 10 credits per 1K tokens for reasoning models.
  - Voice: 10, 35 or 75 credits per minute.
  - Source: [Copilot Studio billing rates](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management)
- Employee-facing use by Microsoft 365 Copilot-licensed users under the user's identity is "No charge", subject to fair-use limits. Agent flows are included only when started by the "When an agent calls the flow" trigger; flows with other triggers, such as autonomous ones, are billed. — [Copilot Studio billing rates](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management)
- Enforcement:
  - At **125% of prepaid capacity**, custom agents are **disabled** after the current conversation ends.
  - Agent flows are blocked when capacity is exhausted.
  - Per-environment allocation and pay-as-you-go are available.
  - Per-agent monthly consumption caps can be set in the Power Platform admin center.
  - Source: [Copilot Studio billing rates](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management)
- Third-party sources put the price at about $0.01 per credit pay-as-you-go and $200 per month for a 25,000-credit pack. Microsoft's Learn page defers to the Licensing Guide. — [CloudZero](https://www.cloudzero.com/blog/copilot-studio-pricing/) (secondary)

**Criticisms and limitations**
- Directions on Microsoft (16 Jul 2026), from its public summary only (the report is paywalled):
  - Agent 365 "does not fully meet all goals at launch".
  - Onboarding often needs developer and IT work.
  - Some agent activity "can't be controlled or monitored".
  - It requires licensing other products.
  - Source: [Directions on Microsoft](https://www.directionsonmicrosoft.com/reports/agent-365-whats-there-whats-missing/)
- Practitioner (8 May 2026):
  - Shadow agents detected through Defender and Entra must be onboarded manually, with no automated path from discovered to governed.
  - Third-party agents (ChatGPT Enterprise, Bedrock, GCP) are fully governed only through the SDK.
  - Custom MCP servers can be registered only through a developer-led CLI or manifest process.
  - Lifecycle rules exist but initial setup is manual.
  - "Flex routing" can temporarily move data out of region at peak, and disabling it may break generative features.
  - Source: [Ragnar Heil](https://ragnarheil.de/microsoft-agent-365-what-it-cant-do-yet-limitations-you-need-to-know/)
- Licensing analysts say the main concern is cost forecasting. Microsoft reportedly acknowledges that per-user licensing for "users who interact with" agents is hard to operationalise because visibility into user-level agent interactions is limited. — [SAMexpert](https://samexpert.com/agent-365-microsoft-ai-licensing/) (via search summary; secondary)
- Platform limits documented by Microsoft:
  - No tenant-configurable topic blocking in Copilot Studio.
  - Customer Lockbox doesn't cover audit or Agent 365 telemetry.
  - Registry duplicates by design.
  - Risk counts lag by up to an hour.
  - Agent-created content isn't auto-labelled.
  - DLP blocks are invisible to the agent.
  - Conditional Access is blind to API-key access.
  - Sources: [Copilot Studio security & governance](https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance); [Agent Registry](https://learn.microsoft.com/en-us/microsoft-agent-365/admin/agent-registry-overview); [Purview for Agent 365](https://learn.microsoft.com/en-us/purview/ai-agent-365); [Conditional Access for agents](https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id)
- Agent Framework durability criticism: see section 5. — [Diagrid](https://www.diagrid.io/blog/still-not-durable-how-microsoft-agent-framework-and-strands-agents-repeat-the-same-mistake)

### Inferences
- The licence follows the accountable human, not the agent. This keeps the cost of the governance plane predictable, but means agent sprawl is never limited by price.
- Consumption metering with hard enforcement (disable at 125%, block flows) is itself a governance control. Per-agent caps act as a spend-based circuit breaker.

### Gaps
- I could not access the full Directions on Microsoft report or Gartner/Forrester analyses.
- I did not retrieve Foundry Agent Service pricing (hosted agent compute, memory, toolboxes).
- Whether Microsoft has since introduced consumption-based Agent 365 charges ("yet") was not found.

## 8. SAP relevance: Copilot/Joule interoperability, SAP connectors, A2A with Joule agents

### Takeaway
Microsoft and SAP have a **bidirectional Joule–Microsoft 365 Copilot integration**, which a Microsoft post reportedly says became GA in late 2025. At **SAP Sapphire (May 2026)** they announced **A2A agent-to-agent integration** between Microsoft 365 Copilot and Joule, with no GA date; an SAP community roundup lists it for Q4 2026. On the Microsoft side, SAP access also comes through Logic Apps connectors exposed as MCP tools (preview, Ignite 2025) and Sentinel for SAP.

### Cited Findings
- SAP describes the bidirectional integration as letting users reach SAP data from Microsoft 365 and Microsoft 365 information from SAP apps, starting in either tool. Its pages conflict on whether it is included with the Joule Base subscription or requires AI Units. — [SAP: Joule and Microsoft 365 Copilot](https://www.sap.com/products/artificial-intelligence/joule-joule-and-microsoft-365-copilot.html) (via search summary; the page returned 403 when fetched)
- Microsoft's Sapphire 2026 post (12 May 2026) announces agent-to-agent integration between Microsoft 365 Copilot and Joule. Joule and Copilot run agentic flows using Microsoft Work IQ and the SAP Knowledge Graph. The example: a user prepares a performance review in Word with Copilot, which uses Joule skills for S/4HANA or SuccessFactors and then schedules a one-on-one. No GA date is given. — [Azure blog, Sapphire 2026](https://azure.microsoft.com/en-us/blog/advancing-enterprise-ai-new-sap-on-azure-announcements-from-sap-sapphire-2026/)
- The same post:
  - SAP Business Data Cloud Connect for Microsoft Fabric (announced at Ignite 2025) offers bi-directional zero-copy delta sharing "coming in the latter half of 2026".
  - Prebuilt agent use cases under Azure Accelerate are built with Copilot Studio or Foundry.
  - Sentinel for SAP is mentioned for security monitoring.
  - Source: [Azure blog, Sapphire 2026](https://azure.microsoft.com/en-us/blog/advancing-enterprise-ai-new-sap-on-azure-announcements-from-sap-sapphire-2026/)
- An SAP community roundup lists A2A interoperability with Microsoft Copilot as a **Q4 2026** item. A Microsoft post reportedly describes Copilot Studio as an orchestration layer consuming Joule services over A2A in early scenarios (Nestlé), but this was not confirmed in the fetched Azure blog. — [SAP Community: Sapphire 2026 announcements](https://community.sap.com/t5/technology-blog-posts-by-sap/sap-sapphire-2026-announcements-only/ba-p/14396190) (via search summary)
- SAP says agents built in Joule Studio will natively support MCP and A2A. — [SAP Sapphire Innovation News Guide 2026](https://www.sap.com/topics/events/sapphire/innovation-news-guide-2026) (via search summary)
- Logic Apps connectors (over 1,400 systems, including SAP) are exposed as MCP tools in Foundry (preview, Ignite 2025). — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
- Ignite 2025 had a session titled "Modernize Identity Governance for SAP with Microsoft Entra" (title only, no announcement detail). — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)

### Inferences
- Microsoft's cross-vendor stance on SAP is protocol-level (A2A, MCP) with Copilot Studio or Copilot acting as orchestrator. There is no evidence yet that Joule agents appear in the Agent 365 registry or carry Entra Agent IDs.

### Gaps
- I found no evidence that SAP Joule agents can be registered in Agent 365 or given Entra Agent IDs, and no documentation of identity propagation (OBO between Entra and SAP IAS/BTP) for Copilot–Joule A2A.
- The GA date for Copilot–Joule A2A is unconfirmed; third-party sources conflict.
- I did not research the Power Platform SAP ERP connector or Dynamics 365 ERP MCP servers in depth. The Dynamics 365 ERP MCP server was preview at Ignite 2025. — [Ignite 2025 Book of News](https://news.microsoft.com/ignite-2025-book-of-news/)
