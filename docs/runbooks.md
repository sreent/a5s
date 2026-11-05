# Runbooks

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md#operations)

For the team that runs a5s. `a5s status` shows how a5s did over the last day, and the gateway's `/status` gives the same to a dashboard. Each section below says what to do when one of its lines goes wrong. Who's on call, and for what, is [below](#on-call).

To follow one run, find its spans by `a5s.run.id`, where the deployment sends traces (`OTEL_EXPORTER_OTLP_ENDPOINT`), and its entries with `a5s ledger tail`. Traces are for debugging. The ledger is the evidence.

## On call

a5s is built to stop safely: when it can't run as it should, it stops and says so, and people carry on in the scenario's own processes. So almost nothing it does needs anyone out of hours.

- **Until people depend on a5s in production,** nobody is on call. The team that runs a5s reads `a5s status` each working day.
- **Once they do,** the team that runs a5s keeps a weekly rota, a primary and a secondary, in working hours, and the status's lines go to a working-hours queue.
- **Out of hours, three things page the primary,** since each can't safely wait:
  - the ledger's copies failing to copy, lock or verify ([below](#the-ledgers-copies-stop)), since that's the evidence: tell assurance too;
  - a change stopped part way through being made ([below](#changes-wait-or-stop-part-way)), since a record may be half-changed;
  - denials in an hour more than five times their usual rate for that hour ([below](#calls-are-denied)), which is what an attack looks like.
- Everything else, such as a model that's down, a budget spent or a chat that didn't take a message, waits for working hours: people carry on without a5s, and it catches up.

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
4. An answer kept back from a group chat someone joined while it was worked out isn't a chat that's down: the status counts it apart. It goes to whoever asked, in a chat of their own, which a5s starts on Matrix, or else their inbox in the web chat, and the group hears where it went.

## Changes wait, or stop part way

**Shows as:** changes waiting for a decision for days, changes approved but not made, or one stopped part way through being made.

1. A waiting change reminds each of its deciders, in their own hours, after two working days, then tells their managers, or the instance's owner, after five, and lapses after ten, telling whoever asked for it. Its deciders are worked out afresh each time, so a part's new owner, or a delegate its owner names with `part-delegate:<part>`, decides what waits there. Nothing needs doing unless a part has nobody who may decide: then the change isn't held at all, and the agent says why.
2. A change approved but not made says why in the outcome its asker was told: its record changed after it was asked for, the instance may no longer act, or the records system didn't take it. They can ask again.
3. A change stopped part way means a5s marked it as being made, and stopped, or the sweep failed for it, before it could record what happened: the gateway's log says `couldn't sweep P-n`. a5s never makes it again by itself. `a5s proposals` lists such changes. Check the record in the scenario's own system, then end it with `a5s proposals end P-n`, as its instance's owner or deputy, an owner of a part it touches, an instance approver or assurance: whoever asked is told it may or may not have been made, and can ask again.
4. A decision that doesn't count shows once in the gateway's log: a decision the core didn't seal, or by someone who may no longer decide it. A sign-in the gateway refused when it checked it again, before sealing, is in the ledger as `refuse-sign-in`: the person decides again. Tell assurance about any of these that nobody can explain, since each could be someone writing what the channels app writes.
5. The status counts the approvals, decisions and grades the gateway hasn't sealed in five minutes. They don't count until it does, and it seals each minute, so any at all mean it can't: its log says why, such as no seal key (`A5S_SEAL_KEYS`) or identity provider. Set it, and it seals them at its next sweep. One left more than a day is refused, and its person decides again.

## Samples wait to be graded, or a cap falls

**Shows as:** samples waiting to be graded, samples that lapsed ungraded, or caps lowered in the last day.

1. Samples are graded on the core's page, `/grade/`, by people who hold the grader role, from outside the teams that build and run the agent. A backlog only slows level 2: ask the scenario's owners for graders. A sample nobody grades in a quarter lapses, and goes after a year.
2. A cap falls on a critical error, on grades that show accuracy below the part's threshold, when the threshold rises past what the grades show, or when someone lowers it. The ledger's `cap` entries give the evidence, and the instance's owner and deputy hear in their digest. It rises again only on new grades.
3. To lower a cap at once, such as while a fault is looked into: `a5s caps lower <agent> <part> <type of action>`, as one of the part's owners, an instance approver, the agent's owner or assurance. Nobody raises a cap by hand.
4. While the settings in force don't check out, nothing is weighed, and caps stand.

## a5s's reader reads less than a document

**Shows as:** forms an agent got that say `unread` or `cut`.

1. `cut` means the document was longer than a5s's reader reads, and the form holds what its first part says. The agent can ask about it, which reads the same part.
2. `unread` says why: the model didn't answer, the field is of a class the model isn't approved for, the call named more documents than a5s reads at once, or what's left of the run's budget hasn't room. Each is a reason to look at the model, the classes in the settings, or the budget, not at the document.

## People get urgent messages in batches

**Shows as:** urgent messages held for a batch.

1. Someone has had five urgent messages today, such as escalations, across all the agents, so the rest wait and go together once an hour, in their working hours. That's a5s working as it should, and a sign an agent writes too much or that much is falling due.
2. Find which agent wrote them with `a5s ledger tail`: each one held shows as a message sent to `batch`.
3. Tell the agent owner. What isn't urgent belongs in the digest.

## An agent doesn't answer in a group chat

**Shows as:** someone saying it ignores them in a group chat, or an inbound message denied with why.

1. It answers only a message that mentions it, as people do, and it's told so, so it asks for answers that mention it. Anything else in the chat it never hears, and nothing is recorded.
2. A mention it won't work on gets one message saying why, naming who or what's in the way, and the ledger records the reason, which the status counts as a chat turned away, not a denial: someone in the chat the directory doesn't know, such as another organisation's app in Teams, more than 20 people, after which it leaves a Matrix room, a Matrix room that shows people what was said before they joined, which its administrator changes, someone a5s may not write to, or a team's channel in Teams. Nothing else runs.
3. In an encrypted Matrix room it says once that it can't read it: people ask in a room made without encryption, or one to one.
4. If no instance of the agent serves everyone in the chat, it says whom, and who can add them. A version of the settings that serves them all, which the part owners approve, lets it work there, or people ask one to one.
5. If a message can't be read, such as when Teams won't say who's in the chat, the chat hears so and the ledger records it. A Matrix event that fails three deliveries running is skipped and recorded, so it can't hold up the rest.

## An agent's question to another goes unanswered

**Shows as:** an `ask_agent` call that failed because the other agent didn't answer.

1. The status counts questions answered and not over the last day. The question's row in `questions` says why one wasn't: the instance asked was suspended, its asker's day's budget was spent, or it wasn't one the settings let it ask, the run that asked had ended, or the run asked failed, such as when its model was down.
2. The ledger links the two runs: the asked run's `open` names the run that asked, and its `answer` names it too.
3. Nothing is left waiting: the worker that asked runs the run asked itself, so no question waits for a worker, and the agent tells the person it couldn't get an answer. A run asks three questions at most.

## A note in the notebook is wrong

**Shows as:** an agent relying on a note its owner thinks wrong. The status counts notes, and those let go in the last day.

1. The agent's owner, or whoever runs the instance, removes the note on the core's page, `/notebook/`, which shows when each was noted and last checked, with a link to each of its records. The ledger records who removed it.
2. A note goes by itself once its records change, checked each day apart from the retention sweep, so a records system that's down holds up no other sweep: its notes wait to be checked. The notebook keeps its newest 50.
3. A note can't carry anyone's words, nor anything from outside: only a run on a schedule writes one, from records it read, and it reaches only people who may see every record that run read. If one seems to, tell assurance, with the note's number.

## a5s won't start: the database is from a later release

**Shows as:** a service exiting with "the database is at migration N, from a later release of a5s than this one".

1. Someone rolled a5s back after a release migrated its database. The older release doesn't know what the newer migrations mean, such as messages from group chats, so it won't serve.
2. Roll forward to the release that migrated it, or restore the database from before it, and roll back then. Migrations wait for a table's lock 15 seconds at most, and are tried three times, so one that can't get it fails the release rather than holding up a5s.

## Connections to the database run out

**Shows as:** errors that a connection couldn't be had, or Postgres refusing new connections.

1. Each part keeps a pool of `A5S_DB_POOL_SIZE` connections, 10 by default, and connects afresh only as many again while they're all in use. Past that, work waits ten seconds for the pool and then fails, to be tried again. So each part uses at most twice its pool: size Postgres's limit to that, for every replica of each part.
2. Work that waits behind the ledger's lock for 30 seconds fails, and is tried again: look for what held it, such as a slow records system read inside a transaction.

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

## A request for someone's data

**Shows as:** the data protection officer asking for what a5s keeps about someone, such as for their request to see it.

1. The officer signs in and puts their sign-in in `A5S_TOKEN`, beside someone from the team that runs a5s, whose service token reaches the core, and they run `a5s export --person <id> --out <file>` with the person's id in the directory. It needs both: the team can't export without the officer's sign-in, nor can anyone else with a role, or the person themselves.
2. The file holds all a5s keeps that names them, and only the officer may read it: the command writes only a new file. It gives nobody else's words, only how much they heard others say in group chats or were answered there, and names records by key and title: what records hold is the records system's to answer for.
3. If they've left, the command names each archive of their id, and the officer exports it the same way, by its name: `--person former:...`. An id the directory later gave someone else exports only its new holder's.
4. The ledger records the export, by whom and for whom, in counts. Delete the file once it's answered.

## A request to erase someone's data

**Shows as:** the data protection officer asking a5s to erase what it keeps about someone, at their request.

1. Export it first, if the officer wants a copy of what goes (above): erasure can't be undone.
2. The officer signs in, beside someone from the team that runs a5s, as for an export, and they run `a5s erase --person <id> --confirm <id>`, with the id twice, so that a mistyped one erases nobody. An archive's name erases that archive alone.
3. It says how much of each kind went. What's evidence of what agents did stays: the ledger, runs, the changes asked for them with their decisions and samples, and what they owe while the records owe it, which the records system answers for. If they're still here, an agent that wrote first to them waits until they write again, since the chats a5s wrote in go too.
4. The ledger records the erasure, by whom and for whom, in counts, and nothing that went.

## Old conversations aren't deleted

**Shows as:** the scheduler's log saying it couldn't ask the core to delete what's past its time.

1. The scheduler asks the core every hour, and the ledger records what each sweep deleted. A sweep that finds nothing to delete records nothing.
2. Check that the scheduler is running and can reach the gateway. Nothing is lost while it's stopped, but a5s keeps what it said it would delete.
3. If it stopped for more than a few days, tell the data protection officer.

## An objective is missed

**Shows as:** `missed` beside replies or chases. `Not known yet` means nothing was answered or fell due: check the runs line, since a day of failed runs answers nothing.

1. Slow replies: look at the queue and at model latency in the traces, then at the sections above.
2. Late chases: check that the scheduler sweeps every minute, and that the records can be read. While they can't, nothing owed changes.
