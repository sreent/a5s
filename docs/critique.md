# Design Critique

**Status:** Rounds 1 to 3, 28 October 2026 · **Design:** [a5s](../README.md)

Every change to the design gets an adversarial review before it settles. The subject is a5s. Where a finding is about a scenario's own process, such as how the lean framework's unified app confirms bank-detail changes, a5s does its part and the rest goes to that scenario's owners. Reviewers who didn't write the design read it cold, each from one angle, and each finding is checked against the documents before it's accepted. This page records what each round found, how the design answers it now, and what each round removed.

- **Designed** means the design stops it, and a test in the [baseline](../scenarios/lean-framework.md#passing-the-baseline) or a5s's own suite will show it once it's built. Nothing is built yet, so nothing is closed.
- **Phase 2** and **Phase 3** mean it's designed for a feature that comes in that phase. Until then, neither the feature nor the loophole exists.
- **Accepted** marks what's left once the design has done what it can: a risk its owner accepts under [accepted risks](#accepted-risks).
- **Scenario's call** means a5s has done its part, and the rest is a control in the scenario's own process, listed [for the lean framework's owners](#for-the-lean-frameworks-owners).
- **Removed** means a later round removed the control the finding was about.

## How we critique

| Angle | Asks |
| --- | --- |
| Outside attacker | How could a fraudster, a malicious document, a tool server or a model provider get data or disruption out of it? |
| Insider | How could people inside, alone or together, get round the rules, or use the agents to? |
| Failure | What breaks, and what do people do when it does? |
| Colleague | Would people treat the agents as colleagues and keep using them, or route around them? |
| Builder and funder | What would a team build first, what does it cost, and what can go or wait? |
| Second scenario | Would it work for a different scenario, such as an [IT service desk](../scenarios/it-service-desk.md), without changing a5s? |

Every round reports the rules it added and the rules it removed, and proposes cuts. Rounds 1 and 2 used only the first four angles and removed nothing, which is how the design doubled in size. Round 3 added the last two.

Two earlier fresh reads checked the design's consistency and its faithfulness to the lean framework. Round 1 was the first adversarial one.

## What round 1 found

45 loopholes: 9 critical, 25 high and 11 medium. The first fixes answered 38 and reduced 7, and the [follow-up](#round-1-follow-up) answered the rest, leaving six risks for their owners to accept. It removed nothing. Most came from five things the first design lacked:

1. **Whose words.** Agents couldn't tell outside words from inside ones, or who had prompted a request. [Provenance](architecture.md#provenance-who-said-what) answers this.
2. **Facts from code.** Agents wrote the facts people decided on, such as which contact to call back or whether two changes matched. Code now computes them.
3. **Independence.** The data team approved its own enforcement and held the only evidence. [Independence](architecture.md#independence) answers this.
4. **Failing safely.** Failing closed stopped the business, and only the data team could reopen it. [When things fail](architecture.md#when-things-fail) answers this.
5. **Colleagues.** Only requesters could talk to an agent, contact was counted per agent instead of per person, and what people said never reached the case. [How an agent lives](architecture.md#how-an-agent-lives) and [channels](architecture.md#channels) answer this.

### Outside attacker

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| A1 | A fraudster gets a supplier's verification phone changed first, then sends the bank letter weeks later, so the call-back reaches them | Critical | The contact in the owner assistant's call-back pack comes from records, by code, never from the request or a document. Which contact the framework trusts is its own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners); test 9) | Scenario's call |
| A2 | Outside text arrives as a record, such as a portal comment claiming the call-back was done | Critical | Outside free text reaches agents only through the extractor, facts people decide on are computed, and an agent can't say a check was done ([provenance](architecture.md#provenance-who-said-what); test 9) | Phase 2 |
| A3 | Data leaves through a link or image that a preview fetches, with no click | Critical | Messages carry only text and the scenario's record links, and go only to the scenario's audience ([channels](architecture.md#channels); test 11) | Designed |
| A4 | Planted text steers the change reconciler's matches and the monthly sample | Critical | Code computes matches and draws samples, and the reconciler reports to internal controls ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 25) | Designed |
| A5 | Deep Agents' own files and `AGENTS.md` become a memory nobody governs | High | Instructions and skills load read-only from the release, scratch files last one run, and Deep Agents' editable memory isn't used ([what a5s uses from Deep Agents](architecture.md#what-a5s-uses-from-deep-agents)) | Designed |
| A6 | The notebook, profiles and summaries make one injection last and spread | High | Marked runs can't write profiles, summaries hold facts by handle and are checked by code, and there's no notebook until phase 3 ([context](architecture.md#context-and-memory); [provenance](architecture.md#provenance-who-said-what); tests 10 and 14) | Designed; R4 accepted |
| A7 | A spoofed email makes anyone "the person" an agent acts for | High | Only people the directory knows start runs, email only from senders who pass DMARC and match the directory, Reply-To is ignored, and other mail is treated as a document ([channels](architecture.md#channels)) | Designed |
| A8 | The extractor's output still steers, and its source tags are lost at the app | High | The extractor has no tools and fixed schemas, values from documents carry their source as handles, and the lean pack never approves them automatically or uses them as contacts ([data protection](architecture.md#data-protection); [provenance](architecture.md#provenance-who-said-what); test 8) | Phase 2; R5 accepted |
| A9 | A2A drops the limits of the person an agent acts for | High | The people travel with the call, and authority never passes between agents ([agent to agent](architecture.md#agent-to-agent)) | Phase 3 |
| A10 | A model provider swaps the model silently, without a release | High | Models are pinned by provider, deployment, region and version, and the model gateway checks every call ([a call, step by step](architecture.md#a-call-step-by-step)) | Designed |
| A11 | Tool servers, skills and held calls are trusted too much | Medium | The gateway refuses tool servers' requests to ask people for input or run the model, skills are pinned in the release, and held calls are a5s's own records, made through the gateway like any call ([data protection](architecture.md#data-protection); [proposals](architecture.md#proposals-and-approvals)) | Designed |
| A12 | A flood of junk requests drains the budget urgent chases need | Medium | Budgets per person and per source of triggers, a share kept for obligations, and outside parties rate-limited ([when things fail](architecture.md#when-things-fail)) | Designed |

### Insider

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| I1 | A delegate gets their own bank change confirmed by feeding it to an agent that acts for nobody | Critical | Requests name everyone whose words they came from, those people can't decide them, and the lean pack never lets such requests through at level 2 ([provenance](architecture.md#provenance-who-said-what); [lean pack](../scenarios/lean-framework.md#the-lean-pack); test 6) | Phase 2 |
| I2 | Settings, decisions and the ledger are records the data team can change | Critical | Settings count only with their owner's signature, decisions on sensitive items are signed for each decision, the ledger records the settings version, and its hourly anchor sits with assurance ([a call, step by step](architecture.md#a-call-step-by-step); [evidence](architecture.md#evidence); test 24) | Designed; R3 accepted |
| I3 | The data team approves its own enforcement | Critical | Changes to the trusted core and policy packs need an approver from outside the team, an attested build and assurance's tests, and the lean scenario adds the app's agent tools ([independence](architecture.md#independence); test 23) | Designed |
| I4 | The change reconciler checks the data team using the data team's own data | Critical | It reads internal controls' own extract of SAP changes, a decider from the data team doesn't make a match, and internal controls approve changes to it, draw its samples and must agree to stop it ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 25) | Designed |
| I5 | Someone sees more through an agent, through a reminder, A2A or an agent with a wider grant | High | A run acts for everyone whose words it serves, reminders included, and sees only what they may all see ([provenance](architecture.md#provenance-who-said-what); [context](architecture.md#context-and-memory); test 12) | Designed |
| I6 | A mass change in small pieces: 300 drafts, a clean-up split by country, or a broad level-2 type | High | Counts at every level, per piece of work that code defines, and types of action defined by their fields and check ([policy](architecture.md#policy); test 5) | Phase 2 |
| I7 | An agent moves up a level on its builders' own evidence | High | Code draws samples, people outside the team that built it grade them, and the part owner decides ([autonomy](agent-model.md#autonomy); [assurance](architecture.md#assurance)) | Phase 2 |
| I8 | Someone steers the evidence other deciders see, through a note framing duplicates or a sample that skips their own requests | High | Case briefs come from records, facts are computed and shown apart from the narrative, and samples skip the reviewer's own items ([provenance](architecture.md#provenance-who-said-what); test 9) | Designed |
| I9 | Nobody owns the transition switch | High | Only the attribute owner and the GPDO turn it, with the app's test evidence, and an unreadable status counts as not moved ([transition](../scenarios/lean-framework.md#until-a-request-type-moves)) | Designed |
| I10 | The platform owner is a single point of control | High | Loosening anything needs someone outside the team that runs a5s and its manager's reporting line, and is reported to assurance ([independence](architecture.md#independence)) | Designed |
| I11 | Ownership moves to a friendlier decider | Medium | Level-2 settings drop to level 1 when a field moves, until the new owner sets them, and a5s sends its measures to the GPDOs directly. Who may own which fields is the framework's own rule ([autonomy](agent-model.md#autonomy); test 7) | Scenario's call; R6 |
| I12 | An owner silences the chaser by withdrawing its approval | Medium | The GPDO is told of every withdrawal, and overdue cases keep escalating through the governance coordinator ([what a5s adds](../scenarios/lean-framework.md#what-a5s-adds); test 21) | Designed |

### Failure

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| F1 | An outage fix, such as a provider failover or turning on tracing, sends data round the gateways | Critical | Models are pinned, failover goes only to a model approved for the same data, and workers reach nothing but the gateways ([data protection](architecture.md#data-protection); test 15) | Designed |
| F2 | Failing closed has no degraded mode, and the data team holds the switch | High | Runs end and their triggers wait, a circuit breaker pauses new runs, the channel service tells people to carry on in the scenario's own process, and overriding a fail-closed rule loosens a5s, so it needs someone outside the team ([when things fail](architecture.md#when-things-fail); test 27) | Designed |
| F3 | During the transition, the vendor treats agents' flags as work orders | High | Flags go to a delegate, and the vendor acts only on the recorded decision ([transition](../scenarios/lean-framework.md#until-a-request-type-moves); test 26) | Designed in a5s, for the framework's owners to confirm |
| F4 | Approvals and withdrawals lag behind reality | High | Settings are cached for at most 30 seconds and a change clears the cache, the app checks with a5s before approving automatically, and level-2 settings record their approver ([a call, step by step](architecture.md#a-call-step-by-step); [autonomy](agent-model.md#autonomy)) | Designed |
| F5 | Counts drift under parallel calls and retries | High | Counts are reserved in the same transaction as the policy decision, and keys come from the piece of work, the record and the change ([a call, step by step](architecture.md#a-call-step-by-step); [how an agent lives](architecture.md#how-an-agent-lives)) | Phase 2 |
| F6 | Someone else gets a person's conversation, through spoofed mail, a reused address or a group chat | High | Directory identities, DMARC-checked mail, no Reply-To, conversations archived when people leave, and no group conversations until phase 3 ([channels](architecture.md#channels); [context](architecture.md#context-and-memory)) | Designed |
| F7 | The change reconciler's failures go to the team it checks | High | Each report states how much it covered, and an incomplete run alerts internal controls ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 25) | Designed |
| F8 | Repairing a thread steers an agent without a trace | High | Run threads last one run, so there's no saved state to repair, and conversations are a5s's own records, written only by the context service ([context](architecture.md#context-and-memory)) | Designed |
| F9 | Every release resets the cap, so security patches wait | High | Releases are proportionate: one that changes only instructions or skills keeps the cap if the last graded samples still pass, and a security fix goes in at once, at level 1 at most ([independence](architecture.md#independence); [lifecycle](agent-model.md#lifecycle)) | Designed |
| F10 | One long conversation per person costs too much and loses facts | Medium | Each run starts fresh with a context assembled within a budget, summaries are structured and checked by code, and answers about the past retrieve the original turns ([context](architecture.md#context-and-memory)) | Designed |
| F11 | Chasing fails across time zones and many instances | Medium | Due times come from the scenario's records, escalation follows working hours, and digests and limits are per person ([channels](architecture.md#channels); tests 16 and 18) | Designed |

### Colleague

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| C1 | The notebook carries one person's words to everyone | High | No notebook until phase 3. When it comes, notes come only from records and tool results, and load only for people who may see them ([context](architecture.md#context-and-memory)) | Phase 3 |
| C2 | Only requesters get a conversation, so a delegate who replies to a chase gets no answer | High | Every agent can be talked to, and a reply starts a run that acts for the sender ([how an agent lives](architecture.md#how-an-agent-lives); test 13) | Designed |
| C3 | What people tell an agent never reaches the case, so the chases keep coming | High | A person can say what they're waiting on, which pauses chases to them until the date they give, with one obligation for each record and person ([how an agent lives](architecture.md#how-an-agent-lives); test 17) | Designed |
| C4 | When an agent can't run, it goes silent | High | The channel service says so in code and names who to ask, and budgets are kept per person ([channels](architecture.md#channels); test 27) | Designed |
| C5 | One person faces many bots, each with its own digest | High | One digest and one limit per person from all the agents, and one conversation per person per agent, whichever instance does the work ([channels](architecture.md#channels); [context](architecture.md#context-and-memory); test 18) | Designed |
| C6 | Handoffs drop the requester's context and the agent's flags | Medium | Drafts and requests carry a handoff note and the agent's flags ([proposals](architecture.md#proposals-and-approvals)) | Designed |
| C7 | One thread forever, with no reset and summaries nobody sees | Medium | Topics, summaries the person can see and correct, and a fresh thread for every run ([context](architecture.md#context-and-memory)) | Designed |
| C8 | Learning is slow, and every release resets earned trust | Medium | Typed preferences and a "how I like to work" note in each profile, and releases that change only instructions or skills keep the cap ([context](architecture.md#context-and-memory); [lifecycle](agent-model.md#lifecycle)) | Designed |
| C9 | A group chat has no thread of its own | Medium | Group conversations come in phase 3 ([context](architecture.md#context-and-memory)) | Phase 3 |
| C10 | The extractor can't answer questions about a document, so people paste it into other tools | Medium | The extractor can answer in free text, marked as outside content and never used as an instruction ([data protection](architecture.md#data-protection)) | Phase 2 |

## Round 1 follow-up

Round 1 left seven risks open. Each now has an answer:

| Open risk | Answer | Where |
| --- | --- | --- |
| A requester and a delegate colluding | The scenario's own risk. a5s's part is that agents never confirm, and the facts they present come from records. Ideas for the framework's own controls are listed for its owners. | [For the lean framework's owners](#for-the-lean-frameworks-owners); test 9 |
| Forged documents | Outside documents reach agents only through the extractor, and the lean pack never approves their values automatically. Checking the facts behind a change is the framework's own rule. | [Data protection](architecture.md#data-protection); test 8 |
| Misleading context, and a compromised model provider | Drafted values carry their source, and facts are shown apart from the agent's narrative. Round 3 removed the second model that checked narratives. | [Provenance](architecture.md#provenance-who-said-what); R4 |
| The builders' reach | Loosening anything needs someone outside the team, and decisions on sensitive items carry their decider's signature | [Independence](architecture.md#independence); test 24 |
| Ownership moved to a friendlier decider | Agents drop to level 1 on moved fields until the new owner sets their level. Who may own what is the framework's own rule. | [Autonomy](agent-model.md#autonomy); test 7 |
| Summaries and trust | Summaries are structured and checked, answers about the past retrieve the original turns, and releases that change only instructions keep earned trust | [Context](architecture.md#context-and-memory); [lifecycle](agent-model.md#lifecycle); test 10 |
| Names and numbers | Each has a starting value, for its owner to confirm | [Starting values](starting-values.md) |

## What round 2 found

Round 2 attacked the follow-up's new controls from two angles, fraud and control, and operations and colleagues. It found 21 problems: 7 critical, 10 high and 4 medium. Most showed the first answers were too narrow: they covered bank details but not other ways to redirect a payment, compared against data a fraudster could change first, sent the riskiest changes to one predictable person, and signed a sign-in rather than a decision. 11 were about a5s. The other 10 were about the lean framework's own controls: a5s does its part, and the rest is for the framework's owners. It removed nothing.

### Fraud and control

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| D1 | Payments redirected through an alternative payee, without touching bank details | Critical | The framework's own rule. Agents never confirm such a change, and what they prepare for it takes its facts from records ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D2 | The supplier's name and country are changed first, so a later account in the new name matches | Critical | The framework's own rule, with ideas listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D3 | Patience beats the contact's age: a contact a forged letter changed 91 days before passes | Critical | The framework's own rule, with ideas listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D4 | The riskiest changes go to one predictable person, and internal controls' re-call has no deadline | Critical | Who confirms what is the framework's own rule, with options listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D5 | A signed sign-in doesn't sign the decision, so it can be reused for another | Critical | Each decision on a sensitive item is signed by its decider for that one decision, through the identity provider, and a signature works once ([proposals](architecture.md#proposals-and-approvals); test 24) | Phase 2 |
| D6 | The builders build the new controls and the tests that judge them | High | Changes to the app's agent tools need an approver from outside the data team. How the app's other controls change is the framework's own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners); test 23) | Scenario's call |
| D7 | Withdrawing and resubmitting re-rolls the random draw, and the pair alert misses a single fraud | High | Drawing confirmers at random is an option for the framework's owners, with the draw kept with the record if they adopt it ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D8 | The people being watched can switch the detection off | High | Stopping a check that detects, such as the change reconciler, loosens a5s, so it needs internal controls' agreement (test 25) | Designed |
| D9 | The channel score rewards account takeover | High | Scoring the risk of a bank change is the framework's own rule, with ideas listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |

### Operations and colleagues

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| O1 | A blocked call-back pack leaves no safe way forward, so the owner rings the number on file | Critical | The pack takes its contact from records, by code. Which contact to use when the trusted one changed recently is the framework's own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners); test 9) | Scenario's call |
| O2 | High-risk changes get a predictable confirmer and a late re-call | Critical | As D4 | Scenario's call |
| O3 | Confirmation stalls when the person drawn is away, and the bank can't check many accounts | High | How confirmers are chosen and accounts checked is the framework's own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| O4 | The counting backstop switches busy assistants off mid-month | High | Case packs and reports don't count, and the backstop counts per person acted for and type of action, or per check ([starting values](starting-values.md); test 28) | Phase 2 |
| O5 | Releases can't be rolled back or patched fast | High | An instance can go straight back to the release before, releases are proportionate, and a security fix goes in at once ([lifecycle](agent-model.md#lifecycle); [independence](architecture.md#independence); test 22) | Designed |
| O6 | The measures of people flag diligent reviewers, and need consent | High | Measures of people judge outcomes, not speed, and are agreed with the data protection officer, and with works councils where there are any, before they start ([assurance](architecture.md#assurance); test 20) | Designed |
| O7 | The context cap has no rule for what happens when it's reached | High | A budget for each part of the context, tested at release, with only the skills for the parts in play ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| O8 | The samples prove little and cost a lot | High | A sequential test at 95% confidence, pooled across a release's instances, and ongoing samples sized to what they need to detect ([starting values](starting-values.md)) | Phase 2 |
| O9 | Chases arrive with the escalation | Medium | A chase goes in the last digest before half the turnaround, and escalation waits at least a working day after it ([starting values](starting-values.md)) | Designed |
| O10 | A sign-in for every decision breeds approval fatigue | Medium | Only decisions on sensitive items are signed one by one, and the rest follow the decision surface's own sign-in ([proposals](architecture.md#proposals-and-approvals)) | Phase 2 |
| O11 | The second model has no rule for outages or disagreement | Medium | Round 3 removed the second model ([round 3](#round-3-fresh-eyes)) | Removed |
| O12 | A quiet December sets the budgets | Medium | Budgets come from current volumes, with a warning at 80% and obligations protected at 100% ([starting values](starting-values.md)) | Designed |

## Round 3: fresh eyes

Two readers who hadn't seen the design read it whole: an owner, for generality, colleague feel, proportionate governance, value and readability, and an engineer, for coherence, buildability, focus and clarity. Both found the safety thinking strong, and both found a governance specification rather than an agent OS a team could build. The design had drifted into the lean framework's own controls, and every round had added rules without removing any.

| Owner's view | Score out of 5 | Engineer's view | Score out of 5 |
| --- | --- | --- | --- |
| Generality | 2 | Coherence | 3 |
| Colleague feel | 3 | Buildability | 2 |
| Proportionate governance | 2 | Focus | 2 |
| Clarity of value | 2 | Clarity | 3 |
| Readability | 3 | | |

| # | Finding | How v0.2 answers it |
| --- | --- | --- |
| S1 | Lean rules sat in a5s's core. "A request from a person's words never goes through at level 2" would block "reset my password" on a service desk, and "inside only" would shut out new joiners. | They're in the [lean pack](../scenarios/lean-framework.md#the-lean-pack) now. a5s's base pack only records who a run acts for and keeps them from deciding what they're named on. The [IT service desk](../scenarios/it-service-desk.md) checks this on paper. |
| S2 | There was no contract for scenarios, and a5s had no settings store or decision surface of its own | The [scenario contract](architecture.md#the-scenario-contract), with a5s's defaults, and a fake of each scenario as its test bench |
| S3 | Source tags can't travel with a value once a model rewrites it as text | [Provenance](architecture.md#provenance-who-said-what) at three grains: marked runs, handles for sensitive values, and exact matching of typed values. Free text is always the agent's own, and handles are prototyped first. |
| S4 | One LangGraph thread forever meant custom summaries, and migrations on every upgrade | A fresh thread for each run, with conversations as a5s's own records ([context](architecture.md#context-and-memory)) |
| S5 | "Enforcement" covered everything, so every change needed outside approval | A small [trusted core](architecture.md#the-trusted-core-and-the-rest), and [proportionate releases](architecture.md#independence) |
| S6 | The path each call takes was unspecified, and no ledger can be impossible to change | [A call, step by step](architecture.md#a-call-step-by-step), and a hash-chained ledger anchored every hour, which makes it tamper-evident ([evidence](architecture.md#evidence)) |
| S7 | There was no first version: all five agents and 28 tests at once | [Phase 1](phase-1.md): the core, conversations and three low-risk agents, with the tests marked by phase |
| S8 | Agents couldn't keep their own promises, or learn how people like to work | Promises and reminders as typed tools that people confirm, and a "how I like to work" note in each profile |
| S9 | A person talked to a separate memory for each part | One conversation per person per agent, with each part's scope enforced at the tools |
| S10 | News waited in the digest with the chases | Outcomes people are waiting for go at once, within a limit per person |
| S11 | The case for building it was about control, with no outcomes or costs | Outcomes and costs in the [README](../README.md#why-build-it) and [phase 1](phase-1.md#costs) |
| S12 | "Closed" claimed what no code shows yet, and the critique only ever added rules | "Designed" instead, two new angles, and every round reports what it removed |
| S13 | Nothing on operations | [Operations](architecture.md#operations): environments, objectives, dashboards, runbooks and on-call |

What round 3 changed:

- **Moved to the lean pack:** no level 2 for requests from a person's words, inside-only contact, sensitive fields, values from documents, the transition switch and the mass-change size.
- **Removed:** long-lived threads and their migrations, the second model that checked narratives, comparing a document's shown text with its hidden text, a design review for every release, shadow runs for new releases, measuring whether messages are read, and emergency access as an idea of its own, now part of loosening.
- **Deferred to phase 2:** held proposals, counts, level 2, samples and sequential tests, the extractor, and signed decisions.
- **Deferred to phase 3:** the notebook, group conversations, agent to agent, and adapters for managed runtimes.
- **Added:** the trusted core, the scenario contract, a call step by step, handles, promises and reminders, the "how I like to work" note, operations, the phase-1 plan, the IT service desk on paper, and costs.
- **Size:** without this critique, the design went from 14,933 words to about 12,400, two new documents included. With it, which grew by this round's record, from 19,743 to about 18,100.

## Accepted risks

Some risk no design removes. These remain, and each needs its owner to accept it.

**a5s's own**

| # | Risk | Why it stays | Accepted by |
| --- | --- | --- | --- |
| R3 | The identity provider, or the environment the organisation's own models run in, being compromised. It's narrowed by holding decisions for 24 hours after an authenticator is reset. | Signed decisions and pinned models rest on them | The executive the scenario's owners and the platform owner report to |
| R4 | A person misled by an agent despite the computed facts and the source flags. It's narrowed by showing the facts apart from the agent's narrative. | People still decide | The scenario's owners, with training on deciding from the facts |

**The lean scenario's**

| # | Risk | Why it stays | Accepted by |
| --- | --- | --- | --- |
| R1 | A requester and a confirmer colluding, unless the framework's owners adopt the options below, and three or more people, including someone who checks them, in any case | Every control relies on someone in it being honest | The GPDOs |
| R2 | A supplier that is itself the fraudster, with a genuine account in its own name | The call-back confirms what the supplier says | The GPDOs |
| R5 | A forged document for a field that isn't sensitive and feeds no other control, where a person decides with the value flagged as coming from a document | Not every field justifies independent verification | Each attribute owner, through what their profile marks as sensitive |
| R6 | The GPDOs choosing, in plain sight, an ownership that creates a conflict | It's their right under the charter | The executive the GPDOs report to, as the charter's escalation already has it, with internal controls told |

## For the lean framework's owners

These are about the framework's own controls, not a5s. The critique raised them along the way, and they're the framework's owners' to take up or leave:

- **Bank-detail call-backs (R-15).** R-15 trusts contact details "that weren't changed along with it", so a contact changed weeks before passes, and a change to the verification contact itself needs no call-back (A1, D3). Options: call back the contact a newer one replaced, treat a recent change to the supplier's name, country or contacts as high risk, and have the confirmer type what the supplier reads out, for code to compare (D2, O1).
- **Other ways to redirect payments.** R-15 covers bank details, while an alternative payee or a payment method can redirect payments just as well (D1).
- **What high risk triggers.** Options: a second confirmer, internal controls' own call-back before the change is used, or confirmers drawn at random from eligible people at work, with the draw kept with the record (D4, D7, O2, O3).
- **Looking for collusion.** Options: internal controls re-performing call-backs on a sample, and matching suppliers' bank accounts and addresses against employees' (R1, R2).
- **Account takeover.** A supplier portal change soon after a password reset, or from a new device, deserves more scrutiny, not less (D9).
- **Ownership conflicts.** Options: internal controls' review of ownership changes that put a sensitive field with people who hold conflicting rights (I11, R6).
- **Changes to the app's own controls.** a5s relies on how the unified app records decisions and confirmations. Changes to those deserve the same outside approval as the app's agent tools (D6).
- **Level 1 and the request assistant.** The rulebook's level 1 has the attribute owner or a delegate approve each proposal, while the request assistant's drafts are submitted by requesters, as their own requests.
- **Releases that widen nothing.** a5s lets the agent owner and a second engineer approve a release that changes only instructions or skills, after its tests. The charter says nobody approves their own agent, so the framework's owners should confirm that reading.
- **The transition.** The transition notes ask the vendor to act on what agents flag. a5s sends flags to a delegate first (F3).
- **Who approves.** Nobody is named to approve agents' releases and models, or changes to the enforcement around them (I3, I10). The [lean contract](../scenarios/lean-framework.md#the-contract) proposes information security.
- **Measures of people.** The operating model's own measures of how many decisions owners make and how long requests wait watch people too, and need agreement with the data protection officer and works councils (O6).

## Next round

Round 4 starts from the accepted risks, from v0.2's new parts, such as the contract, the call path and handles, and from the code once it exists. It reads from all six angles, and reports what it removes.
