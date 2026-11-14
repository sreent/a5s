# Using a5s today

**What this is:** The current user and operator interface, with synthetic records and a scripted demo model. The pages are real a5s pages; the model's answers here demonstrate the journey, not a live-model evaluation. No real people, credentials or business records appear.

## For a person asking an agent for help

### 1. Sign in

The web chat uses the organisation's identity provider through OpenID Connect. a5s checks who the person is and which agents serve them. In development, without an identity provider, the local channel can name a person explicitly instead.

![a5s's sign-in page at the identity provider](images/a5s-sign-in.png)

### 2. Have a conversation

The person chooses an agent and writes to it. Here Ana asks about `Q-1001`, and the assistant answers from the synthetic record. Each person has a conversation with the agent, not one shared with every other user. Tools and records stay within the run's permissions.

![Ana asking the assistant about a record](images/a5s-chat.png)

The same agents can work through Matrix or Teams where the deployment enables them. The command line and web chat use the local channel.

### 3. Ask for longer work, then confirm it

For work that needs more than one run, the agent offers a durable task and asks before starting it. Ana's answer in a later message confirms it; merely receiving the offer does not start work.

![The assistant offering task T-1 before starting it](images/a5s-task-confirmation.png)

a5s then works on the task in bounded runs of its own. A fresh worker resumes from the saved plan and checkpoint after a restart, rather than depending on a process staying alive.

### 4. See progress, results and controls

At `/tasks/`, the person sees their own tasks: each task's agent, status, plan, partial findings, result, deadline and tokens spent. Active tasks can be cancelled. Tasks that repeat appear separately, and stopping one does not cancel its already-running task.

![Ana's completed task with its plan, result and token use](images/a5s-task-complete.png)

To answer a task that needs its owner, the person returns to their chat with the agent. Today the page is a separate route, without a prominent link from the chat, and later progress needs a refresh rather than appearing automatically.

## For the person who runs an agent

The studio at `/studio/` is currently **read-only**: a catalogue, a dashboard for each instance, and a page for each run. It shows only what the signed-in person may see.

### The catalogue

Each agent shows its release, model, autonomy levels, owners, tools and what those tools read or write, and the instances that run it. An instance shows its status, parts, audience and the people who run it.

![The studio's catalogue of an agent, its tools and its instance](images/a5s-studio-catalogue.png)

### The instance's dashboard and runs

An owner or another authorised person can choose an instance and period to see model usage, run outcomes, obligations, reminders, held changes, graded samples, denials and reports. Each run can show its trigger, records read and each tool call's policy decision. Conversation text is not shown.

![An instance's dashboard and recent run](images/a5s-studio-dashboard.png)

The command line, Python client and core API expose the same operational model to code and CI, not just to the page. Operators' aggregate metrics can also go to the organisation's monitoring, without personal data.

## For the person building and deploying an agent

Today that path is deliberately code-led:

1. Create the agent's folder: `agent.yaml`, `AGENTS.md`, skills and test cases.
2. Choose existing reviewed tools, connectors and MCP tools; pin their schemas in `tools.lock`.
3. Run the agent's tests with synthetic equivalents and, where the release requires it, real models.
4. Open a pull request and let CI run.
5. Have the people the release needs sign its manifest with `a5s release`.
6. Approve signed settings for each instance: its audience, parts, permissions, owners and budgets.
7. Deploy the approved release through the existing container or Helm path.
8. Watch it in the studio, and suspend or resume it through the existing authorised controls.

The settings app and the approval, decision, grading, notebook and officer pages support that path. The studio does not hold signing keys or publish around them.

## What is not here yet

The studio does not yet create or edit an agent visually, run a sandbox test pane, or publish an agent from the page. Those are the next authoring steps in [the studio plan](studio.md#build-in-order), not capabilities claimed by the screens above.

The present journey is therefore:

- **A user:** sign in → converse → confirm longer work → inspect or cancel it.
- **An operator:** catalogue → instance dashboard → run detail.
- **A developer:** code and tests → PR and CI → signed release → approved settings → deployment → studio monitoring.

[Testing a5s](testing.md) has the commands for each test layer, what each proves, and how to read failures and scorecards.
