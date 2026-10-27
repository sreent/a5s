# Agent Model

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md)

## Definitions, releases, instances and runs

| Object | What it is | Lasts | In the lean scenario |
| --- | --- | --- | --- |
| Definition | A kind of agent and its job | Until it's retired | The owner assistant |
| Release | A tested, approved version of a definition. It fixes the agent's instructions, skills, tools and their definitions, model, triggers, obligation and reminder types, memory rules and limits. | Until it's withdrawn | The owner assistant, release 0.3.0 |
| Instance | A definition at work in a scope, with its own identity, obligations, memory and status | As long as the scope needs it | The owner assistant for supplier general data |
| Run | One piece of work by an instance, from a trigger until it's done | Minutes of work, parked while a person decides | Preparing the case pack for one routed request |

## Terms that connect a5s to a scenario

| Term | Means | In the lean scenario |
| --- | --- | --- |
| Part | A piece of the business with one owner. Every field an agent touches belongs to one part. | A part of a domain, by subdomain, business unit or group of fields. One record's fields can sit in different parts. |
| Part owner | Approves agents to act in the part, and how far. Decides their proposals there, or names delegates for the decisions the scenario lets delegates take. | The part's attribute owner |
| Scope | The parts an instance may act in: one part, several, or none | One part, a domain's parts, or none, for agents that don't touch master data |
| Grant | The tools, data and models an instance may use: what its release lists, as far as its parts' owners approve | Trade-secret fields only as their attribute owner grants them |
| Type of action | A kind of action that autonomy is set for | A change type, as the domain profile names it |
| Settings | Where part owners keep what a5s reads live: who owns what, which agents they approve and how far, thresholds, sensitive fields and classes of data | The domain profiles and ownership settings, in the unified master data app |
| Governed process | A system's own way of making and approving changes, which agents hand requests to instead of changing data themselves | Requests in the unified app |
| Decision surface | Where people take decisions on agents' proposals | The unified app |
| Acts for | The person whose message or request started a run, if any. A run started by an event or a schedule acts for nobody. | A requester who asks the request assistant for help |

## Roles

| Role | Does |
| --- | --- |
| Platform owner | Accountable for a5s and the agents it runs. Names each agent owner and deputy, and can suspend any instance and withdraw any release. |
| Agent owner, with a deputy | Builds and runs a definition and its instances. Reviews level-2 actions and can reverse them, reviews runs that were cut off, and approves memory entries [TBC]. Can suspend the agent's instances, lower their cap and withdraw its releases. |
| Part owner, and their delegates | The part owner approves an instance for the part, sets how far it may act there, and moves it up or down. They or their delegates decide its proposals, as the scenario allows. Decisions about the agent itself are never a delegate's. |
| Instance approver | Approves an instance to run. For each part in its scope, the part owner. For an instance with no parts, whoever the scenario names, who also sets its level and can withdraw its approval. |
| Release approver | Approves each release after its tests and design review, and can withdraw it. Never someone who built it. The scenario names who. |
| Assurance | Reads the ledger and the samples, and reviews what the scenario asks it to |

## Lifecycle

| A release is | Means |
| --- | --- |
| Draft | Being built or changed |
| Approved | Passed its tests and design review, and approved. Instances can run it until it's withdrawn. |
| Withdrawn | No instance may run it. The agent owner, the release approver or the platform owner can withdraw a release, and instances still on it are suspended until they move to another. |

| An instance is | Means | Who moves it on |
| --- | --- | --- |
| Proposed | Created by its agent owner, waiting for approval | Its approvers: each part's owner, in the settings, or the scenario's approver for an instance with no parts |
| Active | Working, in the parts whose owners have approved it, or, with no parts, while the scenario's approval stands | The agent owner, the deputy or the platform owner can suspend it. The agent owner or the platform owner can retire it. |
| Suspended | No trigger wakes it, every call is denied, even in a run already going, its pending proposals are withdrawn, and its open requests are withdrawn or flagged | Whoever suspended it, or the platform owner, can resume it, but not while the agent has neither an owner nor a deputy |
| Retired | Its identity is disabled, its grants removed, its evidence archived and its memory deleted under the retention rules | Nobody. It's gone. |

- The agent owner, the deputy and the platform owner can also suspend every instance of a definition at once.
- A part owner can stop an instance acting in their part at any time, by withdrawing its approval in the settings.
- If the agent owner and the deputy both leave, the instance is suspended until the platform owner names a new owner.
- An instance moves to another approved release, newer or older, when its agent owner moves it. Its settings carry over, and its cap goes back to level 1 until samples of that release pass.

## Autonomy

| Level | The agent may | People |
| --- | --- | --- |
| 0. Observe | Read, measure and report | Read what it reports |
| 1. Propose | Prepare drafts, hand requests to a governed process, and hold proposals for a person ([how](architecture.md#proposals-and-approvals)) | A person decides each one: whoever uses a draft, whoever the process routes a request to, or, for a held proposal, the part owner or a delegate |
| 2. Act and notify | Take actions of a type the part owner has approved, within the scenario's limits, through the governed process where there is one | The agent owner reviews them and can reverse any of them |

- The level is set for each instance, part and type of action, in the settings. Where it isn't set, the definition's starting level applies. That can only be 0 or 1, so level 2 always comes from a part owner. A release's maximum is the highest level it allows, whatever the settings say.
- a5s also keeps a cap for each instance and type of action, and the instance works at the lower of the cap and the setting. The cap starts at level 1 for each release, rises when samples of that release's work pass [TBC: how many], and falls when samples fail or the agent owner lowers it. The part owner is told of every change.
- An action that touches fields in several parts works at the lowest of their levels.
- Reminding, chasing and routing are allowed at every level, within the contact rules, because they change no data.
- An agent moves up a level only when its part owner approves, with the samples as evidence. The part owner can move it down at any time.
- There's no level above 2. An agent that acts always tells someone.

## The definition format

A definition is a folder in git, and each release is a tagged version of it:

```text
agents/owner-assistant/
  agent.yaml     the definition
  AGENTS.md      instructions, read on every run
  skills/        Agent Skills, one folder each
  tests/         regression and scenario tests
```

This is `agent.yaml` for the lean scenario's owner assistant. Field names will settle as the code is written.

```yaml
id: owner-assistant
release: 0.3.0
works_for: Attribute owners and their delegates
does: >-
  Prepares each case, such as duplicate comparisons, bank-detail call-backs
  and the evidence. Chases anything overdue, and prepares the monthly sample
  of automatic approvals.
owner: "[TBC]"
deputy: "[TBC]"
scope: one-part                  # an instance, identity and memory per part
model: "[TBC: from the approved AI tools list]"
autonomy:
  start: 1                       # 0 or 1; level 2 comes only from settings
  max: 1                         # it has no tools that change master data
tools:
  unified-app: [get_case, list_cases, attach_case_pack]
  data-platform: [find_duplicates, get_record]
triggers:
  - event: case.routed
  - event: decision.recorded
  - schedule: first working day of the month   # the approval sample
  - sweep: weekdays at 08:00
obligations:
  - type: overdue-case
    source: unified-app.cases
    due: turnaround              # from the domain profile; urgent ones in hours
reminders: [follow-up-on-case]   # what people can ask it to remind them of
channels: [teams, email]         # [TBC]; contact rules come from the scenario
memory:
  writes: review
  expires_after: 90d             # [TBC]
budget:
  per_run: "[TBC]"
  per_day: "[TBC]"
```

The register adds what changes without a release: each instance, its identity and its status.
