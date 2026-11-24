# Models as components: execution, verification and routing

**Status:** design for review. Some of it is built: call-level replay (`core/gateway.py`'s
`calling`); drift canaries (`config/canaries.yaml`, `core/canaries.py`), which `a5s canaries`
runs when asked, and the nightly workflow runs on each approved model whose key it has; a
reliability ledger of each model's day,
whose SLO gate stops a model until the release approver puts it back with `a5s health
--restore`, signed in, through the core, which records it in the ledger (`core/health.py`),
and a health page that shows both (`/studio/health`); and a
check that a reply names only record keys its run read, with one correction (`core/verify.py`).
The rest isn't, and the release's `fallbacks`, the scheduler's retry and the tests' `judged()`
are the shallow version this replaces, kept until their replacements land.


## A stalled model call is a bug in a5s, not an outage to tolerate

a5s promises runs that pick up where they left off and tasks that lose no work. Before
call-level replay, one model call that didn't answer destroyed the run: its thread, its tool
results and its place were thrown away, and the work restarted. The provider failing is the
trigger; the run dying is a5s's own defect.

The fix is two layers:

1. **Call-level replay, in the run: built.** Each model call is already a recorded,
   sequenced unit (the ledger's model entries carry their sequence). When a call fails, the
   gateway asks its own model once more, then re-issues it on the next healthy approved model
   that speaks the run's API style: same run, same thread, same tool results, nothing
   re-read. Only when every model in the chain has failed the same call does the run end.
   The release's fallbacks bound the chain, and each attempt is in the ledger by sequence and
   alias.
2. **Run-level retry, after the run.** The committed fallback work remains as the last resort:
   a provider-wide outage, where every call failed, is recovered by retrying the message or
   slice later, as the scheduler already does.

## Reliability and measurement: the control loop

Reliability is five properties, each with its own mechanism:

- **Availability:** call-level replay, circuit breakers, the fallback chain.
- **Correctness:** code-checked invariants (keys, amounts, links) and a verifier model
  before anything reaches a person; human decisions for changes, as today.
- **Latency:** per-operation latency budgets, recorded in measures; degrade before failing.
- **Drift:** a fixed, versioned canary set of scripted cases with exact expected behaviour,
  run on every model change and nightly, scored into a table of its own, the canaries'
  scorecard, outside the ledger's chain. Non-negotiable for a model that ships no dated
  version, where a change behind the name can't otherwise be seen.
- **Safety:** already structural, in the gateway, policy, caps and ledger.

The signals exist (breakers, measures, graded samples, per-call ledger entries, and each
model's day in the reliability ledger); the missing piece is making them attributable per
operation, and letting them act: a model whose stall rate breaches its SLO is routed away from
automatically, as tightening is, except on a day a person put it back, whose decision stands
until midnight; putting it back takes the release approver, signed in, and approving a new
model for an operation is a signed release change, as every loosening is. Only calls a5s sent
a model count towards its stall rate: one a5s skipped, as its breaker was open or the gate had
stopped it, is in the ledger, not in how the model did (round 16, A6). The chain of models for
one call answers within the worker's wait for it, and a model that timed out isn't asked again
in it (round 16, A7).

## The problem, as the incident showed it

A model stalled in the middle of a run and the run died with it: the agent's state was
thrown away, the work restarted, and a5s's only answer was to try again on another model. A
model giving a *wrong* answer would not even have been noticed: nothing checked a reply
before it reached a person. Changing models treats the symptom; the disease is that a5s
holds a model as a monolithic, trusted dependency.

The principles this design serves: policy decides, not the model; every action leaves
evidence; people decide how far each model's answers may go.

## The shape

### 1. Typed model operations, not raw chat

The gateway already screens every call's fields. It also knows what each call is *for*:
answering a person, reading a document, keeping a summary, judging a sample, drafting a
change. Make that first-class: each **operation** has its own policy, in the release and the
models file, saying which models may serve it, what its answer must pass before it's used,
and what it may cost. Routing reads the operation; a fallback chain becomes one knob of the
routing policy, not the feature.

### 2. Resilience at call granularity, keeping the run's state

A model call is a replayable unit. When one stalls, the **call** is re-issued on the next
healthy model *within the same run*: the agent keeps its thread, its tool results and its
place; nothing is re-read and nothing is done twice, because each effect is idempotent and
each call is recorded by its hash. The run survives a model that doesn't answer, instead of
being restarted.

### 3. Replies are verified before they land

Before an agent's message reaches a person, or a change is proposed, what code can check is
checked exactly: keys, amounts and links come from the records, nobody is told a change is
made until a5s made it, a denied tool is never said to have worked. What code cannot check
goes to a **verifier**: a second, different model that asks only whether the reply
contradicts what the run read and what it actually did. The judge already grades samples;
the verifier is the same idea on the runtime path. A wrong answer is caught and the run
continues, instead of landing.

### 4. Reliability as data, routing that reads it

a5s already records what it needs: breakers count failures, measures keep latency and
tokens, graded samples measure accuracy per type of change. Aggregate them per model and
per operation into the ledger: a model that stalls on extraction but answers well keeps
extracting at a lower rate, or not at all, while still answering. People see it on a models
health page, and their choice of model for an agent becomes a reviewable, evidence-backed
setting, as the sample grades already are.

### 5. Evaluation follows the same line

Live tests stop checking words. Code-enforced invariants stay exact; semantic properties go
through a5s's own judge against a rubric, repeated per model, with per-model pass rates
kept over time. The live suite becomes a reliability report: "does qwen3.8-max answer the
resume flow better than deepseek" is answered by accumulated data, not by one flaky
assertion.

## What changes in what exists

- `core/gateway.py`'s `calling` becomes the operation router: operation, then model, then
  verification, each recorded in the ledger as today.
- `core/breakers.py` keys by operation and model, not model alone; `measures` gains the
  per-operation outcomes.
- `runs.model` becomes a per-call record; the run keeps no single model. The release's
  `fallbacks` list becomes the routing policy's first form, kept until the operation
  policies replace it.
- The worker replays the failed call in place; the scheduler's run-level retry and the
  tests' `judged()` helper are the temporary pieces, removed when their replacements land.

## Open questions for review

- The verifier's budget: what fraction of a run's tokens may verification take, and who
  approves a model as a verifier: the release approver, as for the judge?
- What per-operation evidence the health page shows, and what the least it may show is.
- Whether an operation's model may be chosen per data class, per part, or per agent, and
  which of those the settings sign.
- The first slice: call-level replay for a stalling model, or the verifier for replies,
  or the operation split. Each is useful alone.

