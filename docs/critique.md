# Design Critique

**Status:** Rounds 1 and 2, 28 October 2026 · **Design:** [a5s](../README.md)

Every change to the design gets an adversarial review before it settles. The subject is a5s. Where a finding is about a scenario's own process, such as how the lean framework's unified app confirms bank-detail changes, a5s does its part and the rest goes to that scenario's owners. Reviewers who didn't write the design read it cold, each from one angle, and look for loopholes: ways to get round it, abuse it, or make it fail. Each finding is checked against the documents before it's accepted. This page records what each round found and how the design answers it.

- **Closed** means the design now stops it, and a test in the [baseline](../scenarios/lean-framework.md#passing-the-baseline) or a5s's own suite will show it.
- **Reduced** means it's now harder, or caught afterwards, but still possible.
- **Accepted** marks what's left of a loophole once the design has closed what it can: a risk no design removes, which its owner accepts under [accepted risks](#accepted-risks).
- **Scenario's call** means a5s has done its part, and what's left is a control in the scenario's own process, listed [for the lean framework's owners](#for-the-lean-frameworks-owners).

## How we critique

| Angle | Asks |
| --- | --- |
| Outside attacker | How could a fraudster, a malicious document, a tool server or a model provider get money, data or disruption out of it? |
| Insider | How could people inside, alone or together, get round the rules, or use the agents to? |
| Failure | What breaks, and what do people do when it does? |
| Colleague | Would people treat the agents as colleagues and keep using them, or route around them? |

Two earlier fresh reads checked the design's consistency and its faithfulness to the lean framework. Round 1 was the first adversarial one.

## What round 1 found

45 loopholes: 9 critical, 25 high and 11 medium. The first fixes closed 38 and reduced 7, and the [follow-up](#round-1-follow-up) closed the rest, leaving six risks for their owners to accept. Most came from five things the first design lacked:

1. **Whose words.** Agents couldn't tell outside words from inside ones, or who had prompted a request. [Provenance](architecture.md#provenance-who-said-what) answers this.
2. **Facts from code.** Agents wrote the facts people decided on, such as which contact to call back or whether two changes matched. Code now computes them.
3. **Independence.** The data team approved its own enforcement and held the only evidence. [Independence](architecture.md#independence) answers this.
4. **Failing safely.** Failing closed stopped the business, and only the data team could reopen it. [When things fail](architecture.md#when-things-fail) answers this.
5. **Colleagues.** Only requesters could talk to an agent, contact was counted per agent instead of per person, and what people said never reached the case. [How an agent lives](architecture.md#how-an-agent-lives) and [channels](architecture.md#channels) answer this.

### Outside attacker

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| A1 | A fraudster gets a supplier's verification phone changed first, then sends the bank letter weeks later, so the call-back reaches them | Critical | The contact in the owner assistant's call-back pack comes from records, by code, never from the request or a document. Which contact the framework trusts is its own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners); test 9) | Scenario's call |
| A2 | Outside text arrives as a record, such as a portal comment claiming the call-back was done | Critical | Outside free text reaches agents only through the extractor, facts people decide on are computed, and an agent can't say a check was done ([provenance](architecture.md#provenance-who-said-what); test 9) | Closed |
| A3 | Data leaves through a link or image that a preview fetches, with no click | Critical | Messages carry only text and the app's record links, nothing goes outside the organisation, and values are shown only in fields code fills in ([channels](architecture.md#channels); test 11) | Closed |
| A4 | Planted text steers the change reconciler's matches and the monthly sample | Critical | Code computes matches and draws samples, and every match on a sensitive field goes to internal controls ([R-08 and R-06](../scenarios/lean-framework.md#how-the-rules-map); test 25) | Closed |
| A5 | Deep Agents' own files and `AGENTS.md` become a memory nobody governs | High | Instructions and skills load read-only, file tools write only to scratch space wiped after each run, and attachments go to the extractor ([how an agent lives](architecture.md#how-an-agent-lives)) | Closed |
| A6 | The notebook, profiles and summaries make one injection last and spread | High | Marked runs can't write the notebook, notes come only from records, summaries keep source tags and are checked, and drafted values cite their source ([context](architecture.md#context-and-memory); [provenance](architecture.md#provenance-who-said-what); tests 10 and 12) | Closed; R4 accepted |
| A7 | A spoofed email makes anyone "the person" an agent acts for | High | Only authenticated internal senders start runs, Reply-To is ignored, and other mail is treated as a document ([provenance](architecture.md#provenance-who-said-what)) | Closed |
| A8 | The extractor's output still steers, and its source tags are lost at the app | High | Fixed schemas, the page as shown compared with hidden text, sources carried into requests, and values from documents never approved automatically or used as contacts ([data protection](architecture.md#data-protection); test 8) | Closed; R5 accepted |
| A9 | A2A drops the limits of the person an agent acts for | High | The people travel with the call, and the agent called works within what they may all do ([agent to agent](architecture.md#agent-to-agent); test 12) | Closed |
| A10 | A model provider swaps the model silently, without a release | High | Models are pinned by provider, deployment, region and version, and checked on every call and response ([data protection](architecture.md#data-protection)) | Closed |
| A11 | Tool servers, skills and held calls are trusted too much | Medium | Tool servers can't ask people for input or run the model, skills are pinned in the release, and the gateway records held calls, signed, and makes them only after policy checks again ([proposals](architecture.md#proposals-and-approvals)) | Closed |
| A12 | A flood of junk requests drains the budget urgent chases need | Medium | Budgets per source and per person, a share kept for obligations, and outside parties rate-limited ([when things fail](architecture.md#when-things-fail)) | Closed |

### Insider

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| I1 | A delegate gets their own bank change confirmed by feeding it to an agent that acts for nobody | Critical | Requests name everyone whose words they came from, those people can't decide them, and such requests never go through at level 2 ([provenance](architecture.md#provenance-who-said-what); test 6) | Closed |
| I2 | Settings, decisions and the ledger are records the data team can change | Critical | Settings count only with their owner's sign-off, decisions carry the decider's signed sign-in, nobody writes decision records directly, the ledger records the settings version, and its daily anchor sits with internal controls ([policy](architecture.md#policy); [independence](architecture.md#independence); test 24) | Closed; R3 accepted |
| I3 | The data team approves its own enforcement | Critical | Changes to the kernel, gateways, packs, masking and the app's agent tools are releases, approved outside the data team after assurance re-runs the tests ([independence](architecture.md#independence); [starting values](starting-values.md); test 23) | Closed |
| I4 | The change reconciler checks the data team using the data team's own data | Critical | It reads internal controls' own extract of SAP changes, a decider from the data team doesn't make a match, and internal controls approve its releases and draw its samples ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 25) | Closed |
| I5 | Someone sees more through an agent, through a reminder, A2A or an agent with a wider grant | High | A run acts for everyone whose words it serves, reminders included, and the people travel with A2A calls ([provenance](architecture.md#provenance-who-said-what); test 12) | Closed |
| I6 | A mass change in small pieces: 300 drafts, a clean-up split by country, or a broad level-2 type | High | Drafts and requests count at every level, per piece of work that code defines, and level-2 types are defined by their fields and check ([policy](architecture.md#policy); test 5) | Closed |
| I7 | An agent moves up a level on its builders' own evidence | High | Code draws samples, people outside the building team grade them, and a release that changes behaviour needs new samples and the owner's fresh approval ([autonomy](agent-model.md#autonomy); test 22) | Closed |
| I8 | Someone steers the evidence other deciders see, through a note framing duplicates or a sample that skips their own requests | High | Packs and notes come only from records, samples skip the reviewer's own items ([assurance](architecture.md#assurance); test 9) | Closed |
| I9 | Nobody owns the transition switch | High | Only the attribute owner and the GPDO turn it, with the app's test evidence, and an unreadable status counts as not moved ([transition](../scenarios/lean-framework.md#until-a-request-type-moves)) | Closed |
| I10 | The platform owner is a single point of control | High | Loosening anything needs someone outside the team that runs a5s and its manager's reporting line, and approvers and graders sit outside it too ([independence](architecture.md#independence); [starting values](starting-values.md)) | Closed |
| I11 | Ownership moves to a friendlier decider | Medium | Agents stay at level 1 on fields that move until the new owner sets their level, and a5s sends its measures to the GPDOs directly. Who may own which fields is the framework's own rule ([autonomy](agent-model.md#autonomy); test 7) | Scenario's call; R6 |
| I12 | An owner silences the chaser by withdrawing its approval | Medium | The GPDO is told of every withdrawal, and overdue cases keep escalating through the governance coordinator ([what a5s adds](../scenarios/lean-framework.md#what-a5s-adds); test 21) | Closed |

### Failure

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| F1 | An outage fix, such as a provider failover or turning on tracing, sends data round the gateways | Critical | Models are pinned, failover goes only to a model approved for the same data, and workers reach only the gateways and a5s's masking collector ([data protection](architecture.md#data-protection); test 15) | Closed |
| F2 | Failing closed has no degraded mode, and the data team holds the switch | High | Runs end and wait in the queue, a circuit breaker sends people to the governed process, and overriding a fail-closed rule is emergency access ([when things fail](architecture.md#when-things-fail); test 27) | Closed |
| F3 | During the transition, the vendor treats agents' flags as work orders | High | Flags go to a delegate, and the vendor acts only on the recorded decision ([transition](../scenarios/lean-framework.md#until-a-request-type-moves); test 26) | Closed in a5s, for the framework's owners to confirm |
| F4 | Approvals and withdrawals lag behind reality | High | The app checks with a5s before approving automatically, a suspension completes only when the app confirms, caches are cleared by change events, and level-2 settings record their approver ([proposals](architecture.md#proposals-and-approvals); [autonomy](agent-model.md#autonomy)) | Closed |
| F5 | Counts drift under parallel calls and retries | High | Counts are reserved with the policy decision, keys come from the piece of work, record and change, and a timed-out call is pending, not failed ([policy](architecture.md#policy); [how an agent lives](architecture.md#how-an-agent-lives)) | Closed |
| F6 | Someone else gets a person's conversation, through spoofed mail, a reused address or a group chat | High | Directory IDs, authenticated internal mail, no Reply-To, links instead of values in groups, and conversations archived when people leave ([provenance](architecture.md#provenance-who-said-what); [context](architecture.md#context-and-memory)) | Closed |
| F7 | The change reconciler's failures go to the team it checks | High | Each report states how much it covered, and an incomplete run alerts internal controls, who can run it again ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 25) | Closed |
| F8 | Repairing a thread steers an agent without a trace | High | Only the runtime writes thread state, the ledger records its hash, migrations are tested both ways, and editing by hand is emergency access ([independence](architecture.md#independence); [evidence](architecture.md#evidence)) | Closed |
| F9 | Every release resets the cap, so security patches wait | High | A release that changes only dependencies keeps the cap if its tests and re-run samples pass, advisories withdraw affected releases, and a failed drift test lowers the cap ([lifecycle](agent-model.md#lifecycle)) | Closed |
| F10 | One long conversation per person costs too much and loses facts | Medium | Each turn sends a capped context, budgets are per person, summaries are structured, checked by code and open to correction, and answers about the past retrieve the original turns ([context](architecture.md#context-and-memory)) | Closed |
| F11 | Chasing fails across time zones and many instances | Medium | Due times come from the app, people have time zones and holidays, urgent items go to someone at work, and digests and limits are per person ([channels](architecture.md#channels); tests 16 and 18) | Closed |

### Colleague

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| C1 | The notebook carries one person's words to everyone | High | Notes come only from records and tool results, take the highest class of their sources, and load only for people who may see that class ([context](architecture.md#context-and-memory); test 12) | Closed |
| C2 | Only requesters get a conversation, so a delegate who replies to a chase gets no answer | High | Every release has a message trigger that acts for the sender, and the request assistant wakes when its drafts are decided ([how an agent lives](architecture.md#how-an-agent-lives); test 13) | Closed |
| C3 | What people tell an agent never reaches the case, so the chases keep coming | High | A "waiting on" note the person confirms goes on the case and pauses chases, with one obligation per record and person ([how an agent lives](architecture.md#how-an-agent-lives); test 17) | Closed |
| C4 | When an agent can't run, it goes silent | High | The channel service replies in code, names who to ask, and hands urgent obligations on, and budgets are kept per person ([channels](architecture.md#channels); test 27) | Closed |
| C5 | One person faces many bots, each with its own digest | High | One identity per agent, one digest and limit per person, one request assistant across domains [TBC], and context that follows a part split ([channels](architecture.md#channels); test 18) | Closed |
| C6 | Handoffs drop the requester's context and the agent's flags | Medium | A handoff note goes with the work, flags go on the request itself, and recurring flags become checks ([proposals](architecture.md#proposals-and-approvals)) | Closed |
| C7 | One thread forever, with no reset and summaries nobody sees | Medium | Topics with an index and a fresh start, open and versioned summaries, and cut-off runs that release their thread ([context](architecture.md#context-and-memory)) | Closed |
| C8 | Learning is slow, and every release resets earned trust | Medium | Preferences listed in each release and kept in profiles, dependency-only releases that keep the cap, and new releases that earn trust in shadow while the old one keeps working ([lifecycle](agent-model.md#lifecycle)) | Closed |
| C9 | A group chat has no thread of its own | Medium | Each group has its own thread, and the agent shares only what everyone present may see ([context](architecture.md#context-and-memory)) | Closed |
| C10 | The extractor can't answer questions about a document, so people paste it into other tools | Medium | The extractor can answer in free text, marked as outside content, and never used as an instruction or a value ([data protection](architecture.md#data-protection)) | Closed |

## Round 1 follow-up

Round 1 left seven risks open. Each now has an answer:

| Open risk | Answer | Where |
| --- | --- | --- |
| A requester and a delegate colluding | The scenario's own risk. a5s's part is that agents never confirm, and the facts they present come from records. Ideas for the framework's own controls are listed for its owners. | [For the lean framework's owners](#for-the-lean-frameworks-owners); test 9 |
| Forged documents | Outside documents reach agents only through the extractor, and values from them are never approved automatically. Checking the facts behind a change is the framework's own rule. | [Data protection](architecture.md#data-protection); test 8 |
| Misleading context, and a compromised model provider | Drafted values cite their source, facts are shown apart from the agent's narrative, and a model from another provider checks narratives on sensitive decisions | [Provenance](architecture.md#provenance-who-said-what); [data protection](architecture.md#data-protection); test 10 |
| The builders' reach | Loosening anything needs someone outside the team, and decisions carry their decider's signature | [Independence](architecture.md#independence); test 24 |
| Ownership moved to a friendlier decider | Agents stay at level 1 on moved fields until the new owner sets their level. Who may own what is the framework's own rule. | [Autonomy](agent-model.md#autonomy); test 7 |
| Summaries and trust | Summaries are structured and checked, answers about the past retrieve the original turns, and new releases earn trust in shadow | [Context](architecture.md#context-and-memory); [lifecycle](agent-model.md#lifecycle); tests 10 and 22 |
| Names and numbers | Each has a starting value, for its owner to confirm | [Starting values](starting-values.md) |

Round 2 then attacked these answers. Its findings on a5s are closed [below](#what-round-2-found), and those on the framework's own controls went to its owners.

## What round 2 found

Round 2 attacked the follow-up's new controls from two angles, fraud and control, and operations and colleagues. It found 21 problems: 7 critical, 10 high and 4 medium. Most showed the first answers were too narrow: they covered bank details but not other ways to redirect a payment, compared against data a fraudster could change first, sent the riskiest changes to one predictable person, and signed a sign-in rather than a decision. 12 were about a5s, and are closed. The other 9 were about the lean framework's own controls on bank-detail changes: a5s does its part, and the rest is for the framework's owners.

### Fraud and control

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| D1 | Payments redirected through an alternative payee, without touching bank details | Critical | The framework's own rule. a5s agents never confirm such a change, and what they prepare for it takes its facts from records ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D2 | The supplier's name and country are changed first, so a later account in the new name matches | Critical | The framework's own rule, with ideas listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D3 | Patience beats the contact's age: a contact a forged letter changed 91 days before passes | Critical | The framework's own rule, with ideas listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D4 | The riskiest changes go to one predictable person, and internal controls' re-call has no deadline | Critical | Who confirms what is the framework's own rule, with options listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D5 | A signed sign-in doesn't sign the decision, so it can be reused for another | Critical | Each decision is signed on the decider's own device, for that one decision, showing the supplier and the account's last digits, and signatures work once ([independence](architecture.md#independence); test 24) | Closed |
| D6 | The builders build the new controls and the tests that judge them | High | The governed process's controls that a5s relies on, such as how it records decisions and call-backs and flags high risk, change like enforcement, and assurance holds their tests ([independence](architecture.md#independence)) | Closed |
| D7 | Withdrawing and resubmitting re-rolls the random draw, and the pair alert misses a single fraud | High | Random drawing of confirmers is an option for the framework's owners, with the draw kept with the record if they adopt it ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| D8 | The people being watched can switch the detection off | High | Stopping anything that detects, such as the change reconciler, counts as loosening and needs internal controls' agreement. Any collusion checks the framework's owners add run as code internal controls own (test 25) | Closed |
| D9 | The channel score rewards account takeover | High | Scoring the risk of a bank change is the framework's own rule, with ideas listed for its owners ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |

### Operations and colleagues

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| O1 | A blocked call-back pack leaves no safe way forward, so the owner rings the number on file | Critical | The pack takes its contact from records, by code. Which contact to use when the trusted one changed recently is the framework's own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners); test 9) | Scenario's call |
| O2 | High-risk changes get a predictable confirmer and a late re-call | Critical | As D4 | Scenario's call |
| O3 | Confirmation stalls when the person drawn is away, and the bank can't check many accounts | High | How confirmers are chosen and accounts checked is the framework's own rule ([for the lean framework's owners](#for-the-lean-frameworks-owners)) | Scenario's call |
| O4 | The counting backstop switches busy assistants off mid-month | High | Case packs and reports don't count, and the backstop counts per person acted for and change type, or per check ([policy](architecture.md#policy); test 28) | Closed |
| O5 | Releases can't be rolled back or patched fast | High | An instance can go straight back to the release before, new releases take level-0 and level-1 work at once, shadow runs are dry, and information security decides in advance which advisories withdraw a release ([lifecycle](agent-model.md#lifecycle); test 22) | Closed |
| O6 | The measures of people flag diligent reviewers, and need consent | High | Reviewers are flagged on outcomes, not speed, and the measures are agreed with the data protection officer and works councils before they start ([assurance](architecture.md#assurance); test 20) | Closed |
| O7 | The context cap has no rule for what happens when it's reached | High | A budget for each part of the context, tested at release, only the instructions and skills for the parts in play, and an offer to take a long paste as a document ([context](architecture.md#context-and-memory)) | Closed |
| O8 | The samples prove little and cost a lot | High | A sequential test at 95% confidence, pooled across a release's instances, and ongoing samples sized to what they need to detect ([starting values](starting-values.md)) | Closed |
| O9 | Chases arrive with the escalation | Medium | A chase goes in the last digest before half the turnaround, and escalation waits at least a working day after it ([channels](architecture.md#channels)) | Closed |
| O10 | A sign-in for every decision breeds approval fatigue | Medium | Decisions are signed one at a time, and those the scenario marks as lower risk as a reviewed batch, and every signature is bound to what it signs ([independence](architecture.md#independence); test 24) | Closed |
| O11 | The second model has no rule for outages or disagreement | Medium | It never holds up a decision, the decision surface shows when it didn't run, and a checker whose flags rarely hold up is replaced ([provenance](architecture.md#provenance-who-said-what)) | Closed |
| O12 | A quiet December sets the budgets | Medium | The first budgets come from current request volumes, with a warning at 80% and obligations protected at 100% ([when things fail](architecture.md#when-things-fail)) | Closed |

## Accepted risks

Some risk no design removes. These remain after round 2, and each needs its owner to accept it.

**a5s's own**

| # | Risk | Why it stays | Accepted by |
| --- | --- | --- | --- |
| R3 | The identity provider, or the environment the organisation's own models run in, being compromised. It's narrowed by holding decisions for 24 hours after an authenticator is reset. | Signed decisions and pinned models rest on them | The executive the GPDOs and the platform owner report to, since information security approves the models |
| R4 | A person misled by an agent despite the facts, the source flags and the second model's check. It's narrowed by showing the computed facts apart from the agent's narrative. | People still decide | The GPDOs, with training on deciding from the facts |

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
- **Level 1 and the request assistant.** The rulebook's level 1 has the attribute owner or a delegate approve each proposal, while the request assistant's drafts are submitted by requesters, as their own requests.
- **The transition.** The transition notes ask the vendor to act on what agents flag. a5s sends flags to a delegate first (F3).
- **Who approves.** Nobody is named to run an agent's design review, approve its model, or approve changes to the enforcement around it (I3, I10). The [starting values](starting-values.md) propose information security.
- **Measures of people.** The operating model's own measures of how many decisions owners make and how long requests wait watch people too, and need agreement with the data protection officer and works councils (O6).

## Next round

Round 3 starts from the accepted risks, from any change to the design since round 2, and from the code once it exists.
