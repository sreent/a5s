# The studio: build, try, publish, run and watch agents

**Status:** Step 1 is built: the catalogue, the dashboards and each run's page, read only, with their API, a Python client, the command line, and operators' figures for the organisation's monitoring ([progress](#progress)). Authoring waits for the pilot's evidence · **Under:** [Agent model](agent-model.md)

Today, people build and run a5s's agents in code: a folder for each agent, `a5s pin`, a release signed with `a5s release`, settings signed with `a5s sign`, and `a5s status` and `a5s measures` to see how they do. A few pages help: the settings app, and the pages for approving, deciding, grading, the notebook and the officer. The studio gives the people who make and run agents what a maker studio such as Microsoft Copilot Studio gives them: one place to create an agent, try it, publish it, choose where it runs, and watch how it does.

It doesn't add a second way to change a5s. Everything the studio does is a change code can make too: a commit to the agents' folder, a release signed by the same people, a settings version signed by the same owners. The API comes first, and the studio is one client of it, as code, the command line and CI are.

## Progress

- [`core/studio.py`](../src/a5s/core/studio.py) works out what step 1 shows: each agent of the release with its tools and what each reads, writes or changes, and its instances; how an agent's or an instance's runs are doing, from the measures counted for those instances alone, with how runs ended, what was denied and why, and the reports sent; an instance's runs, a page at a time; and what one run did, with each tool call's decision and, for the team that runs a5s, its ledger entries. A run shows only to those who may see every record it handled: what its tools returned, what a5s's brief or a report told it, and what its trigger named, which a5s keeps with the run by key (`run_records`), for as long as the run.
- The core serves it to code, the command line and CI, behind the service token, under `/studio/`: `a5s agents`, `a5s agents show <agent>`, `a5s runs <instance>`, `a5s runs show <run>`, and `a5s measures --agent <agent>` or `--instance <instance>`.
- People see it on the channels app's page, `/studio/`, signed in as on the notebook's, through its own API under `/studio/api/`, from the same module. The chart lets only the worker and the scheduler reach the core, so the channels app reads the figures as its own role, which migration `0044_studio.sql` grants only the columns they count and each run's own record: never what people said, what a reminder, an obligation or a question is about, or a run's token.
- The studio's pages are a React app, in [`studio/`](../studio/), with React Flow for its maps. They take their structure from a maker studio such as Copilot Studio, an agent's overview with what starts it, its tools and what it knows, and their look from a workflow tool such as n8n: each agent's page opens on a map of what starts its runs, the agent, a5s's checks, which every call passes through, and its tools, coloured by what they do, changes first. Each instance has its figures, its runs by day, in each viewer's own time zone, split by how they ended, and its runs; and each run its path, on its agent's map: what started it, each tool it called through a5s's checks, how many times, and how many of those a5s refused, with what it didn't use faded, then its calls in order.
- Its packages are locked in `studio/package-lock.json`, and none runs a script of its own as it installs (`studio/.npmrc`). The image builds the pages in a Node stage of its own ([Dockerfile](../Dockerfile)) into the package, so they are the release's core, file by file, as its Python is, and the release's `build` part names what they were built from. The channels app serves them under the policy every page of a5s has: one script and one stylesheet of their own, nothing inline, and nothing from anywhere else. In a checkout, build them with `npm ci --prefix studio && npm run build --prefix studio`, on Node 20.19 or later, or without Node, as CI's tests do, with `docker build --target studio-built --output src/a5s/core/webchat/studio .`. Unbuilt, `/studio/` says how.
- Someone may watch an instance if they run it, as its owner or deputy, own its agent, own or decide for one of its parts, or approve instances. Of its runs, they see those whose every record they may see, and how many others there are.
- Both apps describe these endpoints in their OpenAPI documents, at `/openapi.json`.
- [`a5s.client`](../src/a5s/client.py) is the Python client for the core's API, by its service token, for the team's own jobs and CI, and the command line makes its calls through it. For example, a job that reads a week of each instance's figures:

  ```python
  from a5s.client import Client

  with Client.from_env() as core:  # A5S_GATEWAY_URL and A5S_SERVICE_TOKEN, as a5s finds them
      for agent in core.agents():
          for inst in agent["instances"]:
              figures = core.measures(days=7, instance=inst["id"])
  ```

- Operators' figures go to the organisation's monitoring as OpenTelemetry metrics ([`core/metrics.py`](../src/a5s/core/metrics.py)): the status's figures, each minute, to the endpoint the deployment names for its traces (`telemetry.endpoint` in the chart), such as a collector that passes them on to Prometheus or Azure Monitor. Each is counted by what it counts, such as an instance, a model, a tool, a trigger or an outcome, and never by a person or a record, nor with anything said. An instance's own figures go out only once it serves at least 5 people, since one that serves an executive alone would count their use of it; smaller ones go together, once together they serve as many. A collection reads the status once, within 5 seconds, and says first whether it could (`a5s.status.readable`), so a database that's down or hung still leaves the monitoring the 0 its runbook alerts on. The core gains no new way in: the gateway sends them out.
- The cap for each type of action stays on the grading page, where the core checks its seal.
- Step 2 has begun with its command line ([`authoring.py`](../src/a5s/authoring.py)): `a5s agent templates` lists the agents a new one may start from, the reference agents and each scenario's, saying which tools this scenario lacks for each; `a5s agent new <name> --from <template>` makes the new agent's folder from one, with its own id, a first release, its instructions, skills and test cases, and its tools pinned; and `a5s agent check` says what would stop an agent's folder from being released here: that it doesn't load as the core loads it, its budgets don't fit, its id isn't its folder's name, the scenario hasn't got a tool, a pin isn't the tool's schema now, or its model isn't approved. The studio's editor will run the same checks as people type.
- Drafts ([`core/drafts.py`](../src/a5s/core/drafts.py)): the studio keeps each draft of an agent for its author, its folder file by file, through the people's API under `/studio/api/drafts`. Someone starts one from a template, for a new agent, if they own an agent or are an engineer; or from an agent's folder as released, for a change to it, if they own it or the organisation names them its author, by the identity provider's group for `agent-author:<agent>`. Each time it's saved, a5s pins the tools it names that the scenario has, as `a5s pin` does, refuses files no agent's folder could hold, and says what would stop its release, by the checks `a5s agent check` makes. A draft is its author's alone, never in force, and gives nobody a right; the ledger records each one started and dropped, by whom. It's in its author's export, and goes when they leave or ask for what a5s keeps of them to be erased.

## What it keeps

- **The studio proposes, and people sign.** What it writes is a pull request, a draft release or a draft settings version, never a change in force. Nobody gets a right through the studio that they wouldn't have at the command line.
- **It holds no keys of its own.** It acts as the person signed in. It opens a pull request as them, through the git host's own sign-in, or gives them the branch to push. It holds no git token, no signing key and no way to write the settings store, so it's never an easier way round a5s than the command line.
- **The studio and the code show the same thing.** An agent is a folder in git, a release is a manifest, settings are a signed version. Someone can start an agent in the studio and finish it in an editor, or the other way round.
- **It shows people only what they may see.** Its pages come from the measures, the status, the ledger and the releases, under the same need-to-know as today. An instance's runs are its owner's, its deputy's and its parts' owners' to see, each only if they may see every record it handled. People's pages show nothing anyone said, not even by its hash, and whom a run acted for only once the data protection officer agrees (`A5S_STUDIO_NAMES`), as [data protection](data-protection.md) requires.

## Who builds what

The development team builds tools, connectors and MCP servers, in the scenario's code. Each is reviewed, and pinned in each release with what it reads, writes or changes. The studio shows them, and an agent's owner chooses from them, but nobody makes or changes a tool in the studio.

That's where most of a new use case's work is. In the [master data](../scenarios/master-data.md) scenario, the agents' definitions were about a tenth of it. The rest was the scenario's code: its rules, duplicate matching, routing, quality measures and who may see what, with their tests. It's also where the safety is. So beside the studio, the development team gets a starter kit for scenarios: a template scenario with the common patterns already wired, and its test bench. The patterns are records that are owed, held changes, a knowledge vault and a reader for outside content. Tools from an MCP server can be brought in the same way as any tool: wrapped in the scenario's code, reviewed, given their risk flags and pinned.

## How it maps

| In a maker studio | In a5s |
| --- | --- |
| An agent, its instructions and topics | An agent's definition: `agent.yaml`, `AGENTS.md` and its skills |
| Knowledge | The scenario's knowledge, such as a Markdown vault, through its tools |
| Actions, connectors and MCP servers | The scenario's tools, which the development team builds, reviews and pins in each release |
| Triggers and autonomous runs | Triggers, schedules, reports and obligations, in the definition |
| The test pane | A chat with a draft agent in a sandbox deployment, and its test cases on real models |
| Publishing | A release, signed by the people the change needs |
| Channels | Teams, Matrix and the web chat, as each deployment configures them |
| Environments and solutions | Deployments, each approving its own releases, and the agents' repository |
| Analytics | The measures, the status and the ledger |
| Admin and governance | Signed settings: instances, whom they serve, their parts, levels and owners |

## Decide first

| Decision | Proposed |
| --- | --- |
| What comes first | Watching, then making, then running. A read-only catalogue and dashboards can't weaken any control, and the pilot's agent and part owners need them: today what they'd want to see is behind the command line. So step 1 is built alongside the pilot. Authoring waits until the pilot shows owners want to change their agents themselves. |
| The API | First, not last. Each step ships its API, in one OpenAPI document, with a Python client and the command line on top, before its pages, so code and CI never wait for the studio. |
| Where it lives | Pages of the channels app, as the settings app is, signed in through the organisation's identity provider. No new service. |
| What the test pane runs in | A sandbox: a separate deployment of a5s, with the scenario's fakes, synthetic data and a budget of its own, as the tests run. A fake model by default, and a real model when asked. It can't reach the production deployment's records, channels or budgets, because it isn't that deployment, whatever a flag says. |
| What publishing makes | A pull request to the agents' repository, opened as the person publishing. CI runs the agent's tests and its suite on real models, and the people the release needs sign it, as now. A deployment with no git host gets a draft release to sign instead. |
| Who may author | An agent's owner, and engineers they name, for the agents they own. A new agent needs the release approver, as its first release does today. |
| What stays in code | The trusted core, the policies, the scenario's code with its tools, connectors and MCP servers, and which models are approved. The studio shows them, and changes none of them. |
| Where figures go | Operators' figures, with no personal data in them, may go to the organisation's own monitoring, such as Azure Monitor or Prometheus. What owners see stays in a5s, under its need-to-know: a business intelligence tool would show everyone everything. |
| Templates | The reference assistant and watcher, and each scenario's agents, such as the master data assistant and watcher. |

## Build, in order

Each step ends with something running and its tests passing, and ships its API before its pages.

1. **The catalogue and the dashboards, read only.**
   - The API: each agent and instance, its release and figures, and each run. The core's, behind the service token, for code, the command line and CI, and the channels app's, for the people who may see them, signed in, from the same module, each in its app's OpenAPI document. The command line on top of the core's: `a5s agents`, `a5s agents show <agent>`, `a5s runs`, and `a5s measures` for one agent or instance.
   - The catalogue: each agent's definition, release and owner; its tools, with what each reads, writes or changes; its knowledge, skills, triggers, schedules, reports, budgets and channels; and its instances, with whom they serve, their parts and levels.
   - A dashboard for each agent and instance, over a period: runs and how they ended, tokens and cost with the share cached, denials and why, held changes and their decisions, grades and the cap, chases and escalations, reports sent, and who came back. It shows the same figures as `a5s measures` and `a5s status`.
   - A page for each run: what started it, whom it acted for, each tool call with the policy's decision, and its ledger entries, as `a5s ledger` shows them.
2. **Authoring and the test pane.**
   - The API and the command line first: `a5s agent new <template>` makes an agent's folder from a template, and the checks a definition must pass run from the command line as from the page.
   - Create an agent from a template, or copy one. Edit what it works for and does, its instructions and skills. Pick tools from the scenario's tools, each with its risk shown. Set its triggers, schedules, reports, obligations, preferences, channels, context and budgets. The definition's own checks run as people type: known tools, pinned schemas, budgets that fit.
   - Test cases: add one from a test conversation, with what an answer must and mustn't say, in the same form as each agent's test suite.
   - The test pane, in the sandbox: chat with the draft against the scenario's fakes, and see each tool call, the policy's decisions and the context the run was given. Run its test cases on a real model, with synthetic data.
   - Publish: the studio shows who must sign the release, from what changed, before anyone publishes. It opens a pull request as the person publishing, with the agent's folder, its pinned tools and its test cases, and CI runs them. Examples for CI test and publish an agent from its repository, and promote a release from one deployment to the next.
3. **Instances.**
   - The settings app, folded in: instances, whom they serve, their parts and levels, owners and deputies, limits, and whom they may ask. Each change is a new settings version, which the owners of its parts sign, as now.
   - Suspend or resume an instance from its page, signed in afresh, as a5s asks today.
   - Held changes, grading, caps and the notebook: the existing pages, reached from each instance.

## Later, with evidence

- **Shadow runs.** People will want to try a draft on their real work, not on fakes. The safe way is for a draft release to answer live traffic beside the live one, sending nothing, under the same need-to-know, with its answers graded as samples are. That processes personal data, so it waits for the data protection officer's assessment, and for the pilot to show the sandbox isn't enough.

## Done means

An agent's owner creates an agent from a template in the studio, tries it in the sandbox's test pane, and publishes it as a pull request. CI passes, the people the release needs sign it, and the owners of its parts approve an instance of it. An engineer does the same from an editor, git and the command line, and gets the same result. Both watch it on a dashboard that shows the same figures `a5s measures` prints. The studio does nothing code can't, and skips no signature.

## Tests

- What the studio publishes is the same folder, pins and manifest that `a5s pin` and `a5s release` make, byte for byte.
- Everything a page does, the API and the command line do too, and the OpenAPI document describes it.
- The studio holds no git token, signing key or way to write the settings store: a pull request it opens is the person's own.
- Someone who isn't an agent's owner can't publish it. A new agent's release still needs the release approver, and a settings change each of its parts' owners.
- The sandbox has its own database, budget and channels, and the production deployment's records can't be reached from it.
- A dashboard shows an instance's runs only to the people who may see them, and nothing anyone said. Figures sent to the organisation's monitoring carry no personal data.
- Every action in the studio is in the ledger, as the command line's are.
- Browser tests for the catalogue, the dashboards, authoring and the test pane, as the settings app has.

## What this doesn't change

The studio holds no authority of its own: it proposes, and people sign. Tools, connectors and MCP servers stay the development team's: built in code, reviewed, and pinned in each release. Nobody edits the trusted core, the policies or which models are approved from a page. Agents kept in code stay first class, since the studio reads and writes the same files.
