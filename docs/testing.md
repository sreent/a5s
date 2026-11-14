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

The default marker configuration excludes live-provider tests. `-m 'not live'` makes that exclusion explicit when selecting a module.

### Postgres

Tests use a real Postgres, not a mocked database. By default they start a throwaway Postgres in Docker on Windows and a local instance where the platform supports it. `A5S_TEST_DATABASE_URL` can name a test Postgres instead; the fixture resets its schemas, so never point it at a database containing anything to keep.

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

If Chromium is unavailable, browser tests may skip locally. To require them, as CI does:

```sh
A5S_TEST_BROWSER=required uv run pytest
```

On Windows, run shell commands and the `sh` deployment scripts from Git Bash.

## Run live-model evaluations

Use synthetic equivalents only, and keep provider keys outside git. A local `.a5s/live.env` is the usual place; do not print it or commit it.

```sh
uv run --env-file .a5s/live.env pytest -m live
```

The approved model list names the key's environment variable for each provider, currently `DEEPSEEK_API_KEY` and `QWEN_API_KEY` for development models. A missing key normally skips the live test. For a release's required regression suites, it must fail instead:

```sh
A5S_REGRESSION=required uv run --env-file .a5s/live.env pytest -m live
```

The resume evaluation accepts `A5S_EVAL_MODEL`, such as `qwen3.7-max`, while defaulting to the release's DeepSeek alias. That changes the evaluation's model, not the production agent's approved model.

To exercise the actual worker image, rather than a worker in the test process:

```sh
docker build -t a5s:dev .
A5S_TEST_WORKER_IMAGE=a5s:dev uv run --env-file .a5s/live.env pytest -m live
```

The worker holds only its run token. The gateway holds provider credentials. The [release workflow](../.github/workflows/release.yml) runs the agents' and scenarios' live suites this way before publishing an image.

### What a live evaluation should measure

For each meaningful case, check the answer's correctness and sources, what the agent must not claim, permission and safety outcomes, effects made once, and ledger integrity. Measure latency, model calls and tokens beside those assertions.

`tests/scorecards.py` prints those measurements for the hard scenario evaluations, including forbidden tool actions. Monetary cost is not inferred: if the approved model has no configured prices, the scorecard says so. Critical cases run more than once so a single fortunate response isn't presented as reliability.

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
```

These are separate scenario stacks. Stop an existing smoke stack first if it holds the same local ports. The scripts clean their own stacks on exit; `deploy/smoke.sh --keep` leaves the sample running to try it.

Run the longer recovery and leak check:

```sh
sh deploy/soak.sh 30
```

Its minutes can be changed. It needs Docker and time, and it kills and restarts its own test services, so run it on the test stack, not on a deployment people are using.

## When something fails

- **A rule or permission assertion failed:** find the cause before changing it. Do not weaken a control to make the test green.
- **A model gave a wrong answer:** record the case and inspect its tools, sources and wording. Fix the scenario or instructions where they were ambiguous, and keep the case as a regression.
- **The provider was unavailable:** an HTTP 502/503 or a timeout is not a completed evaluation. Check the provider with a small request and rerun the full case when it works; never count an outage as a correct answer.
- **A browser or service was missing:** install or start it. Don't silently treat a required browser or integration check as optional.
- **The failure predates the change:** reproduce it on unmodified `main` in isolation before setting it aside, and report it rather than hiding it in an unrelated fix.
- **A test is timing-dependent:** control the boundary deterministically where possible, while retaining an end-to-end check of the real behavior.

CI runs the full suite, container and scenario smoke tests, and a Kubernetes install from the chart. The weekly and manually requested [soak workflow](../.github/workflows/soak.yml) runs the longer recovery test. A release also requires the real-model agent suites; see [the release workflow](../.github/workflows/release.yml).

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

For a new tool or connector, pin its schema and test its risk flags, credentials, permissions, pagination, timeouts, failures and hostile inputs. If it makes an effect, test idempotency under retries and fresh task workers. Skills remain reviewed instructions and reference material: they do not grant tools or run scripts.

For Graphify, the current adapter tests mock the CLI. They do not establish better answers than ordinary search. A graph should be adopted only after a real corpus comparison of correctness, attribution, latency, cost and operational complexity.

The [user journey](user-journey.md) shows the current interface those tests are intended to protect. Each scenario's document links to its own suite, and [phase 4](phase-4.md#tests) lists the long-running task evidence.
