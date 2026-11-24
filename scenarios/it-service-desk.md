# IT Service Desk Scenario

**Status:** Implemented for local development and tests: synthetic tickets, accounts and a Markdown knowledge vault, a dedicated desk assistant, ticket, account and article permissions, replies on tickets, each held for its service area's decider, self-service through the identity provider, as the desk's pack allows it, and each person's devices through device management, with a lost one locked. The resolver assistant and the joiner coordinator, which the desk planned and never wrote by hand, are built in the studio, in [phase 5](../docs/phase-5.md).

An internal IT service desk helps people with accounts, devices, access and the organisation's tools. People raise tickets, resolvers work them in the IT service management tool (ITSM), and new joiners need accounts and equipment ready before their first day. It tests a5s where scenarios differ most: much of its work is self-service, which a person asks for and the identity provider verifies, and some of the people it serves haven't joined yet.

## The contract

| Interface | In the service desk |
| --- | --- |
| Directory | The identity provider, including pre-start accounts for new joiners, which the HR system creates; and the team that runs a5s, who own its agent, with the people from outside it who approve its releases. The ITSM says who may see each ticket. |
| Settings | a5s's own settings store. The parts are service areas, such as accounts and access, devices, and collaboration tools, and the audience includes new joiners, from their pre-start accounts. |
| Tools | The ITSM's tickets, what requesters wrote on them and replies, through the ITSM's MCP server, the identity provider's self-service, through its own, and device management, through its own, which the desk's [`mcp.yaml`](service-desk/mcp.yaml) declares; and the knowledge base |
| Records | Tickets with their response and resolution targets, and joiners' start dates from the HR system |
| Governed process | The ITSM's request fulfilment and access approvals, which already keep requester and approver apart, and the identity provider's own self-service flows |
| Decision surface | The ITSM's approvals, and a5s's decision page for the changes an agent asks for |
| Policy pack | [The service desk pack](#the-service-desk-pack) |
| Tests | [Below](#tests), against a made-up ITSM, identity provider and device management, each behind its MCP server, and live on a real model; and on a5s's containers, through Matrix, with its release approved by its own people |

| a5s term or role | In the service desk |
| --- | --- |
| Part owner | The service owner for an area |
| Type of action | An item in the request catalogue, such as a password reset or a software install |
| Release approver | A person assigned the role from outside the team that runs a5s and its reporting line [TBC: who] |
| Assurance | People assigned the role, independent of IT [TBC: who] |

## The service desk pack

The service desk adds these to a5s's base pack. a5s's levels hold the first; its [`pack.cedar`](service-desk/pack.cedar) holds the second, for self-service and for locking a lost device, and the third, as forbids; and the desk's directory and tools hold the rest:

- **Self-service can run on its own,** for catalogue items the service owner approves, when the person it's for asked for it and the identity provider verifies them in its own flow. The agent starts the flow and never sees the secret.
- **Only for the person asking.** A reset for anyone else never runs on its own: the desk assistant's instructions send whoever asks to the ITSM's approvals, and one it starts all the same waits for the decider of access.
- **Authenticators go to a person.** Registering a new authenticator, or removing one, always goes to a resolver, because that's how account takeovers start.
- **New joiners see only their own joiner record** until their first day.
- **No admin rights.** No agent grants privileged access, whatever it may do.

## The agents

| Agent | Works for | What it may do | Does |
| --- | --- | --- | --- |
| Desk assistant | Everyone in the organisation, and new joiners | Asks first, and acts on its own for verified self-service | Answers from the knowledge base, starts self-service flows, and drafts tickets for people to submit, with what it already tried. Built again in the studio, from nothing, as desk-helper ([its guide](../docs/guides/service-desk/guide.md)) |
| Resolver assistant | Resolvers, in one service area each | Asks first | Briefs each ticket from records, finds similar tickets and articles, drafts replies, posts one once its service area's decider approves it, and chases tickets nearing their targets. Built in the studio, from nothing ([its guide](../docs/guides/resolver/guide.md)) |
| Joiner coordinator | New joiners, and whoever owes them something | Asks first, in access and hardware | Tracks each joiner's accounts, equipment and access against the start date, chases whoever owes something, and answers the joiner's questions before day one. Described in plain words in the studio, drafted with the least it needs, and refined by hand ([its guide](../docs/guides/joiner/guide.md)) |

## What it shows about a5s

- **Limits on acting alone belong to scenarios.** Some scenarios never let an agent act on its own on anything that came from a person's words, because nobody may approve their own change. Here, a person asking for their own password reset is the normal case. So a5s's base pack doesn't rule on it. It records who a run acts for and keeps them from deciding what they're named on, and each pack sets the rest.
- **The audience is a setting.** Most scenarios talk only to people inside the organisation, while the joiner coordinator must reach people who haven't started.
- **The default settings store matters.** The service desk keeps no settings of its own for agents, so it uses a5s's.
- **Each scenario answers who may see a record.** a5s asks the directory interface, and here the ITSM answers for its tickets.
- **Written against the contract, it runs.** Round 5's tests build the desk against the contract alone ([`tests/test_r5_c_service_desk.py`](../tests/test_r5_c_service_desk.py)). They found what a5s had to change, now changed: the desk assistant serves the sales team as a team, so joiners need no new settings; its tools answer with objects, as MCP tools do, and a5s filters them at any depth; its ticket keys have a pattern of their own; it reads one ticket for a brief, not every ticket; and its night shift's hours cross midnight.
- **Where it strains:** a major incident brings thousands of people to the desk assistant at once, and per-person budgets don't help. The channel service would need a known-incident answer it can give without a run, which no phase has built yet [TBC].

## Tests

The tests of what the desk first did, reading only, are in [`tests/test_service_desk.py`](../tests/test_service_desk.py), beside the original contract-only checks in `test_r5_c_service_desk.py`. They cover ticket answers, Markdown knowledge with attribution, ticket and article permissions, requester content as data rather than instructions, saved drafts, and service to a new joiner through their team. A test marked `live` exercises ticket and knowledge answers on a real model. And [`deploy/smoke-scenario.sh service-desk`](../deploy/smoke-scenario.sh) runs it on a5s's containers: the desk's own people approve its release, and a requester asks the desk assistant about their ticket in Matrix.

Its ITSM's tools come through the ITSM's MCP server, as an organisation's would ([phase 5](../docs/phase-5.md)): searching tickets, reading one, what requesters wrote on one, and posting a reply on one, declared in [`mcp.yaml`](service-desk/mcp.yaml) in a5s's own words, and nothing else of the server's. In this made-up desk the server is [`deploy/systems/itsm.py`](../deploy/systems/itsm.py), on the desk's synthetic data, beside the gateway on its own machine: the tests start it once, and the desk's containers run it in the gateway's network ([`deploy/compose.desk.yaml`](../deploy/compose.desk.yaml)). What stays the desk's own code is its directory, who may see each ticket, the obligations its tickets make, a draft reply for a person to send, and its knowledge base.

Self-service comes through the identity provider's MCP server, in this desk [`deploy/systems/idp.py`](../deploy/systems/idp.py): each person's account, ACC- and their id, which they and access's resolvers may see; the provider's own password reset, `reset-password`, which the account's holder finishes there, verifying themselves, so the agent never sees a secret; and removing an account's authenticators, `reset-authenticators`. Where the agent asks first, both wait for access's decider, as every change does. A reset runs on its own only where the service owner's settings let the agent act on its own for it, graded samples have raised a5s's cap for it, the run hasn't read what a requester wrote, and it's the asker's own account, in answer to their own message: anyone else's, even for a resolver, waits for access's decider, as the pack says, and so does a reset in a run nobody asked in, such as a chase of what they owe. No settings let an authenticator change run alone: it always waits for one ([`tests/test_desk_self_service.py`](../tests/test_desk_self_service.py), [`tests/test_r12_desk_levels.py`](../tests/test_r12_desk_levels.py)).

Devices come through device management's MCP server, in this desk [`deploy/systems/mdm.py`](../deploy/systems/mdm.py): each person's devices, by their asset tag, LT- for a laptop and PH- for a phone, in hardware, which their holder and hardware's resolvers may see, with whether each meets the organisation's rules for devices, and why not, in device management's own words; and locking one remotely, `lock-device`, such as a lost phone, which its holder undoes by signing in to it again, and which never wipes it. Where the agent asks first, a lock waits for hardware's decider, and a5s makes it once they approve it, once for a5s's key, which device management honours; what it does there is what a5s shows of the device, and what its decider sees, as the scenario's code reads the system as it stands. A lock runs on its own only where the service owner's settings let the agent act on its own for it in hardware, graded samples have raised a5s's cap for it, and it's the asker's own device, in answer to their own message: anyone else's, even for a resolver, waits for hardware's decider, as the pack says ([`tests/test_desk_devices.py`](../tests/test_desk_devices.py)).

A reply on a ticket is a change of type `reply`: where the agent asks first, a5s holds it for the decider of the ticket's service area, its service owner or whoever they name beside them, never anyone it's for, and posts it once they approve it, once for a5s's key, which the made-up ITSM honours, keeping what's written to it in its memory, over the desk's data, until it stops ([`tests/test_desk_replies.py`](../tests/test_desk_replies.py)).

A joiner's starter requests are tickets like any other, which the HR system raises for their first day, with the joiner as their requester: Jo Joiner's laptop and accounts, in hardware and access, which Jo may see, and so may those service areas' resolvers.
