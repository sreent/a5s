# Design Critique

**Status:** Rounds 1 and 2, 28 October 2026 · **Design:** [a5s](../README.md)

Every change to the design gets an adversarial review before it settles. Reviewers who didn't write the design read it cold, each from one angle, and look for loopholes: ways to get round it, abuse it, or make it fail. Each finding is checked against the documents before it's accepted. This page records what each round found and how the design answers it.

- **Closed** means the design now stops it, and a test in the [baseline](../scenarios/lean-framework.md#passing-the-baseline) or a5s's own suite will show it.
- **Reduced** means it's now harder, or caught afterwards, but still possible.
- **Accepted** marks what's left of a loophole once the design has closed what it can: a risk no design removes, which its owner accepts under [accepted risks](#accepted-risks).

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
| A1 | A fraudster gets a supplier's verification phone changed first, then sends the bank letter weeks later, so the call-back reaches them | Critical | Code chooses the call-back contact: one unchanged for 90 days, or else the one a newer contact replaced, and a recent change makes the payment change high risk ([R-15](../scenarios/lean-framework.md#how-the-rules-map); test 6) | Closed |
| A2 | Outside text arrives as a record, such as a portal comment claiming the call-back was done | Critical | Outside free text reaches agents only through the extractor, facts people decide on are computed, and the app needs a blind call-back record ([provenance](architecture.md#provenance-who-said-what); test 7) | Closed |
| A3 | Data leaves through a link or image that a preview fetches, with no click | Critical | Messages carry only text and the app's record links, nothing goes outside the organisation, and values are shown only in fields code fills in ([channels](architecture.md#channels); test 10) | Closed |
| A4 | Planted text steers the change reconciler's matches and the monthly sample | Critical | Code computes matches and draws samples, and every match on a sensitive field goes to internal controls ([R-08 and R-06](../scenarios/lean-framework.md#how-the-rules-map); test 23) | Closed |
| A5 | Deep Agents' own files and `AGENTS.md` become a memory nobody governs | High | Instructions and skills load read-only, file tools write only to scratch space wiped after each run, and attachments go to the extractor ([how an agent lives](architecture.md#how-an-agent-lives)) | Closed |
| A6 | The notebook, profiles and summaries make one injection last and spread | High | Marked runs can't write the notebook, notes come only from records, summaries keep source tags and are checked, and drafted values cite their source ([context](architecture.md#context-and-memory); [provenance](architecture.md#provenance-who-said-what); test 29) | Closed; R4 accepted |
| A7 | A spoofed email makes anyone "the person" an agent acts for | High | Only authenticated internal senders start runs, Reply-To is ignored, and other mail is treated as a document ([provenance](architecture.md#provenance-who-said-what)) | Closed |
| A8 | The extractor's output still steers, and its source tags are lost at the app | High | Fixed schemas, the page as shown compared with hidden text, sources carried into requests, and values from documents never approved automatically or used as contacts. A bank change rests on facts no document controls, such as the account-holder check ([data protection](architecture.md#data-protection); [collusion, forgery and ownership](../scenarios/lean-framework.md#collusion-forgery-and-ownership); test 26) | Closed; R5 accepted |
| A9 | A2A drops the limits of the person an agent acts for | High | The people travel with the call, and the agent called works within what they may all do ([agent to agent](architecture.md#agent-to-agent); test 11) | Closed |
| A10 | A model provider swaps the model silently, without a release | High | Models are pinned by provider, deployment, region and version, and checked on every call and response ([data protection](architecture.md#data-protection)) | Closed |
| A11 | Tool servers, skills and held calls are trusted too much | Medium | Tool servers can't ask people for input or run the model, skills are pinned in the release, and the gateway records held calls, signed, and makes them only after policy checks again ([proposals](architecture.md#proposals-and-approvals)) | Closed |
| A12 | A flood of junk requests drains the budget urgent chases need | Medium | Budgets per source and per person, a share kept for obligations, and outside parties rate-limited ([when things fail](architecture.md#when-things-fail)) | Closed |

### Insider

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| I1 | A delegate gets their own bank change confirmed by feeding it to an agent that acts for nobody | Critical | Requests name everyone whose words they came from, those people can't decide them, and such requests never go through at level 2 ([provenance](architecture.md#provenance-who-said-what); test 8) | Closed |
| I2 | Settings, decisions and the ledger are records the data team can change | Critical | Settings count only with their owner's sign-off, decisions carry the decider's signed sign-in, nobody writes decision records directly, the ledger records the settings version, and its daily anchor sits with internal controls ([policy](architecture.md#policy); [independence](architecture.md#independence); test 28) | Closed; R3 accepted |
| I3 | The data team approves its own enforcement | Critical | Changes to the kernel, gateways, packs, masking and the app's agent tools are releases, approved outside the data team after assurance re-runs the tests ([independence](architecture.md#independence); [starting values](starting-values.md); test 22) | Closed |
| I4 | The change reconciler checks the data team using the data team's own data | Critical | It reads internal controls' own extract of SAP changes, a decider from the data team doesn't make a match, and internal controls approve its releases and draw its samples ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 23) | Closed |
| I5 | Someone sees more through an agent, through a reminder, A2A or an agent with a wider grant | High | A run acts for everyone whose words it serves, reminders included, and the people travel with A2A calls ([provenance](architecture.md#provenance-who-said-what); test 11) | Closed |
| I6 | A mass change in small pieces: 300 drafts, a clean-up split by country, or a broad level-2 type | High | Drafts and requests count at every level, per piece of work that code defines, and level-2 types are defined by their fields and check ([policy](architecture.md#policy); test 5) | Closed |
| I7 | An agent moves up a level on its builders' own evidence | High | Code draws samples, people outside the building team grade them, and a release that changes behaviour needs new samples and the owner's fresh approval ([autonomy](agent-model.md#autonomy); test 21) | Closed |
| I8 | Someone steers the evidence other deciders see, through a note framing duplicates or a sample that skips their own requests | High | Packs and notes come only from records, samples skip the reviewer's own items, and requester–confirmer pairs are watched ([assurance](architecture.md#assurance); test 19) | Closed |
| I9 | Nobody owns the transition switch | High | Only the attribute owner and the GPDO turn it, with the app's test evidence, and an unreadable status counts as not moved ([transition](../scenarios/lean-framework.md#until-a-request-type-moves)) | Closed |
| I10 | The platform owner is a single point of control | High | Loosening anything needs someone outside the team that runs a5s and its manager's reporting line, and approvers and graders sit outside it too ([independence](architecture.md#independence); [starting values](starting-values.md)) | Closed |
| I11 | Ownership moves to a friendlier decider | Medium | Moves are checked against conflicting rights and sent to internal controls and the other GPDOs, and agents stay at level 1 on moved fields until the new owner sets their level ([collusion, forgery and ownership](../scenarios/lean-framework.md#collusion-forgery-and-ownership); test 30) | Closed; R6 accepted |
| I12 | An owner silences the chaser by withdrawing its approval | Medium | The GPDO is told of every withdrawal, and overdue cases keep escalating through the governance coordinator ([what a5s adds](../scenarios/lean-framework.md#what-a5s-adds); test 20) | Closed |

### Failure

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| F1 | An outage fix, such as a provider failover or turning on tracing, sends data round the gateways | Critical | Models are pinned, failover goes only to a model approved for the same data, and workers reach only the gateways and a5s's masking collector ([data protection](architecture.md#data-protection); test 14) | Closed |
| F2 | Failing closed has no degraded mode, and the data team holds the switch | High | Runs end and wait in the queue, a circuit breaker sends people to the governed process, and overriding a fail-closed rule is emergency access ([when things fail](architecture.md#when-things-fail); test 25) | Closed |
| F3 | During the transition, the vendor treats agents' flags as work orders | High | Flags go to a delegate, and the vendor acts only on the recorded decision ([transition](../scenarios/lean-framework.md#until-a-request-type-moves); test 24) | Closed in a5s, for the framework's owners to confirm |
| F4 | Approvals and withdrawals lag behind reality | High | The app checks with a5s before approving automatically, a suspension completes only when the app confirms, caches are cleared by change events, and level-2 settings record their approver ([proposals](architecture.md#proposals-and-approvals); [autonomy](agent-model.md#autonomy)) | Closed |
| F5 | Counts drift under parallel calls and retries | High | Counts are reserved with the policy decision, keys come from the piece of work, record and change, and a timed-out call is pending, not failed ([policy](architecture.md#policy); [how an agent lives](architecture.md#how-an-agent-lives)) | Closed |
| F6 | Someone else gets a person's conversation, through spoofed mail, a reused address or a group chat | High | Directory IDs, authenticated internal mail, no Reply-To, links instead of values in groups, and conversations archived when people leave ([provenance](architecture.md#provenance-who-said-what); [context](architecture.md#context-and-memory)) | Closed |
| F7 | The change reconciler's failures go to the team it checks | High | Each report states how much it covered, and an incomplete run alerts internal controls, who can run it again ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 23) | Closed |
| F8 | Repairing a thread steers an agent without a trace | High | Only the runtime writes thread state, the ledger records its hash, migrations are tested both ways, and editing by hand is emergency access ([independence](architecture.md#independence); [evidence](architecture.md#evidence)) | Closed |
| F9 | Every release resets the cap, so security patches wait | High | A release that changes only dependencies keeps the cap if its tests and re-run samples pass, advisories withdraw affected releases, and a failed drift test lowers the cap ([lifecycle](agent-model.md#lifecycle)) | Closed |
| F10 | One long conversation per person costs too much and loses facts | Medium | Each turn sends a capped context, budgets are per person, summaries are structured, checked by code and open to correction, and answers about the past retrieve the original turns ([context](architecture.md#context-and-memory); test 29) | Closed |
| F11 | Chasing fails across time zones and many instances | Medium | Due times come from the app, people have time zones and holidays, urgent items go to someone at work, and digests and limits are per person ([channels](architecture.md#channels); tests 15 and 17) | Closed |

### Colleague

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| C1 | The notebook carries one person's words to everyone | High | Notes come only from records and tool results, take the highest class of their sources, and load only for people who may see that class ([context](architecture.md#context-and-memory); test 11) | Closed |
| C2 | Only requesters get a conversation, so a delegate who replies to a chase gets no answer | High | Every release has a message trigger that acts for the sender, and the request assistant wakes when its drafts are decided ([how an agent lives](architecture.md#how-an-agent-lives); test 12) | Closed |
| C3 | What people tell an agent never reaches the case, so the chases keep coming | High | A "waiting on" note the person confirms goes on the case and pauses chases, with one obligation per record and person ([how an agent lives](architecture.md#how-an-agent-lives); test 16) | Closed |
| C4 | When an agent can't run, it goes silent | High | The channel service replies in code, names who to ask, and hands urgent obligations on, and budgets are kept per person ([channels](architecture.md#channels); test 25) | Closed |
| C5 | One person faces many bots, each with its own digest | High | One identity per agent, one digest and limit per person, one request assistant across domains [TBC], and context that follows a part split ([channels](architecture.md#channels); test 17) | Closed |
| C6 | Handoffs drop the requester's context and the agent's flags | Medium | A handoff note goes with the work, flags go on the request itself, and recurring flags become checks ([proposals](architecture.md#proposals-and-approvals)) | Closed |
| C7 | One thread forever, with no reset and summaries nobody sees | Medium | Topics with an index and a fresh start, open and versioned summaries, and cut-off runs that release their thread ([context](architecture.md#context-and-memory)) | Closed |
| C8 | Learning is slow, and every release resets earned trust | Medium | Preferences listed in each release and kept in profiles, dependency-only releases that keep the cap, and new releases that earn trust in shadow while the old one keeps working ([lifecycle](agent-model.md#lifecycle); test 31) | Closed |
| C9 | A group chat has no thread of its own | Medium | Each group has its own thread, and the agent shares only what everyone present may see ([context](architecture.md#context-and-memory)) | Closed |
| C10 | The extractor can't answer questions about a document, so people paste it into other tools | Medium | The extractor can answer in free text, marked as outside content, and never used as an instruction or a value ([data protection](architecture.md#data-protection)) | Closed |

## Round 1 follow-up

Round 1 left seven risks open. Each now has an answer:

| Open risk | Answer | Where |
| --- | --- | --- |
| A requester and a delegate colluding | Bank changes rest on facts nobody in the case controls, the app picks the confirmer at random, internal controls re-perform call-backs on a sample, and collusion is looked for afterwards | [Collusion, forgery and ownership](../scenarios/lean-framework.md#collusion-forgery-and-ownership); tests 26 and 27 |
| Forged documents | A document is never the evidence for a bank change: the account-holder check, the contact's age and the channel are | The same section; test 26 |
| Misleading context, and a compromised model provider | Drafted values cite their source, facts are shown apart from the agent's narrative, and a model from another provider checks narratives on sensitive decisions | [Provenance](architecture.md#provenance-who-said-what); [data protection](architecture.md#data-protection); test 29 |
| The builders' reach | Loosening anything needs someone outside the team, and decisions carry their decider's signed sign-in | [Independence](architecture.md#independence); test 28 |
| Ownership moved to a friendlier decider | Moves are checked against conflicting rights and sent to internal controls and the other GPDOs | [Collusion, forgery and ownership](../scenarios/lean-framework.md#collusion-forgery-and-ownership); test 30 |
| Summaries and trust | Summaries are structured and checked, answers about the past retrieve the original turns, and new releases earn trust in shadow | [Context](architecture.md#context-and-memory); [lifecycle](agent-model.md#lifecycle); tests 29 and 31 |
| Names and numbers | Each has a starting value, for its owner to confirm | [Starting values](starting-values.md) |

Round 2 then attacked these answers and found gaps in the first four, closed [below](#what-round-2-found).

## What round 2 found

Round 2 attacked the follow-up's new controls from two angles, fraud and control, and operations and colleagues. It found 21 problems: 7 critical, 10 high and 4 medium. Most showed the first answers were too narrow: they covered bank details but not other ways to redirect a payment, compared against data a fraudster could change first, sent the riskiest changes to one predictable person, and signed a sign-in rather than a decision. All 21 are now closed.

### Fraud and control

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| D1 | Payments redirected through an alternative payee, without touching bank details | Critical | Every change to where payments go gets the same facts, matched against the supplier whose invoices are paid ([collusion, forgery and ownership](../scenarios/lean-framework.md#collusion-forgery-and-ownership); test 26) | Closed |
| D2 | The supplier's name and country are changed first, so a later account in the new name matches | Critical | The account holder is matched against the name and country as they stood 90 days before, a recent change to either makes the change high risk, and a close match or no answer confirms nothing (test 27) | Closed |
| D3 | Patience beats the contact's age: a contact a forged letter changed 91 days before passes | Critical | Call-backs go to the contact a newer one replaced, any contact change in the last 12 months makes a payment change high risk, and internal controls call a number from outside SAP (test 27) | Closed |
| D4 | The riskiest changes go to one predictable person, and internal controls' re-call has no deadline | Critical | A high-risk change needs the attribute owner and a second confirmer drawn at random, and can't be used until internal controls have re-performed the call-back. Eligibility is checked live against buying and payment rights, and naming a delegate goes through the conflict check (test 26) | Closed |
| D5 | A signed sign-in doesn't sign the decision, so it can be reused for another | Critical | Each decision is signed on the decider's own device, for that one decision, showing the supplier and the account's last digits, and signatures work once ([independence](architecture.md#independence); test 30) | Closed |
| D6 | The builders build the new controls and the tests that judge them | High | The app's assignment, account-holder check, risk scoring and call-back enforcement change like enforcement, and assurance holds their tests ([independence](architecture.md#independence)) | Closed |
| D7 | Withdrawing and resubmitting re-rolls the random draw, and the pair alert misses a single fraud | High | The draw stays with the record and field for 90 days, redraws are logged, pair alerts count withdrawals and rejections, and every change the bank can't confirm gets internal controls' call before use (test 29) | Closed |
| D8 | The people being watched can switch the detection off | High | Collusion checks run as code internal controls own, their flags go straight to internal controls, hashes are keyed, and stopping anything that detects counts as loosening (test 33) | Closed |
| D9 | The channel score rewards account takeover | High | The channel can only add risk, and a portal change soon after a password reset or from a new device is high risk | Closed |

### Operations and colleagues

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| O1 | A blocked call-back pack leaves no safe way forward, so the owner rings the number on file | Critical | Code offers the contact a newer one replaced, or the one verified when the supplier was set up, and the app accepts call-back records only for contacts code offered (test 28) | Closed |
| O2 | High-risk changes get a predictable confirmer and a late re-call | Critical | As D4 | Closed |
| O3 | Confirmation stalls when the person drawn is away, and the bank can't check many accounts | High | The draw is only from people at work, it's drawn again if nobody opens it by half the turnaround, the owner has a standing alternate, and a close match or no answer goes to the normal draw, with the holder confirmed on the call-back and by internal controls | Closed |
| O4 | The counting backstop switches busy assistants off mid-month | High | Case packs and reports don't count, and the backstop counts per person acted for and change type, or per check ([policy](architecture.md#policy); test 35) | Closed |
| O5 | Releases can't be rolled back or patched fast | High | An instance can go straight back to the release before, new releases take level-0 and level-1 work at once, shadow runs are dry, and information security decides in advance which advisories withdraw a release ([lifecycle](agent-model.md#lifecycle); test 34) | Closed |
| O6 | The measures of people flag diligent reviewers, and need consent | High | Reviewers are flagged on outcomes, not speed, pair alerts fire only beyond what random drawing explains, and the measures are agreed with the data protection officer and works councils before they start ([assurance](architecture.md#assurance)) | Closed |
| O7 | The context cap has no rule for what happens when it's reached | High | A budget for each part of the context, tested at release, only the instructions and skills for the parts in play, and an offer to take a long paste as a document ([context](architecture.md#context-and-memory)) | Closed |
| O8 | The samples prove little and cost a lot | High | A sequential test at 95% confidence, pooled across a release's instances, and ongoing samples sized to what they need to detect ([starting values](starting-values.md)) | Closed |
| O9 | Chases arrive with the escalation | Medium | A chase goes in the last digest before half the turnaround, and escalation waits at least a working day after it ([channels](architecture.md#channels)) | Closed |
| O10 | A sign-in for every decision breeds approval fatigue | Medium | Payment changes are signed one at a time, other sensitive changes as a reviewed batch, and every signature is bound to what it signs ([independence](architecture.md#independence)) | Closed |
| O11 | The second model has no rule for outages or disagreement | Medium | It never holds up a decision, the decision surface shows when it didn't run, and a checker whose flags rarely hold up is replaced ([provenance](architecture.md#provenance-who-said-what)) | Closed |
| O12 | A quiet December sets the budgets | Medium | The first budgets come from current request volumes, with a warning at 80% and obligations protected at 100% ([when things fail](architecture.md#when-things-fail)) | Closed |

## Accepted risks

Some risk no design removes. These remain after round 2, and each needs its owner to accept it:

| # | Risk | Why it stays | Accepted by |
| --- | --- | --- | --- |
| R1 | Three or more people colluding, including someone who checks them, such as internal controls' caller | Every control relies on someone in it being honest | The GPDOs |
| R2 | A supplier that is itself the fraudster, with a genuine account in its own name. It's narrowed by matching new suppliers' addresses, phone numbers and tax IDs against employees'. | The account-holder check and the call-back confirm what the supplier says | The GPDOs |
| R3 | The identity provider, or the environment the organisation's own models run in, being compromised. It's narrowed by holding decisions for 24 hours after an authenticator is reset. | Signed decisions and pinned models rest on them | The executive the GPDOs and the platform owner report to, since information security approves the models |
| R4 | A person misled by an agent despite the facts, the source flags and the second model's check. It's narrowed by the blind call-back, which doesn't depend on what the person believes. | People still decide | The GPDOs, with training on deciding from the facts |
| R5 | A forged document for a field that isn't sensitive and feeds no other control, where a person decides with the value flagged as coming from a document | Not every field justifies independent verification | Each attribute owner, through what their profile marks as sensitive |
| R6 | The GPDOs choosing, in plain sight, an ownership that creates a conflict | It's their right under the charter | The executive the GPDOs report to, as the charter's escalation already has it, with internal controls told |

## For the lean framework's owners

a5s answers these for itself, without changing the framework, but the framework's owners may want to address them in it:

- **R-15** verifies bank details with "contact details that weren't changed along with it". A contact changed weeks before passes, and so does a change to the verification contact itself, which needs confirming under R-13 but no call-back (A1, D3). R-15 also covers only bank details, while an alternative payee or a payment method can redirect payments just as well (D1). a5s applies its checks to every field that decides where payments go, and calls back the contact a newer one replaced.
- **High-risk payment changes.** a5s's defaults need a second confirmer, drawn at random, and internal controls' call-back before a high-risk change is used (D4). That goes beyond the charter's two people for a sensitive change.
- **Level 1 and the request assistant.** The rulebook's level 1 has the attribute owner or a delegate approve each proposal, while the request assistant's drafts are submitted by requesters, as their own requests.
- **The transition.** The transition notes ask the vendor to act on what agents flag. a5s sends flags to a delegate first (F3).
- **Who approves.** Nobody is named to run an agent's design review, approve its model, or approve changes to the enforcement around it (I3, I10). The [starting values](starting-values.md) propose information security.
- **Payment runs.** Keep Verification of Payee switched on for supplier payment files, which banks let companies opt into for bulk payments, so a name that doesn't match the account shows before money moves.
- **Ownership conflicts.** Consider making internal controls' review a rule for ownership changes that put a sensitive field with people who hold conflicting rights.
- **Measures of people.** The operating model's own measures of how many decisions owners make and how long requests wait watch people too, and need the same agreement with the data protection officer and works councils (O6).

## Next round

Round 3 starts from the accepted risks, from any change to the design since round 2, and from the code once it exists.
