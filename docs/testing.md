# Testing a5s

**What this covers:** How to run the current tests, what each layer proves, and how to add a meaningful case. Tests use synthetic records and stand-in services. Live-model evaluations must not use real business or personal data.

## The layers

| Layer | What it proves |
| --- | --- |
| Unit tests | Validation, policy, permissions, provenance, budgets, task state, tool contracts and other rules worked out by code |
| Integration tests | Real Postgres transactions, the gateway, the scheduler, channels, tools and browser pages working together |
| Scripted-model conversations | A known sequence of tool calls and replies exercises the whole run deterministically; it does not test a model's choice of tools |
| Live-model evaluations | A real provider chooses tools and answers the questions, repeatedly for critical cases, with semantic assertions and measurements |
| Container smoke tests | The same image running as core, scheduler, channels, workers and supporting services, with sign-in, Matrix, release approval and locked-ledger verification |
| Scenario smoke tests | Each scenario's own directory, agents, records and approvers, through the same container path |
| Soak tests | Continued use, worker and core crashes, scheduler failure, upgrades and a database outage, checking recovery, duplicate work, leaks and lingering leases |

A green scripted test is not proof that a live model reasons correctly. A successful live answer is not proof of reliability if it happened only once.

## Run locally

Install the locked development dependencies and run the normal suite:

```sh
uv sync --locked
uv run ruff check .
uv run basedpyright
uv run pytest
```

Run one test, module or scenario, for example:

```sh
uv run pytest tests/test_tasks.py -q
uv run pytest tests/test_task_runs.py::test_a_task_runs_slice_by_slice_and_writes_to_its_owner_once_its_done -q
uv run pytest tests/test_software_delivery.py -q
uv run pytest tests/test_master_data.py -q
uv run pytest tests/test_connectors.py -q
```

The default marker configuration excludes live-provider tests and those that need the disposable Forgejo (`-m 'not live and not forgejo'` in `pyproject.toml`). A `-m` of your own replaces it, so keep `not forgejo` in it unless `deploy/forgejo.sh` runs the tests.

### Static types

[basedpyright](https://docs.basedpyright.com/), pyright with a baseline, checks a5s's own code, `src/a5s`, at pyright's standard strictness (`[tool.basedpyright]` in `pyproject.toml`). It runs in CI beside ruff, from the locked development dependencies, with its own Node, so nothing else needs installing.

What it found when it was added, and wasn't fixed then, is in `.basedpyright/baseline.json`: chiefly rows read with `fetchone()` that the code takes to be there, such as a count's, and branches the checker can't tell go together. Anything else fails. The baseline only shrinks: fix one of its errors and the checker drops it from the file, and CI fails until that change is committed with the fix. Only `uv run basedpyright --writebaseline` adds to it, which review sees in the diff: fix the error instead, unless a refactor only moved one that was there.

Some of what the checker holds a5s to:

- Every database connection is `db.Connection`, which gives each row as a dict, from a pool typed to match.
- SQL is text in the code, never input: psycopg takes a `LiteralString`, so helpers that build SQL take and give `LiteralString`, and constants they draw on, such as the tables a sweep empties, are `Final`. A value goes in as a parameter. A migration's file is a5s's own, the one cast.
- A lookup that may find nothing says `| None`, and a caller that knows it's there, such as for a task its transaction has locked, uses one that raises instead (`TaskService._held`).

### Postgres

Tests use a real Postgres, not a mocked database. By default they start a throwaway Postgres: in Docker on Windows, and elsewhere from the Postgres installed on the machine. `A5S_TEST_DATABASE_URL` can name a test Postgres instead; the fixture resets its schemas, so never point it at a database containing anything to keep.

### Browser pages

Install Chromium for Playwright:

```sh
uv run playwright install chromium
```

The studio's pages are built, not kept in git. Build them before the tests, as CI does, by the image's own Node stage:

```sh
docker build --target studio-built --output src/a5s/core/webchat/studio .
```

or, with Node 20.19 or later, `npm ci --prefix studio && npm run build --prefix studio`. Unbuilt, the studio answers 503 with how to build it, and its tests fail.

Every page people use, the design system's showcase, the decisions page with a change waiting, the settings app's forms, the approval and grading cards, and the administrators', auditors' and data protection officer's pages with what they show are checked with [axe](https://github.com/dequelabs/axe-core) in light and dark, as wide as a desktop and as a phone, by WCAG's rules and its best practices (`accessible` in `tests/conftest.py`). A page that axe finds anything amiss on fails its test, with axe's report of what and where, and so does one that scrolls sideways. With `A5S_SCREENSHOTS` naming a folder, the browser tests save each page there as it looks, light and dark, and on a phone.

A walk-through goes further: a scenario's people, each in a browser of their own, take an agent from an idea to work through a5s's own pages and its command line alone, on a deployment that isn't in development, so its release must be signed before it runs anything ([phase 5](phase-5.md), `tests/walkthrough.py`). The first, `tests/test_walkthrough.py`, takes a new agent on the sample through the studio, a pull request, `a5s release sign`, the settings app, the approval page, the chat, a decision and the audit trail. A step it can't take through a5s fails, naming the step, as a gap. With `A5S_GUIDE` naming a folder, it writes the scenario's guide there, a picture of each step beside its words: `A5S_GUIDE=docs/guides uv run pytest tests/test_walkthrough.py` makes [the sample's](guides/sample/guide.md). `tests/test_walkthrough_desk.py` builds the service desk's assistant again from nothing, and holds what it may do to the hand-written one's; it writes [the desk's guide](guides/service-desk/guide.md). `tests/test_walkthrough_resolver.py` builds the resolver assistant the desk planned and never built, keeps what it must never do as a test case in the sandbox, and follows a reply it asks for to the service area's decider and back; it writes [the resolver's guide](guides/resolver/guide.md). `tests/test_walkthrough_joiner.py` describes the joiner coordinator in plain words, checks the least it was given, and refines it by hand; it writes [the joiner's guide](guides/joiner/guide.md). `tests/test_walkthrough_delivery.py` builds software delivery's dev assistant again from nothing, follows a review it asks for to the repository's owner, and starts and stops a review task; it writes [its guide](guides/software-delivery/guide.md). `tests/test_walkthrough_master_data.py` builds master data's assistant again from nothing, keeps a test case its judge grades, follows a correction to its data object's owner, and then, once two graders have graded a quarter's corrections, half each, lets it act on its own for corrections in material data through the settings app; it writes [its guide](guides/master-data/guide.md). `tests/test_walkthrough_quality.py` builds master data's data quality watcher again, with its daily reports, and follows one to its owner's day from a5s; it writes [its guide](guides/data-quality/guide.md). `tests/test_walkthrough_procure_to_pay.py` takes a month-end in accounts payable from end to end, on agents already at work: a supplier's mail with a planted note read through a5s's reader, a payment two deciders decide on the decision page, the ERP's signed event, a month-end task in parts through a restart of a5s, a model that stops answering and the spare that hasn't earned acting on its own, a dispute handed to payables and back, and the audit trail; it writes [its guide](guides/procure-to-pay/guide.md). It runs on the stand-in model alone, since what it checks is what a5s holds, makes and refuses, which a real model's words don't change, so it isn't one of the walk-throughs that run on DeepSeek at night.

In CI, a walk-through's agents run on the stand-in model, scripted, so they answer the same every time. Each night, `.github/workflows/nightly.yml` runs every walk-through on DeepSeek instead, on the scenarios' synthetic data alone: with `A5S_TEST_WALK_MODEL` naming an approved model, the agents, the sandbox and the judges run on it, what the script would have said goes nowhere, and each step waits for whatever the agent answers and checks what came of it, a change held, decided and made, rather than its words. Where a walk-through tries an agent in the sandbox or describes one there, it picks that model on the page, as its author would, so the sandbox's cases and descriptions run on it too; what only the stand-in's script makes so, such as the reads a description of the joiner coordinator gives it, the night checks only as far as a5s promises it: nothing done on its own, and whatever writes taken away by hand. Each audit step checks who decided a held change and that a5s made it, as the ledger has them. A real model does what a script never does, and the walk-throughs allow for what a person would: someone confirms a change once when the agent asks them to first, though a5s holds it for its decider anyway, and the scheduler comes round again for a run that failed, as it does each minute in a deployment, before a day from a5s that waits on it. Run one that way by hand with `A5S_TEST_WALK_MODEL=deepseek-v4-pro uv run pytest tests/test_walkthrough_master_data.py`, with `DEEPSEEK_API_KEY` set. The same night runs the drift canaries on each approved model whose key it has, so a model that changed behind its name fails there, naming the canary and the model (`tests/test_canaries.py`), and the assistant's case of someone writing in Thai, which it must answer in Thai (`agents/assistant/tests/language.yaml`).

Some browser tests follow a person's way across pages, as they'd take it. Putting an agent to work starts on its page in the studio, where its owner is offered it, goes through the settings app's form, a fresh sign-in kept on the way, and the review, to its part's owner approving it on the approval page, which says who asked; once a5s puts it in force, the agent's page shows where it runs (`tests/test_settings_app.py`). Making an agent follows its draft's path, from shaping and trying it to publishing it (`tests/test_studio_authoring.py`). The commonest journeys are counted: deciding a change and grading a sample from the home, approving a version from its card, cancelling a task, and opening or suspending an instance by name, each with a budget of clicks and page loads from where the person starts to what they came to do, a fresh sign-in for an act counted as the page load it is. A change that makes one longer fails (`tests/test_journeys.py`).

Persona tests (`tests/test_personas.py`) meet the studio as people new to it do, by what's on their screen alone: a newcomer who holds no role, a builder who may start an agent, and an administrator who approves the settings and decides what agents ask. Each starts on Home and gets to what they came for within a budget of clicks, never by typing an address. Each is told what they are, as a5s has no administrator's mode, only roles, and finds how an agent is built, or who builds them. Every page on the way is checked as a person reads it: one heading, with a line saying what the page is for or its facts; the sidebar marking where they are; none of the code's own words, such as a role's id outside the ids a page shows on purpose, or "undefined"; no error in the browser's console or from the server; and axe, light, dark and at a phone's width. A newcomer on a phone still finds who they are, in the initials at the sidebar's end, and every person in the sample is told their roles and offered the pages their work needs.

If Chromium is unavailable, browser tests may skip locally. To require them, as CI does:

```sh
A5S_TEST_BROWSER=required uv run pytest
```

On Windows, run shell commands and the `sh` deployment scripts from Git Bash.

## Run live-model evaluations

Use synthetic equivalents only, and keep provider keys outside git. A local `.a5s/live.env` is the usual place; do not print it or commit it.

```sh
uv run --env-file .a5s/live.env pytest -m 'live and not forgejo'
```

The Forgejo evaluation's live case is marked `forgejo` too, and runs only through `deploy/forgejo.sh` ([below](#run-the-container-paths)).

The approved model list names the key's environment variable for each provider, currently `DEEPSEEK_API_KEY` and `QWEN_API_KEY` for development models. A missing key normally skips the live test. For a release's required regression suites, it must fail instead:

```sh
A5S_REGRESSION=required uv run --env-file .a5s/live.env pytest -m 'live and not forgejo'
```

The resume evaluation in `tests/test_software_delivery.py` accepts `A5S_EVAL_MODEL`, such as `qwen3.7-max`, while defaulting to the release's DeepSeek alias. That changes the evaluation's model, not the production agent's approved model.

To exercise the actual worker image, rather than a worker in the test process:

```sh
docker build -t a5s:dev .
A5S_TEST_WORKER_IMAGE=a5s:dev uv run --env-file .a5s/live.env pytest -m 'live and not forgejo'
```

The worker holds only its run token. The gateway holds provider credentials. The [release workflow](../.github/workflows/release.yml) runs the agents' and scenarios' live suites this way before publishing an image. Where the test process can't call Docker, start a worker from the image yourself, and name it beside `A5S_TEST_WORKER_IMAGE`: its address in `A5S_TEST_WORKER_URL`, and the gateway URL it was started with in `A5S_TEST_WORKER_GATEWAY`. The tests serve the core on that URL's port, at `A5S_TEST_BRIDGE`'s address, Docker's bridge unless it says (`live_image` and `contained` in `tests/conftest.py`).

### What a live evaluation should measure

For each meaningful case, check the answer's correctness and sources, what the agent must not claim, permission and safety outcomes, effects made once, and ledger integrity. Measure latency, model calls and tokens beside those assertions. Check what the agent's words say through `judged()` in `tests/conftest.py`, which asks an approved model whether the message says what it must, so the same meaning in other words passes; what code enforces, such as drafts, task state, denials and the ledger, stays an exact check ([judged wording checks](model-fallbacks.md#judged-wording-checks-in-the-live-tests)).

`tests/scorecards.py` prints those measurements for the hard scenario evaluations, including forbidden tool actions. Monetary cost is not inferred: if the approved model has no configured prices, the scorecard says so. Critical cases run more than once so a single fortunate response isn't presented as reliability.

`a5s canaries` asks each approved model whose key is set the fixed cases in `config/canaries.yaml`, straight from its provider, keeps whether each gave the answer it must, and prints the day's scores, so a model that changes behind its name shows. `a5s health` shows each model's day, measured, and the studio's `/studio/health` shows both ([model execution](model-execution.md)).

## Run the container paths

Build the image first:

```sh
docker build -t a5s:dev .
sh deploy/smoke.sh
```

Run another scenario with its own made-up approvers:

```sh
sh deploy/smoke-scenario.sh master-data
sh deploy/smoke-scenario.sh software-delivery
sh deploy/smoke-scenario.sh service-desk
sh deploy/smoke-scenario.sh procure-to-pay
```

These are separate scenario stacks. Stop an existing smoke stack first if it holds the same local ports. The scripts clean their own stacks on exit; `deploy/smoke.sh --keep` leaves the sample running to try it.

Check the repository connector against a real Forgejo, on made-up repositories, as CI does:

```sh
sh deploy/forgejo.sh
```

It starts and removes its own containers. With `A5S_TEST_FORGEJO_LIVE=required` and the keys in `.a5s/live.env`, it also runs a real model through a worker from the image ([connectors](connectors.md#read-only-repository-connectors)).

Run the longer recovery and leak check:

```sh
sh deploy/soak.sh 30
```

Its minutes can be changed. It needs Docker and time, and it kills and restarts its own test services, so run it on the test stack, not on a deployment people are using. With `A5S_SOAK_FOUND` naming a file, it writes what it measured there, with every run of each message that ran more than once, so a fallback's retry can be told from work a crash made twice; the soak workflow keeps that file for 14 days.

## When something fails

- **A rule or permission assertion failed:** find the cause before changing it. Do not weaken a control to make the test green.
- **A model gave a wrong answer:** record the case and inspect its tools, sources and wording. Fix the scenario or instructions where they were ambiguous, and keep the case as a regression.
- **The provider was unavailable:** an HTTP 502/503 or a timeout is not a completed evaluation. Check the provider with a small request and rerun the full case when it works; never count an outage as a correct answer.
- **A browser or service was missing:** install or start it. Don't silently treat a required browser or integration check as optional.
- **The failure predates the change:** reproduce it on unmodified `main` in isolation before setting it aside, and report it rather than hiding it in an unrelated fix.
- **A test is timing-dependent:** control the boundary deterministically where possible, while retaining an end-to-end check of the real behaviour.

CI runs the full suite, the Forgejo evaluation, container and scenario smoke tests, and a Kubernetes install from the chart. The weekly and manually requested [soak workflow](../.github/workflows/soak.yml) runs the longer recovery test. A release also requires the real-model agent suites; see [the release workflow](../.github/workflows/release.yml).

## Add a useful test

Start with a user need and an observable result, not a new tool call for its own sake. A good case:

- uses synthetic but linked, non-trivial records;
- tests both the allowed and denied person;
- checks source attribution and what must not be inferred;
- tests stale, deleted or changing information where relevant;
- checks actual side effects and repeated effects after a restart, not only the final text;
- verifies the ledger;
- measures model use for a live case;
- includes ambiguity, correction or a second turn where a real conversation would need it.

For a new page people sign in to, put its routes in a router of its own, as each page of the channels app is, whose API checks who's signed in before any route runs ([`core/web.py`](../src/a5s/core/web.py)). `tests/test_routers.py` asks every route of each such API with no sign-in and expects a refusal, fails on a route that's in none of them and isn't one of those that check for themselves, and holds the sidebar to each page's own check. A route of the core's own API goes on one of its two routers ([`core/gateway.py`](../src/a5s/core/gateway.py)), the service token's or a worker's run token's, and the same test asks every route the core serves with no token.

The studio's TypeScript types are made from its API's description, which each route's response model makes ([`core/studio_models.py`](../src/a5s/core/studio_models.py)): a route checks every answer against its model as it sends it, and a model names every field, so an answer's field the model leaves out fails in the tests rather than reaching the studio unknown. When an answer changes, change its model and make the types again, `uv run python -m a5s.core.studio_api > studio/src/api.gen.ts`: `tests/test_studio_types.py` fails until they're what the code makes, and the studio's build type-checks every page against them.

For a new tool or connector, pin its schema and test its risk flags, credentials, permissions, pagination, timeouts, failures and hostile inputs. If it makes an effect, test idempotency under retries and fresh task workers. Skills remain reviewed instructions and reference material: they do not grant tools or run scripts.

For Graphify, the current adapter tests mock the CLI. They do not establish better answers than ordinary search. A graph should be adopted only after a real corpus comparison of correctness, attribution, latency, cost and operational complexity.

The [user journey](user-journey.md) shows the current interface those tests are intended to protect. Each scenario's document links to its own suite, and [phase 4](phase-4.md#tests) lists the long-running task evidence.
