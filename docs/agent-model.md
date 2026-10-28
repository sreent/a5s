# Agent Model

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md)

## Definitions, releases, instances, threads and runs

| Object | What it is | Lasts | In the lean scenario |
| --- | --- | --- | --- |
| Definition | A kind of agent and its job | Until it's retired | The owner assistant |
| Release | A tested, approved version of a definition. It fixes the agent's instructions, skills, tools and their definitions, model, triggers, obligation and reminder types, the preferences people can set, context rules and limits. | Until it's withdrawn | The owner assistant, release 0.3.0 |
| Instance | A definition at work in a scope, with its own identity, obligations, context and status | As long as the scope needs it | The owner assistant for supplier general data |
| Thread | An ongoing conversation with one person or group, or the history of one case | As long as the person, group or case needs it | The owner assistant's conversation with one delegate |
| Run | One piece of work by an instance, on a thread, from a trigger until it's done | Minutes | Preparing the case pack for one routed request |

## Terms that connect a5s to a scenario

| Term | Means | In the lean scenario |
| --- | --- | --- |
| Part | A piece of the business with one owner. Every field an agent touches belongs to one part. | A part of a domain, by subdomain, business unit or group of fields. One record's fields can sit in different parts. |
| Part owner | Approves agents to act in the part, and how far. Decides their proposals there, or names delegates for the decisions the scenario lets delegates take. | The part's attribute owner |
| Scope | The parts an instance may act in: one part, several, or none | One part, several domains' parts, or none, for agents that don't touch master data |
| Grant | The tools, data and models an instance may use: what its release lists, as far as its parts' owners approve | Trade-secret fields only as their attribute owner grants them |
| Type of action | A kind of action that autonomy is set for, defined by the fields it changes and the check it serves | A change type, as the domain profile names it |
| Settings | Where part owners keep what a5s reads live: who owns what, which agents they approve and how far, thresholds, sensitive fields and classes of data. Each version carries its owner's authenticated sign-off. | The domain profiles and ownership settings, in the unified master data app |
| Governed process | A system's own way of making and approving changes, which agents hand requests to instead of changing data themselves | Requests in the unified app |
| Decision surface | Where people take decisions on agents' proposals | The unified app |
| Acts for | Everyone whose words a run serves: whoever sent the message, set the reminder, or wrote the reply or note a request came from, and everyone in a group conversation. A run started only by an event or a schedule acts for nobody. | A requester asking the request assistant for help, or a delegate replying to the owner assistant |

## Roles

| Role | Does |
| --- | --- |
| Platform owner | Accountable for a5s and the agents it runs. Names each agent owner and deputy, and can suspend any instance and withdraw any release. |
| Agent owner, with a deputy | Builds and runs a definition and its instances. Reviews level-2 actions and can reverse them, reviews runs that were cut off, and samples its notebooks. Can suspend the agent's instances, lower their cap and withdraw its releases. |
| Part owner, and their delegates | The part owner approves an instance for the part, sets how far it may act there, and moves it up or down. They or their delegates decide its proposals, as the scenario allows. Decisions about the agent itself are never a delegate's, and withdrawing an agent's approval is reported to whoever the scenario names. |
| Instance approver | Approves an instance to run. For each part in its scope, the part owner. For an instance with no parts, whoever the scenario names, who also sets its level and can withdraw its approval. |
| Release approver | Approves each release, of an agent or of a5s's own enforcement, after its tests and design review, and can withdraw it. Never from the team that built it, or its manager's reporting line. The scenario names who. |
| Sample graders | Grade samples of an agent's work. Never from the team that built it. The scenario names who. |
| Assurance | Reads the ledger and the samples, holds the ledger's daily anchor, reviews emergency access, and reviews what the scenario asks it to |

## Lifecycle

| A release is | Means |
| --- | --- |
| Draft | Being built or changed |
| Approved | Passed its tests and design review, and approved. Instances can run it until it's withdrawn. |
| Withdrawn | No instance may run it. The agent owner, the release approver or the platform owner can withdraw a release, and a security advisory withdraws every release that pins the affected version. Instances still on it are suspended until they move to another. |

| An instance is | Means | Who moves it on |
| --- | --- | --- |
| Proposed | Created by its agent owner, waiting for approval | Its approvers: each part's owner, in the settings, or the scenario's approver for an instance with no parts |
| Active | Working, in the parts whose owners have approved it, or, with no parts, while the scenario's approval stands | The agent owner, the deputy or the platform owner can suspend it. The agent owner or the platform owner can retire it. |
| Suspended | No trigger wakes it, every call is denied, even in a run already going, its pending proposals are withdrawn, and its open requests are withdrawn or flagged | Whoever suspended it can resume it. Anyone else needs the agreement the scenario requires, and it counts as emergency access. Never while the agent has neither an owner nor a deputy. |
| Retired | Its identity is disabled, its grants removed, its evidence archived and its context deleted under the retention rules | Nobody. It's gone. |

- The agent owner, the deputy and the platform owner can also suspend every instance of a definition at once.
- A part owner can stop an instance acting in their part at any time, by withdrawing its approval in the settings.
- If the agent owner and the deputy both leave, the instance is suspended until the platform owner names a new owner. Replacing an agent owner who hasn't left needs the agreement the scenario requires.
- When a part is split or merged, its instances' context and obligations follow the records into the new parts.
- An instance moves to another approved release, newer or older, when its agent owner moves it, and its thread state moves with tested migrations. A release that changes only dependencies keeps the instance's cap, if its tests pass and the last graded samples still pass when re-run. Any other release starts at level 1 until samples of it pass and the part owner approves level 2 again. It can earn its samples in shadow runs before the move.

## Autonomy

| Level | The agent may | People |
| --- | --- | --- |
| 0. Observe | Read, measure and report | Read what it reports |
| 1. Propose | Prepare drafts, hand requests to a governed process, and hold proposals for a person ([how](architecture.md#proposals-and-approvals)) | A person decides each one: whoever uses a draft, whoever the process routes a request to, or, for a held proposal, the part owner or a delegate |
| 2. Act and notify | Take actions of a type the part owner has approved, within the scenario's limits, through the governed process where there is one | The agent owner reviews them and can reverse any of them |

- The level is set for each instance, part and type of action, in the settings. Where it isn't set, the definition's starting level applies. That can only be 0 or 1, so level 2 always comes from a part owner. A release's maximum is the highest level it allows, whatever the settings say.
- Each level-2 setting records who approved it and the version of the part. If either changes, because the owner leaves, the part is split or a field moves to another part, the level drops to 1 until the new owner sets it, and the old owner is told.
- a5s also keeps a cap for each instance and type of action, and the instance works at the lower of the cap and the setting. The cap follows the release rules above, rises only when samples pass [TBC: how many], and falls when samples fail, a drift test fails, or the agent owner lowers it. The part owner is told of every change.
- An action that touches fields in several parts works at the lowest of their levels.
- Reminding, chasing and routing are allowed at every level, within the contact rules, because they change no data.
- An agent moves up a level only when its part owner approves, with the samples as evidence. The part owner can move it down at any time.
- There's no level above 2. An agent that acts always tells someone.

## The definition format

A definition is a folder in git, and each release is a tagged version of it:

```text
agents/owner-assistant/
  agent.yaml     the definition
  AGENTS.md      instructions, loaded read-only on every run
  skills/        Agent Skills, one folder each, pinned by hash
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
scope: one-part                  # an instance, identity and context per part
model: "[TBC: from the approved AI tools list]"
autonomy:
  start: 1                       # 0 or 1; level 2 comes only from settings
  max: 1                         # it has no tools that change master data
tools:
  unified-app: [get_case, list_cases, attach_case_pack]
  data-platform: [find_duplicates, get_record]
triggers:
  - message: from the people it works for
  - event: case.routed
  - event: decision.recorded
  - schedule: first working day of the month   # the approval sample
  - sweep: weekdays at 08:00
obligations:
  - type: overdue-case
    source: unified-app.cases
    due: turnaround              # from the domain profile; urgent ones in hours
reminders: [follow-up-on-case]   # what people can ask it to remind them of
preferences: [case-pack-layout]  # what people can set in their profile
channels: [teams, email]         # [TBC]; contact rules come from the scenario
context:
  conversations: one per person  # in topics, kept for [TBC], summarised as they grow
  profiles: yes                  # what it knows about each person, visible to them
  notebook_expires_after: 90d    # [TBC]
budget:
  per_run: "[TBC]"
  per_person_per_day: "[TBC]"
```

The register adds what changes without a release: each instance, its identity and its status.
