# Connecting a system

For the engineers who connect an organisation's systems to a5s, and the authors whose agents use them. a5s reaches a system through its [MCP](https://modelcontextprotocol.io) server, the open protocol many systems now offer their tools through, or, for what code of the scenario's own decides, through that code ([adding a tool](tools.md)). Either way, nothing of a system's reaches an agent until a scenario declares it, in a5s's words, and a signed release approves the declaration. This page is the way through, with the service desk's ITSM as its example; the [connectors reference](../connectors.md) says exactly what a5s checks.

## Before you start

- **Find its server.** Many vendors list theirs in the [MCP Registry](https://modelcontextprotocol.io/registry/about), with the address it answers at. a5s speaks MCP over Streamable HTTP to a server that runs as a service: not yet one run as a local process.
- **Decide whose access it uses.** a5s's own account in the system, with a token the deployment keeps, or each person's own, so the system's rules decide what each person sees and does there ([acting as the person](../connectors.md#acting-as-the-person)).
- **Have a stand-in for the sandbox.** The studio's sandbox never calls the real system: a stand-in answers there, on made-up records. The scenarios' own are in [`deploy/systems/`](../../deploy/systems/), such as the desk's ITSM, [`itsm.py`](../../deploy/systems/itsm.py).

## Declare the server

In the scenario's folder, `mcp.yaml` names each server: where it answers, the variable that holds its token, and its stand-in.

```yaml
servers:
  itsm:
    url: https://itsm.example/mcp           # its Streamable HTTP endpoint
    token_env: A5S_MCP_ITSM_TOKEN           # the variable that holds a5s's token there
    sandbox: http://127.0.0.1:9301/mcp      # its stand-in, for the studio's sandbox
```

The token's variable is named for its server, `A5S_MCP_<SERVER>_TOKEN`, and only that server is sent it. On a cluster, the chart's `tokens.mcp` names each server whose token the core gets ([deploy/helm](../../deploy/helm/README.md)). A token never goes in `mcp.yaml`, which is in git.

## Declare each tool, in a5s's words

Start from a draft: `a5s mcp declare <url> --server <name>` asks the server for its tools and prints a draft of their declaration, or writes it with `--out` to a new file of its own, never the scenario's `mcp.yaml`. `--tool` drafts only the tools you name. The draft takes what the server says as a start, never as a5s's word: each description is the server's, marked for you to put in a5s's words; the flags are at least what its hints say, and a tool that says nothing of itself is drafted as writing; and it names none of the fields a5s passes on, so a5s refuses it until you've chosen them.

Then, under `tools`, each of the server's tools an agent may use: its name in a5s and on the server, what it's for, in words the model reads, what it takes, which fields of its answer a5s passes on, and what it does, as [adding a tool](tools.md) says. A tool the declaration leaves out is never offered, whatever the server offers. The desk's ITSM, in [`scenarios/service-desk/mcp.yaml`](../../scenarios/service-desk/mcp.yaml), gives four, such as:

```yaml
tools:
  get_record:
    server: itsm
    calls: get_ticket
    description: Get one ITSM ticket by its key, such as INC0000001.
    arguments: {type: object, required: [key], properties: {key: {type: string}}}
    returns: [key, part, title, status, requester, assignee, contact, opened, due, link]
    record_arg: key
    record_field: key
    handles: [contact]
```

## Give its tools to an agent, and release them

1. **List them** in the agent's `agent.yaml`, under `tools`, and **pin them** with `a5s pin <agent>`, which writes each one's hash into its `tools.lock`. In the studio, a draft's **Design** offers them in its palette once the scenario declares them.
2. **Try them in the sandbox**, where the stand-in answers, and keep tries as test cases ([building an agent](building.md#try-it-in-the-sandbox)).
3. **Release them.** A release covers the scenario's folder, its `mcp.yaml` with it, so a new server or tool needs the release approver's signature, as a change to the scenario's code does ([signing a release](approving.md#sign-a-release)).

Once it's released, a5s asks each server for its tools again every five minutes, and refuses any whose arguments, or what it says of itself, no longer fit its declaration, saying why, until a release declares it again ([what a5s checks](../connectors.md#what-a5s-checks)).

## The desk's ITSM, end to end

The service desk scenario connects three systems this way, each with a made-up server on its own data: its ITSM, its identity provider's self-service and its device management. To follow its ITSM through:

| Step | Where |
| --- | --- |
| The server, a stand-in on made-up tickets | [`deploy/systems/itsm.py`](../../deploy/systems/itsm.py), on the scenario's [`data.yaml`](../../scenarios/service-desk/data.yaml) |
| Its declaration, in a5s's words | [`scenarios/service-desk/mcp.yaml`](../../scenarios/service-desk/mcp.yaml) |
| The agent that uses it, its tools listed and pinned | [`agent.yaml`](../../scenarios/service-desk/agents/desk-assistant/agent.yaml) and [`tools.lock`](../../scenarios/service-desk/agents/desk-assistant/tools.lock) |
| Its tests, through the core | [`tests/test_service_desk.py`](../../tests/test_service_desk.py), and a reply on a ticket held for its service area's decider, [`tests/test_desk_replies.py`](../../tests/test_desk_replies.py) |
| The scenario, as its people read it | [the IT service desk](../../scenarios/it-service-desk.md) |

## Not yet

a5s doesn't yet read a server's resources or prompts, reach a server run as a local process, or speak MCP's stateless envelope of 2026-07-28 ([not yet](../connectors.md#not-yet)).
