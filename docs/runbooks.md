# Runbooks

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md#operations)

For the team that runs a5s. `a5s status` shows how a5s did over the last day, and the gateway's `/status` gives the same to a dashboard. Each section below says what to do when one of its lines goes wrong. Who's on call, and when, is [TBC].

To follow one run, find its spans by `a5s.run.id`, where the deployment sends traces (`OTEL_EXPORTER_OTLP_ENDPOINT`), and its entries with `a5s ledger tail`. Traces are for debugging. The ledger is the evidence.

## Messages are waiting

**Shows as:** the queue has messages waiting, the oldest for more than a few minutes.

1. Check that the scheduler is running, and read its log. It has no port, so its log is the only way to see it.
2. Check that it can reach the gateway, and the gateway the database.
3. Restart the scheduler if it's stuck. A message outlives a scheduler that stops: the next one takes it again once the lease runs out, so nothing is lost or answered twice.

## Runs fail, or a model isn't answering

**Shows as:** runs ending `failed` or `model unavailable`, or a breaker open.

1. A breaker opens after three failures in a row, and a5s tries the model again every five minutes on its own. People are told at once that the model isn't answering.
2. Check the provider's own status, and that its key is set where the gateway runs.
3. A model that answers with another model's name is refused (`model_mismatch`). That's the provider changing its model, not a5s failing: tell the agent owner.
4. There's no failover to a model that isn't approved. Moving an agent to another approved model is a new release, which the release approver signs.

## Budgets run out

**Shows as:** an instance's tokens past four fifths of a person's day, runs ending `budget spent`, or people told an agent has used its budget.

1. Look for one run that used far more than the rest: an agent going round in circles stops at its run's budget, and the ledger shows each model call.
2. Chases and reminders go on, on the fifth of each day kept for them. Reports wait for the next day.
3. Budgets come with the release, so raising one is a new release that widens the agent, which the release approver signs. Don't raise one to get through a bad day.

## Calls are denied

**Shows as:** many denials of one kind.

1. Read the reasons with `a5s ledger tail`. Each denial names the policy that decided it.
2. `tools-match-the-release`: a scenario's tool changed since the release pinned it. Pin the tools again with `a5s pin`, test, and release.
3. `models-see-only-data-they-are-approved-for`: the instance's model isn't approved for the class of data the settings name. Approve a model for it, or use one that is.
4. `messages-go-only-to-the-audience`: an agent tried to write to someone a5s may not write to. That's usually right: check what it was asked.

## An instance isn't active

**Shows as:** an instance suspended, and by whom, or retired.

1. Only the person who suspended it can resume it, with `a5s resume`, signed in. Resuming someone else's suspension needs the release approver.
2. A retired instance comes back with a version of the settings that names it again.

## Settings or the release don't check out

**Shows as:** runs refused because no instance approver signed the settings in force, or because the release isn't approved here.

1. Settings: an instance approver signs the version again, with their key, or approves it on a card. If an approver left, someone who holds the role now does.
2. If the core's seal key changed, approvals made on cards need making again.
3. The release: `a5s release status` says what it still needs, and who must sign.

## The ledger's copies stop

**Shows as:** the copier exiting with an error, or `a5s ledger verify` failing.

1. Don't restart the copier to make the error go away. It stops when the ledger no longer matches its copies, which means the history changed.
2. Run `a5s ledger verify`, and tell assurance what it says.

## An objective is missed

**Shows as:** `missed` beside replies or chases.

1. Slow replies: look at the queue and at model latency in the traces, then at the sections above.
2. Late chases: check that the scheduler sweeps every minute, and that the records can be read. While they can't, nothing owed changes.
