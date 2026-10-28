# Design Critique

**Status:** Round 1, 28 October 2026 · **Design:** [a5s](../README.md)

Every change to the design gets an adversarial review before it settles. Reviewers who didn't write the design read it cold, each from one angle, and look for loopholes: ways to get round it, abuse it, or make it fail. Each finding is checked against the documents before it's accepted. This page records what each round found and how the design answers it.

- **Closed** means the design now stops it, and a test in the [baseline](../scenarios/lean-framework.md#passing-the-baseline) or a5s's own suite will show it.
- **Reduced** means it's now harder, or caught afterwards, but still possible. What remains is under [still open](#still-open).

## How we critique

| Angle | Asks |
| --- | --- |
| Outside attacker | How could a fraudster, a malicious document, a tool server or a model provider get money, data or disruption out of it? |
| Insider | How could people inside, alone or together, get round the rules, or use the agents to? |
| Failure | What breaks, and what do people do when it does? |
| Colleague | Would people treat the agents as colleagues and keep using them, or route around them? |

Two earlier fresh reads checked the design's consistency and its faithfulness to the lean framework. Round 1 was the first adversarial one.

## What round 1 found

45 loopholes: 9 critical, 25 high and 11 medium. The design now closes 38 and reduces 7. Most came from five things the first design lacked:

1. **Whose words.** Agents couldn't tell outside words from inside ones, or who had prompted a request. [Provenance](architecture.md#provenance-who-said-what) answers this.
2. **Facts from code.** Agents wrote the facts people decided on, such as which contact to call back or whether two changes matched. Code now computes them.
3. **Independence.** The data team approved its own enforcement and held the only evidence. [Independence](architecture.md#independence) answers this.
4. **Failing safely.** Failing closed stopped the business, and only the data team could reopen it. [When things fail](architecture.md#when-things-fail) answers this.
5. **Colleagues.** Only requesters could talk to an agent, contact was counted per agent instead of per person, and what people said never reached the case. [How an agent lives](architecture.md#how-an-agent-lives) and [channels](architecture.md#channels) answer this.

### Outside attacker

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| A1 | A fraudster gets a supplier's verification phone changed first, then sends the bank letter weeks later, so the call-back reaches them | Critical | Code chooses the call-back contact, only from fields unchanged for [TBC: 90 days], and a newer one blocks the pack ([R-15](../scenarios/lean-framework.md#how-the-rules-map); test 6) | Closed |
| A2 | Outside text arrives as a record, such as a portal comment claiming the call-back was done | Critical | Outside free text reaches agents only through the extractor, facts people decide on are computed, and the app needs the confirmer's own call-back record ([provenance](architecture.md#provenance-who-said-what); test 7) | Closed |
| A3 | Data leaves through a link or image that a preview fetches, with no click | Critical | Messages carry only text and the app's record links, nothing goes outside the organisation, and values are shown only in fields code fills in ([channels](architecture.md#channels); test 10) | Closed |
| A4 | Planted text steers the change reconciler's matches and the monthly sample | Critical | Code computes matches and draws samples, and every match on a sensitive field goes to internal controls ([R-08 and R-06](../scenarios/lean-framework.md#how-the-rules-map); test 23) | Closed |
| A5 | Deep Agents' own files and `AGENTS.md` become a memory nobody governs | High | Instructions and skills load read-only, file tools write only to scratch space wiped after each run, and attachments go to the extractor ([how an agent lives](architecture.md#how-an-agent-lives)) | Closed |
| A6 | The notebook, profiles and summaries make one injection last and spread | High | Marked runs can't write the notebook, notes come only from records, and summaries keep source tags ([context](architecture.md#context-and-memory)) | Reduced |
| A7 | A spoofed email makes anyone "the person" an agent acts for | High | Only authenticated internal senders start runs, Reply-To is ignored, and other mail is treated as a document ([provenance](architecture.md#provenance-who-said-what)) | Closed |
| A8 | The extractor's output still steers, and its source tags are lost at the app | High | Fixed schemas, the page as shown compared with hidden text, sources carried into requests, and values from documents never approved automatically or used as contacts ([data protection](architecture.md#data-protection)) | Reduced |
| A9 | A2A drops the limits of the person an agent acts for | High | The people travel with the call, and the agent called works within what they may all do ([agent to agent](architecture.md#agent-to-agent); test 11) | Closed |
| A10 | A model provider swaps the model silently, without a release | High | Models are pinned by provider, deployment, region and version, and checked on every call and response ([data protection](architecture.md#data-protection)) | Closed |
| A11 | Tool servers, skills and held calls are trusted too much | Medium | Tool servers can't ask people for input or run the model, skills are pinned in the release, and the gateway records held calls, signed, and makes them only after policy checks again ([proposals](architecture.md#proposals-and-approvals)) | Closed |
| A12 | A flood of junk requests drains the budget urgent chases need | Medium | Budgets per source and per person, a share kept for obligations, and outside parties rate-limited ([when things fail](architecture.md#when-things-fail)) | Closed |

### Insider

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| I1 | A delegate gets their own bank change confirmed by feeding it to an agent that acts for nobody | Critical | Requests name everyone whose words they came from, those people can't decide them, and such requests never go through at level 2 ([provenance](architecture.md#provenance-who-said-what); test 8) | Closed |
| I2 | Settings, decisions and the ledger are records the data team can change | Critical | Settings count only with their owner's sign-off, the ledger records the settings version, and its daily anchor sits with internal controls ([policy](architecture.md#policy); [independence](architecture.md#independence)) | Reduced |
| I3 | The data team approves its own enforcement | Critical | Changes to the kernel, gateways, packs, masking and the app's agent tools are releases, approved outside the data team after assurance re-runs the tests ([independence](architecture.md#independence); test 22) | Closed, once the approver is named |
| I4 | The change reconciler checks the data team using the data team's own data | Critical | It reads internal controls' own extract of SAP changes, a decider from the data team doesn't make a match, and internal controls approve its releases and draw its samples ([R-08](../scenarios/lean-framework.md#how-the-rules-map); test 23) | Closed |
| I5 | Someone sees more through an agent, through a reminder, A2A or an agent with a wider grant | High | A run acts for everyone whose words it serves, reminders included, and the people travel with A2A calls ([provenance](architecture.md#provenance-who-said-what); test 11) | Closed |
| I6 | A mass change in small pieces: 300 drafts, a clean-up split by country, or a broad level-2 type | High | Drafts and requests count at every level, per piece of work that code defines, and level-2 types are defined by their fields and check ([policy](architecture.md#policy); test 5) | Closed |
| I7 | An agent moves up a level on its builders' own evidence | High | Code draws samples, people outside the building team grade them, and a release that changes behaviour needs new samples and the owner's fresh approval ([autonomy](agent-model.md#autonomy); test 21) | Closed |
| I8 | Someone steers the evidence other deciders see, through a note framing duplicates or a sample that skips their own requests | High | Packs and notes come only from records, samples skip the reviewer's own items, and requester–confirmer pairs are watched ([assurance](architecture.md#assurance); test 19) | Closed |
| I9 | Nobody owns the transition switch | High | Only the attribute owner and the GPDO turn it, with the app's test evidence, and an unreadable status counts as not moved ([transition](../scenarios/lean-framework.md#until-a-request-type-moves)) | Closed |
| I10 | The platform owner is a single point of control | High | Approvers and graders sit outside their reporting line, and resuming someone else's suspension or replacing an agent owner needs a GPDO ([independence](architecture.md#independence); [what a5s adds](../scenarios/lean-framework.md#what-a5s-adds)) | Reduced |
| I11 | Ownership moves to a friendlier decider | Medium | Level 2 drops to 1 when a field's owner or part changes, loosening changes are raised on their own, and measures go to the GPDOs directly ([autonomy](agent-model.md#autonomy)) | Reduced |
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
| F10 | One long conversation per person costs too much and loses facts | Medium | Each turn sends a capped context, budgets are per person, and summaries are open to the person to correct ([context](architecture.md#context-and-memory)) | Reduced |
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
| C8 | Learning is slow, and every release resets earned trust | Medium | Preferences listed in each release and kept in profiles, dependency-only releases that keep the cap, shadow runs, and review times weighted by size ([lifecycle](agent-model.md#lifecycle)) | Reduced |
| C9 | A group chat has no thread of its own | Medium | Each group has its own thread, and the agent shares only what everyone present may see ([context](architecture.md#context-and-memory)) | Closed |
| C10 | The extractor can't answer questions about a document, so people paste it into other tools | Medium | The extractor can answer in free text, marked as outside content, and never used as an instruction or a value ([data protection](architecture.md#data-protection)) | Closed |

## For the lean framework's owners

a5s answers these for itself, without changing the framework, but the framework's owners may want to address them in it:

- **R-15** verifies bank details with "contact details that weren't changed along with it". A contact changed weeks before passes, and so does a change to the verification contact itself, which needs confirming under R-13 but no call-back (A1).
- **Level 1 and the request assistant.** The rulebook's level 1 has the attribute owner or a delegate approve each proposal, while the request assistant's drafts are submitted by requesters, as their own requests.
- **The transition.** The transition notes ask the vendor to act on what agents flag. a5s sends flags to a delegate first (F3).
- **Who approves.** Nobody is named to run an agent's design review, approve its model, or approve changes to the enforcement around it (I3, I10).

## Still open

- **Collusion.** A requester and a delegate who collude can still push one false change through. a5s watches pairs, and R-15's call-back stays the main control.
- **Forged documents.** A convincing forged document still produces values that a person has to catch (A8).
- **Misleading context.** An injection can still mislead the person it reaches (A6), and a compromised model provider writes every draft people read (A10).
- **The builders' reach.** The data team still builds the unified app that records decisions (I2), and the platform owner still names agent owners and runs the team (I10).
- **Ownership.** A GPDO can still move ownership to a friendlier decider, though now in plain sight (I11).
- **Summaries and trust.** A summary can still drop a detail (F10), and a release that changes how an agent works still starts at level 1 (C8).
- **Names and numbers.** Who approves releases, packs and models, who grades samples, and the windows, budgets, caps and contact age marked [TBC].

## Next round

Round 2 starts from what's still open, from any change to the design since round 1, and from the code once it exists.
