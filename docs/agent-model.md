# Agent Model

**Status:** Draft v0.2, design only · **Under:** [Architecture](architecture.md)

## Definitions, releases, instances, conversations and runs

| Object | What it is | Lasts |
| --- | --- | --- |
| Definition | A kind of agent: its job, and whom it works for | Until it's retired |
| Release | A tested, approved version of a definition. It fixes the instructions, skills, tools, model, triggers, obligations, the preferences people can set, the context budget and the limits. | Until it's withdrawn |
| Instance | A definition at work in a scope, with its own identity, grant, obligations and status | As long as the scope needs it |
| Conversation | Everything one person and one agent have said to each other, in topics, whichever of the agent's instances did the work | As long as they work together, then as the retention rules say |
| Run | One piece of work, from a trigger until it's done, on a LangGraph thread that ends with it | Minutes |

In the lean scenario, the owner assistant is a definition, and its release 0.3.0 a release. The owner assistant for supplier general data is an instance. A delegate's exchanges with the owner assistant are a conversation, and preparing the case pack for one routed request is a run.

## Terms a scenario fills in

| Term | Means |
| --- | --- |
| Part | A piece of the business with one owner. Every field an agent touches belongs to one part. |
| Part owner | Approves agents to act in the part, and how far. Decides their proposals there, or names delegates to. |
| Scope | The parts an instance may act in: one, several, or none, for an agent that acts on no part's data |
| Grant | The tools, data and models an instance may use: what its release lists, as far as its parts' owners approve |
| Type of action | A kind of action that a level is set for, defined by the fields it changes and the check it serves |
| Acts for | Everyone whose words a run serves: whoever sent the message, set the reminder, or wrote the reply a request came from. A run started only by an event or a schedule acts for nobody. |

The [scenario contract](architecture.md#the-scenario-contract) says where the settings, the governed process and the decision surface come from. Each scenario's page maps these terms, as the [lean framework](../scenarios/lean-framework.md) and the [IT service desk](../scenarios/it-service-desk.md) do.

## Roles

| Role | Does |
| --- | --- |
| Platform owner | Accountable for a5s and the agents it runs. Names each agent owner and deputy, and can suspend any instance or withdraw any release. |
| Agent owner, with a deputy | Builds and runs a definition and its instances. Reviews level-2 actions and can reverse them. Can suspend the agent's instances, lower their cap and withdraw its releases. |
| Part owner, and delegates | The part owner approves an instance for the part, sets how far it may act there, and moves it up or down. They or their delegates decide its proposals, as the scenario allows. Decisions about the agent itself are never a delegate's. |
| Instance approver | For each part in an instance's scope, its owner. For an instance with no parts, whoever the scenario names, who also sets its level. |
| Release approver | Approves releases that widen what an agent may do, and changes to the trusted core. Never from the team that runs a5s, or its manager's reporting line. The scenario names who. |
| Graders, from phase 2 | Grade samples of an agent's work. Never from the team that built it. |
| Assurance | Holds the ledger's anchor, reads the ledger, and is told of everything that loosens a5s |

## Lifecycle

| A release is | Means |
| --- | --- |
| Draft | Being built or changed |
| Approved | Passed its tests and has the approval its kind of change needs ([independence](architecture.md#independence)). Instances can run it until it's withdrawn. |
| Withdrawn | No instance may run it. The agent owner, the release approver or the platform owner can withdraw it, and a security advisory withdraws every release that pins the affected version. Instances still on it are suspended until they move to another release. |

| An instance is | Means | Who moves it on |
| --- | --- | --- |
| Proposed | Created by its agent owner, waiting for approval | Its instance approvers |
| Active | Working, in the parts whose owners approve it | The agent owner, the deputy or the platform owner can suspend it. The agent owner or the platform owner can retire it. |
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

- The level is set for each instance, part and type of action, in the settings. Where none is set, the release's starting level applies, which can only be 0 or 1, so level 2 always comes from a part owner. The release's maximum caps whatever the settings say.
- A level-2 setting records who approved it and the version of the part. If either changes, it drops to level 1 until the new owner sets it.
- From phase 2, a5s also keeps a cap for each instance and type of action, and the instance works at the lower of the cap and the setting. The cap rises only when samples pass ([starting values](starting-values.md)), and falls when they fail or the agent owner lowers it. Raising it by hand loosens, so it needs someone outside the team.
- An action that touches several parts works at the lowest of their levels.
- Reminding, chasing and routing are allowed at every level, within the contact rules, because they change no data.
- A scenario's policy pack can rule out level 2 for some actions altogether. The lean pack does for any request that came from a person's words, while the IT service desk's allows it for self-service that the identity provider verifies.
- There's no level above 2. An agent that acts always tells someone.

## The definition format

A definition is a folder in git, and each release is a tagged version of it:

```text
agents/governance-coordinator/
  agent.yaml     the definition
  AGENTS.md      instructions, loaded read-only on every run
  skills/        Agent Skills, one folder each, pinned by hash
  tests/         regression and scenario tests
```

This is `agent.yaml` for the governance coordinator, the first agent [phase 1](phase-1.md) builds. Field names will settle as the code is written.

```yaml
id: governance-coordinator
release: 0.1.0
works_for: The GPDOs, and the owners of exceptions and decisions
does: >-
  Tracks exceptions before they expire, ownership gaps and open decisions.
  Reminds and chases their owners, and drafts the owner review pack.
owner: "[TBC]"
deputy: "[TBC]"
scope: none                      # it acts on no part's fields
model: "[TBC: from the approved models list]"
autonomy:
  start: 1
  max: 1                         # it drafts, and people decide
tools:
  exception-register: [list_exceptions, get_exception]
  ownership: [get_owners, list_gaps]
  document-library: [create_draft]
triggers:
  - message: from the people it works for
  - schedule: weekdays at 08:00              # a sweep for new gaps
  - schedule: two weeks before the owner review
obligations:
  - type: exception-expiring
    source: exception-register
    due: 14 days before expiry   # [TBC]
reminders: yes                   # follow-ups it offers, and reminders people ask for
preferences: [digest-time, channel]
channels: [teams]
context:
  budget_tokens: 50000           # split by part, tested at release
budget:
  per_run: "[TBC]"
  per_person_per_day: "[TBC]"
```

The register adds what changes without a release: each instance, its identity and its status.
