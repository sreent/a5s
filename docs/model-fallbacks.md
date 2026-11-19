# Model fallbacks, and judged wording checks

## What changed

An agent's release may name other approved models beside its own, in its `agent.yaml`:

```yaml
model: deepseek-v4-pro           # its own, as before
fallbacks: [deepseek-v4-pro-anthropic]  # tried in order when its model isn't answering
```

Nothing about how far the agent acts changes: the release approves the chain as it approves
the model, the gateway refuses any alias `config/models.yaml` doesn't list, and every call, on
whichever model serves it, goes through the same policy, budgets and ledger.

## How a run picks its model

At the moment a run opens, the core picks the instance's model, or, when that one's circuit
breaker is open, or the same work just failed on it, the first fallback the breakers let
through, and keeps the choice on the run (`core/gateway.py`'s `model_for`). Every call of the
run goes to that one model. When a run ends with its model not answering, the scheduler tries
the message again, and the next attempt skips the model that failed, so each model in the
chain gets one go. Only when every one has failed does the person hear a5s's own words for a
model that isn't answering (`services/scheduler.py`). The failed model's breaker still opens
after three failures in a row, as before, so a provider that's down isn't asked for a few
minutes.

Each attempt is in the ledger as before: the run's `model` records which model served it, and
each call's entry names its alias, so the evidence shows which model answered what.

## Judged wording checks in the live tests

The live suites used to hold the agent's words to exact strings (`"done" in told`, every
field's name in one message). Real models say the same thing in different words, so the same
correct behaviour failed the test on one day's phrasing and passed on another's. The wording
checks now go through `judged()` in `tests/conftest.py`, which asks an approved model, plainly,
whether the message says what it must: a model that says the same in other words still passes,
and one that says the opposite fails, however well it's worded. What code enforces stays an
exact check: drafts, task state, denials, routing, and the ledger.

`tests/test_fallbacks.py` proves the fallback chain: a message runs on its fallback once its
model isn't answering, each model is tried once, the person hears a5s's words only when every
one has failed, an unapproved fallback is never called, and a model whose breaker is open is
passed over for the next.

