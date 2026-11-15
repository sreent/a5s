# Connectors

**Status:** MCP servers' tools are built ([below](#mcp-servers)), beside the read-only REST transport and the GitHub adapter · **Under:** [Architecture](architecture.md)

A scenario's tools reach the systems its records are in. A scenario writes most of them in its own code, against the [contract](architecture.md), and a5s gives it two ways to reach a system without writing a client of its own: a read-only REST transport, with a GitHub adapter on it ([architecture](architecture.md)), and the tools of MCP servers, which the rest of this page is about. Every tool, whichever way it's made, is offered to an agent only if its definition lists it, pinned by its hash, and every call goes through the core's checks: the policy, the parts and need-to-know, held changes, the extractor for content from outside, handles for sensitive values, and the ledger.

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

A tool takes the same flags as any of the scenario's: whether it `reads`, `writes` or is `destructive`, whether it `sends_outside`, whether it's `idempotent`, the `record_arg` that names the record a call is about, the `action` a change is, which a5s holds for the record's part to decide below level 2, the `text_fields` that are outgoing text, the `handles` that hold sensitive values, and the `outside` fields that hold content from outside the organisation, with the form a5s's extractor fills from them, `extract`. `returns` is required: it names every field a5s passes on, at any depth, and drops the rest, so a field a server adds, or renames, never reaches an agent unread. A field the tool names a record by, a handle or outside content is among them. The file names each key once, as `agent.yaml` does.

Each tool's name is its own: one the scenario or a5s has already stops a part as it starts. An agent lists the tool among its tools and pins it with `a5s pin`, as any other, by a hash that covers the server's name for the tool and the fields a5s passes on, besides all a scenario's tool's hash covers. The release covers `mcp.yaml`, as all of a scenario's folder, so a change to it needs the release's signatures, as a change to the scenario's code does.

### What a5s checks

Before each call, a5s checks the server still offers the tool as declared, from its list of tools, which it asks for again every five minutes:

- **The arguments it takes, by their shape.** The server's schema and the declaration's must constrain the same arguments in the same way. The words that only describe them may differ, since the model reads a5s's: titles, descriptions, examples and comments. Defaults count, since a default changes what a call does.
- **What it says of itself.** A server's annotations are hints, so a5s never takes them as permission. But one that says more than the declaration does, outright, stops the call: that it changes things, for a tool declared as reading only; that it may destroy what it changes, for one not declared destructive; that asking again does it again, for one declared idempotent; or that it reaches outside the organisation, for one declared neither to read outside content nor to send outside. MCP's defaults for the hints never count.

A server that changed either way is refused, saying why, until a release declares the tool again. What the tool returns comes back as JSON: its structured content if it has some, or its text, parsed as JSON where it is JSON, with only the fields declared. For a tool that names its records, each object in a list names its record by the field, outside any record, or a5s passes none of it on: the core's need-to-know then checks every record, and withholds those the run may not see. What a5s can't pass on as JSON, such as an image, it leaves out, and says it did. A tool's error comes back as its words, cut to 300 characters, except for a tool that reads outside content, whose error could be the content itself.

### How a5s reaches them

a5s speaks MCP's Streamable HTTP, through the `initialize` handshake, in the versions from 2025-03-26 to 2025-11-25. It calls a server over HTTPS, or HTTP on the same machine, follows no redirect, reads an answer of 1 MB at most, and sends the bearer token in the server's `token_env`, an `A5S_MCP_<SERVER>_TOKEN` variable, only to its own server. It begins a session again once if the server ends a5s's. Of a5s's own, a call sends only its key, for a change or an idempotent tool, in its `_meta`, as `a5s/key`, so a server can make a change once for each key: never whom the run acts for, nor the run itself.

In the studio's sandbox, a server's `sandbox` stand-in answers instead, and no token goes there: the sandbox's people and records are made up. A server with no stand-in has its tools offered there, so a draft checks as it will run, but each call is refused.

### Not yet

- MCP's stateless envelope of 2026-07-28, which servers may offer beside the handshake.
- A server's resources and prompts, its requests to the client, such as for sampling or to ask the person something, and servers run as a local process, over standard input and output.
- `a5s mcp declare <url>`, to write a declaration's first draft from a server's list of tools, for its author to put in a5s's words.

Tested against the MCP SDK's own server, over both of Streamable HTTP's ways of answering, and end to end through the core (`tests/test_mcp.py`). The service desk scenario takes its ITSM's tools this way, a reply on a ticket held for its service area's decider among them, and its identity provider's self-service, each from a made-up server on its synthetic data ([`scenarios/service-desk/mcp.yaml`](../scenarios/service-desk/mcp.yaml), [`deploy/desk/itsm.py`](../deploy/desk/itsm.py)), so its suite, its containers and its walk-through run on MCP.
