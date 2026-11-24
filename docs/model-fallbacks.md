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

## Two layers: the call, then the run

A stalled model call is a bug in a5s, not an outage to tolerate: a run that answers someone
must survive one call's failure. So resilience is two layers.

**In the run:** when a model call fails, the gateway asks its own model once more, then
re-issues the same call on the next model its release names that speaks its API style and may
see its data (`core/gateway.py`'s `calling`), all within the same run: the agent keeps its
thread, its tool results and its place, and the worker sees only the last attempt's answer.
Each attempt is in the ledger, by the call's sequence and alias, and the call is bounded by
the chain. The assistant's own fallback is the same model through its other API, so its calls
aren't made again there within a run: the scheduler tries it next, after the run.

**After the run:** if every model failed a run's calls, as in a provider-wide outage, the
scheduler tries the message again on the next model, each tried once, and only once every one
has failed does the person hear a5s's own words for a model that isn't answering
(`services/scheduler.py`, and `core/gateway.py`'s `model_for` at run-open). The failed model's
breaker still opens after three failures in a row, so a provider that's down isn't asked for
a few minutes.

Each attempt is in the ledger as before: the run's `model` records the model it opened on, and
each call's entry names its alias, so the evidence shows which model answered what. A call a
fallback answered leaves the run on that model: its next call is its own model's again, which
policy lets it make (round 16; before, the run took the fallback's name, and policy refused
its next call). Its tokens count at the run's model's price.

A message waits for the next model only when its run found its model not answering. When a5s
refuses to open a run at all, as for a suspended instance, the person hears why once and the
message is answered, whatever models remain (round 16; before, the scheduler took it again at
once, for ever).

**Acting on its own:** a fallback answers, but what the release's own model earned doesn't
come with it. A change a run asks for after a fallback answered one of its calls is made on its
own only where the fallback earned it too, from graded samples of changes made on it, and
otherwise waits for its decider ([phase 2](phase-2.md)). The same holds for an instance its
settings put on another approved model.

## Judged wording checks in the live tests

The live suites used to hold the agent's words to exact strings (`"done" in told`, every
field's name in one message). Real models say the same thing in different words, so the same
correct behaviour failed the test on one day's phrasing and passed on another's. The wording
checks now go through `judged()` in `tests/conftest.py`, which asks an approved model, plainly,
whether the message says what it must: a model that says the same in other words still passes,
and one that says the opposite fails, however well it's worded. What code enforces stays an
exact check: drafts, task state, denials, routing, and the ledger.

`tests/test_fallbacks.py` proves the fallback chain: a run survives its model stalling on one
call, a message runs on its fallback once its model isn't answering, each model is tried once,
the person hears a5s's words only when every one has failed, an unapproved fallback is never
called, and a model whose breaker is open, or whose health gate has stopped it, is passed over
for the next.

