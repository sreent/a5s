# Adding a tool

For the engineers who give a scenario's agents a tool, and the authors who choose among them. A tool is one thing an agent can do in a system: look up a ticket, match an invoice, lock a device. An agent can do nothing else. It reads only what its tools return and changes only what they change, as its release pins them, after a5s's checks.

## Where a tool comes from

- **A system's MCP server**, declared in the scenario's `mcp.yaml` ([connecting a system](connecting.md)). Most tools should come this way: the system's own server does the work, and a5s checks, before each call, that it's still the tool declared.
- **The scenario's own code**, a `Tool` among those its `tools()` returns, for what code decides, such as procure-to-pay's invoice match ([`src/a5s/procure_to_pay.py`](../../src/a5s/procure_to_pay.py)) or master data's checks of a change request ([`src/a5s/master_data.py`](../../src/a5s/master_data.py)).
- **a5s's own**, which an agent may be given beside them, such as `offer_task` and `confirm_task` for a task, `hand_over` for handing a conversation to a person, and `ask_agent` for asking another agent.

## Say what it does

A tool says what it does, in its declaration or its `Tool`, and a5s governs it by that, never by its name:

| It says | With | What a5s does with it |
| --- | --- | --- |
| What it's for | `description` | The model reads these words, never a server's own. |
| What it takes | `arguments` (a `Tool`'s schema), as JSON Schema | A call must fit the whole of it, and nothing else is sent. |
| What an agent may see of its answer | `returns`, for a server's tool | Every other field is dropped, so nothing a server adds reaches an agent unread. |
| Which record a call is about, and each record it returns | `record_arg`, `record_field` | Need-to-know checks each against whom the run is for, and withholds what they may not see. |
| Whether it changes anything, or may destroy what it changes | `writes`, `destructive` | A tool that lets an agent do more than it could needs the release approver's signature. |
| The change it is | `action`, such as `lock-device` | a5s holds the change for the decider of the record's part, unless the agent may act on its own there. |
| How the change is undone | `undo: {tool, args, hours}` | People can [undo](glossary.md#undo) it, with that tool, for 24 hours unless it says, 168 at most. |
| That asking again does it once | `idempotent` | a5s sends a key with each call, so the system can make it once. |
| What came from outside the organisation | `outside`, with the form a5s's reader fills from it, `extract` | The model gets the form's answers, never the words, and the run is marked. |
| Sensitive values | `handles` | The model gets a handle in each one's place, never the value. |

The [connectors reference](../connectors.md#declaring-them) gives the rest, such as `sends_outside`, `text_fields` and `made`.

## What a server says of its tools

A tool on an MCP server may say of itself, in its annotations, much of what a5s's flags say. a5s takes them as hints, never as permission, and checks them against the declaration before each call: one that says more than the declaration, outright, stops the call until a release declares the tool again. MCP's defaults for them never count.

| The server says | a5s's flag | Stopped when |
| --- | --- | --- |
| `readOnlyHint: false`, that it changes things | `writes`, `action` or `destructive` | it's declared as only reading |
| `destructiveHint: true`, that it may destroy what it changes | `destructive` | it isn't declared destructive |
| `idempotentHint: false`, that asking again does it again | `idempotent` | it's declared as doing it once |
| `openWorldHint: true`, that it reaches outside the organisation | `outside` or `sends_outside` | it's declared as neither reading outside content nor sending outside |

A declaration may say more than its server, never less.

## A tool in the scenario's code

A `Tool` takes its name, what it's for, its schema and the function that answers each call, then the same flags as a declaration. Procure-to-pay's match, which reads and changes nothing:

```python
"match_invoice": Tool(
    "match_invoice", "Match an invoice with its purchase order and what the warehouse "
    "received, by code: whether it matches, and what's wrong if it doesn't.",
    invoice, matching, record_arg="key"),
```

Test it as the scenario's own tests do, each case through the core, such as the match's in [`tests/test_procure_to_pay.py`](../../tests/test_procure_to_pay.py).

## Give it to an agent

1. **List it** in the agent's `agent.yaml`, under `tools`, in the group it belongs to, such as `records` or `changes`.
2. **Pin it** with `a5s pin <agent>`, which writes its hash into the agent's `tools.lock`. The hash covers what it's for, its schema and its flags, and, for a server's tool, its name there and the fields a5s passes on. A new agent made from a template has its tools pinned as it's made, with `a5s agent new`.
3. **Release it.** A tool that changes is a new release of each agent that uses it: pin it again, and its signers sign it ([signing a release](approving.md#sign-a-release)).

In the studio, a draft's **Design** offers each of the scenario's tools in its palette, said by what it reads, writes or changes, and each one you give the draft says what follows from it, such as who must now sign its release ([building an agent](building.md#shape-it)).
