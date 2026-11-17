# Architecture

**Status:** Draft v0.3. Phase 1's first step is built ([progress](phase-1.md#progress)) · **Under:** [a5s](../README.md)

a5s runs agents the way an operating system runs programs. It installs them, gives each one an identity and only the rights it needs, wakes it when there's work, checks every call it makes, and keeps a record of what happened. Agents run on LangChain Deep Agents. Each scenario plugs in through a [contract](#the-scenario-contract) and brings its own people, systems and rules.

```mermaid
flowchart LR
  people["People"] <--> channels
  subgraph a5s["a5s"]
    subgraph services["Services"]
      scheduler["Scheduler"]
      context["Context"]
      channels["Channels"]
      approvals["Approvals"]
    end
    workers["Workers running Deep Agents"]
    subgraph core["Trusted core"]
      policy["Policy"]
      gateways["Gateways"]
      ledger["Ledger"]
    end
  end
  scheduler --> workers
  context --> workers
  workers -- "every tool, model and message call" --> gateways
  gateways --> policy
  gateways --> ledger
  gateways --> systems["Scenario systems"]
  gateways --> models["Models"]
  gateways --> channels
```

## The trusted core and the rest

| Part | What it is | A change needs |
| --- | --- | --- |
| Trusted core | Policy, written in Cedar; the gateways for tools, models and outgoing messages; the endpoints where people's messages arrive, which check who sent each one; the credential broker; the ledger writer; masking. Also the data they keep, which changes only through their own interfaces: grants, caps, instance status, run envelopes and held calls. | Approval from outside the team that runs a5s, a protected branch and an attested build ([independence](#independence)) |
| Services | The scheduler, context, channels, approvals and assurance services, and the register's interface. They change core data only through the core's own interfaces, which apply the rules for loosening. | The team's own review and tests |
| Workers | Run each piece of work as a Deep Agents run, with no credentials and no network except to the gateways, in pools: each agent with a pool of its own runs there alone, and every other agent in the shared pool, and a question one agent asks another is answered in the asker's, as part of its run ([worker pools](../deploy/helm/README.md#worker-pools)) | As services |

A fault or a compromise in a service or a worker can make an agent slow, wrong or silent. It can't make one do what policy denies, because every call goes through the core.

## The scenario contract

A scenario plugs into a5s by providing these, or by taking a5s's defaults:

| Interface | Gives a5s | a5s's default |
| --- | --- | --- |
| Directory | People, the roles they hold, such as who owns each part, their teams, reporting lines and working hours, which may cross midnight, and what each may see, for any record | The organisation's identity provider, such as Entra ID, Google Cloud Identity, Okta or Keycloak, or its own directory, such as Active Directory, with roles assigned as groups |
| Settings | The parts each instance works in, whom it serves, by name or as a team or a role's holders, which the directory resolves at each run, how far each agent may act in each part and type of action, limits, sensitive fields, classes of data, the escalation chain, who agents may talk to, and the scenario's switches. A version counts only once the owner of each part its instances work in has signed it, with their own key or through the identity provider, and an instance approver for any instance in no part, or for new classes of data. Its serial only rises, so an older version can't be replayed, and it comes into force only on the version it was written against, which its approvers saw what it changes from: one written against a version no longer in force is superseded, and asked for again. | a5s's settings store, with signed versions from files in git, or approved on cards in the chat, which people can ask for in the studio's settings |
| Tools | The systems agents use, as MCP servers, with each tool's risk attributes | None |
| Records | Where obligations come from, such as cases past their due time, each person's records as they stand, for reports of what changed, one record by its key, for a case's brief, the part each record is in, and the events that wake agents | None |
| Governed process | Where agents' requests to change data go, and who decides them | Held proposals in a5s itself, from phase 2 |
| Decision surface | Where people decide | Cards in the chat, which open the core's own page, apart from the conversation. Each decision there is signed through the identity provider for that one decision. |
| Policy pack | The scenario's own restrictions, which can only add to a5s's base pack | None |
| Tests | The scenario's tests, run against its systems or a fake of them | None |

Each scenario starts with a fake of its contract: fake systems, records and settings, which are also its test bench. a5s has a sample scenario of its own, a fake of every interface with synthetic data, for phase 1 and for building locally. An [IT service desk](../scenarios/it-service-desk.md), written against the contract alone in round 5's tests, checks that the contract is general: its tools answer with objects, as MCP tools do, its keys have their own pattern, and its night shift works across midnight.

### Graphify code knowledge

A coding scenario can expose a local [Graphify](https://docs.graphify.com/concepts/outputs) knowledge graph with the read-only `query_code` tool in [`a5s.graphify`](../src/a5s/graphify.py). Build the graph with `graphify extract /path/to/repository --code-only`, then add `Graphify(folder / "graphify-out" / "graph.json").tools()` to the scenario's tools and `query_code` to the agent's grants. `a5s pin` records its schema in the release like any other tool's.

Local Graphify queries call no model and run without a shell. The scenario must give the graph only to instances whose people may all see the source repository, or wrap it with its own finer permissions: the graph carries source-derived context and source references. Building a graph semantically from documents, rather than code-only, may call a model and needs the deployment's data-class approval for that material.

### Markdown and Obsidian knowledge

A scenario can expose a folder of Markdown notes, including an Obsidian vault, with `MarkdownKnowledge(folder)` from [`a5s.knowledge`](../src/a5s/knowledge.py). Its read-only `search_knowledge` and `read_knowledge` tools use keyword search and fresh reads from disk, so a deleted note never lingers in an index. Hidden folders such as `.obsidian` are not read, and document reads are bounded. The text is source material, never instructions for the agent.

YAML front matter names the document's audience and, optionally, when its review falls due:

```yaml
---
title: Refund procedure
people: [ana]       # or parts: [billing], with the scenario's part-permission callback
review_by: 2027-01-31
---
```

An unmarked document is denied. For a group, every person the run acts for must be named or allowed by the scenario's `sees_part(person, part)` callback. A document whose `review_by` has passed is marked `stale`, not silently served as current. Add both tools to the agent's grants and pin their schemas with `a5s pin`. The adapter doesn't replace the agent's notebook, which holds what it learned from records rather than these curated documents.

### Document libraries in other systems

Beside its handbook, a scenario may name libraries of documents kept elsewhere, in its folder's `libraries.yaml`: a SharePoint site, a Confluence space or a docs repository ([connectors](connectors.md#document-libraries)). Each gives `search_<library>` and `read_<library>`, which read a document only as far as its own permissions allow, for everyone a run acts for: SharePoint and Confluence as each of them, with the accounts they connected, and a docs repository's checkout by the readers each document names in its front matter, as the handbook's do. A library nobody trusted as the handbook is trusted is content from outside: the agent reads it through a5s's reader, and its run is marked.

## A call, step by step

Every tool call, model call and outgoing message takes the same path:

1. The agent sends the call to a gateway with the run's id, and nothing else about the run. The core keeps each run's envelope itself: the instance and the people it acts for, taken from the trigger when the run opened, with a message's sender checked against the channel's signed identity; whether the run has read outside content, which the gateway marks when it returns some; and the handles it issued.
2. In one Postgres transaction, the gateway reads the settings, checks them against their signatures, evaluates the Cedar policies, reserves any counts, and writes the ledger entry. Nothing is cached: while the settings in force don't check out, every call is denied. If any step fails, the call is denied. A run's model calls go one at a time, so calls made together can't overrun its budgets.
3. On allow, the gateway gets a short-lived credential for that one call, resolves the handles to values, and makes the call. In what comes back, at any depth, it withholds records the run may not see, tokenises classified values, puts any handle's value back as its handle, tags it with its source, and records the outcome. Text in the arguments is cleaned at any depth too.
4. On deny, the call never runs, and the agent gets the reasons in words, so it can change course. On hold, it doesn't run either: a hold is a Cedar annotation on a permit, and the gateway keeps the call as a held proposal for a person to decide, answering the agent at once with who decides ([proposals](#proposals-and-approvals)).

The model gateway also checks each model's provider, deployment, region and dated version, and records prompts by hash, not by content. The ledger records every text the same way, by its hash: what people say, what agents write and the arguments of a5s's own tools. Only record keys and a5s's own ids are kept as they are.

## Policy

Policy answers **allow**, **hold** or **deny**, and denies by default.

- **Inputs:** the instance, the people it acts for, the tool or model and its risk attributes (reads, writes, sensitive, destructive, sends outside), the fields it touches with their parts and classes, the level for that part and type of action, the counts, the budget, and the scenario's switches.
- **Rights come first.** Actions a scenario forbids are never in any agent's grant, so no instruction can talk an agent into them. Policy is the second line, not the only one.
- **Levels** come from the scenario's settings for each instance, part and type of action. The instance works at the lower of that setting and a5s's own cap ([autonomy](agent-model.md#autonomy)).
- **Counts** stop a piece of work going past a limit the scenario sets, such as a mass-change size, and send the rest to whoever approves it. Code, not the model, decides what a piece of work is: a run. The settings give each type of action a limit for a run, and one for each person acted for in 30 days, across every agent. The gateway counts in the transaction that decides the call, under a lock, and the same change made again in a run counts once.
- **Failing closed.** If policy, the settings, the counts or the ledger can't be reached, calls are denied, the run ends and its trigger waits.
- **A schema.** A Cedar schema lists the facts every call carries. A call missing any of them is denied, and a pack that refers to anything else fails to load.
- **Packs.** a5s's base pack holds what's always enforced: deny by default, the people a run acts for never decide what it raises, a marked run never acts at level 2 or writes a profile, and [what a5s won't do](#what-a5s-wont-do). A scenario's pack can only add restrictions. Among the facts it may weigh is whether a call is the asker's own: the run answers that one person's own message, one to one, has read nothing from outside, and every record it names is theirs, as the scenario said whose each was when the call read them. A chase, a report, a reminder, a task's slice or another agent's question acts for one person who asked for nothing, so none is. A change a pack rules out at level 2, and nothing else denies, waits for its decider as it would at level 1, and one they approve is made at the level it was held at. The service desk's pack lets a password reset run alone only for the asker's own, and an authenticator change never ([`pack.cedar`](../scenarios/service-desk/pack.cedar)).

## Provenance: who said what

a5s answers "whose words are these?" in code, never by asking the model, at three grains:

- **Runs.** A run that has read outside content, through the extractor, stays marked. It can't act at level 2 or write anyone's profile, and what it drafts says so. What a marked run wrote stays marked wherever a5s passes it on: a run given a held change's words, in its brief of what waits on a record or in a5s's own notice of what became of it, is marked too. So is a run given a team's words in a handed-over conversation, as far as changes go: what it asks for waits for a decider, and is never taken as the person's own (round 15).
- **Values the agent shouldn't retype.** Tools return sensitive values, such as a contact or a bank account, as handles. The agent passes the handle on, the gateway resolves it when it calls a system, and code renders it for people. The source of each such value is exact, and the model never needs to see it.
- **Typed values.** Keys, amounts, dates and codes the agent writes are matched exactly against what the run has read. A match carries its source, and anything else is flagged as the agent's own. A tool's schema may name a string's form, a `date`, a `date-time` or an `email`, and a call whose value isn't one is refused before anything else weighs it. The values a held change carries reach its deciders and a5s's own messages as plain words on one line, cleaned as outgoing text is (round 15).

Free text the agent writes is always its own. Facts a person relies on to decide, such as whether a check was done, are computed by code and shown apart from the agent's narrative. A run acts for everyone whose words it serves: whoever sent the message, set the reminder, or wrote the reply a request came from. They're named on whatever the agent drafts or raises, and none of them may decide it. This follows the CaMeL pattern of keeping untrusted data out of what decides the next step. Phase 1 built typed values and handles alongside conversations, and phase 2 marked runs, with the extractor.

## Proposals and approvals

At level 1, an agent's work reaches people in one of three ways:

| Way | When | Who decides |
| --- | --- | --- |
| Draft | The agent prepares something for a person to use, such as a pre-filled request or a case pack | The person, by using it or not |
| Request | The action belongs to a governed process | Whoever the process routes it to. The process checks the agent's level with a5s before it approves anything automatically. |
| Held proposal | The action has no governed process | The owners of each part it touches, and anyone they name to decide beside them, with an approval for each part, never anyone it was for. a5s holds the exact call, and the agent carries on. Once it's approved, the gateway makes the call, if the records haven't changed, and tells whoever it was for and everyone who decided it. |

Drafts and requests carry a handoff note and the agent's flags, so whoever decides sees them. A decision on a held proposal is signed by its decider for that decision on exactly that change, through the identity provider, and each signature works once. Changes that aren't sensitive can be decided together with one signature, which names each of them. Settings are approved this way from phase 1: a card in each instance approver's chat opens the core's page, where they sign in afresh with a nonce that commits to approving that version, so the provider's signature covers the decision. Where the deployment asks for a second factor, as the chart does, a sign-in that doesn't show one approves nothing ([administration](administration.md)). The channels app, which people reach, checks the sign-in and records it; the gateway, which nobody outside reaches, checks it again and seals the approval with a key only it holds, so breaking into the part people reach gives nobody that key. The approval outlasts the provider's keys, and editing the database approves nothing. Decisions on held changes and grades are sealed the same way. What a seal approves is bound too: a held change's digest covers its exact call, the values its handles stand for, its records as they stood, whom it's for and the words its deciders read, and the core works it out again from what it holds before it makes the change, so one edited in the database is never made; a decision counts once, as the core's own entries in the ledger say; how a change is undone is sealed when it's kept; a sample counts only as the core drew and sealed it, and a grade only of that sample, in its part, when the core sealed it. The ledger says which of a5s's parts wrote each entry, which none may say for itself (round 15). While the provider can't be reached, what's recorded waits, checked again at each sweep for up to a day, so a brief outage refuses nothing. What doesn't check out is refused, and its person hears why in their digest and may do it again, signing in afresh. Decisions are taken only on the decision surface, never by telling the agent in conversation, and after a decider's authenticator is reset, their decisions wait a day before they take effect [TBC]. At level 2, actions run and are reported, to the instance's owner and deputy, or else the owners of the parts they touch, with what each replaced, and the person it was for hears from a5s; the agent owner can reverse them through the scenario's own process.

## How an agent lives

An instance lives in records: its identity, register entry, triggers, obligations and context. Compute is temporary.

1. **Wake.** A message, an event, a schedule or an obligation falling due wakes it. So does a sweep, which runs only while the instance is idle and starts no model when nothing has changed. Every agent can be talked to.
2. **Lease.** The scheduler takes a lease on the person's conversation with the agent, so it runs one thing at a time [TBC: a lease for each topic], and asks the core to open the run, which checks that the instance is active and has budget left. The core puts the work in a topic or case: an obligation by its record, an event in a topic of its own, which the person's reply continues while the conversation is on it, and a message in the conversation's current topic, unless it names another record or the conversation has been quiet for a few hours. No run in another topic is given what an event's run wrote, so what that run read from outside marks its own topic alone.
3. **Assemble.** The context service builds the run's context, within a budget for each part:
   - the release's instructions, and its skills, by name and what each is for, which the run reads, and can't change, when it needs one;
   - the person's profile;
   - the conversation's latest turns, and in a case, the case's summary and older turns;
   - a brief of the case, built from records;
   - what a search of the history finds.
4. **Run.** A fresh Deep Agents run, on a LangGraph thread that lasts only as long as the run. Every call goes through the gateways.
5. **Record.** The context service adds the turn to the conversation, and folds the topic's turns that no longer fit into its summary. The scheduler updates the obligations, and the lease ends.

- **Obligations** are worked out by code from the scenario's records, never inferred by the model, with one for each record and person across all agents, naming the instance that acts on it. A person can say what they're waiting on, which pauses chases to them until the date they give.
- **Reports** are worked out by code too. An agent whose release reports on a kind of record, such as the watcher, tells each person it serves, in their daily digest, what changed in their records since it last told them, and what fell due. Code compares the records with what it last told them, so the model only words the facts, and a day with nothing new starts no model. Each report acts for its person alone.
- **Promises and reminders.** When an agent promises a follow-up, or a person asks for a reminder, a typed tool records it in a5s's own records, and it counts only once the person confirms it, in a later message of their own. It's theirs alone: only a run answering their own message can set one, and content from outside can't. When it falls due, the agent reminds them, and if the agent can't act, the core reminds them itself.
- **Triggers and schedules** come with the release, and an agent can't create its own.
- **Repeats are safe.** Tools are idempotent, with keys made from the piece of work, the record and the change. The piece of work is the run, or for a slice of a task, the task, so a change a later slice asks for again is made once. An adapter declares that contract with `idempotent: true`, which is pinned in its schema hash; the gateway gives it a stable effect key, and the connector uses the key to find and return the original effect. The gateway can't guarantee exactly-once delivery by recording alone: a worker can die between making an external effect and recording it, so the connector must honor the key.
- **Read-only connectors.** A fixed-origin REST transport (`connectors/rest.py`) supplies bounded GET requests, safe pagination and limited transient retries. It follows no redirect to another host, requires HTTPS beyond loopback, and takes credentials only by environment-variable name in the gateway. The read-only GitHub adapter (`connectors/github.py`) exposes issues, pull requests, comments through the reader, source files and diffs as typed tools, with a permission check before every call and no code execution. Scenario adapters wrap and pin these like any other tool; tests exercise a synthetic HTTP service and the gateway (`tests/test_connectors.py`).
- **MCP servers' tools.** A scenario declares, in its folder's `mcp.yaml`, each tool of an MCP server's its agents may use, in a5s's own words, with the flags any of its tools has and the fields of what it returns a5s passes on; nothing else of a server's is offered (`connectors/mcp.py`). Before each call, a5s checks the server still offers the tool as declared, its arguments by their shape and its annotations never more than declared, and what it returns goes through the core's checks as any tool's ([connectors](connectors.md#mcp-servers)).
- **Where its runs run.** In a pool of workers: its agent's own, or the shared pool ([worker pools](../deploy/helm/README.md#worker-pools)). Workers stay up between runs, and a run's only start-up cost is building its agent, in about 15 ms. A worker container starts in about two seconds, on a deploy, an upgrade or a crash, and an upgrade lets the runs in flight finish first. Each of a5s's parts waits for another it can't reach meanwhile, such as one restarting, for up to a minute before it gives up ([`reach.py`](../src/a5s/reach.py)): the scheduler for the core and the pools, and a run for the core, with its tools and model calls. Only a connection that never opened is tried again, so nothing is done twice. Since all an instance's state is in records, any worker in its pool can run its next run. What does go cold between runs is the model provider's prompt cache. The core asks providers to keep what a run sent for the shortest time they offer, a few minutes ([data protection](data-protection.md)), so the first run after a longer pause pays for its whole context again.

## Context and memory

People get one conversation with each agent, and it never runs out of room, however many runs it takes. Each run starts fresh and reads the conversation from a5s's records, so long conversations stay cheap and upgrades never strand them.

| Context | What it is | Written by | Checked by |
| --- | --- | --- | --- |
| Conversation | Every turn with a person, across channels, organised in topics such as one per request | a5s, as turns happen | The person, who can see all of it |
| Summaries | A structured summary of each topic: decisions, commitments, open questions, and facts by handle | a5s, once a topic's turns no longer fit in its runs. Code keeps every key, amount and date they had, and keeps no summary that has one nobody said. | The person, who can correct it |
| Profile | Typed preferences, such as digest time and channel, and a short "how I like to work" note | The person, or the agent with their confirmation | The person |
| Case briefs | The state and history of a case, built for each run | Code, from records | Nobody needs to: the records are the source |
| Instructions and skills | How the agent works | Only a release | The release approver |

- **One conversation per person per agent,** whichever of the agent's instances does the work. A message that names a record goes to the instance that works in the record's part. Each run's grant comes from the instance, so its scope is enforced at the tools.
- **a5s's own words** in an agent's chat, such as an escalation or a reminder the core gives itself, go in that conversation as a5s's notices, so the agent's next run knows what the person is answering. They're never taken for the agent's words, nor counted as something the person said.
- **Records beat recollection.** Commitments and decisions live in records, never only in a conversation, and answers about the past retrieve the original turns, not just the summary.
- **People stay separate.** Nothing from one person's conversation enters a run for someone else. An agent acting for people sees only what the directory says all of them may see.
- **Classified values** are tokenised in conversations, and shown back only to people who may see them.
- **Group conversations.** In a Teams group chat, a Slack group DM or a Matrix room of up to 20 people the directory knows, an agent answers whoever mentions it there, and hears nothing else, which it's told. It acts for everyone in the chat, as the chat itself lists them at each message, so a run there finds, sees and says only what all of them may see. Its changes are for whoever asked and whoever spoke in what it was given: only they don't decide them, and only their limits count them. Its day's budget is the asker's, and it writes only to the group. A Matrix room is someone's own only while nobody else can join or read it, and someone's own chat that another person joins becomes a group's, so a5s writes to them first in a new one. The group's conversation is its own, apart from each person's, with who said each turn and who heard it, and a run is given only what everyone now in the chat heard, so someone added later gets nothing said before. Its summaries are of what everyone in it heard, each fact with who said it, and a run is given one only if everyone it acts for heard all it holds: once someone joins, the next summary starts afresh, from what they heard. What's one person's own stays one to one: notes on how they like to work, digests, their list of reminders, and agents writing first. A reminder asked for in a group is the asker's alone, and what becomes of a held change reaches the asker ([`core/groups.py`](../src/a5s/core/groups.py)).
- **A notebook** of what an agent learns from records, for its instance's later runs, such as which kind of question comes up on a kind of record. Only a run that acts for nobody notes anything, such as one on a schedule its release brings: it hears nobody's words, so a note comes from records alone, never from what someone said, and a run that has read content from outside notes nothing. Code keeps a note only if every record it names was read by the run with a tool, in its instance's parts, and what the run read of them holds every key, amount and date in it. A note reaches only people who may see every record its run read, since it may draw on any of them, and only runs on a case it names, as something to check, not as found. It goes once its records change, checked each day apart from the retention sweep, and the notebook keeps its newest 50. The agent's owner, or whoever runs its instance, reads and removes notes in the studio, `/studio/notebook` ([`core/notebook.py`](../src/a5s/core/notebook.py)).

## Channels

Each agent talks to people under one identity, never a person's, and says it's an AI agent. Outgoing messages, and the text of drafts, go through a gateway that keeps only text and the record links the scenario's systems build. An address ends where a page would end a link, at a quote, a backtick or a `<` as well as a space, and the web chat links only the scenario's records and a5s's own pages, so what the gateway checks is all a page links. Each message the chat shows says who it's by, a person, an agent or a5s, apart from its name, and no agent may be called `you` or `a5s`. Messages go only to the audience the settings name [default: people inside the organisation].

- **Which chats.** Each deployment turns on the chats its people use, any number at once: a web chat the core serves, Matrix on the organisation's own homeserver, Teams and Slack, as well as the command line. The directory names each person in each chat they use. A reply goes back through the chat its message came from. An agent that writes first writes only as its own bot: in the conversation the person last had with it, or else in the chat they last wrote in, where its bot starts one if the chat lets it. Otherwise, and once the person leaves that conversation, it waits in their inbox in the web chat and on the command line. An agent works in a group chat too, answering only when someone mentions it: in Teams, a group chat, never a team's channel; in Slack, a group DM, never a channel; and in Matrix, a room that shows nobody what was said before they joined.
- **Who can start a run.** Only people the directory knows, and the core itself, for the obligations it works out from records and the schedules releases bring. Every message arrives at the core first, which checks who sent it and records it: a sign-in token from the organisation's identity provider, which names the person by a claim they can't change, such as Entra ID's object id or another provider's subject; for Teams, the Bot Framework's signed token, which doesn't cover what a message says, so only the core may receive one; for Slack, the signature of the agent's app over the request's time and body, made with that app's secret, which only the core holds, and for the app and workspace the request names; or, for Matrix, the organisation's own homeserver, which proves each delivery with a token only the core holds, and vouches only for its own people. A run that answers a message takes its sender from that record and can use it once, so no service can say a message came from someone else, and a person's token goes no further than the core. a5s's own notices go only in answer to someone, apart from escalations, which the core writes itself from the records. Another system starts one with an event an agent's release takes, signed with that system's own secret over its time and body, which names the records it's about and the person, if anyone, but carries no words, so nothing it was told reaches a run as if a5s had said it ([`core/events.py`](../src/a5s/core/events.py)). Nobody asked for its run, so it never acts as that person in another system, and a change it asks for says it came of the event. Email starts one only from a sender who passes DMARC and matches the directory, and the agent never answers a Reply-To address. Any other email goes to the extractor as a document.
- **Contact.** Each person gets one digest a day from all the agents together, at a time they choose: the start of their working day unless they ask for another. What agents write to them on their own, such as chases, reports and reminders for a day, waits for it, and the agents' work for it is done when its time comes, so nothing in it is stale. What comes up after it waits for the next one. A digest with one item is that item, from its agent. In Teams, Slack and Matrix, each agent's items go in its own chat; in the inbox, one with more is a5s's own message, with each item under its agent. A digest waits half an hour at most for its agents' work, and goes once a day, by the person's own date. Outcomes people are waiting for, such as answers to their messages, go at once. So do urgent items, such as escalations and reminders for a particular time, up to five a day for each person across all the agents. A reminder someone asked for at a particular time doesn't count toward the five. After the five, the rest wait, and go together once an hour, in the person's working hours. Escalation follows the scenario's chain, in people's working hours, and goes only to people who may see the record.
- **Delivery.** Everything a5s sends to a chat it writes to itself, such as Teams, Slack or Matrix, goes in the outbox in the transaction that decides it, and is delivered after. One the chat doesn't take is tried again after a minute, then two, four and eight, and after five tries it waits in the person's inbox instead, which the ledger records and the status counts. A reminder or chase whose run doesn't finish, because the model is down or the budget is spent, is given by the core itself, in its own words.
- **When an agent can't help,** because it's suspended, out of budget, stopped by an outage or no longer approved, the channel service says so in code and names who to ask. Its obligations escalate in code along the scenario's chain as they fall due.

## Data protection

What a5s keeps about people, where, for how long and who sees it, for the data protection officer's assessment, is in [data protection](data-protection.md).

- **Classes** of data come from the scenario's settings, and decide what's masked and which models may see it.
- **Tokens.** The ledger, conversations, traces and test data hold tokens with record keys, not classified values.
- **Retention.** A conversation is kept for 12 months after the last thing a person and an agent said to each other, and then deleted, with its summaries and the messages that carried it. Notes on how people like to work, and reminders, go 12 months after they ended or, if never confirmed, were offered, and a note someone asks to forget goes at once. What someone waits on stops holding chases back on the date they named, and goes 12 months after they said it, and what a report told a person goes once it's told. What someone owed goes 12 months after the records stopped owing it, and their use of a day's budget, and the log of their digests, once the day is past. The values a run is handed as handles go once it's over. The ledger records what each deletion removed, in counts, and keeps nothing that was said. What a5s keeps for someone who leaves is archived where it is, a day after the directory stops naming them, under a name no person has, and goes on the same clock ([`core/departures.py`](../src/a5s/core/departures.py)).
- **Requests for someone's data.** The data protection officer, signed in with the role, exports all a5s keeps about someone, with nobody else's words, and erases it on request, keeping only what's evidence of what agents did, and the ledger records each ([`core/export.py`](../src/a5s/core/export.py), [`core/erasure.py`](../src/a5s/core/erasure.py)).
- **Models.** Each approved model names its provider, deployment, region and version: a dated version where the provider offers one, and otherwise the version each response reports, checked every time. The model gateway refuses anything else, including a failover to an unapproved model. It speaks both OpenAI-compatible and Anthropic-compatible APIs, so a model from any provider that offers either can be approved, including open-weight models an organisation hosts in its own cloud or on its own premises. A server on the organisation's own network may need no key.
- **Outside content.** A scenario's tool says which fields of what it returns are content from outside the organisation, such as an email's body, and the fixed form a5s's extractor fills from them: keys, amounts, dates, yes or no, choices from a list, and sensitive values, never free text. Each comes as code reads it, never as written: an amount as GBP 860.00, a dated day as 2026-11-04, a month by its name alone, and a key only of a record the scenario knows, so no value carries words (round 15). The agent never gets those fields: the extractor, a call to the instance's own approved model with no tools, fills the form, and code keeps only values the document itself contains, sensitive ones as handles. An agent can also ask the extractor a question about a document its run has read, and the answer comes back in free text, marked as outside content and never used as an instruction. The files people send with a message, text, PDFs and images, are such documents too: the run that answers is marked from the start, the core fetches each from the chat's own file host, as the agent's bot, only once the agent asks about it, and an image goes only to a model approved for images ([`core/files.py`](../src/a5s/core/files.py)). The run is marked whenever a file came, kept or not, since even a file a5s turned away has a name from outside, which the agent hears. A PDF is read in a process of its own, within 20 seconds of the processor's time and 256 MB of memory, two at a time in each of the core's processes, page by page, until it has as much as a5s's reader reads, so one made to take hours to read, or all the memory it can, holds up nothing, and a few sent at once never take the core's memory with them. The run is marked from its first outside content. Classifiers such as Prompt Shields, Model Armor or Bedrock Guardrails add signals. They're never the boundary.
- **Supply chain.** Skills are copied into the release and pinned by hash, and so are the schemas of the tools it uses, so the gateway refuses a tool whose schema has changed. a5s's image pins its base images by digest and its packages by hash, its build's provenance is signed, and the actions that build it are pinned by commit. It also refuses tool servers' requests to ask people for input or to run the agent's model.

## Evidence

The ledger is a hash-chained Postgres table, written in the same transaction as each policy decision. It records the instance and release, the people acted for, the call and its masked arguments, the decision with the policy and settings versions, and the outcome. Every [TBC: hour], the entries since the last copy, and the hash of the last of them, go to object-lock storage that belongs to the scenario's assurance, in an account the team that runs a5s can't administer: S3 Object Lock, on Amazon's S3 or a store of the organisation's own that speaks it, such as MinIO, Azure's immutable Blob Storage or Google Cloud Storage's object retention. Nobody can change or delete a copy until its retention ends, and a5s won't copy a history that no longer matches its copies. So a rewritten history shows, even if every hash after the change is recomputed. That makes the ledger tamper-evident. Because it holds tokens, deleting a token's mapping when its retention ends removes the personal data without breaking the chain.

The same events go out as OpenTelemetry spans, using the GenAI conventions at a pinned version, since they're still at Development stability. Traces are for debugging. The ledger is the evidence.

## Assurance

- **Tests.** Each release passes its regression suite and the scenario's tests, attempted injections included.
- **Measures.** Work handled, acceptance and edit rates, time to decision, chases, cost, and how many people use the agents (`a5s measures`). Measures of individual people judge outcomes, not speed. They're agreed with the data protection officer, and with works councils where there are any, before they start.
- **Samples and level-ups.** a5s keeps its cap for a behaviour: an agent, its model, and the tools of a type of action it may use, as pinned, so a release that changes only instructions keeps the level its grades earned, though for an agent that may work at level 2 the release approver signs it too. Code draws samples of an agent's changes: every held change someone decided, while its cap is 1, and at level 2 changes made, at random, about 100 a quarter. People who hold the grader role grade them on the core's page, signing in afresh to give exactly those grades, at most 20 a sign-in, which the core seals once it has checked, itself, that they may give each: never anyone who owns, authors or drafted the agent, nor anyone from their teams or the teams that run the instance, nor anyone a change was for, who decided it, for any part it touched, or who reports to whoever did, and only for records they may see. An anytime-valid sequential test, on the grades the core sealed since the cap last changed, raises the cap when the evidence shows accuracy meets the part's threshold, and lowers it when it shows it doesn't, or at once on a critical error. The core seals each cap with the ledger entry that set it ([starting values](starting-values.md)).

## Independence

- **Loosening needs someone else.** Anyone with the role can make a5s safer alone: suspend an instance, lower a cap or withdraw a release. Anything that loosens it needs someone outside the team that runs a5s and its manager's reporting line, and is reported to assurance. That covers resuming someone else's suspension, raising a level or cap by hand, widening a grant, and changing the trusted core. A scenario can also mark an agent as a check, such as one that reconciles changes for auditors. Stopping or changing it then needs the scenario's assurance to agree.
- **Releases are proportionate.**

  | A release that | Needs |
  | --- | --- |
  | Changes only instructions or skills, and widens nothing | The agent owner and a second engineer, after the regression suite; and the release approver too, from outside the team, for an agent that may work at level 2, where nobody decides its changes before they're made (round 15) |
  | Changes a tool, a scenario's code, data or knowledge, such as who may read a note, or widens a grant, trigger, model, class of data or cap | The release approver, from outside the team |
  | Fixes a security advisory | Nothing more: it goes in at once, at level 1 at most |
  | Changes the trusted core | The release approver, an attested build, and assurance's tests |

  Each organisation's people approve each release for their own deployment, by signing what it is there. The core works out what changed since the release they approved before, checks the signatures against who that release records may sign the next and who this one records, so a release can't approve itself with an approver it adds, and opens no run until the release has what it needs ([lifecycle](agent-model.md#lifecycle)).

- **Evidence and grading** sit outside the team. The ledger's anchor is with assurance, and nobody from the team that built an agent grades its work.

## When things fail

The scenario's own processes work without agents. So when a5s can't run safely, it stops, says so, and people carry on there.

- A run whose dependency fails ends, and its trigger waits. A circuit breaker pauses new runs while the dependency is down.
- Budgets are kept per person and per source of triggers, with a share kept for obligations, and outside parties are rate-limited.
- An instance can always go straight back to the release it ran before.

## Operations

Phase 1 sets these up:

- **Environments:** local, against the scenario's fake; test; and production. Each scenario's data and agents are kept apart [TBC].
- **Objectives:** how quickly people get answers, nine in ten within two minutes, and the share of what's owed that's chased before it falls due, 95% [TBC: from the first users' baseline].
- **Status and runbooks** for the team that runs a5s: the queue, runs, denials, budgets, suspensions and breakers, and the objectives, from `a5s status` or a dashboard, and what to do when each goes wrong ([runbooks](runbooks.md)). On call: once people depend on a5s, a weekly working-hours rota of the team that runs it, paged out of hours only for the ledger's copies, a change stopped part way, and a sudden rise in denials, since a5s stops safely and people carry on without it ([on call](runbooks.md#on-call)).
- **Traces** as masked OpenTelemetry spans, which carry no prompt, reply, message, tool argument or person, kept for 14 days.

## Hosting

Phase 1 runs a5s's own services and workers on Kubernetes, in each cloud's managed Kubernetes, AKS, GKE and EKS, each with managed Postgres, so nothing ties a5s to one cloud. The same chart runs on the organisation's own clusters on premises, even on a network with no way out, with its own Postgres, identity provider, models and locked storage. They run as one container image, and network policies keep workers away from everything but the gateway ([deploy](../deploy/)). Nothing waits inside a host's session: conversations and held calls live in a5s's records, so a5s can move hosts or use a managed runtime later.

| Host | Runs on | Identity | Gateway |
| --- | --- | --- | --- |
| Any, including the organisation's own premises | a5s's own workers | The organisation's identity provider, through OpenID Connect | An MCP gateway such as agentgateway, with a5s's policy |
| AWS | AgentCore Runtime | AgentCore Identity | AgentCore Gateway |
| Microsoft | Foundry hosted agents | Entra Agent ID | a5s's own |
| Google | Agent Runtime | Agent Identity | Agent Gateway, managed only for Agent Runtime so far |

A host's gateway sits in front of a5s's own policy and ledger, because the decision, the counts and the ledger entry are one transaction.

## What a5s uses from Deep Agents

a5s pins its versions, and treats each upgrade as a release. It needs deepagents 0.7.25 or later, which fixed a way around its approval rules.

| Uses | Doesn't use |
| --- | --- |
| The agent loop, reading a tool result too large for one message from the run's scratch files, skills loaded read-only from the release, and summarisation and offloading within a long run | The editable `AGENTS.md` memory, the long-term store, interrupts, file permissions as a boundary, the Agent Server, and the shell, file and subagent tools, which each model call would carry for nothing |

If the list shrinks further, LangChain's own `create_agent` could be the base instead.

## Agent to agent

An agent asks another what it knows, such as the assistant asking the watcher what changed on someone's records, with the typed tool `ask_agent`. Only instances of one deployment ask each other, and only those an instance's settings name, which the owners of the parts both work in approve, and a release says whether its agent asks at all. The core opens a run of the instance asked at once, acting for the same people as the run that asks, and the worker that asked runs it, as it runs its own, so a question never waits for a worker another run holds. The people travel with the question and authority never passes from one agent to the other: the run asked works within its own grant and level, and what those people may see, and nobody it acts for decides what it holds. It sees no class of data the asking model may not see either, since its answer goes there, and its day's budget is the asker's. An agent that reports on records, such as the watcher, is given what its reports would tell those people. It writes to nobody: its answer goes back to the run that asked, as the tool's result. The question carries the asker's mark to it, and its answer carries its own mark back, so a run that hears from one that read content from outside works as one that has. Only the values it read with its tools and what a5s told it count as found for the run that asked, never those it was asked about, and what came from outside stays from outside, so a value an agent wrote itself is noted as such when it's passed on. An agent that's asked can't ask another, so questions never chain, a run asks three at most, and the ledger links the two runs. A question and its answer can be given as an A2A task, in A2A 1.0's shapes for a message and a task, so agents outside a5s can come later without a second way of asking ([`core/asking.py`](../src/a5s/core/asking.py)).

## Standards

| For | Standard |
| --- | --- |
| Tools | MCP, specification 2026-07-28 |
| Models | OpenAI-compatible and Anthropic-compatible APIs |
| People's identity | OpenID Connect |
| Agent to agent | A2A v1.0 |
| Skills | Agent Skills |
| Identity and delegation | OAuth as MCP uses it, and token exchange (RFC 8693) |
| Policy | Cedar |
| Telemetry | OpenTelemetry GenAI conventions, pinned |

## What a5s won't do

- Let an agent change anything in its own release in production.
- Let a model approve an action, or assert a fact someone relies on to decide.
- Give a model, a worker or a sandbox credentials.
- Take a decision on a proposal anywhere but the decision surface.
- Let an agent act without telling anyone. There's no level above 2.
- Move money. No agent can make, approve or release a payment.
- Write to a system of record except through its own governed process.
