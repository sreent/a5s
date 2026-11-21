# Connectors

**Status:** MCP servers' tools are built ([below](#mcp-servers)), acting as the person with their own permissions where a server is declared to ([below](#acting-as-the-person)), document libraries in SharePoint, Confluence and docs repositories, read as far as each document's own permissions allow ([below](#document-libraries)), and the shared mailboxes a team's work arrives in, whose new mail starts runs and where agents leave draft replies, sending none ([below](#mailboxes)), beside the read-only REST transport and the GitHub adapter · **Under:** [Architecture](architecture.md)

A scenario's tools reach the systems its records are in. A scenario writes most of them in its own code, against the [contract](architecture.md), and a5s gives it two ways to reach a system without writing a client of its own: a read-only REST transport, with a GitHub adapter on it ([architecture](architecture.md)), the tools of MCP servers, which most of this page is about, the [document libraries](#document-libraries) its agents may search beyond the handbook in its release, and the [mailboxes](#mailboxes) its teams' work arrives in. Every tool, whichever way it's made, is offered to an agent only if its definition lists it, pinned by its hash, and every call goes through the core's checks: the policy, the parts and need-to-know, held changes, the extractor for content from outside, handles for sensitive values, and the ledger.

## Read-only repository connectors

A scenario declares repository tools in `repositories.yaml`, beside its settings. For example:

```yaml
repositories:
  delivery:
    kind: forgejo                 # or github
    repository: pilot/delivery    # record keys are pilot/delivery#<number>
    url: https://forgejo.example/api/v1
    site: https://forgejo.example/pilot/delivery
    part: backend                 # visibility follows the directory's sees_part
```

This gives `search_delivery`, `get_delivery`, `get_delivery_comments`, `read_delivery_file` and `get_delivery_diff`, which an agent lists and pins like any other tools. The declaration, endpoint, site and part are covered by the tool hash. The core alone holds the read-only token in `A5S_REPOSITORY_DELIVERY_TOKEN`; the studio sandbox offers the tools but refuses to call the real service. Repository keys join the scenario's provenance pattern and permitted links, and only people who may read the configured part may call them.

The transport and adapter work with GitHub and Forgejo, including Forgejo's repository-scoped search and `.diff` endpoint. PRs report standard commit statuses and any check runs. Files and diffs mark the run as reading evidence outside the release; comments go through a5s's reader. Denied people, other repository keys, paths outside the repository, and searches containing another `repo:` qualifier make no HTTP request.

Run `sh deploy/forgejo.sh` for the real Forgejo evaluation. It creates a disposable server and synthetic repositories with conflicting PRs, changing checks, malicious comments, and deleted and moved files; proves the API token read-only; and removes the server. The same run is a CI job. With `A5S_TEST_FORGEJO_LIVE=required`, it also starts PostgreSQL and an actual a5s worker, loads `.a5s/live.env`, and proves a real model through a copied, signed, backend-only, read-only scenario, the worker and the gateway, without giving the worker a provider key. Rate-limit retry and refusal are deterministic transport tests; a deployment limits request rates at its HTTPS proxy. The [read-only software-team pilot](guides/software-delivery/pilot.md) keeps the real repository/gateway proof distinct from the shipped scenario's synthetic MCP and Matrix rehearsal.

## MCP servers

Many systems now offer their tools through an [MCP](https://modelcontextprotocol.io) server. a5s uses them as a scenario's own tools, governed as strictly: nothing of a server's is offered until a scenario declares it, in a5s's own words, and a release approves the declaration.

### Declaring them

A scenario's folder holds an `mcp.yaml`, beside its `data.yaml`. It names each server, and each tool of theirs the scenario's agents may use:

```yaml
servers:
  tickets:
    url: https://tickets.example/mcp        # its Streamable HTTP endpoint
    token_env: A5S_MCP_TICKETS_TOKEN        # the variable that holds its bearer token, if any
    sandbox: http://127.0.0.1:9100/mcp      # the stand-in the studio's sandbox calls instead
tools:
  search_tickets:                           # its name in a5s, which agents list
    server: tickets
    calls: search                           # the server's own name for it
    description: Search the questions' tickets by the words they hold
    arguments:                              # what it takes: the server's schema, in shape
      type: object
      required: [query]
      properties:
        query: {type: string, description: words a ticket holds}
    returns: [items, key, title, status]    # the fields of what it returns that a5s passes on
    record_field: key                       # the field that names each record it returns
```

A tool takes the same flags as any of the scenario's: whether it `reads`, `writes` or is `destructive`, whether it `sends_outside`, whether it's `idempotent`, the `record_arg` that names the record a call is about, the `action` a change is, which a5s holds for the record's part to decide unless the agent may act on its own, the `text_fields` that are outgoing text, the `handles` that hold sensitive values, and the `outside` fields that hold content from outside the organisation, with the form a5s's extractor fills from them, `extract`, and, for a change, what its answer says once it's made, `made`, such as `{locked: true}`: an answer naming its record but saying otherwise, as a device management answers a lock it has queued until the device next connects, is the change in hand, not made, and never counted, reported or sampled as made. A change can say how it's undone, `undo: {tool, args, hours}`: the scenario's tool that reverses it, each argument from the change's own (`args.<name>`) or from its record as it stood before (`before.<field>`), and for how many hours after it's made, 24 unless it says, 168 at most ([undoing a change](agent-model.md#undoing-a-change)). `returns` is required: it names every field a5s passes on, at any depth, and drops the rest, so a field a server adds, or renames, never reaches an agent unread. A field the tool names a record by, a handle or outside content is among them. The file names each key once, as `agent.yaml` does.

Each tool's name is its own: one the scenario or a5s has already stops a part as it starts. An agent lists the tool among its tools and pins it with `a5s pin`, as any other, by a hash that covers the server's name for the tool and the fields a5s passes on, besides all a scenario's tool's hash covers. The release covers `mcp.yaml`, as all of a scenario's folder, so a change to it needs the release's signatures, as a change to the scenario's code does.

### What a5s checks

Before each call, a5s checks the server still offers the tool as declared, from its list of tools, which it asks for again every five minutes:

- **The arguments it takes, by their shape.** The server's schema and the declaration's must constrain the same arguments in the same way. The words that only describe them may differ, since the model reads a5s's: titles, descriptions, examples and comments. Defaults count, since a default changes what a call does.
- **What it says of itself.** A server's annotations are hints, so a5s never takes them as permission. But one that says more than the declaration does, outright, stops the call: that it changes things, for a tool declared as reading only; that it may destroy what it changes, for one not declared destructive; that asking again does it again, for one declared idempotent; or that it reaches outside the organisation, for one declared neither to read outside content nor to send outside. MCP's defaults for the hints never count.

A server that changed either way is refused, saying why, until a release declares the tool again. A call's arguments must fit the whole of the schema pinned, not only its types: the values it lists, the lengths, patterns and bounds it sets, and how many items a list holds. a5s sends only the arguments the schema declares, so nothing else the model adds reaches the server.

What the tool returns comes back as JSON: its structured content if it has some, or its text, parsed as JSON where it is JSON, with only the fields declared. For a tool that names its records, outside any record a list holds only objects that each name their record by the field, and an object that names none holds only lists and objects, or a5s passes none of it on. A row, a line of text or a record named otherwise would otherwise pass unchecked. The core's need-to-know then checks every record, and withholds those the run may not see. A field among its `handles` is a handle whatever it holds: a string, a number, or each value of a list. A tool that reads outside content may return lists of objects alone, since a line of text in one can't be told apart from that content. A change is made only when the server's answer names the record it changed, by the field: words alone, such as why it didn't make it, are a refusal, never counted, reported or sampled as a change. What a5s can't pass on as JSON, such as an image, it leaves out, and says it did. A tool's error comes back as its words, cut to 300 characters. A tool that reads outside content is the exception, since its error could be the content itself: then a5s says only that the call failed.

### How a5s reaches them

a5s speaks MCP's Streamable HTTP, through the `initialize` handshake, in the versions from 2025-03-26 to 2025-11-25. It calls a server over HTTPS, or HTTP on the same machine, and follows no redirect. It reads an answer of 1 MB at most, counted as it comes, and asks for it uncompressed, refusing one sent compressed, which could be far larger once opened. A call takes two minutes at most, however slowly the server sends. a5s sends the bearer token in the server's `token_env` only to that server. The variable is named for the server, `A5S_MCP_<SERVER>_TOKEN`, so one server's declaration can't name another's token. It begins a session again once if the server ends a5s's. A server that acts as the person takes theirs instead ([below](#acting-as-the-person)). Of a5s's own, a call sends only its key, for a change or an idempotent tool, in its `_meta`, as `a5s/key`, so a server can make a change once for each key: never whom the run acts for, nor the run itself.

In the studio's sandbox, a server's `sandbox` stand-in answers instead, and no token goes there: the sandbox's people and records are made up. Each scenario's made-up systems have a copy of their own for the sandbox, at an address of their own, with their own state, so nothing tried there changes the deployment's: the tests start each beside its system, and the containers run each in the sandbox's network, under the `sandbox` profile, with the sandbox's own overlay. A server with no stand-in has its tools offered there, so a draft checks as it will run, but each call is refused.

### Acting as the person

A server can act as the person a run is for, with their own permissions in its system, never a5s's: `as_person` names the system, as the deployment's `A5S_DELEGATION` names it, in place of a `token_env`, which a server never has beside it ([`core/delegation.py`](../src/a5s/core/delegation.py)).

```yaml
servers:
  desk:
    url: https://desk.example/mcp
    as_person: servicenow                   # the account each person connects, in A5S_DELEGATION
```

So the system's own rules decide what each person sees and changes there, as they would for them, after a5s's own: the policy, what each agent may do, held changes and need-to-know decide first, as for any tool, so an agent does the narrower of the two. Whose access a tool calls with is in its hash, as its approvers pinned it.

- **Connecting.** The deployment names each system people may connect, in `A5S_DELEGATION`, a JSON list of `{name, title, authorize, token, client_id, scopes, whoami, whose, known_as}`: the system's OAuth endpoints, over HTTPS, a5s's client there, the scopes a5s asks for, and where a5s asks whose account a token is: `whoami`, the address the system answers that at, such as Microsoft Graph's `/v1.0/me`, `whose`, the field of its answer that names the account, such as `id` or `result.user_name`, and `known_as`, which of the directory's identities that is, such as `entra`, or none for the person's a5s id. a5s's client secret there is the core's alone, in `A5S_DELEGATION_<NAME>_SECRET`, and the core doesn't start without it, nor with a server acting as the person in a system the deployment doesn't name. Each person connects their account on their own page in the studio, `/studio/you`: the system asks them, as itself, whether a5s may act for them, and sends them back to `/studio/connections`, which each system takes as a5s's way back, with a code. The core exchanges it for their tokens within a minute, with PKCE, so the code is no use to anyone else, and a way back is good only to whoever began it, for 15 minutes.
- **Whose account it is.** Before it keeps a token, the core asks the system whose account it is, and keeps it only if the directory says that's the person who came back with it. So whatever the part people reach records of their way back, a5s never acts as someone in an account that isn't theirs, nor as one person with another's account, and the ledger records each it refused (round 14).
- **Their tokens.** The core keeps them sealed, with AES-GCM under a key it derives from its own seal keys, which the channels app hasn't, each bound to the person and the system, and renews the access token with their refresh token a minute before it lapses. Neither the ledger nor any page holds a token; the ledger records each connection and its end, and someone's export names the systems they connected, with the scopes and when a5s last used them.
- **A run acts as one person, who asked for it.** A tool on such a server is called only for a run acting for one person alone, never for a group chat's, or for one that acts for nobody, such as a schedule's, and only for a run they asked for themselves: their own message, a task or a reminder they asked for, or a question such a run asks another agent. Never for one nobody asked for, such as an event's, a report's or a chase's, which another system, or a5s, starts. And only once they've connected: a run for someone who hasn't hears how to. Each person has a session of their own with the server, which sees them as themselves, and lists what it offers them. In the sandbox, the server's stand-in answers, with no one's token.
- **Ending it.** Someone disconnects on the same page, and a5s forgets their tokens; the system may keep its own record of a5s's access, which they end there. a5s forgets them too when the system stops taking them, after 90 days unused, when someone leaves, or when they ask a5s to erase what it keeps of them ([data protection](data-protection.md)).

With Entra ID, for Microsoft Graph or an API of the organisation's, that's its authorization code flow, with offline access and the API's delegated permissions: chats pass a5s no token of the person's to exchange on their behalf, as the on-behalf-of flow needs, so a5s asks for their consent once instead, on their own page. ServiceNow and GitHub take the same flow, with a5s's OAuth app in each.

Tested against a made-up OAuth system of the test's own, with PKCE and refresh, and the MCP SDK's server, which reads whose token each call carries (`tests/test_delegation.py`).

### Not yet

- The on-behalf-of exchange of a token someone's chat passes a5s, where a chat passes one.
- MCP's stateless envelope of 2026-07-28, which servers may offer beside the handshake.
- A server's resources and prompts, its requests to the client, such as for sampling or to ask the person something, and servers run as a local process, over standard input and output.
- `a5s mcp declare <url>`, to write a declaration's first draft from a server's list of tools, for its author to put in a5s's words.

Tested against the MCP SDK's own server, over both of Streamable HTTP's ways of answering, and end to end through the core (`tests/test_mcp.py`), with round 12's checks of what a server answers (`tests/test_r12_mcp.py`). The service desk scenario takes its ITSM's tools this way, a reply on a ticket held for its service area's decider among them, its identity provider's self-service, and its device management's, with a lock held for hardware's decider, software delivery its forge's, with a review request held for a repository's owners, and master data SAP's, with a correction held for the data object's owner, each from a made-up server on its synthetic data ([`scenarios/service-desk/mcp.yaml`](../scenarios/service-desk/mcp.yaml), [`deploy/systems/itsm.py`](../deploy/systems/itsm.py)), so its suite, its containers and its walk-through run on MCP.

## Document libraries

Beside the handbook a release holds, a scenario may name libraries of documents kept in other systems, for its agents to search: a SharePoint site, a Confluence space, or a docs repository ([`connectors/libraries.py`](../src/a5s/connectors/libraries.py)). Each document is read only as far as its own permissions allow, for everyone a run acts for, and never with a5s's own access. A scenario names them in its folder's `libraries.yaml`, which its release covers, so a library, where it is and how a5s reads it, needs the release approver's signature:

```yaml
libraries:
  policies:                                 # its tools: search_policies and read_policies
    title: HR policies
    about: HR's policies, such as travel and leave
    kind: sharepoint
    site: https://contoso.sharepoint.com/sites/HR   # each document's link starts here
    as_person: entra                        # read as each person, with the account they connect
  runbooks:
    title: Operations runbooks
    kind: confluence
    site: https://example.atlassian.net/wiki
    api: https://api.atlassian.com/ex/confluence/<cloud id>/wiki
    space: OPS
    as_person: atlassian
  procedures:
    title: Desk procedures
    kind: repository                        # a checkout the deployment keeps current
    site: https://github.com/example/desk-procedures/blob/main
    outside: false                          # its editors are trusted as the handbook's
    sandbox: libraries/procedures           # made-up documents, for the studio's sandbox
```

a5s offers two tools for each library: `search_<library>`, which finds documents by their words, and `read_<library>`, which reads one by the id a search gave. An agent's definition lists them as it lists any tool, and pins each by a hash that covers its library's declaration: where it is, how a5s reads it, whose permissions it reads it with, and whether its documents are content from outside. So moving a library, or trusting it, needs its agents pinned again too.

### Whose permissions decide

- **SharePoint and Confluence** are read as the people a run is for, in a run they asked for themselves, as for [a tool that acts as the person](#acting-as-the-person), each with the account they connected on their own page, `as_person` naming the system as `A5S_DELEGATION` does ([acting as the person](#acting-as-the-person)). So the system's own permissions decide what each may read, as they would for them. a5s searches as the first of them, and keeps only the documents each of the others may read there too, asking the system as each. A run for someone who hasn't connected hears how they do. A run for nobody, such as a schedule's, or one nobody asked for, such as an event's or a report's, reads none of a library, nor one for more than ten people, since a5s asks the system as each. The core doesn't start with a library read as the person in a system the deployment doesn't name.
- **A docs repository** is read from a checkout the deployment keeps current, such as with [git-sync](https://github.com/kubernetes/git-sync), in a folder by the library's name under `A5S_LIBRARY_ROOT`. The chart runs a git-sync beside the core for each repository its values name, over HTTPS, with read access in a Secret of the deployment's own ([`deploy/helm/libraries-example.yaml`](../deploy/helm/libraries-example.yaml)); with compose, mount a checkout the host keeps current on the gateway, read-only, at `/var/lib/a5s/libraries/<name>`. Each document names its readers in its front matter, as the handbook's do: `audience: everyone`, `people`, `teams`, `roles`, or `parts`, which the scenario's own directory decides. Everyone the run acts for must be among them, and a document that names none is read by nobody. Who may read each document a run reads is kept for the run, never shown to its agent, so the studio shows the run, its answer and its words only to those who may read every one; what's read as the person, in SharePoint, Confluence or a server acting as them, is theirs alone. a5s follows the checkout as git-sync moves it to each new revision.

A document is a library's only if its link is within the library's `site`, or, in Confluence, in its space. A search asks the system for words alone: no system's query syntax gets through, so a search can't reach beyond its library. An agent may link people to a library's documents, within its `site`, and nowhere else.

### What a document says

Whatever a document says is source material, never an instruction. Nobody approved it as a release's handbook is approved, so a library's documents are content from outside unless its release says its editors are trusted as the handbook's, `outside: false`. Then:

- A search shows the agent each document's title, link and when it last changed, never a line of one. A title and a link are written outside the release too, so the run is marked once it has them, as for any content from outside.
- Reading one gives the agent the form a5s's [extractor](architecture.md) fills from it, by default the date it says it takes effect and whether it says it's a draft, with the document's number. The agent asks a5s's reader about it with `ask_about`, so its definition gives it `context.documents`, and its run is marked, as for any content from outside: it never acts on its own, and what it drafts says it drew on outside content. A library's `extract` names its own form, in the extractor's types.

A trusted library's search shows a few lines of each document around the words it found, and a read gives the agent its text, the first 12,000 characters of it, as the handbook's.

From SharePoint, a5s reads text, Markdown, HTML and PDFs as they are, and Office documents as Graph converts them to PDFs, each fetched from where Graph keeps it, with no one's token sent there, ten megabytes at most. From Confluence, it reads a page's storage format as text: through the second version of its API on Atlassian's cloud, and the first in a Data Center (`edition: data-center`). a5s keeps no cookie either system sets, so a session one person's request opens never goes with another's: each is theirs by their own token alone.

In the studio's sandbox, a library reads its `sandbox` folder in the scenario, of made-up documents that name their readers as a docs repository's do, with no one's token; one without a stand-in isn't read there. On their own page, people see which libraries agents read as them, beside each system they may connect.

Tested against a SharePoint and a Confluence of the test's own, which answer each person by whose token their call carries, a docs repository's checkout as git-sync keeps one, and end to end through the core, where a run reads SharePoint as the person through a5s's reader, and is marked (`tests/test_libraries.py`).

### Not yet

- SharePoint's own pages, whose words are in web parts rather than files.
- A docs repository read as the person, by the forge's own permissions, rather than by its documents' readers.
- Searching by meaning, beside words.


## Mailboxes

Much of a team's work arrives by email. A scenario may name the shared mailboxes in Microsoft 365 it arrives in, for its agents to read, and to leave replies in for the team to send ([`connectors/mailboxes.py`](../src/a5s/connectors/mailboxes.py)). It names them in its folder's `mailboxes.yaml`, which its release covers, so a mailbox, and whom an agent may read it for, needs the release approver's signature:

```yaml
mailboxes:
  requests:                                 # its tools search_requests, read_requests, draft_requests
    address: requests@contoso.example       # the shared mailbox
    title: Finance requests
    about: customers' questions about their invoices
    readers: [team:finance]                 # whom an agent may read it for, as `serves` names them
    drafts: true                            # agents may leave a reply among its drafts
    extract: {record: key, amount: amount, asks: "choice:refund|copy|date|other"}
    sandbox: mailboxes/requests             # made-up messages, a YAML file each, for the sandbox
```

a5s offers `search_<mailbox>`, which finds messages by their words, `read_<mailbox>`, which reads one, and, where `drafts` is true, `draft_<mailbox>`. An agent's definition lists them as it lists any tool, and pins each by a hash that covers the mailbox's declaration: where it is, whom it's read for, whether agents draft there, and the form its messages are read through.

### How a5s reads them

The core reads each mailbox through Microsoft Graph with the deployment's own app, in the tenant `A5S_MAIL_TENANT` names, as `A5S_MAIL_CLIENT_ID`, with its secret in `A5S_MAIL_CLIENT_SECRET`, which the core alone holds ([configuration](configuration.md)). The app is granted `Mail.Read`, and `Mail.ReadWrite` where agents draft, and Exchange's application access policy keeps it to the mailboxes it's given, so it reads those alone. The core doesn't start with a mailbox named and no app to read it with, and only the core reads one: in a5s's other parts, a mailbox's tools refuse, and the channels app, built from the same scenario, starts without the app's secret.

Whoever a run reads a mailbox for must be among its `readers`: people, teams and roles, as the directory decides. For a run for nobody, such as one a schedule starts, everyone its instance serves must be: what it finds may reach them. The app reads it, never anyone's own account, so nobody is acted as.

A mailbox's new mail goes only to an instance whose people all read the mailbox, so finance's mail never goes to operations' instance of the same agent. The run it starts sees only the records every reader may see, since its draft waits where they all read it. What a5s found in a mailbox, the studio shows to its readers alone, on a run's page, the feedback page, shadows and cases kept from runs.

a5s names each message by a key of its own, such as `M-3f2a9c0d41b7e8a6`, never by the mailbox's id for it, and keeps each key beside Graph's id, never a message's words. A search asks Graph for words alone, as a library's does.

### What a message says

Everything a message says, its subject and its words, is content from outside. A search shows the agent when each message came and its subject, and marks the run, since a subject is written outside too. Whom a message came from, the agent gets as a [handle](architecture.md): its sender chose the address, and a5s alone keeps it. Reading one gives the agent the form a5s's [extractor](architecture.md) fills from it, by default the record it names, an amount, a date it gives and whether it says it's urgent, or the mailbox's own `extract`, with the message's number, and the agent asks a5s's reader about it with `ask_about`. Its run is marked, as for any content from outside: it never acts on its own, and what it drafts says it drew on outside content.

### New mail starts runs

At each of the core's sweeps of events, at most once a minute for each mailbox, a5s asks Graph what's come into the inbox since it last asked, and keeps each new message as the mailbox's event, `mail-received`, from the system named as the mailbox is. An agent whose release takes it works on it at once, as on any system's [events](architecture.md): in a topic of its own, for nobody, on the mailbox's own day of budget, its task naming the message by its key alone. The first time, a5s notes where the inbox stands, so mail already there starts nothing. A mailbox Graph doesn't answer for is asked again at the next sweep, and one core asks at a time.

Every new message is kept as its event once, though a search found it first. Past 1,000 of a mailbox's events waiting, as a system is told to wait past them, the rest wait in the inbox, and a look takes 30 seconds at most, so a slow Graph holds up the sweep's other work no longer: a5s reads on from where it stopped, at the next sweep. A run whose model didn't answer, and which wrote, changed and sent nothing, leaves its message to be tried again half an hour later, for two days at most, as any event that can't be worked on now.

```yaml
events:                                     # in the agent's definition
  - source: requests
    type: mail-received
    task: Read the new message, find its record, and leave a reply among the mailbox's drafts.
```

### Replies wait for a person

a5s sends no mail. `draft_<mailbox>` leaves a reply to a message among the mailbox's drafts, for someone of the team to read, change and send, or not: a5s writes nothing else there. A draft changes no record and sends nothing, so it waits for no decider, and an instance that reads only leaves none. Its words are the agent's outgoing text, cleaned as any is, and nothing else: a5s's notes on them, such as a date the agent gave itself, go to the mailbox's readers in their digests, in the language each reads, never into what a customer would read. a5s puts no value a [handle](architecture.md) stands for in a draft, such as another customer's address: the agent is told to write without it, and the team adds what's needed. A draft is addressed to whom the message came from, never to a Reply-To the message names, and a message whose sender a5s can't tell gets none. The ledger keeps each draft by hash and length.

In the studio's sandbox, a mailbox reads its `sandbox` folder of made-up messages, each with `from`, `received`, `subject` and `text`, and a draft goes nowhere; one without a stand-in has its tools offered there, and each call refused.

Tested against an Exchange of the test's own, which answers the deployment's app alone and records what a5s asks of it: new mail starting a run that reads it through a5s's reader and leaves a draft, sending nothing, and a mailbox read for its readers alone, its searches by words alone. Round 15's tests add the rest: mail going only to an instance whose people read it, its run seeing what every reader may, a search that swallows no mail, what was found shown to readers alone, notes to the readers' digests, no handle's value in a draft, a run its model failed tried again, a flood waiting in the inbox, and a look of bounded length (`tests/test_mailboxes.py`).

### Not yet

- Attachments: a5s says a message has some, and reads none.
- Mailboxes read as the person, each in their own mailbox with their own account.
- Mail outside Microsoft 365, through IMAP.
- Threads: a message is read alone, never with the replies before it.
