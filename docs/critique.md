# Design Critique

**Status:** Rounds 1 to 4, 29 October 2026 · **Design:** [a5s](../README.md)

Every change to the design gets an adversarial review before it settles. Reviewers who didn't write the design read it cold, each from one angle, and each finding is checked against the documents before it's accepted. This page records the findings about a5s, how the design answers them now, and what each round removed.

- **Designed** means the design stops it, and a test in a5s's own suite will show it once it's built.
- **Fixed** means the code stops it, and a test in a5s's own suite shows it. Round 4 is the first round of findings about code.
- **Phase 2** and **Phase 3** mean it's designed for a feature that comes in that phase. Until then, neither the feature nor the loophole exists.
- **Accepted** marks what's left once the design has done what it can: a risk its owner accepts under [accepted risks](#accepted-risks).
- **Removed** means a later round removed the control the finding was about.

## How we critique

| Angle | Asks |
| --- | --- |
| Outside attacker | How could a malicious document, sender, tool server or model provider get data or disruption out of it? |
| Insider | How could people inside, alone or together, get round the rules, or use the agents to? |
| Failure | What breaks, and what do people do when it does? |
| Colleague | Would people treat the agents as colleagues and keep using them, or route around them? |
| Builder and funder | What would a team build first, what does it cost, and what can go or wait? |
| Second scenario | Would it work for a different scenario, such as an [IT service desk](../scenarios/it-service-desk.md), without changing a5s? |

Every round reports the rules it added and the rules it removed, and proposes cuts.

## The rounds

- **Round 1** found 45 loopholes and **round 2** found 21. Both read a5s through its first scenario, a master data governance framework, so many findings were about that scenario's own controls, and every answer added rules to a5s. Neither removed anything, and the design doubled in size.
- **Round 3** read the design with fresh eyes and found it had drifted into that scenario. It cut a5s back to a small trusted core, a scenario contract and a phase-1 plan ([below](#round-3-fresh-eyes)). A consistency read then fixed the gaps between the documents.
- **Then the scenario was removed** from a5s, with the findings that were only about its controls, so that a5s's design depends on no one scenario. The findings below are those about a5s itself, in general terms.
- **Round 4** read the code phase 1's first step built, with three reviewers who hadn't written it, from all six angles. It found 22 problems, two of them critical, and removed the parts that let services stand between people and the core ([below](#round-4-the-code)).

## Findings about a5s

### Outside attacker

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| A2 | Outside text arrives as a record, such as a comment claiming a check was done | Critical | Outside free text reaches agents only through the extractor, facts people decide on are computed, and an agent can't say a check was done ([provenance](architecture.md#provenance-who-said-what)) | Phase 2 |
| A3 | Data leaves through a link or image that a preview fetches, with no click | Critical | Messages and drafts carry only text and the scenario's record links, and messages go only to the audience the settings name ([channels](architecture.md#channels)) | Designed |
| A4 | Planted text steers what a check reports | Critical | Checks compute their results in code, and a scenario can mark an agent as a check, so stopping or changing it needs the scenario's assurance ([independence](architecture.md#independence)) | Designed |
| A5 | Deep Agents' own files and `AGENTS.md` become a memory nobody governs | High | Instructions and skills load read-only from the release, scratch files last one run, and Deep Agents' editable memory isn't used ([what a5s uses from Deep Agents](architecture.md#what-a5s-uses-from-deep-agents)) | Designed |
| A6 | Profiles and summaries make one injection last and spread | High | Marked runs can't write profiles, summaries hold facts by handle and are checked by code, and there's no notebook until phase 3 ([context](architecture.md#context-and-memory)) | Designed; R4 accepted |
| A7 | A spoofed email makes anyone "the person" an agent acts for | High | Only people the directory knows start runs, email only from senders who pass DMARC and match the directory, Reply-To is ignored, and other mail is treated as a document ([channels](architecture.md#channels)) | Designed |
| A8 | The extractor's output still steers, and its sources are lost downstream | High | The extractor has no tools and fixed schemas, values from documents carry their source as handles, and a pack can refuse to approve them automatically or use them as contacts ([data protection](architecture.md#data-protection)) | Phase 2 |
| A9 | A2A drops the limits of the person an agent acts for | High | The people travel with the call, and authority never passes between agents ([agent to agent](architecture.md#agent-to-agent)) | Phase 3 |
| A10 | A model provider swaps the model silently, without a release | High | Models are pinned by provider, deployment, region and version, and the model gateway checks every call ([data protection](architecture.md#data-protection)) | Designed |
| A11 | Tool servers, skills and held calls are trusted too much | Medium | Skills and tool schemas are pinned in the release, the gateway refuses tool servers' requests to ask people for input or run the model, and held calls are made through the gateway like any call ([data protection](architecture.md#data-protection)) | Designed |
| A12 | A flood of junk requests drains the budget urgent chases need | Medium | Budgets per person and per source of triggers, a share kept for obligations, and outside parties rate-limited ([when things fail](architecture.md#when-things-fail)) | Designed |

### Insider

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| I1 | Someone gets their own change approved by feeding it to an agent that acts for nobody | Critical | Requests name everyone whose words they came from, and none of them may decide it. A pack can also rule out level 2 for such requests ([provenance](architecture.md#provenance-who-said-what)) | Phase 2 |
| I2 | Settings, decisions and the ledger are records the team that runs a5s can change | Critical | Unsigned settings don't count, decisions on sensitive items are signed one by one, the ledger records the settings version, and its hourly anchor sits with assurance ([a call, step by step](architecture.md#a-call-step-by-step); [evidence](architecture.md#evidence)) | Designed; R3 accepted |
| I3 | The team that runs a5s approves its own enforcement | Critical | Changes to the trusted core and policy packs need an approver from outside the team, an attested build and assurance's tests, and releases pin tools' schemas, so a changed tool needs that approver too ([independence](architecture.md#independence)) | Designed |
| I5 | Someone sees more through an agent, through a reminder, A2A or an agent with a wider grant | High | A run acts for everyone whose words it serves, reminders included, and sees only what they may all see ([context](architecture.md#context-and-memory)) | Designed |
| I6 | A large change made in small pieces | High | Counts per piece of work that code defines, across runs and types of action ([policy](architecture.md#policy)) | Phase 2 |
| I7 | An agent moves up a level on its builders' own evidence | High | Code draws samples, people outside the team that built it grade them, and the part owner decides ([autonomy](agent-model.md#autonomy); [assurance](architecture.md#assurance)) | Phase 2 |
| I8 | Someone steers the evidence other deciders see | High | Case briefs come from records, facts are computed and shown apart from the agent's narrative, and samples skip the reviewer's own items ([provenance](architecture.md#provenance-who-said-what)) | Designed |
| I10 | The platform owner is a single point of control | High | Loosening anything needs someone outside the team that runs a5s and its manager's reporting line, and is reported to assurance ([independence](architecture.md#independence)) | Designed |
| I11 | A field moves to a friendlier owner | Medium | A level-2 setting drops to level 1 when its part or owner changes, until the new owner sets it ([autonomy](agent-model.md#autonomy)) | Phase 2 |
| I12 | An owner silences the chases by withdrawing an agent's approval | Medium | Obligations escalate in code along the scenario's chain when no approved agent can act on them ([channels](architecture.md#channels)) | Designed |

### Failure

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| F1 | An outage fix, such as a provider failover or turning on tracing, sends data round the gateways | Critical | Models are pinned, failover goes only to a model approved for the same data, and workers reach nothing but the gateways ([data protection](architecture.md#data-protection)) | Designed |
| F2 | Failing closed has no degraded mode, and one team holds the switch | High | Runs end and their triggers wait, a circuit breaker pauses new runs, the channel service tells people to carry on in the scenario's own process, and overriding a fail-closed rule needs someone outside the team ([when things fail](architecture.md#when-things-fail)) | Designed |
| F4 | Approvals and withdrawals lag behind reality | High | Settings are cached for at most 30 seconds and a change clears the cache, and level-2 settings record their approver ([a call, step by step](architecture.md#a-call-step-by-step); [autonomy](agent-model.md#autonomy)) | Designed |
| F5 | Counts drift under parallel calls and retries | High | Counts are reserved in the same transaction as the policy decision, and keys come from the piece of work, the record and the change ([a call, step by step](architecture.md#a-call-step-by-step)) | Phase 2 |
| F6 | Someone else gets a person's conversation, through spoofed mail, a reused address or a group chat | High | Directory identities, DMARC-checked mail, no Reply-To, conversations archived when people leave, and no group conversations until phase 3 ([channels](architecture.md#channels); [context](architecture.md#context-and-memory)) | Designed |
| F8 | Repairing a thread steers an agent without a trace | High | Run threads last one run, so there's no saved state to repair, and conversations are a5s's own records, written only by the context service ([context](architecture.md#context-and-memory)) | Designed |
| F9 | Every release resets earned trust, so security patches wait | High | Releases are proportionate, and a security fix goes in at once, at level 1 at most ([independence](architecture.md#independence); [lifecycle](agent-model.md#lifecycle)) | Designed |
| F10 | One long conversation per person costs too much and loses facts | Medium | Each run starts fresh with a context assembled within a budget, summaries are checked by code, and answers about the past retrieve the original turns ([context](architecture.md#context-and-memory)) | Designed |
| F11 | Chasing fails across time zones and many instances | Medium | Escalation follows working hours, and digests and limits are per person ([channels](architecture.md#channels)) | Designed |

### Colleague

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| C1 | A notebook carries one person's words to everyone | High | No notebook until phase 3. When it comes, notes come only from records and tool results ([context](architecture.md#context-and-memory)) | Phase 3 |
| C2 | Only some people get a conversation, so someone who replies to a chase gets no answer | High | Every agent can be talked to, and a reply starts a run that acts for the sender ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| C3 | What people tell an agent never reaches the work, so the chases keep coming | High | A person can say what they're waiting on, which pauses chases until the date they give ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| C4 | When an agent can't run, it goes silent | High | The channel service says so in code and names who to ask ([channels](architecture.md#channels)) | Designed |
| C5 | One person faces many bots, each with its own digest | High | One digest and one limit per person from all the agents, and one conversation per person per agent ([channels](architecture.md#channels); [context](architecture.md#context-and-memory)) | Designed |
| C6 | Handoffs drop the context and the agent's flags | Medium | Drafts and requests carry a handoff note and the agent's flags ([proposals](architecture.md#proposals-and-approvals)) | Designed |
| C7 | One thread forever, with no reset and summaries nobody sees | Medium | Topics, summaries the person can see and correct, and a fresh thread for every run ([context](architecture.md#context-and-memory)) | Designed |
| C8 | Agents don't learn how people like to work | Medium | Typed preferences and a "how I like to work" note in each profile ([context](architecture.md#context-and-memory)) | Designed |
| C9 | A group chat has no conversation of its own | Medium | Group conversations come in phase 3 ([context](architecture.md#context-and-memory)) | Phase 3 |
| C10 | The extractor can't answer questions about a document, so people paste it into other tools | Medium | The extractor can answer in free text, marked as outside content and never used as an instruction ([data protection](architecture.md#data-protection)) | Phase 2 |

### Builder and operator

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| D5 | A signed sign-in doesn't sign the decision, so it can be reused for another | Critical | Each decision on a sensitive item is signed for that one decision, and a signature works once ([proposals](architecture.md#proposals-and-approvals)) | Phase 2 |
| D6 | The builders build the controls and the tests that judge them | High | Assurance holds the tests for the trusted core, and changes to it need an outside approver ([independence](architecture.md#independence)) | Designed |
| D8 | The people being watched can switch the detection off | High | Stopping or changing an agent the scenario marks as a check needs the scenario's assurance ([independence](architecture.md#independence)) | Designed |
| O4 | A counting backstop switches busy assistants off mid-month | High | Only requests and changes count, per person acted for and type of action ([starting values](starting-values.md)) | Phase 2 |
| O5 | Releases can't be rolled back or patched fast | High | An instance can go straight back to the release before, and a security fix goes in at once ([lifecycle](agent-model.md#lifecycle)) | Designed |
| O6 | Measures of people flag diligent reviewers, and need consent | High | Measures of people judge outcomes, not speed, and are agreed with the data protection officer, and works councils where there are any, before they start ([assurance](architecture.md#assurance)) | Designed |
| O7 | The context cap has no rule for what happens when it's reached | High | A budget for each part of the context, tested at release ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| O8 | Samples prove little and cost a lot | High | A sequential test at 95% confidence, pooled across a release's instances ([starting values](starting-values.md)) | Phase 2 |
| O9 | Chases arrive with the escalation | Medium | A chase comes well before the escalation, which waits at least a working day after it ([starting values](starting-values.md)) | Designed |
| O10 | A sign-in for every decision breeds approval fatigue | Medium | Only decisions on sensitive items are signed one by one ([proposals](architecture.md#proposals-and-approvals)) | Phase 2 |
| O11 | A second model checking narratives has no rule for outages or disagreement | Medium | Round 3 removed the second model | Removed |
| O12 | A quiet month sets the budgets | Medium | Budgets come from current volumes, with obligations protected ([starting values](starting-values.md)) | Designed |

## Round 3: fresh eyes

Two readers who hadn't seen the design read it whole: an owner, for generality, colleague feel, proportionate governance, value and readability, and an engineer, for coherence, buildability, focus and clarity. Both found the safety thinking strong, and both found a governance specification rather than an agent OS a team could build.

| Owner's view | Score out of 5 | Engineer's view | Score out of 5 |
| --- | --- | --- | --- |
| Generality | 2 | Coherence | 3 |
| Colleague feel | 3 | Buildability | 2 |
| Proportionate governance | 2 | Focus | 2 |
| Clarity of value | 2 | Clarity | 3 |
| Readability | 3 | | |

| # | Finding | How the design answers it |
| --- | --- | --- |
| S1 | The first scenario's rules sat in a5s's core. "A request from a person's words never goes through at level 2" would block "reset my password" on a service desk, and "inside only" would shut out new joiners. | They left a5s's core. Its base pack only records who a run acts for and keeps them from deciding what they're named on, and the [IT service desk](../scenarios/it-service-desk.md) checks this on paper. |
| S2 | There was no contract for scenarios, and a5s had no settings store or decision surface of its own | The [scenario contract](architecture.md#the-scenario-contract), with a5s's defaults and its own sample scenario |
| S3 | Source tags can't travel with a value once a model rewrites it as text | [Provenance](architecture.md#provenance-who-said-what) at three grains: marked runs, handles for sensitive values, and exact matching of typed values |
| S4 | One LangGraph thread forever meant custom summaries, and migrations on every upgrade | A fresh thread for each run, with conversations as a5s's own records ([context](architecture.md#context-and-memory)) |
| S5 | "Enforcement" covered everything, so every change needed outside approval | A small [trusted core](architecture.md#the-trusted-core-and-the-rest), and [proportionate releases](architecture.md#independence) |
| S6 | The path each call takes was unspecified, and no ledger can be impossible to change | [A call, step by step](architecture.md#a-call-step-by-step), and a hash-chained ledger anchored every hour, which makes it tamper-evident ([evidence](architecture.md#evidence)) |
| S7 | There was no first version | [Phase 1](phase-1.md): the core, conversations and two reference agents of a5s's own, against its sample scenario |
| S8 | Agents couldn't keep their own promises, or learn how people like to work | Promises and reminders as typed tools that people confirm, and a "how I like to work" note in each profile |
| S9 | A person talked to a separate memory for each part | One conversation per person per agent, with each part's scope enforced at the tools |
| S10 | News waited in the digest with the chases | Outcomes people are waiting for go at once, within a limit per person |
| S11 | The case for building it was about control, with no outcomes or costs | Outcomes and costs in the [README](../README.md#why-build-it) and [phase 1](phase-1.md#costs) |
| S12 | "Closed" claimed what no code shows yet, and the critique only ever added rules | "Designed" instead, two new angles, and every round reports what it removed |
| S13 | Nothing on operations | [Operations](architecture.md#operations): environments, objectives, dashboards, runbooks and on-call |

What round 3 and what followed changed:

- **Removed from a5s's core:** the first scenario's rules, such as no level 2 for requests from a person's words, inside-only contact, its sensitive fields, its transition switch and its limit on changes.
- **Removed:** long-lived threads and their migrations, the second model that checked narratives, comparing a document's shown text with its hidden text, a design review for every release, shadow runs for new releases, measuring whether messages are read, and emergency access as an idea of its own, now part of loosening.
- **Deferred to phase 2:** held proposals, counts, level 2, samples and sequential tests, the extractor, and signed decisions.
- **Deferred to phase 3:** the notebook, group conversations, agent to agent, and adapters for managed runtimes.
- **Added:** the trusted core, the scenario contract, a call step by step, handles, promises and reminders, the "how I like to work" note, operations, the phase-1 plan, the IT service desk on paper, and costs.
- **The consistency read** found that a compromised worker could claim whom a run acts for, so the core now keeps each run's envelope itself, and that a check could be stopped without its assurance agreeing, so a scenario can now mark an agent as a check.
- **The first scenario,** its findings and its accepted risks then left a5s altogether.

## Round 4: the code

Three reviewers who hadn't written the code read it cold: one as an outside attacker and an insider, one for failure and for the team that builds and runs it, and one as a colleague and the author of a second scenario. Each traced every finding to the code and reproduced most of them in tests. Where two or three reviewers found the same thing, it's one finding here.

| # | Finding | Severity | How the code answers it | Status |
| --- | --- | --- | --- | --- |
| B1 | Every part connected as the Postgres superuser that owns the core's tables, so a compromised service could forge a Teams message, open a run with its own token, lift a suspension or truncate the ledger | Critical | Each part connects as its own role, with only the rights its job needs. The core's tables belong to a role nobody logs in as, and no role may change, delete or truncate the ledger | Fixed |
| B2 | The core never checked signed settings itself. An instance the settings left out kept running, an older signed version could be put back, and editing the database widened an instance (found by all three) | Critical | The core checks the signed bytes whenever a run opens, requires the latest version, and refuses an instance whose record differs from them, its release or the ledger's last status change. A version that leaves an instance out retires it | Fixed |
| B3 | Without an identity provider, the core took anyone's word. Workers could reach the local channel, and sign-in tokens passed through the scheduler could be replayed | High | Every message arrives at the core, which checks the sender and records the message. A run takes its sender from that record, the scheduler has no port, and taking people's word must be asked for, in development | Fixed |
| B4 | Anyone with the service token could lift anyone's suspension, by typing their name (found by two) | High | Suspending and resuming take the person from their sign-in, and the first suspender's suspension stands | Fixed |
| B5 | A run with no sender could answer anyone's Teams message, again and again | High | A run answers a message the core recorded, takes its sender from it, and can use it once | Fixed |
| B6 | A message the scheduler had claimed vanished, without a word, if the scheduler stopped, the gateway was down or a call failed (found by two) | High | Taking a message takes its conversation's lease, renewed while the scheduler works. A lapsed lease puts the message back, and when the core can't be reached, the message waits and is tried again | Fixed |
| B7 | Nothing let another scenario plug in: a5s always built the sample, and the reference agent named the sample's people | High | A5S_SCENARIO names the scenario, each instance's owner and deputy come from the signed settings, and a release that needs tools the scenario lacks is refused | Fixed; tools from a scenario's own MCP servers come next |
| B8 | Teams reached only one agent | High | Each agent can be its own bot | Fixed |
| B9 | Schema changes never reached an existing database | Medium | Numbered migrations, applied once each, under a lock | Fixed |
| B10 | Run tokens never expired, and runs whose scheduler stopped stayed open (found by two) | Medium | Runs expire after an hour, and a run that outlives its time is closed and its person told | Fixed |
| B11 | The model gateway forwarded the whole request, so a worker could turn on a provider's own web search | Medium | Providers get only known fields and the agent's own function tools | Fixed |
| B12 | Links escaped the sanitizer in other cases and forms, and drafts weren't filtered | Medium | Outgoing text keeps only words and the scenario's record links, whatever the form, and tools' text arguments, such as a draft's body, are cleaned too | Fixed |
| B13 | Every release broke runs until the gateway restarted | Medium | Releases ship in the gateway's image, the attested build, so applying a release goes with deploying that image: the setup step runs with the new image before the gateways start | Kept by design |
| B14 | Notices named the wrong person or nobody, an outage read as a failure, and the agent saw old requests a5s had turned away, without times (found by two) | Medium | a5s names someone who can help, never the person asking, says when the model is down, and the agent sees when each turn was said and what a5s told the person, within a budget | Fixed |
| B15 | Sign-in ignored how the directory knows people, so an Entra ID object id found nobody | Medium | Sign-in finds people through the directory, as Teams does | Fixed |
| B16 | A copier that found the ledger rewritten only logged it, and nothing recovers from restoring the database to an earlier point | Medium | The copier exits with an error, so the platform notices | Fixed; restoring is a runbook for step 5 |
| B17 | Teams' check for a resent message spanned conversations, so one person's message could be taken for another's | Medium | It's keyed by the conversation and the message | Fixed |
| B18 | A tool could change its risk flags, such as claiming it no longer writes, without a new release (found while fixing B12) | Medium | A tool's whole definition is pinned | Fixed |
| B19 | One planted head object stopped every later copy of the ledger | Low | The copier follows the copies that continue the chain and match the ledger, and the check reports anything else | Fixed; R5 accepted |
| B20 | DeepSeek's undated model was never checked against what answered | Low | Every response must report the approved version, and an undated model must name it | Fixed; R6 accepted |
| B21 | A call that ran but couldn't be recorded was reported as denied, so it might be made again | Low | It's reported as made but not recorded | Fixed |
| B22 | The docs overstated what's built | Low | The progress table and status lines say what's built, and what's still to do | Fixed |

What round 4 changed:

- **Removed:** the local channel in the scheduler, the scheduler's port, its wait for a busy conversation and the notice that went with it, sign-in tokens passing through the scheduler, the separate Teams endpoint (now the core's channels), the gateway's own ledger endpoints, outbox rows for Teams, the sample's people in the reference agent, taking people's word by default, and a schema that couldn't change.
- **Added:** a role for each part, migrations, the core's checks on signed settings, one front door for every channel, a queue the scheduler works through, run expiry, the model gateway's allowlist, a sturdier sanitizer, a bot per agent, and the scenario loader.
- **Proposed, for you to decide:** two reviewers proposed removing the middleware that asks the core to explain a tool call before making it, and its endpoint, until held proposals arrive in phase 2. In phase 1 a denied call already never runs and the agent hears why, so explaining adds a round trip and a policy check to every tool call. It stays until you decide, because you asked for it.
- **Deferred:** a connection pool, checkpoints so the copier needn't read every head each hour, and heads signed by the copier, which would stop R5.

## Accepted risks

Some risk no design removes. These remain, and each needs its owner to accept it.

| # | Risk | Why it stays | Accepted by |
| --- | --- | --- | --- |
| R3 | The identity provider, or the environment the organisation's own models run in, being compromised. It's narrowed by holding decisions for 24 hours after an authenticator is reset. | Signed decisions and pinned models rest on them | The executive the platform owner reports to |
| R4 | A person misled by an agent despite the computed facts and the source flags. It's narrowed by showing the facts apart from the agent's narrative. | People still decide | Each scenario's owners, with training on deciding from the facts |
| R5 | Someone who can write to the ledger's store can plant a copy that continues the chain in good form, which stops the copying until assurance moves it to a new prefix. It can't hide a change, which the check reports. | Telling a5s's copies from good forgeries needs heads the copier signs, which are deferred | Assurance |
| R6 | A provider that offers no dated version, such as DeepSeek, can change the model behind its name unseen. Each response must still report the approved name. | Only the provider can pin it | The platform owner, for development with synthetic data only |

## Next round

Round 5 starts from the accepted risks, round 4's proposals and deferrals, and the code that phase 1's next steps build. It reads from all six angles, and reports what it removes.
