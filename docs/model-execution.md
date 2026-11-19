# Models as components: execution, verification and routing

**Status:** design for review. Nothing here is built; the pieces in the tree today (release
`fallbacks`, the scheduler's retry, the tests' `judged()`) are the shallow version this
replaces, kept until its first slice lands.


## A stalled model call is a bug in a5s, not an outage to tolerate

a5s promises runs that pick up where they left off and tasks that lose no work. Today one
model call that doesn't answer destroys the run: its thread, its tool results and its place
are thrown away, and the work restarts. The provider failing is the trigger; the run dying is
a5s's own defect.

The fix is two layers:

1. **Call-level replay, in the run.** Each model call is already a recorded, sequenced unit
   (the ledger's model entries carry their sequence). When a call fails, the worker asks the
   gateway to re-issue it on the next healthy approved model — same run, same thread, same
   tool results, nothing re-read. Only when every model in the chain has failed the same call
   does the run end, as today. The release's fallbacks bound the chain, and each attempt is
   in the ledger by sequence and alias, so the evidence shows which model answered what.
2. **Run-level retry, after the run.** The committed fallback work remains as the last resort:
   a provider-wide outage, where every call failed, is recovered by retrying the message or
   slice later, as the scheduler already does.

## Reliability and measurement: the control loop

Reliability is five properties, each with its own mechanism:

- **Availability** — call-level replay, circuit breakers, the fallback chain.
- **Correctness** — code-checked invariants (keys, amounts, links) and a verifier model
  before anything reaches a person; human decisions for changes, as today.
- **Latency** — per-operation latency budgets, recorded in measures; degrade before failing.
- **Drift** — a fixed, versioned canary set of scripted cases with exact expected behaviour,
  run on every model change and nightly, scored into the ledger. Non-negotiable for a model
  that ships no dated version, where a change behind the name can't otherwise be seen.
- **Safety** — already structural: gateway, policy, caps, ledger.

The signals exist (breakers, measures, graded samples, per-call ledger entries); the missing
piece is making them attributable per model and per operation, and letting them act: a model
whose stall rate breaches its SLO is routed away from automatically — tightening is always
automatic — while putting it back, or approving a new model for an operation, is a signed
release change, as every loosening is.

## The problem, as the incident showed it

A model stalled in the middle of a run and the run died with it: the agent's state was
thrown away, the work restarted, and a5s's only answer was to try again on another model. A
model giving a *wrong* answer would not even have been noticed: nothing checks a reply
before it reaches a person. Changing models treats the symptom; the disease is that a5s
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
  approves a model as a verifier — the release approver, as for the judge?
- What per-operation evidence the health page shows, and what the least it may show is.
- Whether an operation's model may be chosen per data class, per part, or per agent, and
  which of those the settings sign.
- The first slice: call-level replay for a stalling model, or the verifier for replies,
  or the operation split — each is useful alone.

