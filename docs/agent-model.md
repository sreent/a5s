# Agent Model

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md)

## Definitions, instances and runs

| Object | What it is | Lasts | In the lean scenario |
| --- | --- | --- | --- |
| Definition | A kind of agent: its job, instructions, skills, tools, model, triggers and limits, released as tested versions | Until it's retired | The owner assistant, release 0.3 |
| Instance | A definition serving one scope, with its own identity, autonomy, obligations, memory and status | As long as the scope needs it | The owner assistant for supplier general data |
| Run | One piece of work by an instance, from a trigger until it's done or waiting for a person | Minutes of work, then parked while it waits | Preparing the case for one routed request |

Four terms connect a5s to a scenario:

| Term | Means | In the lean scenario |
| --- | --- | --- |
| Scope | The part of the business an instance serves | A part of a domain |
| Scope owner | The person who approves an instance for their scope, and how far it may act there | The part's attribute owner |
| Settings | Where the scope owner keeps what a5s reads live: autonomy, thresholds, sensitive fields and classes of data | The domain profile, in the unified master data app |
| Decision surface | Where people decide proposals | The unified master data app |

## Roles

| Role | Does |
| --- | --- |
| Agent owner, with a deputy | Builds and runs a definition and its instances. Reviews level-2 actions and can reverse them, and approves memory entries [TBC]. |
| Scope owner, and their delegates | The scope owner approves an instance for their scope and how far it may act there. They or their delegates decide its proposals. |
| Release approver | Approves each release after its tests and design review. Never someone who built it. The scenario says who. |
| Assurance | Reads the ledger and the samples, and reviews what the scenario asks it to |

## Lifecycle

| Status | Means | Next |
| --- | --- | --- |
| Draft | Being built or changed | Approved, once its tests pass and the release approver approves it |
| Approved | Ready, but not running | Active, once a scope owner approves it for their scope |
| Active | Running in its scope | Suspended or retired |
| Suspended | No trigger wakes it, and every tool call is denied, including in a run already going | Active again, when its agent owner or scope owner resumes it, or retired |
| Retired | Its identity is disabled, its grants removed, its evidence archived and its memory deleted under the retention rules | Nothing |

- Any change to a release is a new release, back to draft: its instructions, skills, tools or their definitions, model, triggers, memory rules or limits.
- An instance runs only while its definition has an owner or a deputy. If both leave, it's suspended until a new owner is named.
- The agent owner, the deputy and the scope owner can suspend an instance, and the agent owner and deputy can suspend every instance of a definition at once. The scenario can add others.

## Autonomy

| Level | The agent may | People |
| --- | --- | --- |
| 0. Observe | Read, measure and report | Read what it reports |
| 1. Propose | Prepare an action for a person to decide | The scope owner or a delegate decides each one |
| 2. Act and notify | Take actions of a type the scope owner has approved, within the scenario's limits | The agent owner reviews them and can reverse any of them |

- Autonomy is set for each instance and type of action, in the scope's settings. Where it isn't set, the definition's starting level applies.
- Reminding, chasing and routing are allowed at every level, within the contact rules, because they change no data.
- An agent moves up a level only when its scope owner approves, on evidence from sampled work. Anyone who can move it up can move it down.
- There's no level above 2. An agent that acts always tells someone.

## The definition format

A definition is a folder in git:

```text
agents/owner-assistant/
  agent.yaml     what the register holds
  AGENTS.md      instructions, read on every run
  skills/        Agent Skills, one folder each
  tests/         regression and scenario tests
```

This is `agent.yaml` for the lean scenario's owner assistant. Field names will settle as the code is written.

```yaml
id: owner-assistant
release: 0.1.0
works_for: Attribute owners and their delegates
does: >-
  Prepares each case, such as duplicate comparisons, bank-detail call-backs
  and the evidence. Chases anything overdue, and prepares the monthly sample
  of automatic approvals.
owner: "[TBC]"
deputy: "[TBC]"
scope: domain-part               # one instance, identity and memory per part
model: "[TBC: from the approved AI tools list]"
autonomy:
  start: 1
  max: 1                         # it changes no master data
tools:
  unified-app: [get_case, list_cases, attach_case_pack]
  data-platform: [find_duplicates, get_record]
triggers:
  - event: case.routed
  - event: decision.recorded
  - schedule: first working day of the month   # the approval sample
  - sweep: weekdays at 08:00
obligations:
  - source: unified-app.cases
    due: turnaround              # from the domain profile
    escalate: [delegates, attribute-owner, gpdo]
channels:
  via: [teams, email]            # [TBC]
  digest: daily
  max_per_person_per_day: 2      # [TBC]
memory:
  writes: review
  expires_after: 90d             # [TBC]
budget:
  per_run: "[TBC]"
  per_day: "[TBC]"
```

The register adds what changes without a release: each instance, its identity, its status and its approvals.
