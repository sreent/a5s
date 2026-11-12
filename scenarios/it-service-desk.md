# IT Service Desk Scenario

**Status:** A read-only MVP is implemented for local development and tests: synthetic tickets, a Markdown knowledge vault, a dedicated desk assistant, and ticket/article permissions. Self-service actions and the joiner coordinator remain future work.

An internal IT service desk helps people with accounts, devices, access and the organisation's tools. People raise tickets, resolvers work them in the IT service management tool (ITSM), and new joiners need accounts and equipment ready before their first day. It tests a5s where scenarios differ most: much of its work is self-service, which a person asks for and the identity provider verifies, and some of the people it serves haven't joined yet.

## The contract

| Interface | In the service desk |
| --- | --- |
| Directory | The identity provider, including pre-start accounts for new joiners, which the HR system creates; and the team that runs a5s, who own its agent, with the people from outside it who approve its releases. The ITSM says who may see each ticket. |
| Settings | a5s's own settings store. The parts are service areas, such as accounts and access, devices, and collaboration tools, and the audience includes new joiners, from their pre-start accounts. |
| Tools | The ITSM's tickets, comments and request catalogue, the knowledge base, the identity provider's self-service flows, and device management, read only |
| Records | Tickets with their response and resolution targets, and joiners' start dates from the HR system |
| Governed process | The ITSM's request fulfilment and access approvals, which already keep requester and approver apart, and the identity provider's own self-service flows |
| Decision surface | The ITSM's approvals |
| Policy pack | [The service desk pack](#the-service-desk-pack) |
| Tests | [On paper](#tests-on-paper), against a fake ITSM, knowledge base and identity provider |

| a5s term or role | In the service desk |
| --- | --- |
| Part owner | The service owner for an area |
| Type of action | An item in the request catalogue, such as a password reset or a software install |
| Release approver | A person assigned the role from outside the team that runs a5s and its reporting line [TBC: who] |
| Assurance | People assigned the role, independent of IT [TBC: who] |

## The service desk pack

The service desk adds these to a5s's base pack:

- **Self-service can run at level 2,** for catalogue items the service owner approves, when the person it's for asked for it and the identity provider verifies them in its own flow. The agent starts the flow and never sees the secret.
- **Only for the person asking.** A request for anyone else goes to the ITSM's approvals.
- **Authenticators go to a person.** Registering a new authenticator, or removing one, always goes to a resolver, because that's how account takeovers start.
- **New joiners see only their own joiner record** until their first day.
- **No admin rights.** No agent grants privileged access, at any level.

## The agents

| Agent | Works for | Starts at | Does |
| --- | --- | --- | --- |
| Desk assistant | Everyone in the organisation, and new joiners | Level 1, and level 2 for verified self-service | Answers from the knowledge base, starts self-service flows, and drafts tickets for people to submit, with what it already tried |
| Resolver assistant | Resolvers, in one service area each | Level 1 | Briefs each ticket from records, finds similar tickets and articles, drafts replies, and chases tickets nearing their targets |
| Joiner coordinator | Hiring managers and new joiners | Level 1, with no parts | Tracks each joiner's accounts, equipment and access against the start date, chases whoever owes something, and answers the joiner's questions before day one |

## What it shows about a5s

- **Level-2 limits belong to scenarios.** Some scenarios rule out level 2 for anything that came from a person's words, because nobody may approve their own change. Here, a person asking for their own password reset is the normal case. So a5s's base pack doesn't rule on it. It records who a run acts for and keeps them from deciding what they're named on, and each pack sets the rest.
- **The audience is a setting.** Most scenarios talk only to people inside the organisation, while the joiner coordinator must reach people who haven't started.
- **The default settings store matters.** The service desk keeps no settings of its own for agents, so it uses a5s's.
- **Each scenario answers who may see a record.** a5s asks the directory interface, and here the ITSM answers for its tickets.
- **Written against the contract, it runs.** Round 5's tests build the desk against the contract alone ([`tests/test_r5_c_service_desk.py`](../tests/test_r5_c_service_desk.py)). They found what a5s had to change, now changed: the desk assistant serves the sales team as a team, so joiners need no new settings; its tools answer with objects, as MCP tools do, and a5s filters them at any depth; its ticket keys have a pattern of their own; it reads one ticket for a brief, not every ticket; and its night shift's hours cross midnight.
- **Where it strains:** a major incident brings thousands of people to the desk assistant at once, and per-person budgets don't help. The channel service would need a known-incident answer it can give without a run [TBC: phase 2].

## Tests

The read-only MVP's tests are in [`tests/test_service_desk.py`](../tests/test_service_desk.py), beside the original contract-only checks in `test_r5_c_service_desk.py`. They cover ticket answers, Markdown knowledge with attribution, ticket and article permissions, requester content as data rather than instructions, saved drafts, and service to a new joiner through their team. A test marked `live` exercises ticket and knowledge answers with the real provider. And [`deploy/smoke-scenario.sh service-desk`](../deploy/smoke-scenario.sh) runs it on a5s's containers: the desk's own people approve its release, and a requester asks the desk assistant about their ticket in Matrix.

Self-service identity flows, authenticator changes, ticket writes, and the joiner coordinator remain outside this read-only release.
