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
| Acts for | Everyone whose words a run serves: whoever sent the message, set the reminder, or wrote the reply a request came from, whoever a reminder of an obligation is for, and whoever a report on their own records is for. A run started only by an event or a schedule acts for nobody. A run writes only to the people it acts for. |

The [scenario contract](architecture.md#the-scenario-contract) says where the settings, the governed process and the decision surface come from. Each scenario's page maps these terms, as the [IT service desk](../scenarios/it-service-desk.md) does.

## Roles

Roles are held by people, never by job titles. An organisation assigns people to roles in its directory, and a5s checks each role's rules in code whenever the role is used, such as an approver coming from outside the team that runs a5s and its manager's reporting line. The platform owner and the release approver for the trusted core are a5s's own roles, held once for all of it. Each scenario assigns the rest.

| Role | Does |
| --- | --- |
| Platform owner | Accountable for a5s and the agents it runs. Names each agent owner and deputy, and can suspend any instance or withdraw any release. |
| Agent owner, with a deputy | Builds and runs a definition and its instances. Reviews level-2 actions and can reverse them. Can suspend the agent's instances, lower their cap and withdraw its releases. |
| Part owner, and delegates | The part owner approves an instance for the part, sets how far it may act there, and moves it up or down. They or their delegates decide its proposals, as the scenario allows. Decisions about the agent itself are never a delegate's. |
| Instance approver | For each part in an instance's scope, its owner. For an instance with no parts, whoever the scenario names, who also sets its level. |
| Release approver | Approves what loosens a5s: releases that change a tool or widen what an agent may do, changes to the trusted core, and anything else the scenario names nobody else for. Never from the team that runs a5s, or its manager's reporting line. |
| Graders, from phase 2 | Grade samples of an agent's work. Never from the team that built it. |
| Assurance | Holds the ledger's anchor, reads the ledger, and is told of everything that loosens a5s |

## Lifecycle

| A release is | Means |
| --- | --- |
| Draft | Being built or changed |
| Approved | Passed its tests and has the approval its kind of change needs ([independence](architecture.md#independence)). Instances can run it until it's withdrawn. |
| Withdrawn | No instance may run it. The agent owner, the release approver or the platform owner can withdraw it, and a security advisory withdraws every release that pins the affected version. Instances still on it are suspended until they move to another release. |

Each organisation approves a release for its own deployment, with its own people. A release of a5s is everything it runs there: from its image, the trusted core, the services and what the image was built from; from the deployment, its approved models, its scenario's directory and tools, and its agents' definitions. Its manifest lists a digest of every file, and what each agent and model may do (`a5s release show`). The people its changes need sign the manifest with their own keys (`a5s release sign`), anywhere and offline, and the administrator records the signatures (`a5s release approve`). What it needs comes from comparing it with the release approved there before ([independence](architecture.md#independence)), and different people must meet each need. The core checks the signatures again, against the directory, back to the first release approved there, and opens no run until the release has what it needs, so editing the database approves nothing. An image whose code isn't what it was built with doesn't run at all. If someone who approved one of those releases leaves, or their key changes, the history no longer checks out, and once restarted the core opens no run until the release in use is approved again as a baseline (`a5s release approve --baseline`), which needs everyone.

| An instance is | Means | Who moves it on |
| --- | --- | --- |
| Proposed | Created by its agent owner, waiting for approval | Its instance approvers |
| Active | Working, in the parts whose owners approve it | The agent owner, the deputy or the platform owner can suspend it, except that stopping an agent the scenario marks as a check needs the scenario's assurance. The agent owner or the platform owner can retire it. |
| Suspended | No trigger wakes it, its next call is denied, even in a run already going, and its open work is withdrawn or flagged in the scenario's process | Whoever suspended it can resume it. Anyone else needs someone outside the team, because resuming loosens. Never while it has neither an owner nor a deputy. |
| Retired | Its identity is disabled, its grant removed and its evidence archived. Conversations follow the retention rules. | Nobody |

- A part owner can stop an instance acting in their part at any time, by withdrawing its approval in the settings.
- If the agent owner and the deputy both leave, the instances are suspended until the platform owner names a new owner.
- An instance moves to another approved release when its agent owner moves it. Runs start fresh, so nothing needs migrating, and it can always go straight back to the release it ran before.
- From phase 2, a release that widens what an agent does starts at level 1 for what it widens, and earns level 2 on samples. One that changes only instructions or skills keeps its cap if the last graded samples still pass when re-run.

## Autonomy

| Level | The agent may | People |
| --- | --- | --- |
| 0. Observe | Read, measure and report | Read what it reports |
| 1. Propose | Prepare drafts, raise requests in a governed process, and, from phase 2, hold proposals ([how](architecture.md#proposals-and-approvals)) | A person decides each one |
| 2. Act and notify, from phase 2 | Take actions of a type the part owner has approved, within the scenario's limits, through the governed process where there is one | The agent owner reviews them and can reverse any |

- The level is set for each instance, part and type of action, in the settings. Where none is set, the release's starting level applies, which can only be 0 or 1, so level 2 always comes from the settings, never from the release. The release's maximum caps whatever the settings say.
- A level-2 setting records who approved it and the version of the part. If either changes, it drops to level 1 until the new owner sets it.
- From phase 2, a5s also keeps a cap for each instance and type of action, and the instance works at the lower of the cap and the setting. The cap rises only when samples pass ([starting values](starting-values.md)), and falls when they fail or the agent owner lowers it. Raising it by hand loosens, so it needs someone outside the team.
- An action that touches several parts works at the lowest of their levels.
- Reminding, chasing and routing are allowed at every level, within the contact rules, because they change no data.
- A scenario's policy pack can rule out level 2 for some actions, such as anything a person asked for in their own words, or narrow it, such as to self-service that the identity provider verifies.
- There's no level above 2. An agent that acts always tells someone.

## The definition format

A definition is a folder in git. A hash of everything in it is part of the release, so any change to the folder is a new release:

```text
agents/assistant/
  agent.yaml     the definition
  AGENTS.md      instructions, loaded read-only on every run
  tools.lock     the schema of each tool it uses, pinned by hash
  skills/        Agent Skills, one folder each, from a later step
  tests/         its regression cases, run against the model it names before each release
```

This is [`agent.yaml`](../agents/assistant/agent.yaml) for the assistant, one of the two reference agents [phase 1](phase-1.md) builds. Fields marked for later steps are read but not yet used.

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
preferences: [digest-time, channel]
channels: [teams]
context:
  budget_tokens: 50000           # split by part, tested at release
budget:
  per_run: "[TBC]"
  per_person_per_day: "[TBC]"
```

A schedule names its times, in the time zone of the instance's owner, its days, and the task a5s gives the agent each time, such as `{name: morning, at: "09:00", days: weekdays, task: Look through the open questions.}`. Times need quotes, because YAML reads an unquoted 9:00 as a number.

An agent whose release keeps reminders gets a5s's own tools for them: it offers a reminder, or to follow something up, and a5s keeps it only once the person says yes in a later message of their own. Its people can list and cancel theirs, and say what they're waiting on for one of their records, which pauses reminders about it until the date they give.

A report names a kind of record, such as `{source: records}`, as the [watcher's](../agents/watcher/agent.yaml) does. Each working day, in each person's digest, the agent tells each person it serves what changed in their records of that kind since it last told them, and what fell due. The first time, it tells them what's open. Code works the facts out from the records, and the agent only puts them into words, so a day with nothing new starts no model. The run acts for that person alone.

The preferences a release lists are those people may set through the agent, such as `digest-time`, the time their daily digest comes, which a5s's own tool sets when they ask.

The register adds what changes without a release: each instance, its identity and its status. Each deployment's signed settings name who an instance serves, its level, and its owner and deputy, who are people in that deployment's directory, so the same definition serves any scenario.
