# a5s

**An agent OS on LangChain Deep Agents, for agents that live and work alongside people, under the rules people set.**

| Principle | What it means |
| --- | --- |
| **Agents live and remember** | An agent keeps its identity, its conversations, what it knows about the people it works with, and what it owes them, for as long as it's in service. Compute comes and goes, and the context stays. |
| **Policy decides, not the model** | Every tool and model call is checked outside the model, and is allowed, held for a person or denied. Anything not allowed is denied, and if the check can't run, nothing runs. What an agent must never do, it never has the rights to do. |
| **People decide, agents propose** | How far an agent may act is a setting that the owner of each part of the business approves, for each type of action. |
| **Every action leaves evidence** | An append-only ledger records what each agent did, for whom, under which policy and with what result. |
| **Change is a release** | An agent changes only through a tested, approved release, never by itself. |
| **Own the rules, rent the plumbing** | Identity, sandboxes, gateways and telemetry come from the host cloud, through adapters and open standards. a5s keeps the rules, so it can move between clouds. |

## The problem

Three kinds of product each solve part of the problem:

- **Agent frameworks,** such as LangChain Deep Agents, run a task well and then stop. Who the agent is, what it owes people, what it remembers and what it may do are left to whoever builds on them.
- **Cloud agent platforms** from Microsoft, AWS and Google now give each agent an identity and a registry entry, and AWS and Google can check every tool call at a gateway. None of them knows the business's rules: who may approve what, how far each agent may act in each part of the business, and what evidence moves it up a level.
- **Personal agents,** such as Nous Research's Hermes Agent, live: they stay on, remember, work on schedules and talk to people over chat. But nothing inside them is a security boundary, and they can rewrite their own skills and set their own schedules.

a5s takes the agent loop from Deep Agents, the plumbing from the cloud and the persistence from Hermes, and adds the rules none of them has. The [research](docs/research/platform-lessons.md) has the evidence, as of October 2026.

## The target setup

| Layer | What | Does |
| --- | --- | --- |
| Define | Agent definitions, kept in git | Say what each agent is for, whom it works for, and its instructions, skills, tools, model, triggers and limits. Each version is a tested release. |
| Govern | The a5s kernel | Registers agents and their owners, gives each one an identity, checks every tool and model call against policy and the approved autonomy, and gets proposals to the people who decide them. |
| Live | Scheduler, context and channels | Wakes an agent when something happens or falls due, picks up the conversation or case where it left off, and lets it talk to people within contact rules. |
| Prove | Ledger and assurance | Records every action, measures how people review proposals, and builds the evidence for moving an agent up or down a level. |
| Host | Deep Agents on LangGraph, in the cloud | Runs each piece of work. Identity, sandboxes, gateways and telemetry come from the host through adapters. |

## The baseline scenario

The [lean framework](https://github.com/sreent/lean-framework) for master data governance is the first scenario, and the baseline a5s is measured against. It has five agents, three autonomy levels, payment data and trade secrets. [The scenario](scenarios/lean-framework.md) maps its rules onto a5s and lists the tests a5s must pass.

## Documents

| Document | What it holds |
| --- | --- |
| [Architecture](docs/architecture.md) | The kernel's components, policy, proposals, how an agent lives, what comes from Deep Agents and what a5s adds, and hosting |
| [Agent model](docs/agent-model.md) | Definitions, releases, instances and runs, the terms that connect a5s to a scenario, roles, lifecycle, autonomy, and the definition format |
| [Lean framework scenario](scenarios/lean-framework.md) | The baseline: the five agents in a5s, how the framework's rules map, and the tests |
| [Research](docs/research/platform-lessons.md) | What Deep Agents, Microsoft, AWS, Google and Hermes Agent offer, with the [notes](docs/research/notes/) behind it |

## Open decisions

`[TBC]` marks a default to confirm or a gap to fill. The [scenario](scenarios/lean-framework.md) marks its own. For a5s itself:

- **Host:** where runs execute, in a5s's own workers or in AWS AgentCore, Microsoft Foundry or Google Agent Runtime. It decides the identity and gateway adapters ([hosting](docs/architecture.md#hosting)).
- **Policy language:** Cedar, unless there's a reason for another. AgentCore Policy uses it too.
- **Channels:** Teams, email or both.
- **Retention:** how long conversations, profiles and the ledger are kept, and where the ledger is stored so that the team that runs a5s can't change it.
- **Numbers:** contact limits, budgets, how long a proposal waits before it's chased and escalated, and the window for counting actions.
