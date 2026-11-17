# Agent Model

**Status:** Draft v0.3. Phase 1's first step is built ([progress](phase-1.md#progress)) · **Under:** [Architecture](architecture.md)

## Definitions, releases, instances, conversations and runs

| Object | What it is | Lasts |
| --- | --- | --- |
| Definition | A kind of agent: its job, and whom it works for | Until it's retired |
| Release | A tested, approved version of a definition. It fixes the instructions, skills, tools, model, triggers, obligations, the preferences people can set, the context budget and the limits. | Until it's withdrawn |
| Instance | A definition at work in a scope, with its own identity, grant and status | As long as the scope needs it |
| Conversation | Everything one person and one agent have said to each other, in topics, whichever of the agent's instances did the work | As long as they work together, then as the retention rules say |
| Run | One piece of work, from a trigger until it's done, on a LangGraph thread that ends with it | Minutes |

For example, a5s's own assistant is a definition, and its release 0.3.0 a release. The assistant for the finance team is an instance. One person's exchanges with it are a conversation, and answering one of their messages is a run.

## Terms a scenario fills in

| Term | Means |
| --- | --- |
| Part | A piece of the business with one owner. Every field an agent changes belongs to one part. |
| Part owner | Approves agents to act in the part, and how far. Decides their proposals there, or names delegates to. |
| Scope | The parts an instance may act in: one, several, or none, for an agent that acts on no part's data |
| Grant | The tools, data and models an instance may use: what its release lists, as far as its parts' owners approve |
| Type of action | A kind of action that a level is set for, as the scenario defines it, such as a change type or a catalogue item |
| Acts for | Everyone whose words a run serves: whoever sent the message, set the reminder, or wrote the reply a request came from, whoever a reminder of an obligation is for, and whoever a report on their own records is for. A run started only by a schedule acts for nobody, and one started by another system's event acts for the person it names, where the instance serves them, or else for nobody. A run writes only to the people it acts for. |

The [scenario contract](architecture.md#the-scenario-contract) says where the settings, the governed process and the decision surface come from. Each scenario's page maps these terms, as the [IT service desk](../scenarios/it-service-desk.md) does.

## Roles

Roles are held by people, never by job titles. An organisation assigns people to roles in its directory, and a5s checks each role's rules in code whenever the role is used, such as an approver coming from outside the team that runs a5s and its manager's reporting line. The platform owner and the release approver for the trusted core are a5s's own roles, held once for all of it. Each scenario assigns the rest.

| Role | Does |
| --- | --- |
| Platform owner | Accountable for a5s and the agents it runs. Names each agent owner and deputy, and can suspend any instance or withdraw any release. |
| Agent owner, with a deputy | Builds and runs a definition and its instances. Reviews level-2 actions and can reverse them. Can suspend the agent's instances, lower their cap and withdraw its releases. |
| Part owner, and delegates | The part owner, who holds `part-owner:<part>` in the directory, approves an instance for the part, sets how far it may act there, and moves it up or down. They or their delegates decide its proposals, as the scenario allows. Decisions about the agent itself are never a delegate's. |
| Instance approver | For each part in an instance's scope, its owner. For an instance with no parts, whoever the scenario names, who also sets its level. |
| Release approver | Approves what loosens a5s: releases that change a tool or widen what an agent may do, such as more tools, another model, long tasks or more for them, another owner or deputy, or listing it for everyone, changes to the trusted core, and anything else the scenario names nobody else for. Never from the team that runs a5s, or its manager's reporting line. |
| Graders | Grade samples of an agent's work. Never anyone who owns, authors or drafted it, nor anyone from their teams, nor anyone a change was for or who decided it. |
| Assurance | Holds the ledger's anchor, reads the ledger, and is told of everything that loosens a5s |
| Data protection officer | Answers requests for someone's data, asking on the core's page for all a5s keeps about them to be exported (`a5s export`), or erased (`a5s erase`), which the team that runs a5s carries out, keeps the record of whose archive is which, and agrees the measures before they start ([data protection](data-protection.md)) |

## Lifecycle

| A release is | Means |
| --- | --- |
| Draft | Being built or changed |
| Approved | Passed its tests and has the approval its kind of change needs ([independence](architecture.md#independence)). Instances can run it until it's withdrawn. |
| Withdrawn | No instance may run it. The agent owner, the release approver or the platform owner can withdraw it, and a security advisory withdraws every release that pins the affected version. Instances still on it are suspended until they move to another release. |

Each organisation approves a release for its own deployment, with its own people. A release of a5s is everything it runs there: from its image, the trusted core, the services and what the image was built from; from the deployment, its approved models, its scenario's directory and tools, and its agents' definitions. Its manifest lists a digest of every file, and what each agent and model may do (`a5s release show`). The people its changes need sign the manifest with their own keys (`a5s release sign`), anywhere and offline, and the administrator records the signatures (`a5s release approve`). What it needs comes from comparing it with the release approved there before ([independence](architecture.md#independence)), and different people must meet each need. Each release also records who may sign the one after it: everyone its directory gives a key, with their team and roles. A signature counts only if it counts both as the release before records its signer and as this one does, checked with the key of record, so a release can't approve itself with an approver it adds, nor count someone it removes. The core checks the signatures again, back to the first release approved there, and opens no run until the release has what it needs, so editing the database approves nothing. An image whose code isn't what it was built with doesn't run at all. Someone leaving is a release of its own, which those who stay approve: a release approver hands over by bringing their successor in with one release, and leaving with the next, and the history still checks out. What people sign is an approval of the release: its manifest, the image it runs as, the release it follows there, and the security advisory it fixes, if it's approved as fixing one, so none of them can be changed or added after. If the only release approver left before handing over, the release in use is signed again as a baseline (`a5s release sign --baseline`), which needs everyone and is judged by the release before it all the same, except that a role nobody of record who remains could hold may be signed for by someone it brings in, as long as assurance of record signs it too. Only the first release a deployment approves follows none.

| An instance is | Means | Who moves it on |
| --- | --- | --- |
| Proposed | Created by its agent owner, waiting for approval | Its instance approvers |
| Active | Working, in the parts whose owners approve it | The agent owner, the deputy or the platform owner can suspend it, except that stopping an agent the scenario marks as a check needs the scenario's assurance. The agent owner or the platform owner can retire it. |
| Suspended | No trigger wakes it, its next call is denied, even in a run already going, and its open work is withdrawn or flagged in the scenario's process | Whoever suspended it can resume it. Anyone else needs someone outside the team, because resuming loosens. Never while it has neither an owner nor a deputy. |
| Retired | Its identity is disabled, its grant removed and its evidence archived. Conversations follow the retention rules. | Nobody |
| Shadow | A new version answering beside the instance it shadows, sending and changing nothing, for graders to compare ([shadow runs](#shadow-runs)). It has no work of its own. | As an active instance: suspended, it answers nothing, and resumed, it's a shadow again. The owners of its parts make it an instance of its own by taking `shadows` out of its settings. |

- A part owner can stop an instance acting in their part at any time, by withdrawing its approval in the settings.
- If the agent owner and the deputy both leave, the instances are suspended until the platform owner names a new owner.
- An instance moves to another approved release when its agent owner moves it. Runs start fresh, so nothing needs migrating, and it can always go straight back to the release it ran before.
- a5s keeps its caps for a behaviour, not a release: the agent, its model, and the tools of a type of action it may use, as pinned. A release that changes only instructions or skills keeps its caps, after its regression suite and a re-run of the last graded samples; one that changes a tool of that type, or the model, starts again at level 1 for what it widens.

## Autonomy

| Level | The agent may | People |
| --- | --- | --- |
| 0. Observe | Read, measure and report | Read what it reports |
| 1. Propose | Prepare drafts, raise requests in a governed process, and, from phase 2, hold proposals ([how](architecture.md#proposals-and-approvals)) | A person decides each one |
| 2. Act and notify, from phase 2 | Take actions of a type the part owner has approved, within the scenario's limits, through the governed process where there is one | The agent owner reviews them and can reverse any |

- The level is set for each instance, part and type of action, in the settings. Where none is set, the release's starting level applies, which can only be 0 or 1, so level 2 always comes from the settings, never from the release. The release's maximum caps whatever the settings say. A part's own level applies to drafts and requests, and is never above 1; a change of a type the settings don't set for the part works at level 1 at most, so level 2 is always for a type of action, such as `parts: {billing: {level: 1, actions: {change-due-date: 2}}}`, and the settings must give that type a limit.
- An instance works only on records in its parts, and only on those everyone it acts for may see. A call about records works at the lowest level it has in their parts, and one about no record in particular at the lowest of all its parts.
- A level-2 setting counts only while someone who approved the settings in force still owns the part. If the part's owner changes, no run opens until the new owner approves the version in force, and level 2 counts again only once they have.
- a5s also keeps a cap for each behaviour, part and type of action, which starts at 1, and the instance works at the lower of the cap and the setting. The cap rises only when samples pass ([starting values](starting-values.md)), and falls when they fail or someone who may lowers it, such as the agent owner or the part's owner (`a5s caps lower`). Nobody raises it by hand.
- A change about no record, about a record in no part, or from a run that has read content from outside, or whose conversation holds what such a run passed on, works at level 1 at most, and so does any change past the scenario's limits for its type.
- An action that touches several parts works at the lowest of their levels.
- Reminding, chasing and routing are allowed at every level, within the contact rules, because they change no data.
- A scenario's policy pack can rule out level 2 for some actions, such as anything a person asked for in their own words, or narrow it, such as to self-service that the identity provider verifies.
- There's no level above 2. An agent that acts always tells someone.

### Undoing a change

A tool that changes a record can say how the change is reversed (`undo`, [`core/undoing.py`](../src/a5s/core/undoing.py)): by calling a tool of the scenario's, often the same one, with arguments from the change's own (`args.<name>`) and from the record as it stood before it (`before.<field>`, a field of the record as the scenario gives it), for as long after it's made as the tool says, a day unless it says otherwise and a week at most. The sample's `change_due_date` is undone by setting the due date the question had before, for a day. How a tool is undone is part of what its approvers pin, in its hash, and the core doesn't start with an undo that names a tool it hasn't, or doesn't name the record the change did.

- **What a5s keeps.** When a5s makes such a change, at level 2 or once its deciders approve it, it keeps the call that reverses it, worked out then, and the fields it restores as the change left them, read again just after. A change about more than one record, or to a record a5s couldn't read before, can't be undone this way.
- **Who may undo it.** Whoever it was for, and whoever decides that type of change in its record's part, so long as they may see the record, until its time is up. Whoever it was for finds it on their home, and the agent is told how and until when, to tell them, as the instance's owner is, in their digest. Each undoes it on its page in the studio, `/studio/undo?change=<id>`, signing in afresh for that act alone, as for deciding: the channels app records it with the sign-in and can undo nothing, and the core checks the sign-in again, and whether they may now, then makes the call that reverses it, within a minute.
- **Only as the change left it.** A record someone has changed since is left as it is: putting it right is for whoever changed it, in the records system. So is one that can't be read just then. A tool that has changed since undoes nothing.
- **It counts against the agent.** An undone change counts as a wrong grade of the agent's work, which the core seals at once, whether or not it was drawn as a sample, so an agent whose changes people undo loses level 2 sooner, and earns it later ([samples](#autonomy)). A critical grade stays critical.
- **Everyone hears.** The ledger records each undo and who asked for it, never what the record held. Whoever the change was for, and the instance's owner and deputy, hear of it in their digest, and the agent's next run knows, from the conversation. Whoever asked hears in their digest of one a5s couldn't undo, and why.

A tool from an MCP server says the same in `mcp.yaml`, as `undo: {tool, args, hours}` ([connectors](connectors.md#declaring-them)).

### Handing a conversation over

An agent can hand a person's conversation over to people, such as the service desk, who answer them in the same chat until they hand it back ([`core/handover.py`](../src/a5s/core/handover.py)). An instance's settings name the directory's teams it may hand one to, `hands_to: [service-desk]`, which the owners of its parts approve, as they approve whom it may ask, reading it in words; and its agent's release lets it, `context: {handover: true}`. The core won't take a version that names a team nobody in the directory is in, or an agent whose release hands nothing over, and checks at every run that the instance hands to the teams its signed settings name, as it checks whom it may ask. The map shows each team an instance may hand to.

- **At the person's word.** The agent hands it over with `hand_over`, naming the team and a short brief of what the person needs, only in answer to a message of theirs, in their own chat, never a group chat's, and never from a run that has read content from outside. a5s tells the person, in their chat, who takes it from there and what they see.
- **What the team reads.** The brief, and what the person said in this talk, back to the last time they left it a day or more, their own words alone, never anything older, nor the agent's answers, whose records may not be the team's to see. A record's key any of them may not see reads as such. The agent writes the brief from what its run read, which it may say without naming a record, so someone of the team reads it only if they may see every record that run handled, as the studio would show them the run; anyone else reads what the person said instead. The channels app reads no conversation: the core keeps those words with the handover.
- **While it's handed over,** the agent answers nothing in that chat. The team finds it on their home and on the studio's page of conversations handed to them, `/studio/handovers`. One of them takes it, and answers from the studio; the core puts each answer in the person's chat, as the agent's bot, with the answerer's name, cleaned as anything a5s sends is, the scenario's own links alone and never a5s's own notes, and keeps it, with what the person wrote, in their conversation: as theirs, whose words the agent reads, never as a5s's on its behalf.
- **Handed back,** by whoever took it, or anyone of the team, the agent answers again, knowing what was said, and the person is told. One nobody has answered or handed back in three days is handed back. What the person wrote meanwhile that nobody answered, the agent answers once, given all of it as they wrote it and when, never each in a run of its own as if just said.
- **Whose words.** A value the agent takes from a team's answer, such as a date someone of the team agreed, says so to whoever decides the change it asks for, and whoever wrote it decides nothing of that change, as nobody decides what their own words in a group chat asked for.

The ledger records each handover, each answer's delivery and its end, never the words.

### Shadow runs

A new version of an agent can answer what people ask an instance, beside it, sending and changing nothing, so its answers are graded before anyone puts it to work ([`core/shadows.py`](../src/a5s/core/shadows.py)). The new version is released as an agent of its own, such as `assistant-next`, with its new instructions, or another model, and its own regression suite. A shadow is an instance of it whose settings name the instance it answers beside:

```yaml
instances:
  assistant-next-finance:
    definition: assistant-next
    serves: [ana, ben]        # nobody assistant-finance doesn't serve
    parts: [billing]          # and no part it doesn't work in
    owner: ana
    shadows: assistant-finance
data_protection:
  shadow_runs: true           # the data protection officer's choice
```

- **The officer's choice.** A shadow reads what people say to the instance it shadows, and what their records hold, on a model that may be new, and graders read what was said and what it answered. So the data protection officer chooses whether shadows may answer at all, `shadow_runs` in the signed settings, which a version changes only with their approval. Without it, the core takes no version with a shadow in it, and opens no shadow's run.
- **What its approvers read.** The owners of its parts approve it as any instance, reading that it answers what the instance it shadows is asked, beside it, as the same people, sending and changing nothing. The core won't take one that serves anyone the instance it shadows doesn't, works in a part it doesn't, shadows a shadow, or asks or hands over anything.
- **Beside each answer.** Once the instance it shadows has answered a message, the shadow answers the same, as the same people, given the conversation as that run was given it, and the files they sent with it, under the same need-to-know. Its status, `shadow`, gives it no work of its own: no message, reminder, schedule, report or task is ever its. A run of its own is refused, and so is a second answer beside the same run.
- **Its model.** It's given the conversation of the instance it shadows, which holds what that instance's model may read, so the core opens a shadow's run only on a model approved for the settings' class of data and for each class of field the other's model may read, and says in the ledger why not.
- **It only reads.** The policy lets a shadow call only the tools of its grant that change, write and send nothing, and its own model, and lets it send nothing at all. Of a5s's own tools, it's offered only those that read: searching the conversation, asking a5s's reader, and listing reminders and tasks. What it answers goes nowhere: the core keeps it beside the answer that was sent, cleaned as any message is.
- **Graded beside the answer sent.** Graders, from outside the team that built the shadow's agent and the teams of its instance's owners, as for samples, and never anyone it answered, read each pair whose records they may all see, and whose documents they may all read, while the officer's choice lets shadows answer: until the officer agrees to names, none of an instance serving fewer people than they chose, and the rest with names, emails, links and long numbers masked by code, as answers said to be wrong are. They read it on the studio's page of new versions' answers, `/studio/shadows`, never whose it was. They say whether the new version's answer is better, as good, worse, or wrong. A shadow whose agent names a [judge](#the-judge) hears from it too, kept apart from people's grades. Its owners, the owners of the instance it shadows and its agent's owners read how it did, in counts, and so do graders it offers a pair to, or who graded one, or who may know its agent exists.
- **Costs and figures.** A shadow's runs are its own, with their own budget and spending, so what a new version costs is seen beside what it answers.

A shadow's grades move no cap: they're evidence for its owners, who put the new version to work, if they choose, with a release of the agent it shadows, or by taking `shadows` out of its settings. The ledger records each shadow's run and answer, and each grade, never the words.

## The definition format

A definition is a folder in git. A hash of everything in it is part of the release, so any change to the folder is a new release:

```text
agents/assistant/
  agent.yaml     the definition
  AGENTS.md      instructions, loaded read-only on every run
  tools.lock     the schema of each tool it uses, pinned by hash
  skills/        Agent Skills, one folder each, whose SKILL.md names it and says what it's for, as
                 text a run reads: Markdown, text, CSV, JSON or YAML, never a script, since no
                 run can run one
  tests/         its regression cases, run against the model it names before each release
```

This is [`agent.yaml`](../agents/assistant/agent.yaml) for the assistant, one of the two reference agents [phase 1](phase-1.md) builds. Fields marked for later steps are read but not yet used.

A scenario may instead carry its own definitions in `scenarios/<name>/agents/`, as the service-desk scenario does. Set `A5S_AGENTS_DIR` to that folder along with `A5S_SCENARIO_DIR`; the release then includes only those agents, leaving the reference deployment's release and web-chat agent list unchanged. With no such setting, agents come from the root's `agents/` folder.

```yaml
id: assistant
release: 0.1.0
works_for: The people its instance is assigned to
does: >-
  Keeps one conversation with each person, drafts on request, records the
  follow-ups it offers and the reminders people ask for, and chases what
  falls due.
scope: none                      # it changes no part's data
model: deepseek-v4-pro           # from config/models.yaml, the approved list
autonomy:
  start: 1
  max: 1                         # it drafts, and people decide
tools:
  records: [search_records, get_record]    # the scenario's records, read only
  documents: [create_draft]
triggers:
  - message: from the people it works for
obligations: [records]           # it reminds its people of what falls due in the records
schedules: []                    # none: what it does, it does for someone
reminders: true                  # it offers reminders, and keeps those people confirm
preferences: [digest-time, how-i-work]
channels: [teams]
listed: false                    # the studio's catalogue shows it to everyone, if true: else
                                 # only to those with a role on it, and the people it serves
context:
  budget_tokens: 24000           # split by part, tested at release
  recall: true                   # it searches its conversation with the person it acts for
budget:                          # in tokens, as the providers count them [TBC: from current volumes]
  per_run: 200000
  per_person_per_day: 1000000    # a fifth kept for chases and reminders, and tasks stop at three fifths
evaluation:                      # a judge of its work, beside people's grades ([below](#the-judge))
  judge: deepseek-v4-pro         # an approved model, best another than its own
  rubric: A due date moves only to a date the customer asked for, and never into the past.
```

Each model call carries the whole context and, beside it, the instructions, the tools and what the run has read so far, so the budgets are checked against the context when a release is loaded: a run's budget must fit six calls of the context and about 6,000 tokens beside it, and a person's day, beside the fifth kept for chases and reminders, twelve answers of two calls each. A release that doesn't fit is refused.

A schedule names its times, in the time zone of the instance's owner, its days, and the task a5s gives the agent each time, such as `{name: morning, at: "09:00", days: weekdays, task: Look through the open questions.}`. Times need quotes, because YAML reads an unquoted 9:00 as a number.

An event is what another system says happened, such as a ticket opened: `events` names each the agent takes, by its `type`, the `source` that sends it, as the deployment names that system, and the `task` a5s gives the agent each time, such as `{type: ticket-opened, source: itsm, task: Read the new ticket, and if it's a known problem, propose its fix.}`. The system names the records it's about and the person, if anyone, and nothing else: the agent reads what it needs of each record itself, through its tools. Within a minute, an instance at work in every record's part works on it, one that serves the person it names first, acting for them and writing to them, in a topic of its own, which their reply continues for a while: what the run read, such as a requester's words from outside, marks that topic alone, never their own chat. Nobody asked for the run, and whoever holds the system's secret, or poses as someone to it, can start one, so it never acts as them in another system, nor reads what they may read there with their own account, and a change it asks for says it came after the event, about them, and that nobody asked for it. An event that names nobody acts for nobody, as a schedule's run does, on a day's budget each system has of its own, as one person's day. One that can't be worked on now, such as while its instance is suspended, its release waits for approval, or the day's budget is spent, waits and is tried again every half hour, for two days at most, when it's turned away, and the ledger says why; and each system's events take their turn, so one that sends many holds no other's back. Taking events widens what an agent does, so its release approver signs for them ([`core/events.py`](../src/a5s/core/events.py)).

An agent whose release keeps reminders gets a5s's own tools for them: it offers a reminder, or to follow something up, and a5s keeps it only once the person says yes in a later message of their own. Its people can list and cancel theirs, and say what they're waiting on for one of their records, which pauses a5s's chases about it until the date they give. Confirming names the offer the person said yes to, so two offers waiting are never confused.

An agent whose release names `tasks`, with the most one may spend, `budget_tokens`, and the `days` it has, takes on long tasks for people: work that takes more than one run, such as going through every open record of someone's. It offers one in the person's own chat, and it starts only once they say yes in a later message, as a reminder does. a5s then works on it a slice at a time, each slice a run of the agent's that acts for them, which the scheduler opens when it's due: the run is told the task, its plan and what its earlier runs found, and each of its model calls is held to what's left of the task's budget. It keeps its work with `checkpoint_task`, says what it came to with `finish_task`, and writes to the person only once it's done or needs them. It can split its work into parts that can be done apart (`split_task`), each a task of its own with a share of the budget, and goes on once they've ended, told what each found. A task that stops without a word, such as when its deadline passes, a5s tells them about itself. Each of its runs is given what its earlier runs read, with where each value came from, and opens marked if any of them read content from outside, so nothing an earlier run made up passes as the records'. People can ask for one to be done again and again, such as every Monday at 09:00, and each time it comes round it's a task of its own; to change one, the agent offers it as it'll be, and it takes the old one's place once they say yes. People list and stop theirs through the agent, or on their own page (`/tasks/`), and when one needs them, say what it needs, and it goes on ([phase 4](phase-4.md), [`core/tasking.py`](../src/a5s/core/tasking.py)).

A report names a kind of record, such as `{source: records}`, as the [watcher's](../agents/watcher/agent.yaml) does. Each working day, in each person's digest, the agent tells each person it serves what changed in their records of that kind since it last told them, and what fell due. The first time, it tells them what's open. Code works the facts out from the records, and the agent only puts them into words, so a day with nothing new starts no model. The run acts for that person alone.

The preferences a release lists are those people may set through the agent, such as `digest-time`, the time their daily digest comes, which a5s's own tool sets when they ask.

The register adds what changes without a release: each instance, its identity and its status. Each deployment's signed settings name who an instance serves, by name or as a team or a role's holders, such as `team:sales`, which the directory resolves when each run opens, its level, and its owner and deputy, who are people in that deployment's directory, so the same definition serves any scenario.

## The judge

An agent's definition may name a judge, an approved model, with its rubric: what a right change is for this agent, in its owners' words. a5s asks the judge about each sample of the agent's work it draws for people to grade, as their page shows it: the change, in code's words, what code flagged to its decider, the records it named as they stood, and what its decider did. The judge says right, wrong or critical, and why, in a sentence ([`core/judging.py`](../src/a5s/core/judging.py)).

- **People's grades stay the evidence.** The test that raises and lowers a5s's caps reads people's grades alone, so a judge's verdict never moves a cap, however sure it is ([autonomy](#autonomy)).
- **People grade blind.** The channels app, which serves the grading page, can read a verdict only once people have graded its sample, so graders grade as they would without it.
- **a5s measures the judge.** On the samples both graded, `a5s measures` and the studio's figures say how often the judge agreed with people, how often it passed what they found wrong or critical, and so missed it, how often it failed what they found right, and Cohen's kappa, their agreement beyond chance. Its owners learn, as the evidence grows, how far to trust it.
- **It sees only what it's approved for.** A judge reads a sample as its decider did: the values the agent's handles stood for, and every field of the records it named. So a judge not approved for the class of data the settings name, for every class they give a field, and for every one its agent's own model is, judges nothing. Each call is in the ledger, by the hash of what it was asked, and a verdict goes with its sample, a year after it's graded, and is in an export of the people it's about.

A judge reads what a sample's records say, which may hold instructions, so it's told never to follow them, and a5s keeps only its grade and a sentence of why: an answer it can't read as a grade it keeps as none, and doesn't ask again.

The same judge grades the agent's test cases where they ask it: a step that says what a right answer is, in its author's words (`judged`), for an answer that can be right in more than one way. It's shown what was said, what the agent answered and the tools it used, and grades it as it grades a sample; the step passes only if it says right, beside its exact checks, in the agent's suite before each release and in the studio's sandbox ([`cases.py`](../src/a5s/cases.py), [studio](studio.md)). A test case's verdict moves nothing either: it's what the case found, for the people who approve the release.
