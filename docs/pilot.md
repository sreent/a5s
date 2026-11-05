# Pilot

**Status:** Draft, for confirmation · **Under:** [Architecture](architecture.md)

Phases 1 to 3 are built, and tested against the sample scenario, which is a fake. Two things in [phase 1's Done means](phase-1.md#done-means) only real use can give: the suite passing in a cloud, and a baseline of the measures from the first users. The pilot gets both, with one team, in stages, each with what it shows before the next begins. What comes after phase 3 is chosen from what it shows, not before.

## Decide first

| Decision | Proposed |
| --- | --- |
| Which team | One team of 5 to 15 people whose work lives in one records system and falls due, such as a finance team's customer questions or a service desk's queue. Enough people for group chats, few enough to ask each of them what they think. [TBC: which] |
| Where | Azure, with Entra ID and Teams, as phase 1 decided, in the test tenant first. Google Cloud and AWS once Azure's first day is done. |
| Which model | One on the organisation's approved list for the class of the team's data, such as a model the organisation runs in its own subscription. DeepSeek and Qwen stay on synthetic data. [TBC: which] |
| The scenario | The team's records system through [the contract](architecture.md#the-scenario-contract): its people from the directory, its records and their obligations, and its settings, as the service desk was written in [round 5](critique.md#round-5-steps-3-to-6). Its tools only read, until stage 3. |
| Who holds the roles | The platform owner, a release approver outside the team that runs a5s, instance approvers, the part's owner, assurance, the data protection officer, and from stage 3, graders from outside the team. Each named before stage 2. [TBC: who] |
| How long | About 12 weeks: a week each for the first day and a shadow run, four for the baseline, and six for held changes, groups, asking and the notebook. |

## Stages

Each stage ends when what it shows is written down, here and in the phase it serves.

0. **The first day** (week 1).
   - The release: `main` under its rulesets, the regression suites' keys in the repository's secrets, and `v0.1.0` tagged once its live suites pass and the release approver approves it.
   - The four checks in [phase 1's first day](phase-1.md#progress), in the test tenant and Azure: signing in with Entra ID, Teams with its group chats, Azure's Postgres, locked storage and network policies, and what they sent kept as fixtures, so CI checks the real services' shapes from then on.
   - Shows: a5s's suite passes on Azure, the first half of phase 1's Done means.
1. **Shadow** (week 2).
   - The team that runs a5s works with the assistant and the watcher on the sample scenario, in Teams, for a week, with the [soak test](../deploy/soak.py) against the deployment beside them.
   - Each runbook is tried once: suspending and resuming an instance, a chat that won't take a message, a model that's down, and a release.
   - Shows: replies within the objective, nine in ten within two minutes, nothing lost, and what a run costs on the approved model, once its prices are in the approved list (`a5s measures`).
2. **One team, reading** (weeks 3 to 6).
   - The watcher at level 0, and the assistant at level 1 at most: they read, remind and chase, and people make the changes.
   - The data protection officer signs off the assessment before any of the team's data reaches a model.
   - Shows: the baseline, the second half of phase 1's Done means. Promises and reminders met on time, time from something falling due to it being done, people who come back, and cost per run, from `a5s measures` each week, beside what each person says in a short conversation at the end. Four weeks hold two fortnights but not two months, so who came back is over a fortnight here (`a5s measures --days 14`), and over a month from the end of stage 3.
3. **Held changes** (weeks 7 to 10).
   - One type of action the team does often, such as moving a due date, held for the part's owner to decide on the core's page.
   - Graders grade a sample each week. Level 2 only if samples earn it ([phase 2](phase-2.md)).
   - Shows: how long decisions take and how many are approved, how often the agent's changes are right (`a5s measures`), and graders' time, which they note, against its estimate of five hours a quarter.
4. **Groups, asking and the notebook** (weeks 11 and 12).
   - The team's own group chat with the assistant, the assistant asking the watcher, and a weekly schedule that notes what it learns from the records ([phase 3](phase-3.md)).
   - Shows: how often people mention it, what the watcher is asked and answers, and how many notes are kept, given to runs and let go (`a5s measures`).

## What stops it

Any of these suspends the instance first, which anyone with the role can do, and the stage waits until it's understood:

- something a5s should have stopped: a change it shouldn't have made, a message to the wrong person, or an answer or a note with what someone may not see;
- a finding the pilot's own round of the critique marks high, until it's fixed;
- cost per run more than twice the estimate for two weeks running;
- fewer than a third of the team coming back to an agent, over a fortnight in stage 2 and a month after, which says a5s isn't worth their time as built.

## What it decides

- **Phase 1's Done means,** with the suite on Azure and the baseline written into [phase 1](phase-1.md#done-means).
- **The starting values marked [TBC],** such as budgets, digest times and the reply objective, from what the team used ([starting values](starting-values.md)).
- **Phase 4,** from the critique's deferrals and what the pilot shows:
  - if agents keep few notes, or runs are rarely given them, notes from facts code works out from a5s's own records, such as which records keep coming up;
  - if group chats reach their limit of 20, or the team works in Teams channels, bigger rooms;
  - if the team works with agents outside the organisation, agent to agent beyond a5s, with what they say treated as content from outside;
  - if a deployment needs one, adapters for managed runtimes, phase 3's last step;
  - and Google Cloud and AWS, which phase 1 decided on, once Azure is steady.

## Costs

| Cost | Estimate |
| --- | --- |
| People | The platform owner, and an engineer for about half their time, for the 12 weeks. The team's own time is a short conversation each at the end. Graders, about five hours a quarter for the one type of action. |
| Models | About $0.50 a run before caching at illustrative prices, so about $500 for 1,000 runs a month ([phase 1](phase-1.md#costs)). The approved model's own prices may differ. [TBC] |
| Platform | AKS, managed Postgres, locked blob storage and telemetry in one region. [TBC: from Azure's prices] |
