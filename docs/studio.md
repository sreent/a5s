# The studio: build, try, publish, run and watch agents

**Status:** Proposed, to confirm before it's built · **Under:** [Agent model](agent-model.md)

Today, people build and run a5s's agents in code: a folder for each agent, `a5s pin`, a release signed with `a5s release`, settings signed with `a5s sign`, and `a5s status` and `a5s measures` to see how they do. A few pages help: the settings app, and the pages for approving, deciding, grading, the notebook and the officer. The studio gives the people who make and run agents what a maker studio such as Microsoft Copilot Studio gives them: one place to create an agent, try it, publish it, choose where it runs, and watch how it does.

It doesn't add a second way to change a5s. Everything the studio does is a change code can make too: a commit to the agents' folder, a release signed by the same people, a settings version signed by the same owners. Everything it reads and writes goes through the core's documented API, which code, the command line and CI use as well.

## What it keeps

- **The studio proposes, and people sign.** What it writes is a pull request, a draft release or a draft settings version, never a change in force. Nobody gets a right through the studio that they wouldn't have at the command line.
- **The studio and the code show the same thing.** An agent is a folder in git, a release is a manifest, settings are a signed version. Someone can start an agent in the studio and finish it in an editor, or the other way round.
- **It shows people only what they may see.** Its pages come from the measures, the status, the ledger and the releases, under the same need-to-know as today. An instance's runs are its owner's, its deputy's and its parts' owners' to see. What people said to an agent appears only by its hash, as [data protection](data-protection.md) requires.

## How it maps

| In a maker studio | In a5s |
| --- | --- |
| An agent, its instructions and topics | An agent's definition: `agent.yaml`, `AGENTS.md` and its skills |
| Knowledge | The scenario's knowledge, such as a Markdown vault, through its tools |
| Actions and connectors | The scenario's tools, written in code, reviewed, and pinned in each release |
| Triggers and autonomous runs | Triggers, schedules, reports and obligations, in the definition |
| The test pane | A chat with a draft agent against the scenario's fakes, and its test cases on real models |
| Publishing | A release, signed by the people the change needs |
| Channels | Teams, Matrix and the web chat, as each deployment configures them |
| Environments and solutions | Deployments, each approving its own releases, and the agents' repository |
| Analytics | The measures, the status and the ledger |
| Admin and governance | Signed settings: instances, whom they serve, their parts, levels and owners |

## Decide first

| Decision | Proposed |
| --- | --- |
| What comes first | Watching, then making, then running. A read-only catalogue and dashboards can't break anything, and they show what there is. Then authoring with a test pane, publishing as pull requests. Then instances, by folding the settings app in. |
| Where it lives | Pages of the channels app, as the settings app is, signed in through the organisation's identity provider, with the core's API behind them. No new service. |
| What publishing makes | A branch and a pull request to the agents' repository, where CI runs the agent's tests and its suite on real models, and the people the release needs sign it, as now. A deployment with no git host gets a draft release to sign instead. |
| Who may author | An agent's owner, and engineers they name, for the agents they own. A new agent needs the release approver, as its first release does today. |
| What the test pane runs on | A fake model by default. A real model only with synthetic data, the scenario's fakes and a budget of its own: never the deployment's records, channels or budgets. |
| What stays in code | The trusted core, the policies, the scenario's code and tools, and which models are approved. The studio shows them, and changes none of them. |
| Templates | The reference assistant and watcher, and each scenario's agents, such as the [master data](../scenarios/master-data.md) assistant and watcher. |

## Build, in order

Each step ends with something running and its tests passing.

1. **The catalogue and the dashboards, read only.**
   - The catalogue: each agent's definition, release and owner; its tools, with what each reads, writes or changes; its knowledge, skills, triggers, schedules, reports, budgets and channels; and its instances, with whom they serve, their parts and levels.
   - A dashboard for each agent and instance, over a period: runs and how they ended, tokens and cost with the share cached, denials and why, held changes and their decisions, grades and the cap, chases and escalations, reports sent, and who came back. It draws on the same figures as `a5s measures` and `a5s status`.
   - A page for each run: what started it, whom it acted for, each tool call with the policy's decision, and its ledger entries, as `a5s ledger` shows them.
   - The API behind them, under the core's management API, and the command line on top of it: `a5s agents`, `a5s agents show <agent>`, and `a5s measures` for one agent or instance.
2. **Authoring and the test pane.**
   - Create an agent from a template, or copy one. Edit what it works for and does, its instructions and skills. Pick tools from the scenario's tools, each with its risk shown. Set its triggers, schedules, reports, obligations, preferences, channels, context and budgets. The definition's own checks run as people type: known tools, pinned schemas, budgets that fit.
   - Test cases: add one from a test conversation, with what an answer must and mustn't say, in the same form as each agent's test suite.
   - The test pane: chat with the draft against the scenario's fakes, and see each tool call, the policy's decisions and the context the run was given. Run its test cases on a real model, with synthetic data.
   - Publish: the studio shows who must sign the release, from what changed, before anyone publishes. It opens a pull request with the agent's folder, its pinned tools and its test cases, and CI runs them.
3. **Instances.**
   - The settings app, folded in: instances, whom they serve, their parts and levels, owners and deputies, limits, and whom they may ask. Each change is a new settings version, which the owners of its parts sign, as now.
   - Suspend or resume an instance from its page, signed in afresh, as a5s asks today.
   - Held changes, grading, caps and the notebook: the existing pages, reached from each instance.
4. **Code and APIs, documented.**
   - One OpenAPI document for the core's management API, a Python client, and the command line on top of it.
   - `a5s agent new <template>`, which makes the same folder the studio does.
   - Examples for CI: test and publish an agent from its repository, and promote a release from one deployment to the next.

## Done means

An agent's owner creates an agent from a template in the studio, tries it in the test pane, and publishes it as a pull request. CI passes, the people the release needs sign it, and the owners of its parts approve an instance of it. An engineer does the same from an editor, git and the command line, and gets the same result. Both watch it on a dashboard that shows the same figures `a5s measures` prints. The studio does nothing code can't, and skips no signature.

## Tests

- What the studio publishes is the same folder, pins and manifest that `a5s pin` and `a5s release` make, byte for byte.
- Someone who isn't an agent's owner can't publish it. A new agent's release still needs the release approver, and a settings change each of its parts' owners.
- The test pane never reaches the deployment's records, real channels or budgets, and a real model in it sees only synthetic data.
- A dashboard shows an instance's runs only to the people who may see them, and what was said only by its hash.
- Every action in the studio is in the ledger, as the command line's are.
- Browser tests for the catalogue, the dashboards, authoring and the test pane, as the settings app has.

## What this doesn't change

The studio holds no authority of its own: it proposes, and people sign. There's no low-code tool builder: tools stay the scenario's code, reviewed and pinned in each release. Nobody edits the trusted core, the policies or which models are approved from a page. Agents kept in code stay first class, since the studio reads and writes the same files.
