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

## Deliveries a chat didn't take

**Shows as:** deliveries being tried again, or left in people's local inbox.

1. a5s tries a message a chat didn't take after a minute, then two, four and eight. After five tries it leaves it in the person's inbox in the web chat and on the command line, and the ledger records a `message fallback` with the chat's answer.
2. Read why with `a5s ledger tail`: a chat that's down, a bot's credentials that expired, or a person who left the conversation.
3. Mend the chat. What's already in someone's inbox stays there, so tell them where to find it if they don't use the web chat.

## People get urgent messages in batches

**Shows as:** urgent messages held for a batch.

1. Someone has had five urgent messages today, such as escalations, across all the agents, so the rest wait and go together once an hour, in their working hours. That's a5s working as it should, and a sign an agent writes too much or that much is falling due.
2. Find which agent wrote them with `a5s ledger tail`: each one held shows as a message sent to `batch`.
3. Tell the agent owner. What isn't urgent belongs in the digest.

## Calls are denied

**Shows as:** many denials of one kind.

1. Read the reasons with `a5s ledger tail`. Each denial names the policy that decided it.
2. `tools-match-the-release`: a scenario's tool changed since the release pinned it. Pin the tools again with `a5s pin`, test, and release.
3. `models-see-only-data-they-are-approved-for`: the instance's model isn't approved for the class of data the settings name. Approve a model for it, or use one that is.
4. `messages-go-only-to-the-audience`: an agent tried to write to someone a5s may not write to. That's usually right: check what it was asked.
5. `settings-must-check-out`: the settings in force don't match their signatures or their rows, so every call is denied until they do. See [settings or the release don't check out](#settings-or-the-release-dont-check-out).
6. `lasting-or-outside-effects-need-level-2`: a tool the scenario marks as destructive, or as sending outside the organisation, was called below level 2. Tell the agent owner: below level 2, agents draft and people act.
7. `arguments-fit-the-schema` or `records-are-named-by-key`: the agent called a tool with arguments it doesn't take. Once in a while is the model's mistake. Many in a row may mean the tool's description misleads it: tell the agent owner.

## An instance isn't active

**Shows as:** an instance suspended, and by whom, or retired.

1. Only the person who suspended it can resume it, with `a5s resume`, signed in. Resuming someone else's suspension needs the release approver.
2. A retired instance comes back with a version of the settings that names it again.

## Settings or the release don't check out

**Shows as:** runs refused because the settings in force aren't approved, or because the release isn't approved here.

1. Settings: the reason names whose approval is missing, such as the owner of a part. They sign the version again, with their key, or approve it on a card. If an approver left, whoever holds the role now does.
2. If the core's seal key changed, approvals made on cards need making again.
3. The release: `a5s release status` says what it still needs, and who must sign.

## The ledger's copies stop

**Shows as:** the copier exiting with an error, or `a5s ledger verify` failing.

1. Don't restart the copier to make the error go away. It stops when the ledger no longer matches its copies, which means the history changed.
2. Run `a5s ledger verify`, and tell assurance what it says.

## Old conversations aren't deleted

**Shows as:** the scheduler's log saying it couldn't ask the core to delete what's past its time.

1. The scheduler asks the core every hour, and the ledger records what each sweep deleted. A sweep that finds nothing to delete records nothing.
2. Check that the scheduler is running and can reach the gateway. Nothing is lost while it's stopped, but a5s keeps what it said it would delete.
3. If it stopped for more than a few days, tell the data protection officer.

## An objective is missed

**Shows as:** `missed` beside replies or chases. `Not known yet` means nothing was answered or fell due: check the runs line, since a day of failed runs answers nothing.

1. Slow replies: look at the queue and at model latency in the traces, then at the sections above.
2. Late chases: check that the scheduler sweeps every minute, and that the records can be read. While they can't, nothing owed changes.
