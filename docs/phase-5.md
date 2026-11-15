# Phase 5: the three scenarios, built and run in the studio

**Status:** Step 0 is built: the walk-through harness, and a first walk-through on the sample, which found two gaps, both closed ([progress](#progress)). The service desk is next · **Under:** [Architecture](architecture.md)

The service desk, software delivery and master data scenarios were written by hand: each agent's `agent.yaml`, its instructions, its pins and its tests are files someone typed. That proved a5s runs them. It didn't prove that a team can make them with a5s. This phase builds each scenario's agents again, and the ones they planned but never built, the way an organisation would: in the studio, published, signed and put to work through a5s's own pages, run in the chat, and watched, graded and audited there. Nobody edits an agent's file by hand. Where a step can't be done in a5s, that's a gap, and the gap is the work.

## Progress

- [`tests/walkthrough.py`](../tests/walkthrough.py) is the harness: each step in the words its guide tells it in, a browser of each person's own, signed in through the stand-in identity provider, and a picture of where each step ended. A step a5s can't take fails as a gap, naming the step.
- [`tests/test_walkthrough.py`](../tests/test_walkthrough.py) is the first walk-through, on the sample, on a deployment that isn't in development. Priya builds a new agent, due-dates, in the studio, plans its first instance and publishes it; the team merges its pull request; `a5s release status` says who must sign the release that adds it, Rosa and Priya sign it with `a5s release sign`, and it's recorded with `a5s release approve`; Priya puts it to work from its plan; Ana approves that from her studio home; Ben asks it to move a due date in the chat; Ana decides the change it asks for on its card; Priya watches it on its instance's page; and Kofi reads it in the audit trail. Its guide is [guides/sample](guides/sample/guide.md).

### Gaps the walk-throughs found

| | Gap | Found by | Now |
| --- | --- | --- | --- |
| G-1 | A new agent's release needs its owner's signature, but nobody holds that role until the directory names someone, and nothing said so: the studio named "the due-dates's owner" as if someone were. | The sample, step 5 | The draft's "Who signs its release", and its pull request, name who holds each role a person holds, and say when nobody does yet, so its release can't be approved until the directory names someone. Naming them stays the directory's, as an identity provider's administrator would. |
| G-2 | Wherever a5s isn't in development, the studio's home failed for everyone: it shows a release that waits for someone's signature, and the channels app, which serves it, couldn't read the releases this deployment recorded. Every test ran in development, where it doesn't ask. | The sample, step 12 | Migration `0070_releases_shown.sql` lets the channels app read them: their manifests and signatures, which are open. |

An instance that serves fewer people than the settings' threshold shows its runs only in its daily figures, as round 11 made it, so one by one they don't say what one person did: the walk-through watches its figures, as its owner would.

## Done means

For each scenario, its walk-through runs on the container stack in CI, and the same walk-through, run by hand, is its guide:

1. **Its builders** make each of its agents in the studio, from a template or by describing it: the designer for its tools, abilities, schedules and plan; its instructions; and its test cases, among them what it must never do. They try it in the sandbox until its cases pass, and publish it as a pull request.
2. **Its release approvers** sign the release, and a5s deploys it.
3. **The owners of its parts** approve the version of the settings that puts its first instance to work, from the plan its builders kept with the draft.
4. **The people it serves** use it in the chat. Each change it asks for waits for its part's decider, below level 2, and where its scenario allows level 2, a5s makes it alone only as the settings and graded samples allow.
5. **Its owner** watches its runs, grades its samples, and raises its level where the evidence holds, as a version of the settings.
6. **An auditor** follows a change from the person who asked to the record it changed.

And: each studio-built agent passes its scenario's suite, as the hand-written one did, and its folder is what the studio made. The hand-written folder goes once the two agree.

## What stays code, and what the studio does

The studio builds agents. A scenario is the world they work in, and its builders don't write it:

| | Who makes it | Where |
| --- | --- | --- |
| Its systems: the ITSM, SAP's master data, the forge and its CI | The team that runs a5s connects them | MCP servers, declared in the scenario's `mcp.yaml`, which the release covers ([connectors](connectors.md#mcp-servers)). Here they're made-up servers on the scenario's synthetic data, each with a stand-in for the sandbox |
| Its people, parts and records | The identity provider and the systems | The directory, the settings, `data.yaml` |
| Its policy pack | The team that runs a5s, signed in the release | The scenario's folder |
| Its agents | Their builders | The studio: nothing typed into a file |
| Where they work, whom they serve, their levels | The owners of their parts | The settings app, from each draft's plan |

Each scenario's systems move behind MCP servers before its agents are rebuilt, because that's how an organisation connects its own. It makes MCP-1 carry real work, writes among it, and a scenario's tools stop being Python only a5s's own repository can hold.

## Build in this order

0. **The walk-through harness.** A walk-through signs in as each role in turn, through the stand-in identity provider, and drives the studio, the settings app, the approve and grade pages and the chat on the container stack, as people do. In CI its model is the stand-in, scripted for each walk-through, so it gives the same answers every time; at night, DeepSeek, on synthetic data. It writes a picture of each step, which is the scenario's guide, "built in the studio". Each step it can't take through a5s fails with what was missing, and goes on the gap list.
1. **The service desk's systems behind MCP.** The ITSM's tickets, comments and request catalogue, the knowledge base, the identity provider's self-service flows and device management, as made-up servers on the desk's synthetic data, declared in `scenarios/service-desk/mcp.yaml`. The hand-written desk assistant keeps passing its suite on them before anything is rebuilt.
2. **The desk assistant, rebuilt.** Its walk-through makes it in the studio and compares the folder it publishes with the hand-written one. What differs, and isn't the studio doing better, is a gap.
3. **The desk's agents never built.** The resolver assistant, which briefs a resolver's tickets in one service area and drafts their replies, and the joiner coordinator, described in plain words and drafted least-privilege, then refined by hand. Ticket writes come in, each held for the service area's decider. Self-service runs at level 2 for the catalogue items the service owner approves, once the identity provider verifies the person in its own flow, as the desk's pack says. Authenticators always go to a person.
4. **Software delivery.** The forge and its CI behind MCP; the dev assistant rebuilt; and the held change the scenario left for later, assigning a reviewer, decided by the repository's owners. Its review tasks, which take more than one run, are started, watched and stopped from the chat and its people's own page.
5. **Master data.** SAP's master data behind MCP; the master data assistant and the data quality watcher rebuilt; test cases the judge scores beside its exact ones, since a correction's reasoning can be right in more than one way; and one type of correction taken to level 2 in one part, from graded samples, as the settings give it.
6. **At night, live, then a review.** Each walk-through runs on DeepSeek with synthetic data every night, and round 12 of the critique reviews this phase with what came before it.

"Describe it" (BUILD-3) and test cases the judge scores (BUILD-4) are built where the walk-throughs first need them: the joiner coordinator is described before it's drawn, and master data's corrections are judged.

## Tests

- Each scenario's walk-through takes every step above on the container stack, as its roles, and nothing in it edits a file.
- Each studio-built agent passes its scenario's suite, and its must-never cases, against the stand-in model in CI and against DeepSeek at night.
- A change an agent asks for is held for its part's decider below level 2, and an auditor finds who asked, who decided and what changed.
- A server that changes a tool from what `mcp.yaml` declares is refused until a release declares it again, in each scenario.
- Self-service at level 2 happens only for the person who asked, for an approved catalogue item, once the identity provider has verified them; for anyone else, it goes to the ITSM's approvals.
- The guide's pictures are the walk-through's own, so they never drift from what a5s does.

## What this does not change

The scenarios stay synthetic: no real ITSM, SAP or forge, and no real person's data, so a provider-hosted model sees only made-up records. The scenario contract stays as it is. The studio doesn't write a tool's code or connect a system: that stays the work of the team that runs a5s, reviewed in the release. And nothing here lets an agent widen what it may do: a builder's plan is never in force until its parts' owners approve it.
