# Baseline scenario: what the LEAN master data governance framework requires of its agents and of the platform that runs them

Source corpus: the local repository `/home/user/lean-framework` (git HEAD `01589e7`), read in full and not modified. There was no web research. Citation form: `[file › section or rule, Lnn]`. Paths are relative to the repository root, and line numbers refer to HEAD `01589e7`. "Stated" means the documents say it. "Inference" means I derived it, and it is labelled every time.

---

## 1. Corpus, status and document hierarchy

### Takeaway
The framework is a set of drafts. When documents conflict, the charter wins, then the rulebook. Agent requirements are concentrated in a small number of places: rules R-18, R-19, R-21 and R-22 with the autonomy-level table, the operating model's "Agents" section (which *is* the agent register), the charter's "controls we never switch off", and controls-catalogue rows R-18, R-21 and R-22. The other rules mostly constrain agents indirectly, through the unified app, the sensitive-field lists, classification and segregation of duties.

### Cited Findings
- I read 13 files in full, about 11,300 words: README.md, charter.md, rulebook.md, operating-model.md, controls.md, delivery/transition.md, domains/template.md, and domains/starters/{customer, supplier, material, pricing, production, finance-structures}.md. [repository file listing]
- **Statuses:** charter "Draft v0.4", "Effective from: [TBC]" [charter.md › header, L3]; rulebook "Draft v0.11", change-log entry dated 2026-10-25 [rulebook.md › header L3; › Change log L130]; operating model and controls catalogue "Draft v0.4" [operating-model.md L3; controls.md L3]; transition notes are "Working notes for the data team, outside the governance framework" [delivery/transition.md › header, L3]; each starter is "Starter v0.1 … Starter material, not a decision" [domains/starters/*.md L3–6].
- **Precedence:** "Where documents differ, this charter wins, then the rulebook." [charter.md › How documents are approved, L113]
- **Approvals:**
  - The charter is approved by the four GPDOs and the platform owner.
  - The rulebook, operating model and controls catalogue are approved by the platform owner.
  - In domain profiles, the GPDO approves the breakdown and each attribute owner approves their part's settings.
  - A rulebook change "that adds work for owners or delegates goes to the owner review before it takes effect".
  - [charter.md › How documents are approved, L104–113; README.md › Documents, L52–60]
- **The LEAN pillars:**
  - "**E**mbedded controls | The app decides by default and logs its own evidence."
  - "**A**gent-operated | AI agents do the coordination and routine work."
  - [README.md › pillar table, L5–10]
- **Target layers:**
  - Coordinate = "AI agents | Prepare, chase, route, draft and propose, and flag what needs a person's judgement".
  - Enforce = "The unified app, SAP and the data platform | Check every request, approve what passes, hold sensitive changes, measure quality and log the evidence".
  - Run = "The data team, under the platform owner | Build and run the app, the data platform and the agents".
  - Assure = "Internal controls | Review emergency access and any change made without a request".
  - "Technology runs governance, and people decide."
  - [README.md › The target setup, L28–38]
- **Charter principle 3:** "**Agent-operated.** AI agents do the coordination and routine work: they prepare, chase, route, draft and propose. People decide, and stay accountable." [charter.md › Principles, L41–43]
- **Never-switch-off controls** "can't be waived by exception, and changing them needs every signatory" [charter.md › Controls we never switch off, L117]. "The controls the charter lists can't be waived." [rulebook.md › R-20, L124]
- **Scope of the rules:**
  - Rules apply to "the systems the framework governs: SAP now, and other systems as they come in".
  - "Five rules apply to all data from the start, wherever it's held: ownership (R-01, R-02), classified fields and access (R-16), trade secrets (R-21) and AI tools (R-22)."
  - [rulebook.md › intro, L24–28]
- **Effective date:** "The rules apply to new and changed records, access and copies from the effective date in the charter. Each domain is brought into line as its requests move into the unified master data app, and until then, gaps are tracked on the scorecards rather than treated as breaches." [rulebook.md › intro, L30–33]
- **How controls evolve:** "controls change here as the app grows, and the rules don't." [controls.md › intro, L5–7]
- **R-01 covers agents explicitly.** The GPDO is "accountable for its data however it's changed: by people, third parties, the app or agents." [rulebook.md › R-01, L39]

### Inferences
- *Inference:* The charter outranks the other documents. Its "never" list for agents and its definition of "an environment the organisation controls" are therefore the hardest constraints on any agent platform design, and only every signatory can change them.
- *Inference:* R-18 (agents) and R-19 (data team) are not among the five rules that "apply to all data from the start". Read literally, R-18 would bind only agents working on governed systems. However, the charter's never-list (L123–124) is unconditional. A platform should apply R-18 to every agent, wherever it works.
- *Inference:* The controls catalogue is the most changeable document ("controls change here as the app grows"). Platform mechanisms should be traced to rules first and to controls second.

### Gaps
- The repository holds no design documents for the unified app or for the agents. "How each control works in practice" is an open decision [README.md › Open decisions, L71–72].

---

## 2. The five agents: who each serves, what it does, what it reads and writes, starting autonomy, and what it must never do

### Takeaway
All five agents are owned by one named agent owner in the data team, who has a named deputy. Four start at level 1 (propose); the change reconciler starts at level 0 (observe/report only). No starter profile grants any level-2 change ("None yet"). In the transition period, no agent may create or change master data. The operating model gives each agent's role in one line. Most read and write needs are not stated, so the per-agent data access in the table below is largely inferred and labelled as such.

### Cited Findings

**Common to all five**
- The register: "This is the agent register (R-18). The agent owner for every agent is a named person in the data team [TBC: name], with a named deputy [TBC: name]." [operating-model.md › Agents, L51–53]
- Starting levels: "Each agent starts at level 1, where it proposes and a person decides, apart from the change reconciler, which only reports." [operating-model.md › Agents, L53–54]
- The register's columns are: Agent | Works for | Does | Rules. [operating-model.md › Agents, L62–68]
- What agents are for: "they prepare, chase, route, draft and propose. They also flag what needs a person's judgement, such as a likely duplicate, and propose an answer. A check with a fixed answer belongs in the app, and a decision belongs to a person." [operating-model.md › Agents, L45–49]
- Agents "are never accountable, so they aren't in the [RACI] table". [operating-model.md › Who does what, L14–16]
- Every starter profile sets "Agent changes approved at level 2 (R-18) | None yet": customer, supplier, material, pricing, production and finance-structures. [domains/starters/*.md, last row, L26–27]

**A. Request assistant**
- **Works for:** Requesters. [operating-model.md › Agents, L64]
- **Does:** "Helps fill in requests, pre-filling them from documents such as a bank letter. Explains failed checks, answers questions from the domain profile, and flags values that pass the checks but look wrong." [operating-model.md › Agents, L64]
- **Also:** "It pre-fills requests from documents, explains failed checks and answers questions, so requesters rarely need a person." [operating-model.md › Requesters, L107–108]
- **First point of escalation:** "Questions go to the request assistant first, then the attribute owner or their delegate, then the GPDO." [charter.md › Escalation and visibility, L136–138]
- **Rules served:**
  - R-03: "created and changed only through the governed process … starting with a complete request".
  - R-05: "passes its domain's mandatory checks, including a duplicate check, before it's approved".
  - [operating-model.md L64; rulebook.md › R-03 L46, R-05 L48]
- **Starting level:** 1. [operating-model.md › Agents, L53]
- **Reads (stated):**
  - Documents such as a bank letter.
  - Failed-check results.
  - The domain profile. The app shows each field's conventions "from the domain profile" as the field is filled in.
  - [operating-model.md L64, L105–106]
- **Context:**
  - "Requesters enter the data themselves." [README.md L40; operating-model.md › Requesters, L102]
  - Bank details are Restricted payment data. [rulebook.md › classification table, L97; starters/customer.md L24; starters/supplier.md L24]
  - Bank details are a sensitive field. [starters/customer.md L21; starters/supplier.md L21]

**B. Owner assistant**
- **Works for:** "Attribute owners and their delegates". [operating-model.md › Agents, L65]
- **Does:** "Prepares each case: duplicate comparisons, bank-detail call-backs, and the evidence. Chases anything overdue, and prepares the monthly sample of automatic approvals." [operating-model.md L65]
- **Charter:** "Agents prepare each case and chase what's overdue." [charter.md › Delegates, L89–90]
- **Rules served:**
  - R-05 (checks and duplicates).
  - R-06: approval within the domain's rules; "Nobody approves their own request"; turnaround times.
  - R-13: sensitive changes held until confirmed; "Nobody confirms a change they requested or entered".
  - R-15: bank details "verified with the supplier using contact details that weren't changed along with it".
  - [operating-model.md L65; rulebook.md L48–49, L71, L73]
- **The human decisions it prepares, with their frequency:**
  - Confirm a sensitive change: daily.
  - Decide a likely duplicate, or approve a request the app can't: daily.
  - Review a sample of automatic approvals: monthly.
  - [operating-model.md › Who does what, L25–27]
- **Who calls the supplier:** "The owner or their delegate calls the supplier back on contact details already on file, and records it on the request. The app flags bank accounts already used by another supplier or customer." [controls.md › R-15, L28]
- **Overdue thresholds:** starters set "2 business days for standard requests; 4 business hours for urgent ones". [starters/customer.md L13; supplier L13; material L13; finance-structures L13] The pricing and production values are [TBC]. [starters/pricing.md L13; production.md L13]
- **Starting level:** 1. [operating-model.md L53]
- **Transition:** "Until the request assistant and the owner assistant start, attribute owners and their delegates prepare their own cases." [delivery/transition.md › What's different, L27–28]

**C. Quality agent**
- **Works for:** Attribute owners. [operating-model.md › Agents, L66]
- **Does:** "Finds duplicates in existing data, groups failures by cause, raises fix requests and proposes new checks. Runs the clean-up, sorts differences between non-SAP copies and SAP, and asks whether inactive records are still needed." [operating-model.md L66]
- **Rules served:**
  - R-04: one system of record; other systems "send changes back as requests".
  - R-09: critical fields, conventions, checks and thresholds; "Results are published monthly".
  - R-10: "fixed in the system of record, never only in a downstream copy or report"; recurring issues lead to a new check "which the attribute owner adds".
  - R-11: inactive records blocked; "The attribute owner approves the list as a whole".
  - [operating-model.md L66; rulebook.md L47, L57–59]
- **Control:** "The quality agent groups failures by cause and raises fix requests in the unified app; owners add checks for issues that recur." Evidence: "Issue log, profile changes". [controls.md › R-10, L23]
- **R-11 control:** "A monthly report lists inactive records, the owner approves the list, and the app blocks them." [controls.md › R-11, L24]
- **Bringing in a system:** "Checks start on the data platform, including a comparison with SAP that the quality agent sorts." [operating-model.md › The data landscape, step 3, L95–96]
- **Transition role:**
  - "likely duplicates flagged by the quality agent" (R-05).
  - "The quality agent groups failing records by cause and proposes new checks; the vendor fixes the records in SAP" (R-10).
  - "After the vendor leaves, the quality agent and the attribute owners handle what remains" of the clean-up.
  - The vendor must "Act on what the agents flag, such as likely duplicates, before processing a request (R-05)".
  - [delivery/transition.md L72, L77, L59–60, L97–98]
- **Reads (stated):** the data platform "holds the data agents read" [operating-model.md › The platform, L41].
- **Duplicate rules it must apply:** these come from the profiles. Examples:
  - customer: "two SAP records with the same partner function linked to the same CRM ID";
  - supplier: "same bank account";
  - material: "Same GTIN".
  - [starters/customer.md L18; supplier.md L18; material.md L18]
- **Restricted trade-secret data:** "Restricted data stays off the data platform unless the owner approves (R-21), so checks on it run where it's held." [starters/production.md L25]
- **Starting level:** 1. [operating-model.md L53]

**D. Governance coordinator**
- **Works for:** "GPDOs and the platform owner". [operating-model.md › Agents, L67]
- **Does:** "Prepares the owner review and the quarterly scorecard. Tracks decisions, exceptions and ownership gaps, and reminds owners. Drafts changes to profiles and documents, keeps the list of systems in the data landscape, and assembles audit evidence." [operating-model.md L67]
- **Rules served:**
  - R-02: exactly one owner per field.
  - R-20: exceptions "recorded with its rule, reason, approver and expiry, expires within [TBC: 90 days], and can be renewed once"; approved by the attribute owner, "never by a delegate or by whoever asked for them".
  - [operating-model.md L67; rulebook.md L40, L124]
- **Ownership gaps:** "the governance coordinator agent flags any field with no owner or more than one". [charter.md › Who owns what, L63–64] Control: "the governance coordinator flags gaps and overlaps". Evidence: "Ownership settings, gap report". [controls.md › R-02, L15]
- **Profile drafting:** "The governance coordinator agent can draft the profile from the starters and the data as it stands. The profile lives in the unified app as settings: owners approve changes there, and the app logs each one and keeps the history." [domains/template.md › intro, L5–8]
- **The data landscape:** "the GPDOs confirm the systems that hold their data, and the governance coordinator keeps the list." [operating-model.md › The data landscape, L73–75]
- **The owner review** is run "from the pack the governance coordinator prepares … covers scorecards, exceptions, ownership gaps, profile changes, agent performance and rule changes". [operating-model.md › Rhythm, L116–120]
- **Transition:** "Exceptions are recorded in a register [TBC: where], and the governance coordinator reminds owners before they expire." [delivery/transition.md › R-20, L84] In the target state, "The unified app records each exception and reminds its owner before it expires." [controls.md › R-20, L33]
- **Who approves it:** "Agents that don't touch master data, such as the governance coordinator, are approved by the GPDOs at the owner review, because the data team owns them." [operating-model.md › Agents, L57–59]
- **Charter:** "The governance coordinator agent prepares and chases; the data team: owns and supervises the agents…" [charter.md L93–98]
- **Starting level:** 1. [operating-model.md L53]

**E. Change reconciler**
- **Works for:** Internal controls. [operating-model.md › Agents, L68]
- **Does:** "Matches SAP changes to the approved requests or change records behind them where the daily report can't, and reports any without one." [operating-model.md L68]
- **Rule served:** R-08, "Every change to master data in a governed system can be traced to an approved request." [rulebook.md › R-08, L51]
- **Starting level:** 0 ("which only reports"). [operating-model.md L53–54]
- **Control:** "Only the unified app, or a domain's own governed process, can change master data in SAP. A daily report on the data platform shows any change without a request, for internal controls to review." Evidence: "Reconciliation report". [controls.md › R-08, L21]
- **Review of its work:** internal controls "Reviews emergency access, any change made without a request, and a sample of the change reconciler's matches (R-08, R-19)". [charter.md › Who decides what, L74]
- **Source of truth for changes:** SAP "change documents record every change (R-08)". [operating-model.md › The platform, L40]
- **Transition:**
  - "Each month, SAP changes are matched to requests in the current app, with the change reconciler agent's help. Internal controls reviews any change left unmatched, and a sample of the agent's matches." [delivery/transition.md › R-08, L75]
  - Sensitive changes other than bank details "are confirmed before the vendor enters them, and the monthly matching checks what was entered". [delivery/transition.md › R-13, L80]

**Summary table.** S = stated, with source above. I = inference.

| Agent | Works for | Start level | Reads | May write / produce | Agent-specific "never" |
| --- | --- | --- | --- | --- | --- |
| Request assistant | Requesters (S) | 1 (S) | Uploaded documents such as a bank letter (S); failed-check results (S); domain profile (S); requester's draft request and existing record values (I) | Proposed field values in the requester's draft, explanations, answers, "look wrong" flags (S for the functions; I that output stays a proposal the requester submits) | Never treat document text as instructions (R-22, S). Never change sensitive fields such as bank details (R-18, S); the change goes through R-13/R-15 confirmation (S). |
| Owner assistant | Attribute owners and delegates (S) | 1 (S) | Routed requests and check results, candidate duplicates, contact details on file, bank-account reuse, automatic-approval log (I, derived from what it prepares) | Case packs and evidence, chasers, monthly sample of automatic approvals (S) | Never decide duplicates, approve requests or confirm sensitive changes; these belong to owners or delegates (charter L80–84; R-18) (S). Never take call-back contacts from data changed with the request (R-15) (I). |
| Quality agent | Attribute owners (S) | 1 (S) | Data platform: stored data, check results, scorecards, SAP vs non-SAP comparisons (S: platform "holds the data agents read"); usage data for inactivity, CRM IDs for duplicates (I, from starter rules) | Fix requests in the unified app (S); proposed checks (S); questions about whether inactive records are still needed (S); clean-up (S, "Runs the clean-up"), but only at an approved level 2 or as an R-07 mass change (I) | Never fix only a downstream copy (R-10, S). Never block without the owner-approved list (R-11, S). Never delete; never change sensitive fields (R-18, S). Never exceed the mass-change size at level 2 (S). |
| Governance coordinator | GPDOs and the platform owner (S) | 1 (S) | Ownership settings, exception register, decisions, scorecards, control logs and evidence, starters, "the data as it stands" (S/I) | Owner-review pack, quarterly scorecard, reminders, *drafts* of profile and document changes, data-landscape list, audit-evidence assembly (S) | Never approve exceptions (R-20: owner only) or profile settings (controls preamble). Drafts only (S). |
| Change reconciler | Internal controls (S) | 0 (S) | SAP changes and change documents, unified-app request log, other governed processes' change records, data-platform daily report; in transition, the current app (S/I) | Reconciliation report and list of unmatched changes (S) | Report only; internal controls reviews unmatched changes and samples its matches (S). |

### Inferences
- *Inference:* The quality agent is the only agent described as making changes ("Runs the clean-up"). It is therefore the most likely first candidate for level 2. A clean-up of existing data can easily exceed the mass-change size (default [TBC: 50] records). Those runs then need the R-07 path: owner sign-off, a test and a rollback plan.
- *Inference:* The request assistant is the main **untrusted-input** surface. It ingests outside documents such as a bank letter (R-22). Those documents carry **Restricted payment data**, and they feed **sensitive** bank-detail changes that are a known payment-fraud vector (R-13 to R-15). This is the highest-risk combination in the framework.
- *Inference:* The change reconciler is owned by the data team. Yet it partly checks for data-team changes made outside the governed process (R-19), so there is an independence concern. The documents mitigate this through internal controls' sampling of its matches [charter.md L74]. A platform should prevent the agent owner from silently altering the reconciler's findings.
- *Inference:* The "never" lists differ by role. The owner assistant must stay strictly on the preparation side of decisions that delegates hold. The governance coordinator must stay on the drafting side of settings and document approvals.

### Gaps
- No agent has a documented input/output contract, tool list, prompt, or list of data sources beyond the one-line register entry.
- "Bank-detail call-backs" under the owner assistant is ambiguous: it could mean preparing call-backs or doing them. The controls catalogue assigns the call itself to "the owner or their delegate" [controls.md L28], so I read it as *prepare*.
- The approval route for the change reconciler is not stated. It does not touch master data, which suggests GPDO approval at the owner review, but it works for internal controls. *Inference only.*
- Whether the request assistant and owner assistant will run during the transition at all is unclear. The transition notes speak of "until [they] start" without a date. [delivery/transition.md L27–28]

---

## 3. Requirements on agents as a class

### Takeaway
R-18 is the core rule. Every agent must be in the register with a named owner, work within the autonomy level the attribute owner approved for their part, log every action, and change master data only through the unified app at level 2. The never-list is absolute and cannot be waived. R-21 and R-22 add model-environment and prompt-injection rules. R-19 adds testing before release. Segregation of duties means the data team owns the agents but never approves them.

### Cited Findings

**R-18 (verbatim).** "Every agent is recorded in the agent register with a named agent owner, works only within the autonomy level the attribute owner has approved for their part, and logs every action. At any level, agents may remind, chase and route, because that changes no data. They change master data only through the unified app, at level 2. They never approve requests or exceptions, confirm sensitive changes, change sensitive fields, delete records or grant access." Why: "Audit risk". [rulebook.md › Automation and agents › R-18, L103]

**Register, owner and deputy**
- The platform owner "names the agent owner and a deputy". [charter.md › data team's governance tasks, L96–98]
- The data team "owns and supervises the agents: keeps the register, checks their accuracy and handles what they escalate (R-18)". [charter.md L96–97]
- The agent owner for every agent is a named data-team person [TBC: name], with a named deputy [TBC: name]. [operating-model.md › Agents, L51–53]
- RACI:
  - "Build and run the app, the data platform and the agents": GPDO I, Data team R, Platform owner A, Ongoing.
  - "Supervise the agents": GPDO I, Attribute owner I, Data team R, Platform owner A, Ongoing.
  - [operating-model.md › Who does what, L28–29]
- The platform owner is "Accountable for the unified app, the data platform and the agents … Decides nothing about data content." [charter.md › Who decides what, L72]

**Autonomy levels (verbatim table)** [rulebook.md › Automation and agents, L106–112]

| Level | The agent may | Human role |
| --- | --- | --- |
| 0. Observe | Read, measure and report | Reads the reports |
| 1. Propose | Prepare a change or decision for a person to approve | The attribute owner or their delegate approves each one |
| 2. Act and notify | Make changes of a type the attribute owner has approved, never to sensitive fields, through the unified app, in runs below the mass-change size | The agent owner reviews the log and can reverse any change |

**Who approves each level and each move up**
- "Attribute owners approve how far an agent may act in their part, including each move up a level, in the domain profile." [operating-model.md › Agents, L55–57]
- "An agent moves up a level only with the owner's approval, on evidence from a sample of its work." [controls.md › R-18, L31]
- The attribute owner decides "what agents may do" for their part. [charter.md › Who decides what, L71]
- The template has a settings row "Agent changes approved at level 2 | R-18" for each part. [domains/template.md › Settings, L85]
- RACI row "Approve a part's settings: classification, checks, automatic approvals and what agents may do": Attribute owner A/R, GPDO I, Data team C. It is not marked \*, so it cannot be handed to delegates. [operating-model.md › Who does what, L13, L22]
- The charter confirms: "The owner stays accountable, and keeps settings, exceptions, mass changes and access." [charter.md › Delegates, L86–87]
- Level-1 proposals are approved by "The attribute owner or their delegate … each one". [rulebook.md L111]
- Level-2 activity is reviewed by "The agent owner", who "can reverse any change". [rulebook.md L112]
- "Agents that don't touch master data, such as the governance coordinator, are approved by the GPDOs at the owner review, because the data team owns them." [operating-model.md › Agents, L57–59]
- "Every setting in the unified app changes only with its owner's approval, which the app logs, and each domain profile keeps its version history." [controls.md › preamble, L9–10]

**Allowed at any level**
- "At any level, agents can remind, chase and route, because that changes no data." [operating-model.md › Agents, L54–55; rulebook.md › R-18, L103]

**Never list (charter, cannot be waived)**
- "Agents never approve requests or exceptions, confirm sensitive changes, change sensitive fields, delete records or grant access (R-18)." [charter.md › Controls we never switch off, L123–124]
- "No one approves their own request, exception or agent." [charter.md L132]

**Changing master data**
- Agents change master data "only through the unified app, at level 2". [rulebook.md › R-18, L103]
- Level 2 means "never to sensitive fields … in runs below the mass-change size". [rulebook.md L112]
- Mass-change size: "A change to more than [TBC: 50] records, or the number the domain profile sets, is a mass change. It needs the attribute owner's sign-off, a test and a rollback plan." [rulebook.md › R-07, L50]
- R-03: master data is changed "only through the governed process for its domain, starting with a complete request". [rulebook.md L46]
- R-08: every change "can be traced to an approved request". [rulebook.md L51]

**Outside content (R-22)**
- "Agents and the AI tools people use treat content from outside the organisation as data to check, never as instructions. Confidential and Restricted data goes to an AI model outside an environment the organisation controls only with the attribute owner's approval, and the data protection officer's for personal data. Trade secrets follow R-21." Why: "Trade secret risk, privacy risk". [rulebook.md › R-22, L104]
- Control: "Only approved AI tools are used, and the owner's approval, and the data protection officer's for personal data, is recorded before Confidential or Restricted data goes to an outside model." Evidence: "Approved-tools list, approvals". [controls.md › R-22, L35]

**Trade secrets and models (R-21)**
- "Trade secrets, such as formulas, recipes and process parameters, are Restricted wherever they're held, in SAP or not. They're copied, extracted or made available to people or agents only as the attribute owner approves, and never go to an AI model outside an environment the organisation controls, as the charter defines it." [rulebook.md › R-21, L81]
- Charter definition of a controlled environment: "its own systems, or a provider's service under a contract that stops the provider keeping or training on the data (R-21)". [charter.md › Controls we never switch off, L125–128]
- Control: "Trade secrets stay off the data platform and out of extracts unless the owner approves, and agents use AI models only in an environment the organisation controls." Evidence: "Access reviews, approvals, agent register". [controls.md › R-21, L34]

**AI model approval before start**
- "Before any agent starts, its AI model is approved under R-21 and R-22." [operating-model.md › Agents, L59–60]
- Control: "The agent register, a design review before each agent starts, including approval of its AI model (R-21, R-22), and a log of every action." Evidence: "Register, logs, sample results". [controls.md › R-18, L31]

**Design review, testing and release (R-18, R-19)**
- R-19: "Nobody who builds or changes the app or the agents changes live master data outside the governed process, except through emergency access that internal controls reviews. Changes to the app and the agents are tested before release." [rulebook.md › R-19, L118]
- Control: "Emergency access is logged and reviewed by internal controls, and changes to the app and agents go through change management." Evidence: "Review log, release records". [controls.md › R-19, L32]
- Charter: "The data team can't change master data outside the governed process, except through emergency access that internal controls reviews. Every change can be traced to an approved request (R-08, R-19)." [charter.md L129–131]

**Segregation of duties as it touches agents**
- No one approves their own agent. [charter.md L132]
- The data team owns, builds, runs and supervises the agents but "Decides nothing about data content". [charter.md L73, L96–98]
- Attribute owners approve agent autonomy for their part in the domain profile. [operating-model.md L55–57]
- GPDOs approve agents that don't touch master data "because the data team owns them". [operating-model.md L57–59]
- The platform owner names the agent owner and deputy. [charter.md L97–98]
- Internal controls samples the change reconciler's matches. [charter.md L74]
- "Nobody approves their own request." [rulebook.md › R-06, L49]
- "Nobody confirms a change they requested or entered." [rulebook.md › R-13, L71]
- Exceptions are approved "by the attribute owner, never by a delegate or by whoever asked for them". [rulebook.md › R-20, L124]
- **The R-12 analogue for third parties:** "It never sets rules, approves exceptions or confirms sensitive changes." [rulebook.md › R-12, L65]

**Design principle**
- "A check with a fixed answer belongs in the app, and a decision belongs to a person." [operating-model.md › Agents, L48–49]
- "Decisions happen in the app, not in meetings. Owners and their delegates decide there, prompted by the agents." [operating-model.md › Rhythm, L114–115]

### Inferences
- *Inference:* Autonomy is not one setting per agent. It is a matrix of **agent × part of a domain × change type**, because the attribute owner approves "for their part" and level 2 covers "changes of a type the attribute owner has approved". One agent can sit at level 2 for one change type in one business unit and at level 1 everywhere else.
- *Inference:* A level-2 change must still satisfy R-08 traceability ("traced to an approved request"). The only write path is the unified app, which "records the request behind every change". So an agent's level-2 change most plausibly enters the app as a request whose type the owner pre-approved for that agent. The app then checks it (R-05) and auto-approves it within the approved type (R-06). The documents do not spell out this mechanism.
- *Inference:* At level 2, review falls to the **agent owner**, who sits in the data team, not to the attribute owner. Reversibility of every level-2 change is therefore a hard platform requirement, because without it the level-2 safeguard does not exist.
- *Inference:* R-22 allows Confidential or Restricted data to go to an outside model with the owner's (and DPO's) approval. Controls R-21 says "agents use AI models only in an environment the organisation controls". Read together, agents must always run in a controlled environment, and the R-22 outside-model route is practically limited to people's AI tools. The rulebook text applies R-22 to "Agents and the AI tools people use", so this is a tension between documents, not a settled reading. The conservative design is controlled-environment-only for agents.
- *Inference:* The sensitive-field restriction applies at every level. Level 2 is "never to sensitive fields", and the never-list says agents "never … change sensitive fields". Unblocking a record "count[s] as" a sensitive change under R-13, so agents should never unblock.
- *Inference:* "Delete records" is prohibited. The material starter has a request type "block or flag for deletion" [starters/material.md L11]. Whether an agent may *flag for deletion* is undefined. The safe default is that it may not.

### Gaps
- Not stated:
  - who conducts the design review;
  - who approves the AI model;
  - what the review checks.
- No size or method is given for the "sample of its work" that supports a level-up.
- No demotion or suspension process is described (moving an agent down a level or switching it off), and no decommissioning.
- Not stated whether the deputy agent owner can approve or reverse level-2 changes.
- "Logs every action" is not defined: whether reads, model calls and drafts count is left open.

---

## 4. Measures and evidence the framework expects for agents

### Takeaway
Agents are measured on work handled, proposal acceptance and review time, with an explicit rubber-stamping warning sign. Evidence for R-18 is the register, the logs and sample results. Agents also produce evidence for other controls: the reconciliation report, issue log, gap report, exception register reminders and audit-evidence assembly.

### Cited Findings
- **Agent measures:** "Agents: work handled, proposal acceptance and review time. Almost no rejections combined with very short reviews usually means rubber-stamping." [operating-model.md › Measures, L138–139]
- **Baseline:** "Baseline each measure in the first month, then set targets." [operating-model.md › Measures, L125–126]
- **Owner review:** covers "agent performance" among other things; monthly at first, then quarterly. [operating-model.md › Rhythm, L116–120; charter.md L139]
- **Accuracy:** the data team "checks their accuracy". [charter.md L96–97]
- **Framework measures that agents feed or influence** [operating-model.md › Measures, L128–137]:
  - "Share of requests the app approves without a person"
  - "Decisions owners and delegates make each week, and how long requests wait for them"
  - "Time from request to use, and first-time-right by requesting team"
  - "Records passing their domain's checks"
  - "Duplicates, and differences between SAP and non-SAP copies"
  - "Downstream issues traced back to master data"
  - "SAP changes without an approved request"
- **Scorecards:** "A one-page scorecard goes to the executive team every quarter." [charter.md L140] The governance coordinator prepares it. [operating-model.md L67]
- **Evidence by control relevant to agents:**

| Control | Evidence | Agent link | Source |
| --- | --- | --- | --- |
| R-18 Agents | Register, logs, sample results | All agents | controls.md L31 |
| R-19 Data team | Review log, release records | Agent changes go through change management | controls.md L32 |
| R-21 Trade secrets | Access reviews, approvals, agent register | Agents' model environment and trade-secret access | controls.md L34 |
| R-22 AI tools and data | Approved-tools list, approvals | Agents' model and outside-model approvals | controls.md L35 |
| R-08 Traceability | Reconciliation report | Change reconciler; internal controls samples its matches | controls.md L21; charter.md L74 |
| R-10 Fix at source | Issue log, profile changes | Quality agent | controls.md L23 |
| R-02 Delegation | Ownership settings, gap report | Governance coordinator | controls.md L15 |
| R-20 Exceptions | Exception register (target); Register (transition) | Governance coordinator reminds | controls.md L33; transition.md L84 |
| R-06 Approval | Approval log, sample reviews | Owner assistant prepares the monthly sample | controls.md L19; operating-model.md L65 |
| R-15 Bank verification | Call-back record, flag report | Owner assistant prepares the call-back | controls.md L28 |

### Inferences
- *Inference:* "Review time" and "proposal acceptance" can only be computed if the platform records, for each level-1 proposal:
  - when it was presented;
  - who reviewed it;
  - when they decided;
  - the outcome (accept, reject or edit).
  Rubber-stamping detection needs per-reviewer distributions, not just per-agent averages.
- *Inference:* "Sample results" as level-up evidence implies a repeatable sampling and grading workflow per agent, per part and per change type, matching the granularity of the autonomy approval.

### Gaps
- No thresholds are given for acceptance rate, review time or the rubber-stamping signal. No error-rate target is given for agents, and no sample sizes.
- No log-retention period is stated for agent logs.

---

## 5. Identity and access implications, and where agents fit

### Takeaway
SAP master data is changed only by the unified app's service identity, or by a domain's own governed process. Agents therefore never write to SAP directly. Classified fields are visible only to roles the attribute owner approves. Restricted and personal data must be masked outside live systems, and extracts of Restricted data need owner approval. The documents never describe agent identities explicitly; their shape has to be inferred from these rules.

### Cited Findings
- "Only the unified app's service identity changes the master data the app handles; data with its own governed process, such as engineering changes, changes only through that process." [operating-model.md › The platform › SAP, L40]
- "Only the unified app, or a domain's own governed process, can change master data in SAP." [controls.md › R-08, L21]
- "The data team checks each quarter that confirmers, and the unified app, hold no buying or payment rights." [controls.md › R-14, L27]
- R-14: "Whoever confirms a change to [payment data], or can change them directly in SAP, can't create purchase orders, post invoices, run payments or release credit." [rulebook.md › R-14, L72]
- R-16: "Each domain profile lists the fields that are Confidential or Restricted … and marks those that hold personal data, payment data or trade secrets. Access to them is limited to roles that need it, as the attribute owner approves, and reviewed [TBC: twice a year] in each system the data landscape lists. A report or extract takes the highest classification of the data in it, and Restricted and personal data is masked outside live systems." [rulebook.md › R-16, L79]
- Control: "The unified app limits who sees classified fields to the roles the owner approves. The owner reviews who has access and approves extracts of Restricted data, and Restricted and personal data is masked outside live systems." Evidence: "Settings, access reviews, approvals". [controls.md › R-16, L29]
- R-21: trade secrets are "made available to people or agents only as the attribute owner approves". [rulebook.md L81]
- **Classification levels** [TBC: use the company's scheme if it has one] [rulebook.md L87–97]:
  - Public: "Approved for release outside the organisation".
  - Internal: "Everyday business data".
  - Confidential: "Harmful if disclosed; access on business need", for example "prices and margins … payment terms, credit limits, standard costs; all personal data".
  - Restricted: "Serious financial, legal, competitive or fraud harm if disclosed", for example "Bank details; tax IDs of individuals; formulas, recipes, process parameters and own product specifications".
- "Classification is about who can see data, and sensitive fields (R-13) are about which changes need confirming, so a supplier's address can be Internal and still sensitive." [rulebook.md L83–85]
- **Sensitive fields per starter:**
  - customer: "Bank details, credit limit and risk category, payment terms, tax IDs" [starters/customer.md L21];
  - supplier: "Bank details, alternative payee, payment terms, payment methods, tax IDs, name and address, and the phone numbers and email addresses used to verify changes (R-15)" [starters/supplier.md L21];
  - material: "Standard price, valuation class, price control" [starters/material.md L21];
  - finance: "Account type, reconciliation account setting, posting controls" [starters/finance-structures.md L21];
  - pricing: "Prices and discounts that change by more than [TBC]%" [starters/pricing.md L21];
  - production: "None by default", with the attribute owner or delegates confirming "unblocking records" [starters/production.md L22–23].
- **Undecided shared data:** In S/4HANA, business partner central data is shared, so its owner and sensitive fields are "a joint decision for the Commercial and Procurement GPDOs. The supplier starter treats name and address as sensitive and this one doesn't, so they need to choose." [starters/customer.md L12; starters/supplier.md L12]
- **Access reviews:** "Approve which roles can see classified data, review who has access, and approve extracts of Restricted data": Attribute owner A/R, Data team R; "Roles once; reviews [TBC: twice a year]; extracts as they arise". [operating-model.md › Who does what, L24]
- **Agents and access rights:** agents never "grant access". [rulebook.md › R-18, L103; charter.md L124]
- **Vendor analogue (transition):** "SAP access for named individuals only, reviewed quarterly." Vendor staff "lose the SAP rights to change it" as each request type moves, and "lose all SAP access the day their work ends". [delivery/transition.md L117, L143–144]

### Inferences
- *Inference:* Each agent needs its own non-human identity, distinct from the unified app's service identity. The reasons:
  - "Logs every action" and R-01 accountability require attribution.
  - The register is per agent.
  - Agents must never hold the approve, confirm or grant-access rights that the app itself exercises.

  The agent calls the app as a client. The app's service identity, not the agent, posts to SAP.
- *Inference:* Agent identities should hold no buying or payment rights. R-14 names confirmers, anyone who can change payment data directly in SAP, and the unified app. Agents act through the app, so the same separation should extend to them.
- *Inference:* Agent read access to Confidential and Restricted fields is a "role that needs it", which the attribute owner must approve. It falls within the periodic access review in every landscape system. For trade secrets, R-21 makes this explicit for agents.
- *Inference:* An agent's logs, memory, scratch files, caches and evaluation datasets are "outside live systems" (R-16). Restricted and personal data in them must be masked. This pulls against "logs every action" and against keeping evidence for internal controls. The platform needs field-level masking in logs that still preserves enough to reconstruct and reverse a change, for example record keys and hashed or tokenised values.
- *Inference:* An agent working for a person should be scoped to that person's entitlements and part (least privilege), so it cannot surface data its principal could not see. Example: the request assistant must not reveal Restricted bank data on other records. R-16's "limited to roles that need it" supports this, but agent scoping is never stated.
- *Inference:* Self-approval checks need to see through the agent. If an agent pre-fills a request for requester X, X remains the requester and cannot confirm it (R-13). The platform must record both the agent and its human principal on each action.

### Gaps
- No statement anywhere of how agents authenticate, what identity they use, whether they act on behalf of the user or as themselves, or how their credentials are stored or rotated.
- The data protection officer is named only in R-22. No privacy role is defined for agent design reviews.

---

## 6. Systems and integrations in play, and what each agent needs from them

### Takeaway
Three systems enforce the rules: the unified master data app (the front door and the only write path), SAP (the system of record, written only by the app's service identity or a domain's own governed process) and the data platform (checks, scorecards, comparisons, and "the data agents read"). Other systems are brought in one at a time; ownership, classification, trade-secret and AI-tool rules already apply to them. Agents mostly read from the data platform and the app, write only proposals, requests, reports and reminders, and never write directly to SAP or to non-SAP systems.

### Cited Findings
- **Unified master data app:** "The front door for SAP master data, built by the data team. It holds each domain's settings, checks every request on entry, approves the request types owners have approved, routes the rest to the part's owner or their delegates, holds sensitive changes until they're confirmed, and records the request behind every change. Later, it can take requests from non-SAP systems." [operating-model.md › The platform, L39]
- **SAP:** "The system of record. Only the unified app's service identity changes the master data the app handles … Its change documents record every change (R-08)." [operating-model.md L40]
- **Data platform:** "Runs the checks on stored data, builds the scorecards, compares non-SAP copies with SAP, finds changes without a request, and holds the data agents read." [operating-model.md L41]
- **Data landscape examples** [operating-model.md › The data landscape, L79–86]:
  - Recipe and formulation systems [TBC: names]: hold "Formulas, recipes, process parameters"; "Masters the recipes that aren't in SAP".
  - PLM: holds "Engineering data and specifications"; "Masters engineering attributes".
  - CRM: holds "Customer contacts and segmentation, and copies of SAP customers"; "Masters sales contacts; takes customers from SAP".
  - E-commerce or PIM: holds "Product content, and copies of SAP customers and materials"; "Masters marketing content; takes the rest from SAP".
  - Procurement platform or supplier portal: holds "Supplier onboarding data"; "Sends create requests to the unified app".
  - Spreadsheets and local files: hold "Price lists, recipes, local copies of master data"; "None; to be replaced by data from the systems of record".
- **Every landscape system** "is owned and protected now, under the five rules that apply everywhere (R-01, R-02, R-16, R-21 and R-22), and comes under the other rules when its GPDO proposes it." [operating-model.md L75–77]
- **Bringing a system in:**
  1. The GPDO proposes it, and the attribute owner adds its fields and checks to the profile.
  2. The GPDOs settle whether it masters fields or takes them from SAP and "sends changes back as requests (R-04)".
  3. "Checks start on the data platform, including a comparison with SAP that the quality agent sorts. Checks at entry follow, through the system's own workflow or the unified app."
  4. The other rules apply from an agreed date.
  - [operating-model.md L88–98]
- **Other governed processes:**
  - Production uses "The engineering change process [TBC: its name], which also governs formula and recipe changes". [starters/production.md L10]
  - Pricing uses "The pricing request process [TBC: its name]". [starters/pricing.md L10]
  - Both set "Request types approved automatically" to "Not applicable", because their own process approves changes. [starters/pricing.md L25; production.md L26]
- **Other systems named in starters:**
  - "[TBC: group reporting structure in a consolidation tool]" [starters/finance-structures.md L12]
  - "[TBC: any pricing or quoting tool outside SAP]" [starters/pricing.md L12]
  - "[TBC: PLM for engineering bills of materials]" [starters/production.md L12]
- **External checks the app runs:** these are app checks, not agent checks. Examples include "screened against sanctions lists", "VAT number valid (e.g. EU VIES)", "IBAN check digits and bank key valid". [starters/supplier.md L16; customer.md L16]
- **Transition systems:**
  - "the current app [TBC: its name, and who runs it]", where requests are raised and the vendor processes them in SAP [delivery/transition.md L5–7];
  - an exceptions "register [TBC: where]" [delivery/transition.md L84];
  - vendor reports [delivery/transition.md L73, L113].
- **Profiles as settings:** "The profile lives in the unified app as settings." [domains/template.md L7–8] In transition, "Where a control there relies on the unified app, ownership and settings are recorded in the domain profiles instead." [delivery/transition.md L65–67]

**Agent × system needs.** R = read, P = propose or draft (no data change), W = write a change, N = notify, remind or route. S = stated; I = inference.

| System | Request assistant | Owner assistant | Quality agent | Governance coordinator | Change reconciler |
| --- | --- | --- | --- | --- | --- |
| Unified app: profile settings | R: conventions, checks, answers "from the domain profile" (S) | R: routing, turnaround, sensitive fields (I) | R: checks and thresholds (I); P: new checks (S) | R: ownership settings (S); P: drafts of profile changes (S) | R: request types (I) |
| Unified app: requests | P: pre-fill the requester's draft (S); explain failed checks (S) | R: routed cases (I); P: case packs and evidence (S); N: chase overdue (S) | W: raise fix requests (S); W at level 2: clean-up changes, if approved (S rule; none approved yet) | R: decisions and exceptions (S, "tracks"); N: remind owners (S) | R: request log to match against (S) |
| Unified app: approval and confirmation functions | Never (S) | Never (S) | Never (S) | Never (S) | Never (S) |
| SAP | R: existing values to flag "look wrong" (I) | R: duplicate candidates, contacts on file, bank-account reuse (I) | R, mostly via the data platform (I) | – | R: change documents (S, implied by "Matches SAP changes") |
| Data platform | R (I) | R (I) | R: stored data, check results, comparisons (S, "holds the data agents read") | R: scorecards (S) | R: the daily changes-without-request report (S, "where the daily report can't") |
| CRM, PIM/e-commerce, PLM | – | – | R: comparisons with SAP, sorted by this agent (S); CRM IDs for the customer duplicate rule (I) | R: landscape list it "keeps" (S) | – |
| Procurement platform / supplier portal | R: incoming create requests are outside content (I) | R (I) | – | R: landscape list (S) | – |
| Recipe and formulation systems | – | – | R in place only, with owner approval; trade secrets stay off the data platform (S rule, I application) | R: landscape list (S) | – |
| Engineering change and pricing processes | – | – | – | – | R: "change records" behind SAP changes (S) |
| Current app (transition) | – | – | flags for the vendor (S) | R: exception register (S) | R: requests to match monthly (S) |

### Inferences
- *Inference:* The unified app is the agents' main integration point. It needs APIs for:
  - reading settings;
  - creating and annotating requests;
  - attaching case evidence;
  - posting proposals that owners and delegates decide "in the app" (operating-model.md L114–115);
  - notifications and reminders.

  It must withhold approve, confirm, exception-approval and access-grant functions from agent identities.
- *Inference:* SAP is read-only for agents. The change reconciler needs SAP change-document data, most likely delivered through the data platform.
- *Inference:* Data under its own governed process (engineering change, pricing) cannot be changed by an agent through the unified app at level 2, because it "changes only through that process" (operating-model.md L40). Every starter has "None yet" for level 2 anyway.
- *Inference:* Non-SAP systems are read sources and comparison targets. Changes flow back as requests (R-04), never as direct agent writes.

### Gaps
- No interface specifications, APIs or event models exist for the unified app, the data platform or the current app.
- The names of the recipe systems, the current app, the pricing process, the engineering-change process and the consolidation tool are all [TBC].

---

## 7. What the transition period requires of agents before the unified app exists

### Takeaway
Until each request type moves to the unified app (customer and supplier in December 2026, the rest one at a time, vendor gone by Q2 2027), agents may "coordinate, check and propose, but never create or change master data". The quality agent flags duplicates and root causes for the vendor. The change reconciler helps with monthly matching of SAP changes to current-app requests. The governance coordinator reminds owners about expiring exceptions. Ownership and settings are read from the domain profiles rather than from the app.

### Cited Findings
- **Timeline:** "Customer and supplier requests move first, in December 2026, once their profiles are approved in early November. The rest, including the material master, follow one request type at a time, and the vendor leaves by Q2 2027." [delivery/transition.md L11–13]
- **Gate:** "Nothing moves on a date alone. If a profile isn't approved, or the app fails its tests, the request type stays with the vendor until it's ready." [delivery/transition.md L45–47]
- **Agents in transition:** "**Agents** coordinate, check and propose, but never create or change master data (R-18). Until the request assistant and the owner assistant start, attribute owners and their delegates prepare their own cases." [delivery/transition.md › What's different, L26–28]
- **Requests:** raised in the current app, and "the vendor makes the changes in SAP. For the request types it handles, only the vendor's staff hold SAP change rights." [delivery/transition.md L18–21]
- **R-05:** "The vendor's checklist and SAP's mandatory fields, with likely duplicates flagged by the quality agent." [delivery/transition.md L72]
- **Vendor duty:** "Act on what the agents flag, such as likely duplicates, before processing a request (R-05)." [delivery/transition.md L97–98]
- **R-08:** "Each month, SAP changes are matched to requests in the current app, with the change reconciler agent's help. Internal controls reviews any change left unmatched, and a sample of the agent's matches." [delivery/transition.md L75]
- **R-10:** "The quality agent groups failing records by cause and proposes new checks; the vendor fixes the records in SAP." [delivery/transition.md L77]
- **R-13:** "Other sensitive changes are confirmed before the vendor enters them, and the monthly matching checks what was entered." [delivery/transition.md L80]
- **R-20:** "Exceptions are recorded in a register [TBC: where], and the governance coordinator reminds owners before they expire." [delivery/transition.md L84]
- **Settings source:** "Where a control there relies on the unified app, ownership and settings are recorded in the domain profiles instead." [delivery/transition.md L65–67]
- **Clean-up:**
  - "The vendor's remaining capacity goes into this clean-up before it leaves, as mass changes the attribute owner signs off (R-07)."
  - "After the vendor leaves, the quality agent and the attribute owners handle what remains."
  - [delivery/transition.md L57–60]
- **Agent instructions:** "Before each request type moves, write down the working rules and checks the team uses for it, so they can become the unified app's checks and agent instructions." [delivery/transition.md › Exit, L138–140]
- **Data protection (vendor):**
  - "Personal data is handled under a data processing agreement. Any work done outside [TBC: country or region] is agreed in advance."
  - Trade secrets are "seen only by named individuals under a confidentiality agreement, and never from outside [TBC: country or region] unless agreed in advance (R-21)."
  - [delivery/transition.md L121–125]
- **The step-2 build list** per request type: "the checks, routing to the attribute owner and their delegates, holding sensitive changes until they're confirmed, recording the request behind every change, and posting to SAP". [delivery/transition.md L37–40]

### Inferences
- *Inference:* The platform needs a **per-request-type mode switch**. For request types still with the vendor, master-data writes are globally disabled, so level 2 is impossible whatever the profile says. Writes become possible only after the request type moves and the attribute owner approves level-2 change types.
- *Inference:* During transition, agents must read settings and ownership from domain-profile *documents* or another store, not from the app, and must integrate with the current app [TBC]. The agent platform therefore cannot assume the unified app is the only source of settings in 2026–27.
- *Inference:* The change reconciler's transition role extends beyond matching. The monthly matching "checks what was entered" for sensitive changes confirmed before vendor entry, which means comparing entered values against confirmed values.
- *Inference:* Agent instructions are to be derived from vendor working rules, so they are a governed, versioned artefact per request type. Changes to them count as "changes to … the agents" that are tested before release (R-19).
- *Inference:* The vendor's data-residency clauses for personal data and trade secrets ([TBC: country or region]) may need to apply to where agent models run and where agent data is stored. The documents do not say so.

### Gaps
- The name of the current app and who runs it are [TBC]. The location of the exceptions register is [TBC]. The fallback if a request type isn't ready by the vendor's exit is [TBC].
- No date is given for when the request and owner assistants start.

---

## 8. Open [TBC] items that affect the agent platform

### Takeaway
The open items that matter most for the agent platform are:
- the names of the agent owner and deputy;
- the approved AI tools list;
- the classification scheme;
- the mass-change size (which caps level-2 run size);
- the access-review cadence;
- system names for integrations: the current app, recipe systems, the pricing and engineering-change processes;
- the region constraints that may govern model hosting.

### Cited Findings
- **Agent owner [TBC: name] and deputy [TBC: name]:** this is the agent register's accountable person. [operating-model.md › Agents, L52]
- **Platform owner** "The Head of Data, AI & Development [TBC: name]": names the agent owner and deputy, and is accountable for the agents. [charter.md L72]
- **Internal controls team [TBC: name]:** samples the change reconciler's matches. [charter.md L74]
- **Role holders:** "Held by [TBC]". [charter.md L68] Charter "Effective from: [TBC]", when R-18 and the other rules start to apply. [charter.md L3]
- **Approved AI tools:** an open decision "as the setup is built: … the approved AI tools". [README.md › Open decisions, L71–72] The approved-tools list is R-22 evidence [controls.md L35]; no list exists in the repository.
- **Classification scheme** "[TBC: use the company's scheme if it has one]": sets the labels the platform must enforce. [rulebook.md L87]
- **Mass-change size** "[TBC: 50]" records: caps level-2 runs. [rulebook.md › R-07, L50] Production may set a larger size "[TBC: larger than the rulebook's, for component swaps across many bills of materials]". [starters/production.md L21]
- **Access-review cadence** "[TBC: twice a year]": applies to roles, including those agents may hold. [rulebook.md › R-16, L79; operating-model.md L24]
- **Exception expiry** "[TBC: 90 days]": drives the governance coordinator's reminders. [rulebook.md › R-20, L124]
- **Pricing sensitivity threshold:** "Prices and discounts that change by more than [TBC]%" — this is a conditional sensitive-field rule a policy engine must evaluate. [starters/pricing.md L21] Also "Price within [TBC]% of the previous price". [starters/pricing.md L16]
- **Recipe and formulation systems [TBC: names]:** trade-secret systems where checks run in place. [operating-model.md L81]
- **Current app** "[TBC: its name, and who runs it]"; exceptions "register [TBC: where]"; programme plan "[TBC: where it's kept]". [delivery/transition.md L6, L84, L14]
- **Governed processes:** pricing "[TBC: its name]" and engineering change "[TBC: its name]"; "[TBC: any pricing or quoting tool outside SAP]"; "[TBC: PLM for engineering bills of materials]"; "[TBC: group reporting structure in a consolidation tool]". [starters/pricing.md L10, L12; production.md L10, L12; finance-structures.md L12]
- **Region constraints:** vendor work outside "[TBC: country or region]" for personal data and trade secrets. [delivery/transition.md L122, L125]
- **Scope of classification:** material "Restricted: specifications that reveal a product's formulation (trade secrets) [TBC]"; finance "person responsible … (personal data) [TBC]"; pricing "Restricted: none by default [TBC]"; production "Confidential: standard values and work centre costs [TBC]". [starters/material.md L24; finance-structures.md L24; pricing.md L24; production.md L25]
- **Credit management** "[TBC]" as attribute owner of credit limit and risk category: affects routing. [starters/customer.md L22]
- **One-time accounts and payee in document** "[TBC: named cases, below a set amount]": these are sensitive-change triggers. [starters/customer.md L23; supplier.md L23]
- **Personal data lifecycle:** "SAP blocks personal data … deletes it … [TBC: how]". [controls.md › R-17, L30]
- **Training format** [TBC] [delivery/transition.md L41]; **fallback** past vendor exit [TBC] [delivery/transition.md L46–47, L145–146].
- **Not marked [TBC], but missing:** who conducts the design review, and who approves the AI model under R-21 and R-22. [controls.md L31; operating-model.md L59–60]

### Inferences
- *Inference:* None of these items blocks the platform's architecture. However, the policy engine must take the mass-change size, sensitive-field lists (including conditional thresholds), classification labels and review cadence as **configuration read from the domain profiles**, not hard-coded values. The documents expect them to change.

### Gaps
- The approved AI tools list and the approver of agent models are the two gaps most likely to block go-live of any agent.

---

## 9. Capability requirements for the agent OS, traced to source

### Takeaway
The framework reduces to 80 platform capabilities across 11 groups. The non-negotiable core:
- a register with a named owner and deputy, and a pre-start gate covering design review and model approval;
- enforced autonomy levels per agent × part × change type;
- a deterministic deny-list for approve, confirm, sensitive-field change, delete and grant;
- writes only through the unified app, below the mass-change size;
- outside content treated as data, never instructions;
- models only in an organisation-controlled environment;
- a log of every action, enough to review and reverse level-2 changes;
- sample-based evidence for level-ups, and acceptance and review-time measures with rubber-stamping detection.

### Cited Findings
Each requirement is tagged **[Stated]** when the documents require it directly, or **[Inference]** when it is my derivation; the reason is given.

#### A. Identity and access
- **AOS-01** Each agent runs under its own non-human identity, linked to its register entry, so every action is attributable to that agent and, through the register, to its named agent owner. — [rulebook.md › R-18 L103 "recorded in the agent register with a named agent owner … logs every action"; R-01 L39 "however it's changed: by … agents"] — **[Inference]**: attribution is required; a distinct identity is the implied means.
- **AOS-02** Agent identities have no write access to SAP master data. The only SAP write path is the unified app's service identity, or a domain's own governed process. — [rulebook.md › R-18 L103; operating-model.md › The platform › SAP L40; controls.md › R-08 L21] — **[Stated]**
- **AOS-03** Agent identities never hold rights to approve requests or exceptions, confirm sensitive changes, or grant access, in the unified app or any landscape system. — [rulebook.md › R-18 L103; charter.md › Controls we never switch off L123–124] — **[Stated]**
- **AOS-04** Agent identities hold no rights to create purchase orders, post invoices, run payments or release credit. — [rulebook.md › R-14 L72; controls.md › R-14 L27] — **[Inference]**: R-14 names confirmers, direct SAP changers and the unified app; agents act through the app.
- **AOS-05** Agent access to Confidential and Restricted fields comes only through roles the attribute owner approves for that part, and is included in the periodic access review ([TBC: twice a year]) in each landscape system. — [rulebook.md › R-16 L79; operating-model.md › Who does what L24; controls.md › R-16 L29] — **[Stated]** for roles; **[Inference]** that agent identities are such roles.
- **AOS-06** Trade-secret data (formulas, recipes, process parameters, formulation-revealing specifications) is made available to an agent only with explicit attribute-owner approval for that agent. — [rulebook.md › R-21 L81 "made available to people or agents only as the attribute owner approves"; controls.md › R-21 L34] — **[Stated]**
- **AOS-07** Every agent action records both the agent and the human principal it is working for, so that "Nobody approves their own request" and "Nobody confirms a change they requested or entered" still hold when an agent prepared or pre-filled the work. — [rulebook.md › R-06 L49, R-13 L71; charter.md › Delegates L87–88] — **[Inference]**
- **AOS-08** An agent's data scope is limited to its principal's part and entitlements (least privilege). For example, the owner assistant sees cases routed to that owner's part; the request assistant sees no more than the requester can. — [rulebook.md › R-16 L79 "limited to roles that need it"] — **[Inference]**
- **AOS-09** Builders of agents do not, through build or run tooling, gain a path to change live master data outside the governed process. Emergency access is separate, logged and reviewed by internal controls. — [rulebook.md › R-19 L118; controls.md › R-19 L32; charter.md L129–131] — **[Stated]** rule; the separation mechanism is **[Inference]**.

#### B. Registry and lifecycle
- **AOS-10** An agent register lists every agent with:
  - name;
  - "Works for";
  - "Does";
  - rules served;
  - a named agent owner and a named deputy.

  Owner and deputy are named by the platform owner. — [rulebook.md › R-18 L103; operating-model.md › Agents L51–53, L62–68; charter.md L96–98] — **[Stated]**
- **AOS-11** The register also records, per agent:
  - the approved autonomy level per part and per change type, with approver and date;
  - the approved AI model and its hosting environment;
  - trade-secret access approvals;
  - design-review outcome;
  - status.

  It serves as evidence for R-18 and R-21. — [controls.md › R-18 L31 evidence "Register"; controls.md › R-21 L34 evidence "agent register"; domains/template.md L85] — **[Inference]**: the field list is derived from what the register must evidence.
- **AOS-12** Changes to the register follow the operating model's approval. The register currently *is* a section of the operating model, approved by the platform owner. A platform registry must stay consistent with it, or become its system of record. — [operating-model.md › Agents L51 "This is the agent register (R-18)"; README.md › Documents L58] — **[Inference]**
- **AOS-13** A pre-start gate blocks an agent from running until:
  1. a design review is complete;
  2. its AI model is approved under R-21 and R-22;
  3. it has business approval — attribute owners for agents acting in their part, or the GPDOs at the owner review for agents that don't touch master data.

  — [controls.md › R-18 L31; operating-model.md › Agents L55–60] — **[Stated]**
- **AOS-14** The data team, which owns and builds the agents, cannot approve them. The approval workflow enforces "No one approves their own … agent". — [charter.md L132; operating-model.md L57–59] — **[Stated]**
- **AOS-15** Every change to an agent is tested before release and goes through change management, producing release records. This covers instructions, prompts, tools, model or model version, and policies. — [rulebook.md › R-19 L118; controls.md › R-19 L32] — **[Stated]**; the list of what counts as a change is **[Inference]**.
- **AOS-16** Agent instructions are versioned per request type and can be seeded from the vendor's written working rules and checks. — [delivery/transition.md › Exit L138–140] — **[Stated]** source; versioning **[Inference]**.
- **AOS-17** New agents default to level 1; a pure reporting agent such as the change reconciler defaults to level 0. — [operating-model.md › Agents L53–54] — **[Stated]**
- **AOS-18** An escalation channel from each agent to the data team, which "handles what they escalate". — [charter.md L96–97] — **[Stated]**
- **AOS-19** The platform supports demoting, suspending and retiring an agent, with the same approval and logging. — no source; **[Inference]**, because the documents describe level-ups only. Listed as a gap.

#### C. Autonomy and human approval
- **AOS-20** Autonomy is enforced per agent × part of a domain × change type, read from the domain-profile setting "Agent changes approved at level 2". That setting is currently "None yet" in all six starters. — [rulebook.md › R-18 L103, autonomy table L112; domains/template.md L85; starters/*.md] — **[Stated]**
- **AOS-21** Level semantics are enforced:
  - 0: "Read, measure and report".
  - 1: "Prepare a change or decision for a person to approve", with "The attribute owner or their delegate approves each one".
  - 2: "Make changes of a type the attribute owner has approved, never to sensitive fields, through the unified app, in runs below the mass-change size", with "The agent owner reviews the log and can reverse any change".

  — [rulebook.md › autonomy table L106–112] — **[Stated]**
- **AOS-22** At level 1, approval is per item ("each one"). Every proposal gets an individual human decision, with the approver's identity and time recorded. — [rulebook.md L111] — **[Stated]** per item; **[Inference]** that bulk approval which hides individual items would breach it.
- **AOS-23** At level 2, the agent owner has a review queue over the agent's change log and a one-step reversal for any change. — [rulebook.md L112] — **[Stated]**; mechanism **[Inference]**.
- **AOS-24** A level-up workflow requires the attribute owner's own approval (not a delegate's), based on sample-of-work evidence attached to the request, and is recorded as a domain-profile setting with version history. — [controls.md › R-18 L31; operating-model.md L55–57; charter.md L86–87; operating-model.md L13, L22 (row not marked \*); controls.md preamble L9–10] — **[Stated]**
- **AOS-25** Agents that don't touch master data are approved by the GPDOs at the owner review. — [operating-model.md L57–59] — **[Stated]**
- **AOS-26** Remind, chase and route are allowed at every level, including level 0, and are classed as "changes no data". — [rulebook.md › R-18 L103; operating-model.md L54–55] — **[Stated]**
- **AOS-27** Human decisions are taken in the unified app, where agents prompt owners and delegates. Agent proposals and evidence must surface in the app's decision flow. — [operating-model.md › Rhythm L114–115] — **[Stated]** principle; integration **[Inference]**.
- **AOS-28** Agents never make decisions or hold accountability. Fixed-answer checks are implemented in the app, not in agents. — [operating-model.md › Agents L48–49; › Who does what L14–16] — **[Stated]**
- **AOS-29** Hand-off from the request assistant to people follows the chain: request assistant, then attribute owner or delegate, then GPDO. Routing goes to an available delegate; at least two are named so someone is always available. — [charter.md › Escalation L136–138; › Delegates L76–78; domains/template.md L34–36] — **[Stated]**

#### D. Policy enforcement on tool calls
- **AOS-30** A deterministic, non-waivable deny-list sits outside the model and applies at every level and for any instruction: approve request; approve exception; confirm sensitive change; change a sensitive field; delete a record; grant access. — [rulebook.md › R-18 L103; charter.md › Controls we never switch off L117, L123–124] — **[Stated]** list; placement outside the model **[Inference]**, from "can't be waived".
- **AOS-31** Each write is checked field by field against the **live** sensitive-field list in the domain profile. The check covers:
  - payment data, which is always sensitive;
  - conditional sensitivity, such as pricing "Prices and discounts that change by more than [TBC]%";
  - the special cases R-13 counts as sensitive: unblocking a record, and bank details on one-time accounts or entered as a payee in a document.

  — [rulebook.md › R-13 L71, R-14 L72; starters/pricing.md L21; domains/template.md L79–81] — **[Stated]**
- **AOS-32** Read and write policies are separate: classification governs who can see a field, and sensitivity governs which changes need confirming. — [rulebook.md L83–85 "a supplier's address can be Internal and still sensitive"] — **[Stated]**
- **AOS-33** Where the sensitive-field status of shared business-partner central data is unresolved (the customer and supplier starters disagree on name and address), the guard treats it as sensitive until both GPDOs decide. — [starters/customer.md L12; supplier.md L12] — **[Stated]** conflict; default **[Inference]**.
- **AOS-34** A run-size limit applies to level-2 runs: the record count must stay below the mass-change size (rulebook default [TBC: 50], or the profile's own value). Anything larger goes to the R-07 mass-change path (owner sign-off, test, rollback plan). Splitting one logical change into sub-threshold runs is detected and blocked. — [rulebook.md › R-07 L50, autonomy table L112; controls.md › R-07 L20; starters/production.md L21] — **[Stated]** limit; anti-splitting **[Inference]**.
- **AOS-35** A change-type allowlist per agent per part, sourced from the profile. Anything not listed is a level-1 proposal at most. — [rulebook.md L112; domains/template.md L85] — **[Stated]**
- **AOS-36** Master-data writes are exposed only as unified-app API calls. No agent tool writes master data directly to SAP, the data platform or non-SAP systems. Data under its own governed process (engineering change, pricing) is not changeable by agents through the unified app. — [rulebook.md › R-03 L46, R-18 L103; operating-model.md L40; starters/production.md L10; pricing.md L10] — **[Stated]** for the unified-app-only rule; **[Inference]** for the other-process exclusion.
- **AOS-37** A transition-mode switch per request type: while a request type is still with the vendor or current app, agents cannot create or change master data at all. — [delivery/transition.md L26–28] — **[Stated]**
- **AOS-38** Fix requests target the system of record, never only a downstream copy or report. — [rulebook.md › R-10 L58, R-04 L47] — **[Stated]**
- **AOS-39** Inactive records are blocked only from an attribute-owner-approved list, and the app does the blocking, not the agent. — [rulebook.md › R-11 L59; controls.md › R-11 L24] — **[Stated]**
- **AOS-40** Egress control on tool calls: trade secrets are not copied, extracted or sent to any destination (data platform, extract, model) without owner approval, and never to a model outside a controlled environment. — [rulebook.md › R-21 L81; controls.md › R-21 L34] — **[Stated]**

#### E. Data protection and classification
- **AOS-41** Per-field classification labels (Public, Internal, Confidential, Restricted, or the company scheme [TBC]) with personal-data, payment-data and trade-secret markers, read from the domain profile and available to the policy engine. — [rulebook.md › R-16 L79, L87–97] — **[Stated]**
- **AOS-42** Every agent output that is a report or extract takes the highest classification of the data in it. Examples: owner-review pack, scorecard, case pack, reconciliation report, evidence pack. — [rulebook.md › R-16 L79] — **[Stated]** rule; application to agent outputs **[Inference]**.
- **AOS-43** Restricted and personal data is masked in everything "outside live systems": agent logs, traces, memory, caches, scratch files, evaluation datasets and reports. Masking must still leave logs usable for review and reversal, for example by keeping record keys. — [rulebook.md › R-16 L79; controls.md › R-16 L29] — **[Stated]** rule; scope and tension with AOS-54 **[Inference]**.
- **AOS-44** An agent copying Restricted data into its own store (memory, file system, vector index) is treated as an extract or copy needing the attribute owner's approval. — [operating-model.md L24 "approve extracts of Restricted data"; rulebook.md › R-21 L81 "copied, extracted or made available"] — **[Inference]**
- **AOS-45** Trade secrets stay off the data platform unless the owner approves, so agent checks on them run where the data is held (recipe systems, SAP). — [controls.md › R-21 L34; starters/production.md L25] — **[Stated]**
- **AOS-46** Personal data:
  - DPO approval is recorded before any outside-model use (R-22).
  - Agent-held copies follow purpose and retention limits (R-17).
  - Agents never delete master-data records (R-18); in the target, SAP does the blocking and deletion.

  — [rulebook.md › R-17 L80, R-18 L103, R-22 L104; controls.md › R-17 L30] — **[Stated]** for DPO and agents not deleting; agent-copy retention **[Inference]**.
- **AOS-47** Data residency for agent hosting, model inference and storage may need to match the region limits set for the vendor's personal-data and trade-secret work ([TBC: country or region]). — [delivery/transition.md L121–125] — **[Inference]**

#### F. Prompt-injection defence
- **AOS-48** All content from outside the organisation is treated as data to check, never as instructions. This applies to agents and to people's AI tools. — [rulebook.md › R-22 L104] — **[Stated]**
- **AOS-49** Known outside-content entry points are tagged as untrusted:
  - documents such as a bank letter used for pre-fill;
  - supplier onboarding data from the procurement platform or supplier portal, arriving as create requests;
  - inference: supplier and customer emails or attachments, and customer content in CRM or e-commerce.

  — [operating-model.md L64, L85; starters/supplier.md L12] — **[Stated]** for the first two; others **[Inference]**.
- **AOS-50** Untrusted content can never change an agent's tools, autonomy, routing targets, recipients or policy. The deterministic deny-list and sensitive-field guard (AOS-30, AOS-31) act as the backstop if injection succeeds. — **[Inference]** from R-22 together with R-18.
- **AOS-51** For bank-detail changes, verification contacts come only from details "already on file" that "weren't changed along with it". An agent must never take call-back contacts from the incoming document or request. — [rulebook.md › R-15 L73; controls.md › R-15 L28; starters/supplier.md L21 (verification phone and email are sensitive)] — **[Stated]** rule; agent application **[Inference]**.
- **AOS-52** Anomaly flagging is a required behaviour: "flags values that pass the checks but look wrong". The app separately flags bank accounts already used by another supplier or customer. — [operating-model.md L64; rulebook.md › R-15 L73] — **[Stated]**

#### G. Audit and evidence
- **AOS-53** Every agent action is logged. Evidence for R-18 is "Register, logs, sample results". — [rulebook.md › R-18 L103; controls.md › R-18 L31] — **[Stated]**; that this includes tool calls, model calls, reads, proposals, reminders, routes, changes and escalations is **[Inference]**.
- **AOS-54** Logs are detailed enough for the agent owner to review every level-2 change and reverse any of them. — [rulebook.md L112] — **[Stated]**
- **AOS-55** End-to-end traceability: SAP change document → unified-app request → agent identity → approving setting or approver. An agent's level-2 changes enter the app as requests. — [rulebook.md › R-08 L51; operating-model.md L39–40] — **[Stated]** R-08; agent-change-as-request **[Inference]**.
- **AOS-56** The following approvals are recorded as evidence:
  - level-up approvals, with their sample evidence;
  - AI-model approval;
  - the approved-tools list;
  - owner and DPO approvals, recorded *before* Confidential or Restricted data goes to an outside model;
  - trade-secret access approvals.

  — [controls.md › R-18 L31, R-21 L34, R-22 L35] — **[Stated]**
- **AOS-57** Evidence is retrievable for the governance coordinator's audit-evidence assembly and for internal controls' sampling of the change reconciler's matches. — [operating-model.md L67; charter.md L74; delivery/transition.md L75] — **[Stated]**
- **AOS-58** Settings changes, including agent level-2 approvals, are logged by the unified app with owner approval and version history. — [controls.md preamble L9–10; domains/template.md L7–8] — **[Stated]**
- **AOS-59** Release records for every agent change. — [controls.md › R-19 L32] — **[Stated]**
- **AOS-60** Agent logs are tamper-evident and cannot be altered by the agent owner or the data team. They serve audit-risk rules (R-18, R-19), and internal controls reviews data-team activity. — **[Inference]**

#### H. Evaluation and level-up evidence
- **AOS-61** A sampling-and-grading workflow over each agent's work, per part and change type, produces "sample results" that support a level-up. — [controls.md › R-18 L31] — **[Stated]** sample; granularity **[Inference]**, matching AOS-20.
- **AOS-62** The data team runs accuracy checks on agents. — [charter.md L96–97] — **[Stated]**
- **AOS-63** Agent changes are tested before release, with a regression suite per agent. — [rulebook.md › R-19 L118] — **[Stated]** test-before-release; suite **[Inference]**.
- **AOS-64** Internal controls can review a sample of the change reconciler's matches against ground truth. — [charter.md L74; delivery/transition.md L75] — **[Stated]**
- **AOS-65** Evaluation datasets comply with masking (R-16) and trade-secret (R-21) rules. — **[Inference]**

#### I. Observability and measures
- **AOS-66** For each agent the platform measures:
  - work handled;
  - proposal acceptance;
  - review time.

  A rubber-stamping signal is computed ("Almost no rejections combined with very short reviews"), ideally per reviewer. — [operating-model.md › Measures L138–139] — **[Stated]**; per-reviewer **[Inference]**.
- **AOS-67** Each measure is baselined in the first month, then targets are set. — [operating-model.md L125–126] — **[Stated]**
- **AOS-68** Agent performance is reported into the owner-review pack (monthly, then quarterly) and the quarterly one-page executive scorecard. — [operating-model.md › Rhythm L116–121; charter.md L139–140] — **[Stated]**
- **AOS-69** Overdue tracking against profile turnaround times drives chasing. Starters set 2 business days standard and 4 business hours urgent. — [operating-model.md L65; rulebook.md › R-06 L49; starters/customer.md L13] — **[Stated]**
- **AOS-70** Agent escalations are tracked to resolution by the data team. — [charter.md L96–97] — **[Stated]**
- **AOS-71** Agent activity feeds the framework's other measures:
  - decisions per week and wait times;
  - time to use;
  - first-time-right by team;
  - duplicates;
  - differences between SAP and non-SAP copies;
  - SAP changes without an approved request.

  — [operating-model.md › Measures L128–137] — **[Stated]** measures; agent contribution **[Inference]**.

#### J. Integration with the unified app and SAP
- **AOS-72** Unified-app connector, read side: domain-profile settings (ownership, classification, sensitive fields, conventions, checks, auto-approval types, agent level-2 change types, turnaround, mass-change size), requests, check results, routing and the approval log. — [operating-model.md L39; domains/template.md L7–8, L61–85] — **[Stated]** that these live in the app; connector **[Inference]**.
- **AOS-73** Unified-app connector, write side, restricted to:
  - pre-filling draft requests for a requester;
  - raising fix requests;
  - attaching case evidence;
  - posting proposals for owner or delegate decision;
  - notifications and reminders;
  - level-2 changes as requests of approved types.

  The approve, confirm, exception and access functions are never exposed. — [operating-model.md L64–68; controls.md › R-10 L23; rulebook.md › R-18 L103] — **[Stated]** functions; API shape **[Inference]**.
- **AOS-74** SAP is read-only for agents; the change reconciler needs SAP change-document data. — [operating-model.md L40, L68] — **[Stated]**
- **AOS-75** The data platform is the primary read source ("holds the data agents read"): stored data, check results, scorecards, SAP vs non-SAP comparisons, and the daily changes-without-request report. — [operating-model.md L41; controls.md › R-08 L21] — **[Stated]**
- **AOS-76** Non-SAP connectors (CRM, PLM, PIM or e-commerce, procurement platform or supplier portal, recipe systems, spreadsheets) are added one system at a time as each is brought in. They are read-only for agents, and changes flow back as requests (R-04). The governance coordinator maintains the landscape list. — [operating-model.md › The data landscape L72–98; rulebook.md › R-04 L47] — **[Stated]**
- **AOS-77** Read access to other governed processes' change records (engineering change, pricing process) for reconciliation. — [operating-model.md L68 "approved requests or change records"; starters/production.md L10; pricing.md L10] — **[Stated]**
- **AOS-78** Transition integrations: the current app [TBC] (requests to match), the exceptions register [TBC: where], domain-profile documents as the settings source, and agent flags made visible to the vendor before it processes requests. — [delivery/transition.md L5–7, L65–67, L84, L97–98] — **[Stated]**

#### K. Hosting and model environment
- **AOS-79** Agent models run only in an environment the organisation controls: "its own systems, or a provider's service under a contract that stops the provider keeping or training on the data". — [charter.md L125–128; rulebook.md › R-21 L81; controls.md › R-21 L34] — **[Stated]**
- **AOS-80** Only AI tools and models on the approved-tools list may be used. — [controls.md › R-22 L35; README.md L71–72] — **[Stated]**

Model approval itself is covered by AOS-13 (pre-start gate) and AOS-56 (approval evidence). The outside-model route for Confidential or Restricted data is covered by AOS-40, AOS-46 and AOS-56, with the R-21 vs R-22 tension noted in section 3. A change of model, provider or version counts as an agent change under AOS-15. Data residency is AOS-47.

### Inferences
- *Tally:* Of the 80 requirements, 44 are fully **[Stated]**, 24 combine a stated rule with an inferred application or mechanism, and 12 are pure **[Inference]**. *Inference:* The biggest inferred areas are agent identity design (AOS-01, AOS-04, AOS-07, AOS-08), log masking against completeness (AOS-43 vs AOS-53/54), anti-splitting of level-2 runs (AOS-34), and treating agent memory as an extract (AOS-44).
- *Inference:* The framework puts much of the enforcement burden on the **unified app**: holding sensitive changes, auto-approving, routing, logging settings, blocking. The agent OS does not need to duplicate those checks, but it must not offer agents a route around them. In practice the agent OS's own enforcement duties are:
  - identity;
  - the deny-list;
  - the autonomy matrix;
  - egress and model-environment control;
  - injection handling;
  - logging and evaluation.
- *Inference:* Comparing platforms against this baseline will hinge on a few capabilities:
  - per-tool-call policy evaluated against external, frequently changing configuration (the domain profiles);
  - human-in-the-loop approval with reviewer identity and timing captured;
  - reversible, logged writes;
  - non-human identities that can be included in access reviews;
  - a guaranteed no-retention, no-training model hosting option.

### Gaps
- The documents give no requirements on:
  - agent-to-agent communication;
  - kill switches or incident response for a misbehaving agent;
  - rate limits;
  - log retention periods;
  - model evaluation beyond accuracy sampling;
  - cost;
  - availability or service levels for agents.
- Who performs the design review, and who approves the AI model, is not stated anywhere.
