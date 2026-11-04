# Design Critique

**Status:** Rounds 1 to 6, 31 October 2026 · **Design:** [a5s](../README.md)

Every change to the design gets an adversarial review before it settles. Reviewers who didn't write the design read it cold, each from one angle, and each finding is checked against the documents before it's accepted. This page records the findings about a5s, how the design answers them now, and what each round removed.

- **Designed** means the design stops it, and a test in a5s's own suite will show it once it's built.
- **Fixed** means the code stops it, and a test in a5s's own suite shows it. Rounds 4 to 6 found problems in code.
- **Phase 2** and **Phase 3** mean it's designed for a feature that comes in that phase. Until then, neither the feature nor the loophole exists.
- **Accepted** marks what's left once the design has done what it can: a risk its owner accepts under [accepted risks](#accepted-risks).
- **Removed** means a later round removed the control the finding was about.
- **Kept by design** means the round's reviewers proposed a change, and it isn't worth what it costs.

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
- **Round 5** read the code of phase 1's steps 3 to 6, with three new reviewers, and wrote a second scenario, an IT service desk, against the contract alone. It found 45 problems, six of them high, mostly work lost when something failed and data protection that stopped at the top level of a tool's answer, and removed Deep Agents' unused tools, the gateway's cache of settings and the ledger's short-text rule ([below](#round-5-steps-3-to-6)).
- **Round 6** read phase 2's code, with three new reviewers, and plugged the service desk into it through the contract alone. It found 60 problems, 40 once merged, ten of them high: outside content that got past the extractor or past the mark, level 2 without its evidence, approved changes lost when one failed, and caps that fell with every release. It removed caps kept for each release and deciders fixed when a change is held ([below](#round-6-phase-2)).

## Findings about a5s

### Outside attacker

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| A2 | Outside text arrives as a record, such as a comment claiming a check was done | Critical | Outside free text reaches agents only through the extractor, facts people decide on are computed, and an agent can't say a check was done ([provenance](architecture.md#provenance-who-said-what)) | Fixed: the sample's customers' emails reach agents only as the extractor's checked form |
| A3 | Data leaves through a link or image that a preview fetches, with no click | Critical | Messages and drafts carry only text and the scenario's record links, and messages go only to the audience the settings name ([channels](architecture.md#channels)) | Designed |
| A4 | Planted text steers what a check reports | Critical | Checks compute their results in code, and a scenario can mark an agent as a check, so stopping or changing it needs the scenario's assurance ([independence](architecture.md#independence)) | Designed |
| A5 | Deep Agents' own files and `AGENTS.md` become a memory nobody governs | High | Instructions and skills load read-only from the release, scratch files last one run, and Deep Agents' editable memory isn't used ([what a5s uses from Deep Agents](architecture.md#what-a5s-uses-from-deep-agents)) | Designed |
| A6 | Profiles and summaries make one injection last and spread | High | Marked runs can't write profiles, summaries hold facts by handle and are checked by code, and there's no notebook until phase 3 ([context](architecture.md#context-and-memory)) | Designed; R4 accepted |
| A7 | A spoofed email makes anyone "the person" an agent acts for | High | Only people the directory knows start runs, email only from senders who pass DMARC and match the directory, Reply-To is ignored, and other mail is treated as a document ([channels](architecture.md#channels)) | Designed |
| A8 | The extractor's output still steers, and its sources are lost downstream | High | The extractor has no tools and fixed schemas, values from documents carry their source as handles, and a pack can refuse to approve them automatically or use them as contacts ([data protection](architecture.md#data-protection)) | Fixed: the form holds only typed values the document contains, with sensitive ones as handles, and the run is marked |
| A9 | A2A drops the limits of the person an agent acts for | High | The people travel with the question: the agent asked acts for them, within its own grant and what they may see, writes to nobody, and can't ask on, and its mark comes back with its answer ([agent to agent](architecture.md#agent-to-agent)) | Fixed |
| A10 | A model provider swaps the model silently, without a release | High | Models are pinned by provider, deployment, region and version, and the model gateway checks every call ([data protection](architecture.md#data-protection)) | Designed |
| A11 | Tool servers, skills and held calls are trusted too much | Medium | Skills and tool schemas are pinned in the release, the gateway refuses tool servers' requests to ask people for input or run the model, and held calls are made through the gateway like any call ([data protection](architecture.md#data-protection)) | Designed |
| A12 | A flood of junk requests drains the budget urgent chases need | Medium | Budgets per person and per source of triggers, a share kept for obligations, and outside parties rate-limited ([when things fail](architecture.md#when-things-fail)) | Designed |

### Insider

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| I1 | Someone gets their own change approved by feeding it to an agent that acts for nobody | Critical | Requests name everyone whose words they came from, and none of them may decide it. A pack can also rule out level 2 for such requests ([provenance](architecture.md#provenance-who-said-what)) | Fixed: a held change names who it was for, none of whom may decide it, and a run that read outside content never acts at level 2 |
| I2 | Settings, decisions and the ledger are records the team that runs a5s can change | Critical | Unsigned settings don't count, decisions on sensitive items are signed one by one, the ledger records the settings version, and its hourly anchor sits with assurance ([a call, step by step](architecture.md#a-call-step-by-step); [evidence](architecture.md#evidence)) | Designed; R3 accepted |
| I3 | The team that runs a5s approves its own enforcement | Critical | Changes to the trusted core and policy packs need an approver from outside the team, an attested build and assurance's tests, and releases pin tools' schemas, so a changed tool needs that approver too ([independence](architecture.md#independence)) | Designed |
| I5 | Someone sees more through an agent, through a reminder, A2A or an agent with a wider grant | High | A run acts for everyone whose words it serves, reminders included, and sees only what they may all see ([context](architecture.md#context-and-memory)) | Designed |
| I6 | A large change made in small pieces | High | Counts per piece of work that code defines, a run, and for each person acted for in 30 days, across runs and agents ([policy](architecture.md#policy)) | Fixed |
| I7 | An agent moves up a level on its builders' own evidence | High | Code draws samples, people outside the team that built it, who neither asked for nor decided what they grade, grade them, and the part owner sets the threshold ([autonomy](agent-model.md#autonomy); [assurance](architecture.md#assurance)) | Fixed |
| I8 | Someone steers the evidence other deciders see | High | Case briefs come from records, facts are computed and shown apart from the agent's narrative, and samples skip the reviewer's own items ([provenance](architecture.md#provenance-who-said-what)) | Designed |
| I10 | The platform owner is a single point of control | High | Loosening anything needs someone outside the team that runs a5s and its manager's reporting line, and is reported to assurance ([independence](architecture.md#independence)) | Designed |
| I11 | A field moves to a friendlier owner | Medium | A level-2 setting counts only while someone who approved the settings in force owns the part, and no run opens at all until a part's new owner approves them ([autonomy](agent-model.md#autonomy)) | Fixed |
| I12 | An owner silences the chases by withdrawing an agent's approval | Medium | Obligations escalate in code along the scenario's chain when no approved agent can act on them ([channels](architecture.md#channels)) | Designed |

### Failure

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| F1 | An outage fix, such as a provider failover or turning on tracing, sends data round the gateways | Critical | Models are pinned, failover goes only to a model approved for the same data, and workers reach nothing but the gateways ([data protection](architecture.md#data-protection)) | Designed |
| F2 | Failing closed has no degraded mode, and one team holds the switch | High | Runs end and their triggers wait, a circuit breaker pauses new runs, the channel service tells people to carry on in the scenario's own process, and overriding a fail-closed rule needs someone outside the team ([when things fail](architecture.md#when-things-fail)) | Designed |
| F4 | Approvals and withdrawals lag behind reality | High | Settings are cached for at most 30 seconds and a change clears the cache, and level-2 settings record their approver ([a call, step by step](architecture.md#a-call-step-by-step); [autonomy](agent-model.md#autonomy)) | Designed |
| F5 | Counts drift under parallel calls and retries | High | Counts are reserved in the same transaction as the policy decision, under a lock for each type of action, and keys come from the piece of work, the records and the change ([a call, step by step](architecture.md#a-call-step-by-step)) | Fixed |
| F6 | Someone else gets a person's conversation, through spoofed mail, a reused address or a group chat | High | Directory identities, DMARC-checked mail, no Reply-To, and conversations archived when people leave. A group chat's conversation is apart from each person's: no run there reads one, an agent never writes first into a group, and what's one person's own is asked for one to one ([channels](architecture.md#channels); [context](architecture.md#context-and-memory)) | Fixed |
| F8 | Repairing a thread steers an agent without a trace | High | Run threads last one run, so there's no saved state to repair, and conversations are a5s's own records, written only by the context service ([context](architecture.md#context-and-memory)) | Designed |
| F9 | Every release resets earned trust, so security patches wait | High | Releases are proportionate, and a security fix goes in at once, at level 1 at most ([independence](architecture.md#independence); [lifecycle](agent-model.md#lifecycle)) | Designed |
| F10 | One long conversation per person costs too much and loses facts | Medium | Each run starts fresh with a context assembled within a budget, summaries are checked by code, and answers about the past retrieve the original turns ([context](architecture.md#context-and-memory)) | Designed |
| F11 | Chasing fails across time zones and many instances | Medium | Escalation follows working hours, and digests and limits are per person ([channels](architecture.md#channels)) | Designed |

### Colleague

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| C1 | A notebook carries one person's words to everyone | High | Only a run that acts for nobody, and so hears nobody's words, notes anything, never once it has read content from outside; code checks each note against the records it names; and a run is given only the notes whose records all its people may see ([context](architecture.md#context-and-memory)) | Fixed |
| C2 | Only some people get a conversation, so someone who replies to a chase gets no answer | High | Every agent can be talked to, and a reply starts a run that acts for the sender ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| C3 | What people tell an agent never reaches the work, so the chases keep coming | High | A person can say what they're waiting on, which pauses chases until the date they give ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| C4 | When an agent can't run, it goes silent | High | The channel service says so in code and names who to ask ([channels](architecture.md#channels)) | Designed |
| C5 | One person faces many bots, each with its own digest | High | One digest and one limit per person from all the agents, and one conversation per person per agent ([channels](architecture.md#channels); [context](architecture.md#context-and-memory)) | Designed |
| C6 | Handoffs drop the context and the agent's flags | Medium | Drafts and requests carry a handoff note and the agent's flags ([proposals](architecture.md#proposals-and-approvals)) | Designed |
| C7 | One thread forever, with no reset and summaries nobody sees | Medium | Topics, summaries the person can see and correct, and a fresh thread for every run ([context](architecture.md#context-and-memory)) | Designed |
| C8 | Agents don't learn how people like to work | Medium | Typed preferences and a "how I like to work" note in each profile ([context](architecture.md#context-and-memory)) | Designed |
| C9 | A group chat has no conversation of its own | Medium | Each group chat has a conversation of its own, with who said each turn and who heard it, and a run there is given only what everyone now in it heard ([context](architecture.md#context-and-memory)) | Fixed |
| C10 | The extractor can't answer questions about a document, so people paste it into other tools | Medium | The extractor can answer in free text, marked as outside content and never used as an instruction ([data protection](architecture.md#data-protection)) | Fixed |

### Builder and operator

| # | Loophole | Severity | How the design answers it | Status |
| --- | --- | --- | --- | --- |
| D5 | A signed sign-in doesn't sign the decision, so it can be reused for another | Critical | Each decision is signed for that decision on exactly the changes it names, and a signature works once ([proposals](architecture.md#proposals-and-approvals)) | Fixed: for settings in phase 1, and for held changes in phase 2 |
| D6 | The builders build the controls and the tests that judge them | High | Assurance holds the tests for the trusted core, and changes to it need an outside approver ([independence](architecture.md#independence)) | Designed |
| D8 | The people being watched can switch the detection off | High | Stopping or changing an agent the scenario marks as a check needs the scenario's assurance ([independence](architecture.md#independence)) | Designed |
| O4 | A counting backstop switches busy assistants off mid-month | High | Only changes count, held or made, per person acted for and type of action, and past a limit a change waits for a person rather than stopping ([starting values](starting-values.md)) | Fixed |
| O5 | Releases can't be rolled back or patched fast | High | An instance can go straight back to the release before, and a security fix goes in at once ([lifecycle](agent-model.md#lifecycle)) | Designed |
| O6 | Measures of people flag diligent reviewers, and need consent | High | Measures of people judge outcomes, not speed, and are agreed with the data protection officer, and works councils where there are any, before they start ([assurance](architecture.md#assurance)) | Designed |
| O7 | The context cap has no rule for what happens when it's reached | High | A budget for each part of the context, tested at release ([how an agent lives](architecture.md#how-an-agent-lives)) | Designed |
| O8 | Samples prove little and cost a lot | High | An anytime-valid sequential test at 95% confidence, pooled across a release's instances, which can be checked after every grade ([starting values](starting-values.md)) | Fixed |
| O9 | Chases arrive with the escalation | Medium | A chase comes well before the escalation, which waits at least a working day after it ([starting values](starting-values.md)) | Designed |
| O10 | A sign-in for every decision breeds approval fatigue | Medium | Changes that aren't sensitive can be decided together, with one sign-in that names each; sensitive ones are decided one by one ([proposals](architecture.md#proposals-and-approvals)) | Fixed |
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
- **Removed after the round, as two reviewers proposed:** the middleware that asked the core to explain a tool call before making it, and its endpoint, until held proposals arrive in phase 2. A denied call already never runs and the agent hears why, so explaining only added a round trip and a policy check to every tool call.
- **Decided after the round:** the clouds run a5s on each one's own container service, not Kubernetes, and R5 and R6 are accepted by the owners below. (On 3 November 2026 hosting changed to Kubernetes everywhere, from one Helm chart, so a5s runs the same way in every cloud and network policies isolate the worker in each.)
- **Deferred:** a connection pool, checkpoints so the copier needn't read every head each hour, and heads signed by the copier, which would stop R5.

## Round 5: steps 3 to 6

Three reviewers who hadn't written it read the code of phase 1's steps 3 to 6 cold: conversations, summaries, provenance and handles, budgets, breakers, classes of data, traces, status, retention, the urgent cap, parts and need-to-know, and the settings app. One read it as an outside attacker and an insider, one for failure and for the team that runs it, and one as a colleague and as the author of a second scenario, an IT service desk written against the contract alone. They found 45 problems and reproduced most of them in 66 tests. Where two or three reviewers found the same thing, it's one finding here, and each test now passes as the fix's regression test.

| # | Finding | Severity | How the code answers it | Status |
| --- | --- | --- | --- | --- |
| E1 | A reminder or chase whose run failed was never given, because it was marked given when the run opened, and a5s then told the person's manager it had been (found by two) | High | When such a run doesn't finish, the core gives the reminder or chase itself, in its own words, in the person's digest or chat | Fixed |
| E2 | Teams and Matrix got one try, after the commit, so a digest, escalation, reminder or approval card was lost when the chat failed | High | What a5s sends to a chat goes in the outbox in the transaction that decides it, is tried five times with longer waits, and is then left in the person's local inbox, which the ledger and the status record | Fixed |
| E3 | Any part owner could stop every approved version being applied, with a level written as a quoted number, or make the core build about 100 GB from a 2 KB request, with YAML aliases | High | Settings are read by a strict model: no anchors or aliases, whole-number levels, ids and classes as plain words, and nothing else. The sweep works on each request and each version alone | Fixed |
| E4 | A tool that answered with an object, as MCP tools do, skipped parts, visibility, handles and classes; a record key that wasn't a string skipped the part check; and text inside an object argument wasn't cleaned (round 4's B12 again) (found by two) | High | Results and arguments are filtered, cleaned and resolved at any depth. A call that names a record other than by its key is denied, and a result that holds records without their keys is withheld | Fixed |
| E5 | A second reminder for the same day was dropped while the agent was told it was set, and saying yes kept the last offer, whatever the person said yes to | High | An offer matches another only if it's about the same thing, and confirming names the offer | Fixed |
| E6 | An instance's `serves` listed people one by one, so every joiner was a new signed version that widened what agents do | High | `serves` may name a team or a role's holders, which the directory resolves when each run opens. A group nobody is in is refused before anyone is asked | Fixed |
| E7 | Retiring an instance and bringing it back lifted someone else's suspension (round 4's B4 by a new path) | Medium | Bringing an instance back keeps its suspension, and the ledger's entry says so | Fixed |
| E8 | The gateway cached a checked version for its whole life, and once the settings in force stopped checking out, classified fields came back in clear and model calls went ahead | Medium | Nothing is cached. While the settings don't check out, model and tool calls are denied | Fixed |
| E9 | The gateway's own database role could put back an older, wider version (round 4's B2, reopened by a later migration) | Medium | It may change only a version's text and signatures, and the core checks the two latest versions against their rows | Fixed |
| E10 | A part owner's request could put a link in every approver's card, as often as they liked | Medium | Ids, parts and classes are plain words, people and groups must be in the directory, a person may make five requests a day with one waiting at a time, and nobody is asked about a version that changes nothing | Fixed |
| E11 | A classified title reached models not approved for it, and an escalation named a record to people who may not see it | Medium | The title is withheld where the model isn't approved for it, and escalations go only to people who may see the record | Fixed |
| E12 | People's words went into the append-only ledger as they were, past a note they'd asked a5s to forget and past retention, and approvals kept sign-ins that still worked (found by two) | Medium | The ledger keeps every text by its hash, and approvals keep sign-ins by their hash. Retention clears what people wait on, unconfirmed notes and old report snapshots | Fixed |
| E13 | Model calls made at the same time overran run and day budgets: eight calls used 7,200 tokens of a budget of 1,000 | Medium | A run's model calls go one at a time | Fixed |
| E14 | A handle's value came back to the model in a tool's result or error | Medium | Any handle's value in a result or an error goes back to the agent as its handle | Fixed |
| E15 | One slow chat stopped a5s answering anyone, in any chat | Medium | Sweeps run on their own thread, and chats are written from the outbox | Fixed |
| E16 | A chase refused for budget held the person's whole digest all day, changing the digest time sent a second digest, and held escalations went out after hours | Medium | A digest waits half an hour at most for its work, goes once a local day, and batches wait for working hours | Fixed |
| E17 | A summary refused for one invented value lost code's facts and was asked for again on every run; it could be refused for citing the date a5s showed; and its facts grew until they crowded the conversation out (found by two) | Medium | A summary keeps what checks out, counts the turns' dates as said, keeps the newest 500 facts, takes a third of a run's budget at most, and folds a backlog a run's worth at a time | Fixed |
| E18 | Budgets didn't fit the context each call carries: a long conversation left a run four calls, and a person seven answers a day | Medium | Deep Agents' tools for files, subagents and a shell aren't offered, which saves about 2,500 tokens a call, the contexts are smaller, and a release whose budgets don't fit six calls a run and twelve answers a day is refused | Fixed |
| E19 | What a5s wrote in an agent's chat, such as an escalation, never reached the agent, and a digest from several agents arrived as one of their bots | Medium | What a5s writes in an agent's chat goes in that conversation as a5s's notice, and in Teams and Matrix each agent's digest goes in its own chat | Fixed |
| E20 | The provenance note flagged dates a5s itself had given the agent, an agent could write a5s's note itself, a correction kept the agent's words as the person's, and common forms of amounts and dates went unchecked (found by two) | Medium | What a5s's tools return and its own context count as sources, a forged note is removed, a5s's note is kept apart from the agent's words, a correction must match what the person said, and more forms are recognised | Fixed |
| E21 | The approval page told the first of two approvers the version would be in force within a minute | Medium | It says whose approval it still needs | Fixed |
| E22 | The watcher said records were gone when only its parts had changed | Medium | A record that's still theirs, in a part it no longer works in, is left out of what it says, not said to be gone | Fixed |
| E23 | The service desk couldn't run without changing a5s: a key pattern with a group broke cases, one ticket's brief read every ticket, a night shift was never working hours, the wrong person was named to someone nobody serves, a5s's tools named the sample's keys, and a message never reached a second instance of an agent (found by all three) | Medium | Keys are matched whole, a scenario may read one record with `record(key)`, hours may cross midnight, the owners of the instances' parts are named, a5s's own tools name no scenario's keys, and a message goes to the instance that works in its record's part | Fixed |
| E24 | Approving accepted a sign-in that had no time of sign-in, so a silent sign-in at an unlocked browser could approve | Low | A sign-in must say it's fresh | Fixed |
| E25 | A reminder for someone who'd left was refused every minute, forever, and a reminder at a set time counted toward the urgent cap | Low | Such a reminder is ended once, in the ledger, and reminders people asked for at a time don't count toward the cap | Fixed |
| E26 | The status said replies met their objective when nothing had been answered, read warnings from the whole ledger and said nothing about failed deliveries; and traces said tools, messages and run openings took no time | Low | The status says "not known yet" with nothing to measure, reads warnings from the budgets, counts deliveries a chat didn't take, and reads denials by an index. Spans now enclose the work | Fixed |
| E27 | No policy used a tool's `destructive` or `sends_outside` flags, so only the grant stopped a level-1 agent from using one | Low | Such tools need level 2, which comes in phase 2 | Fixed |
| E28 | `note_waiting` promised to pause the person's own reminders, and the assistant offered a channel preference nothing implemented | Low | Its words say what it does, and the preference is gone | Fixed |
| E29 | A run that provokes three provider failures stops that model for everyone for five minutes | Low | Only a provider's own failures count, not a refused request, and a provider that fails for one run is likely failing for all | Kept by design |
| E30 | Obligations are one per source, record and person, so a ticket's response and resolution targets need separate sources, and a queue can't owe anything | Low | A scenario names a source for each target, and the system that assigns a queue's work says who owes it | Kept by design |

What round 5 changed:

- **Removed:** the gateway's cache of checked settings, YAML's anchors and aliases in settings, Deep Agents' file, subagent and shell tools, the assistant's channel preference, the ledger's rule that kept short text as it was, sign-ins kept as tokens, report snapshots kept after they're told, the rewrite of every open obligation every minute, a5s's own words in place of the agent's, the three empty spans, and the status's scans of the whole ledger.
- **Added:** the outbox for every chat, the core giving reminders and chases itself, a half-hour bound on a digest's wait, one model call at a time for each run, strict settings, groups in `serves`, `record(key)` in the contract, hours across midnight, notice turns, budgets checked against the context at release, a policy for destructive and outside tools, and the status's lines for deliveries.
- **Proposed and kept:** approval cards still say what a version changes, since every word in them now comes from the directory or a plain id; the urgent cap stays, since status shows when it holds anything back; and digests in the local inbox still combine all of a person's agents.
- **Deferred:** sealing approvals in the gateway's sweep rather than the channels app, which would take the seal key off the internet-facing service and narrow R7 (done on 4 November 2026, for decisions and grades too); one check for parts and visibility in place of four; and a record shape the contract defines, in place of a tool's `record_field`, `record_arg`, `handles` and `text_fields`.

## Round 6: phase 2

Three reviewers who hadn't written it read phase 2's code cold: the extractor and marked runs, held proposals and signed decisions, counts, types of action and level 2, and samples, grades and the cap. One read it as an outside attacker and an insider, one for failure and for the team that runs a5s, and one as a colleague and as the author of the IT service desk of round 5, plugged into phase 2 through the contract alone. They found 60 problems, which come to the 40 below, and reproduced most of them in 71 tests. Each test now passes as its fix's regression test.

| # | Finding | Severity | How the code answers it | Status |
| --- | --- | --- | --- | --- |
| G1 | Outside content reached the agent when its field wasn't a plain string, such as an email's body as Microsoft Graph gives it, or sat inside an item, such as an attachment (found by two) | High | Every outside field, whatever its type, goes to the extractor as text, at any depth, and the agent gets only the form | Fixed |
| G2 | The extractor's handle kind took any text an email held, so a link of the sender's choosing reached messages and drafts, since text was cleaned before handles were resolved | High | The handle kind is gone, and text is cleaned again once handles are resolved, keeping a5s's own notes | Fixed |
| G3 | The mark stayed with the run: what a marked run passed on, the person's next run read unmarked, and acted on at level 2 | High | A run opens marked when its conversation, in its topic or its latest turns, holds a turn from a marked run | Fixed |
| G4 | A change to a record in no part, or with a tool that can't be undone or sends outside, worked at the instance's own level: level 2 with no level for its type of action, no cap earned on samples, and no sample drawn (found by two) | High | Level 2 is only for a type of action the settings set in a record's part, up to the cap. Anything else, and any change in a marked run, works at level 1 at most, and a part's own level never goes above 1 | Fixed |
| G5 | A critical error lowered the cap for a minute, since the next sweep weighed the same grades and raised it again, and once level 2 was earned, the grades that earned it hid a fall: 88% over a quarter against 98% went unnoticed (found by all three) | High | Each test weighs only the grades given since the cap last changed, so each change starts a fresh test, and level 2 is earned again on new grades | Fixed |
| G6 | One failure in the proposals sweep lost approved changes: they were made only after its loop, one record that couldn't be read stopped every sweep, and a change made just before its record couldn't be read was never recorded | High | Each change is swept on its own, made as soon as it's marked, and its outcome recorded first, in a transaction of its own. Its records are read once, when it's held | Fixed |
| G7 | Every release threw away level 2, since caps were kept for a release, whose id covers every file: one sentence of instructions dropped every cap to 1 (found by two) | High | Caps are kept for a behaviour: the agent, its model, and the tools of that type it may use, as pinned. A release that changes only instructions keeps them, after its regression suite and a re-run of the last graded samples; one that changes a tool or the model starts again for what it widens | Fixed |
| G8 | The extractor read, and `ask_about` answered about, documents on records the run may not see (found by two) | High | Need-to-know comes first, then the extractor | Fixed |
| G9 | A call that changed many records counted as one, so one call closed any number of tickets at level 2, past a limit of two a run | High | Each record a change names counts | Fixed |
| G10 | A change in two parts was decided by one part's owner, and when nobody could decide, a5s told a requester to make it themselves when they couldn't | High | Each part's deciders approve for their part, and a rejection by any ends it. a5s says which case it is when nobody may decide | Fixed |
| G11 | A run that read outside content could send outside or destroy at level 2: policy forbade it only tools that write | Medium | It may use none of the three at level 2 | Fixed |
| G12 | Grades and caps counted as stored: the channels' role could write grades, and the gateway's caps; and a sign-in the browser kept could grade | Medium | A grade needs a fresh sign-in whose nonce commits to exactly those grades, and the core seals it. A cap counts only as the core sealed it, with the ledger entry that set it, while that's the ledger's last word on it | Fixed |
| G13 | A decider approved a handle, not the value the change writes; nothing said which values came from a customer's email; there was no link to the record, and no word it had changed since (found by two) | Medium | The page and the card give the values, a link to each record, a flag for each value from a document from outside, and which records have changed since | Fixed |
| G14 | The extractor sent an outside field to a model not approved for its class | Medium | It isn't read, and the form says why | Fixed |
| G15 | One message could send a decider any number of requests | Medium | Requests are urgent messages: past a person's five a day, they wait for a batch | Fixed |
| G16 | The same change made again in a run was made again at level 2 though counted once; runs for nobody escaped the per-person limits; and no key let a tool make a change once (found by two) | Medium | a5s answers the same change with what became of it, and doesn't make it twice. A tool gets a key for each change, and a run for nobody counts against its instance | Fixed |
| G17 | The same change asked for again in a later run was held again, asked again, and could be approved twice, and nothing told a later run it waited (found by two) | Medium | A waiting change is matched across runs, by instance, people and change, and a run's context lists what waits on its record | Fixed |
| G18 | Held changes were stranded when deciders changed: deciders were fixed when held, a part's new owner couldn't decide, chasing followed the first decider alone, a reminder went only to those at work that minute, a manager was sent a link to a page that showed them nothing, and a card went to a chat its decider doesn't use (found by all three) | Medium | Deciders are worked out afresh at review, decision and chase. Each is reminded in their own hours, and only then are their managers told, each in their own hours, or the instance's owner; they can see what waits, but only its deciders decide it. A request goes where the decider works with the agent | Fixed |
| G19 | At level 2, a change the records system refused was reported as made, counted and sampled, and one whose report failed answered the agent with an error, so it asked again. The report didn't say what the change replaced, the person it was for heard nothing from a5s, and with no owner nobody did (found by all three) | Medium | An error the system answers with is a failure, and isn't counted. The report comes from what a5s read before the change, to the owner and deputy, or else the part's owners, and the person gets a5s's notice in their conversation | Fixed |
| G20 | A slow records system stalled every agent while a change was held, since records were read inside the ledger's lock | Medium | They're read before the lock is taken | Fixed |
| G21 | The extractor's cost had no limit: it sent each document whole, again for each question, and read the same email again | Medium | It reads the first 24,000 characters of each, ten documents a call, within what's left of the run's budget, once a run | Fixed |
| G22 | The decision and grading pages cut their lists before filtering, so what a person could decide or grade could hide behind what they couldn't (found by all three) | Medium | Waiting changes come oldest first, and samples are read in pages until 20 are found, with what a query can leave out left out | Fixed |
| G23 | The proposals sweep read every waiting change every minute | Medium | When each step falls due is kept with the change, and the sweep reads only what's due | Fixed |
| G24 | A cap ignored the threshold it was earned under, and while the settings didn't check out the sweep lowered every cap | Medium | A cap keeps its threshold, and is tested again when it rises. Nothing is weighed while the settings don't check out | Fixed |
| G25 | Below level 2, a change that can't be undone or sends outside was denied, never held, so it could never earn level 2; and a classified value didn't make a change sensitive | Medium | Such a change waits for its decider, alone, and so does one that writes a classified value | Fixed |
| G26 | A decider couldn't say why they rejected a change | Medium | They may, briefly. It's sealed with their decision, and told to whoever asked | Fixed |
| G27 | Graders saw neither what code flagged to the decider nor the record as it stood, but as it was after the change (found by two) | Medium | A sample keeps the flags, and the records as they stood when the change was asked for | Fixed |
| G28 | A grader could grade the approvals of the manager they report to, and graders could come from the team that runs the instance | Medium | Neither may grade. The sample's grader is in a quality team, which may see billing's records | Fixed |
| G29 | The settings accepted a limit or a level for a type of action no tool takes, and level 2 for a type with no limit | Medium | Both are refused before anyone is asked | Fixed |
| G30 | The team that runs a5s couldn't list or end a change stopped part way through making, nor lower a cap, and the status and runbooks said nothing of phase 2's failures | Medium | `a5s proposals` lists and ends them, `a5s caps lower` lowers a cap, each in the ledger, and the status and runbooks cover each | Fixed |
| G31 | Only a part's owners could decide its changes | Medium | Its owner may name delegates, `part-delegate:<part>`, who decide beside them | Fixed |
| G32 | The form kept a year the email never gave | Low | A date is kept only as fully as the document gives it | Fixed |
| G33 | A change held for being past a limit didn't tell its decider why | Low | Its flags say so | Fixed |
| G34 | The whole settings said an instance works at level 2 where the cap held it at 1 | Low | They say level 2 waits for graded samples | Fixed |
| G35 | Ungraded samples, counts of changes and changes stopped part way were kept forever | Low | Ungraded samples lapse after a quarter and go after a year, counts after their 30 days, and a stopped change once it's ended | Fixed |
| G36 | A part's owner could change another part's threshold alone | Low | A changed threshold needs its part's owner. Limits already need the owner of every part an instance works in | Fixed |
| G37 | The sample scenario read all its changes on every read | Low | They're indexed by key | Fixed |
| G38 | A decision that didn't count went unsaid, deciders weren't told what became of a change, nobody was told when a cap changed, and the page stopped after a decision | Low | Everyone who decided a change hears what became of it, owners hear when a cap changes, and the page lists what waits again | Fixed |
| G39 | Two approved changes to one record were both made, each checked against the record before either was made | Low | Each is checked just before it's made, so the second waits for a new request | Fixed |
| G40 | A record field that changes all the time, such as a last-updated time, stops every held change on it | Low | The contract says a record's fields are what deciders weigh, not values that change by themselves | Kept by design |

What round 6 changed:

- **Removed:** the extractor's handle kind, Simpson's rule (the evidence is now exact), caps kept for each release, a part's own level as a way to level 2 for changes, records read again after a change, deciders fixed when a change is held, reading every waiting change every minute, and the rubber-stamping flag by default, until the data protection officer agrees (O6).
- **Added:** decisions for each part, part delegates, caps kept for a behaviour and sealed with the ledger's entry, grades signed for and sealed, a fresh test after each change of cap, counts for each record, changes made once with keys for tools, waiting changes matched across runs and listed in a run's context, a level-2 report to someone always, `a5s proposals` and `a5s caps lower`, and limits on what a5s's reader reads.
- **Proposed and kept:** caps don't count instructions, since the release table already asks for a re-run of the last graded samples; rejected changes are still sampled, since a grade of what the agent asked for is evidence about it whatever the decider did; held changes stay apart from obligations, which are one person's; and sensitive changes are held, not denied, so they can be decided and earn level 2.
- **Deferred:** a hook for a scenario to route a decision to its own approval process, beside part delegates; and making a change exactly once in a system that knows no keys, where a5s marks it as being made, and someone ends it by hand.

## Accepted risks

Some risk no design removes. These remain, each accepted by its owner.

| # | Risk | Why it stays | Accepted by |
| --- | --- | --- | --- |
| R3 | The identity provider, or the environment the organisation's own models run in, being compromised. It's narrowed by holding decisions for 24 hours after an authenticator is reset. | Signed decisions and pinned models rest on them | The executive the platform owner reports to |
| R4 | A person misled by an agent despite the computed facts and the source flags. It's narrowed by showing the facts apart from the agent's narrative. | People still decide | Each scenario's owners, with training on deciding from the facts |
| R5 | Someone who can write to the ledger's store can plant a copy that continues the chain in good form, which stops the copying until assurance moves it to a new prefix. It can't hide a change, which the check reports. | Telling a5s's copies from good forgeries needs heads the copier signs, which are deferred | Assurance |
| R6 | A provider that offers no dated version, such as DeepSeek, can change the model behind its name unseen. Each response must still report the approved name. | Only the provider can pin it | The platform owner, for development with synthetic data only |
| R7 | Someone who holds the core's seal key and can also write to its database can make an approval of settings, a decision on a held change, a grade or a cap, as if its person had made it on the core's page, or samples had earned it. Only the gateway holds the key, which nobody outside reaches: the channels app, which people reach, records what people do with their sign-in, and the gateway checks it again before it seals it. | The core seals what it checked so it outlasts the identity provider's keys. Signatures made with people's own keys don't rest on the core. | The platform owner |

## Next round

Round 7 starts from the accepted risks, round 6's deferrals, and the code phase 3 builds. It reads from all six angles, and reports what it removes.
