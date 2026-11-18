# Runbooks

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md#operations)

For the team that runs a5s. `a5s status` shows how a5s did over the last day, and the gateway's `/status` gives the same to a dashboard. Each section below says what to do when one of its lines goes wrong. Who's on call, and for what, is [below](#on-call).

To follow one run, find its spans by `a5s.run.id`, where the deployment sends traces (`OTEL_EXPORTER_OTLP_ENDPOINT`), and its entries with `a5s ledger tail`, or `a5s runs show <run>`. Traces are for debugging. The ledger is the evidence.

The gateway sends the status's figures to the same endpoint as OpenTelemetry metrics, each minute, named `a5s.*` ([`core/metrics.py`](../src/a5s/core/metrics.py)), so the organisation's monitoring can alert on them: `a5s.status.readable` at 0 when the gateway can't read its status, which is the database ([below](#connections-to-the-database-run-out)); `a5s.queue.oldest` when [messages are waiting](#messages-are-waiting); `a5s.breakers.open` when [a model isn't answering](#runs-fail-or-a-model-isnt-answering); `a5s.changes.stuck` and `a5s.unsealed` when [changes stop part way, or aren't sealed](#changes-wait-or-stop-part-way); `a5s.instances.not_active` when [an instance isn't active](#an-instance-isnt-active); and `a5s.ledger.copies.stopped` or `a5s.ledger.copies.failing` at 1, `a5s.ledger.copies.age` past half an hour, `a5s.ledger.check.problems` above 0, or `a5s.ledger.check.age` past two days, when [the ledger's copies stop](#the-ledgers-copies-stop), as the copier records them each minute it looks, or can't, and each day it checks the whole ledger. `a5s agents`, `a5s runs <instance>` and `a5s measures --instance <instance>` show one agent's or instance's part in it.

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
3. Restart the scheduler if it's stuck. A message outlives a scheduler that stops: the next one takes it again once the lease runs out, so nothing is lost or answered twice. A message whose run had begun isn't run again, since the run may have done something already: once the stopped scheduler's lease on it has lapsed two minutes, the core's next sweep closes the run as abandoned, and its person is told to send it again, unless they had their answer. A task's slice ends the same way, and the task goes on from what it kept.

## Runs fail, or a model isn't answering

**Shows as:** runs ending `failed` or `model unavailable`, or a breaker open.

1. A breaker opens after three failures in a row, and a5s tries the model again every five minutes on its own. People are told at once that the model isn't answering.
2. Check the provider's own status, and that its key is set where the gateway runs.
3. A model that answers with another model's name is refused (`model_mismatch`). That's the provider changing its model, not a5s failing: tell the agent owner.
4. There's no failover to a model that isn't approved. Moving an agent to another approved model is a new release, which the release approver signs.
5. For slow providers, the provider timeout is `A5S_PROVIDER_TIMEOUT` (180 seconds by default), and the worker's calls to the core use `A5S_WORKER_TIMEOUT` (240), which should stay longer. The database's connection timeout is `A5S_DB_CONNECT_TIMEOUT` (2). Change them deliberately and record why, rather than letting calls wait forever.

## Budgets run out

**Shows as:** an instance's tokens past four fifths of a person's day, runs ending `budget spent`, or people told an agent has used its budget.

1. Look for one run that used far more than the rest: an agent going round in circles stops at its run's budget, and the ledger shows each model call.
2. Chases and reminders go on, on the fifth of each day kept for them. Reports wait for the next day. A person's tasks stop at three fifths, so their own chat goes on beside them, and a task put off says so in its `last_error`.
3. Budgets come with the release, so raising one is a new release that widens the agent, which the release approver signs. Don't raise one to get through a bad day.

## Deliveries a chat didn't take

**Shows as:** deliveries being tried again, or left in people's local inbox.

1. a5s tries a message a chat didn't take after a minute, then two, four and eight. After five tries it leaves it in the person's inbox in the web chat and on the command line, and the ledger records a `message fallback` with the chat's answer.
2. Read why with `a5s ledger tail`: a chat that's down, a bot's credentials that expired, or a person who left the conversation.
3. Mend the chat. What's already in someone's inbox stays there, so tell them where to find it if they don't use the web chat.
4. An answer kept back from a group chat someone joined while it was worked out isn't a chat that's down: the status counts it apart. It goes to whoever asked, in a chat of their own, which a5s starts on Matrix, or else their inbox in the web chat, and the group hears where it went.

## Changes wait, or stop part way

**Shows as:** changes waiting for a decision for days, changes approved but not made, or one stopped part way through being made.

1. A waiting change reminds each of its deciders, in their own hours, after two working days, then tells their managers, or else the instance's owner or deputy, but never one of its deciders nor whom it's for, after five, when whoever asked hears in their digest that it waits still; it lapses after ten, telling whoever asked for it and, in their digest, those it waited for. Once one decider's decision settles a change, another's is refused at once, naming who decided; and an approval while the instance is suspended is refused, so reject it, or approve it once the instance is at work again. Its deciders are worked out afresh each time, so a part's new owner, or a delegate its owner names with `part-delegate:<part>`, decides what waits there. Nothing needs doing unless a part has nobody who may decide: then the change isn't held at all, and the agent says why.
2. A change approved but not made says why in the outcome its asker was told: its record changed after it was asked for, the instance may no longer act, or the records system didn't take it. They can ask again.
3. A change stopped part way means a5s marked it as being made, and stopped, or the sweep failed for it, before it could record what happened: the gateway's log says `couldn't sweep P-n`. a5s never makes it again by itself. `a5s proposals` lists such changes. Check the record in the scenario's own system, then end it with `a5s proposals end P-n`, as its instance's owner or deputy, an owner of a part it touches, an instance approver or assurance: whoever asked is told it may or may not have been made, and can ask again.
4. A decision that doesn't count shows once in the gateway's log: a decision the core didn't seal, or by someone who may no longer decide it. A sign-in the gateway refused when it checked it again, before sealing, is in the ledger as `refuse-sign-in`: the person decides again. Tell assurance about any of these that nobody can explain, since each could be someone writing what the channels app writes.
5. The status counts the approvals, decisions and grades the gateway hasn't sealed in five minutes. They don't count until it does, and it seals each minute, so any at all mean it can't: its log says why, such as no seal key (`A5S_SEAL_KEYS`) or identity provider. Set it, and it seals them at its next sweep. One left more than a day is refused, and its person decides again.

## Samples wait to be graded, or a cap falls

**Shows as:** samples waiting to be graded, samples that lapsed ungraded, or caps lowered in the last day.

1. Samples are graded in the studio, `/studio/grade`, by people who hold the grader role, from outside the teams that build and run the agent. A backlog only slows an agent coming to act on its own: ask the scenario's owners for graders. A sample nobody grades in a quarter lapses, and goes after a year.
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
2. A mention it won't work on gets one message saying why, naming who or what's in the way, and the ledger records the reason, which the status counts as a chat turned away, not a denial: someone in the chat the directory doesn't know, such as another organisation's app in Teams, more than 20 people, after which it leaves a Matrix room, a Matrix room that shows people what was said before they joined, which its administrator changes, someone a5s may not write to, a team's channel in Teams, or a channel in Slack, where only whoever mentioned it is told. Nothing else runs.
3. In an encrypted Matrix room it says once that it can't read it: people ask in a room made without encryption, or one to one.
4. If no instance of the agent serves everyone in the chat, it says whom, and who can add them. A version of the settings that serves them all, which the part owners approve, lets it work there, or people ask one to one.
5. If a message can't be read, such as when Teams or Slack won't say who's in the chat, the chat hears so and the ledger records it. A Matrix event that fails three deliveries running is skipped and recorded, so it can't hold up the rest.

## An agent's question to another goes unanswered

**Shows as:** an `ask_agent` call that failed because the other agent didn't answer.

1. The status counts questions answered and not over the last day. The question's row in `questions` says why one wasn't: the instance asked was suspended, its asker's day's budget was spent, or it wasn't one the settings let it ask, the run that asked had ended, or the run asked failed, such as when its model was down.
2. The ledger links the two runs: the asked run's `open` names the run that asked, and its `answer` names it too.
3. Nothing is left waiting: the worker that asked runs the run asked itself, so no question waits for a worker, and the agent tells the person it couldn't get an answer. A run asks three questions at most.

## Tasks wait, or their slices lapse

**Shows as:** the status's tasks line: many due, the oldest for a long time, or slices whose lease lapsed.

1. Tasks due wait for a slot in their agent's pool. Each pool keeps one of its slots for people's messages, which work that falls due never takes, so a pool of one slot runs tasks only between messages. Give a busy agent's pool more slots (`A5S_WORKER_SLOTS`, such as `assistant=8`, or `workers.pools.<agent>.slots` in the chart), or more replicas.
2. A slice whose lease lapsed was cut off, as when its worker or the scheduler stopped part way: the runs' sweep closes its run, and the task goes on from its last checkpoint in a fresh run, after a wait. Five failed slices in a row fail the task, and its owner hears so.
3. A task ends at the tasks' sweep once its deadline passes, its agent is retired, or its agent no longer serves its owner, waiting on its parts or its owner too. A person's tasks stop short of two fifths of their day with the agent, so a task put off for that says so in its `last_error`, and goes on the next day.

## Sign-ins refused for want of a second factor

**Shows as:** the status's line of refusals for want of a second factor, by what was refused: approving, deciding, grading, the officer's requests, reading the audit trail.

1. Only the identity provider's policy makes a sign-in show a second factor: the people refused can't, and signing in again won't, which a5s tells them, with whom to ask. Check that the provider's policy for a5s's client asks for one, such as a Conditional Access policy in Entra ID, a sign-on policy in Okta or a step-up flow in Keycloak, and that the claim and values in `A5S_OIDC_MFA` are the ones its sign-ins show, such as `amr:mfa` or `acr:<level>` ([the first day](first-day.md#2-peoples-sign-in)).
2. Where the second factor is a level, as `acr:<level>` names it, a5s's pages ask the provider for that level as people sign in to do what counts (`acr_values`), and a provider that supports it asks them for one then.
3. The status counts refusals by the day, and by what was refused, never by whom: the counts go after a week.

## A note in the notebook is wrong

**Shows as:** an agent relying on a note its owner thinks wrong. The status counts notes, and those let go in the last day.

1. The agent's owner, or whoever runs the instance, removes the note in the studio's notebook, `/studio/notebook`, which shows when each was noted and last checked, with a link to each of its records. The ledger records who removed it.
2. A note goes by itself once its records change, checked each day apart from the retention sweep, so a records system that's down holds up no other sweep: its notes wait to be checked. The notebook keeps its newest 50.
3. A note can't carry anyone's words, nor anything from outside: only a run on a schedule writes one, from records it read, and it reaches only people who may see every record that run read. If one seems to, tell assurance, with the note's number.

## a5s won't start: the database is from a later release

**Shows as:** a service exiting with "the database is at migration N, from a later release of a5s than this one".

1. Someone rolled a5s back after a release migrated its database. The older release doesn't know what the newer migrations mean, such as messages from group chats, so it won't serve.
2. Roll forward to the release that migrated it, or restore the database from before it, and roll back then. Migrations wait for a table's lock 15 seconds at most, and are tried three times, so one that can't get it fails the release rather than holding up a5s.

## a5s won't start: the database is older than the release

**Shows as:** a service exiting with "the database is at migration N, and this release of a5s needs M: run `a5s migrate` first".

1. Nobody ran this release's migrations. The chart's migration job and the stack's `setup` run them before the parts start; a part started by hand needs them run first.
2. Run `a5s migrate` as the database's administrator, then start the parts again. A part would otherwise fail later, at the first column it lacks, without saying why.

## a5s won't start: a part connects as the wrong role

**Shows as:** a service exiting with "the gateway connects to the database as postgres, a superuser", or "as another part's role".

1. Each part connects as its own role, which `a5s migrate` makes: the gateway as `a5s_gateway`, the channels app as `a5s_channels`, the scheduler as `a5s_scheduler`. Each role's grants keep its part to its own, and a superuser is bound by none of them, nor by the triggers that keep the ledger and the seals.
2. Give the part its own role's address in `A5S_DATABASE_URL`, as the chart's secrets and the stack's compose file do.

## Rotating the seal key

**When:** on a schedule your security team sets, when someone who held the key leaves, or when the key may have leaked.

The core seals what people approve, decide and grade, the caps it raises, the changes it keeps to undo and the accounts people connect, with the first key of `A5S_SEAL_KEYS`, and takes a seal made with any of them. It remembers each key it starts with by a fingerprint, never the key.

1. Make a new key of at least 32 characters, at random, and put it first in `A5S_SEAL_KEYS`, keeping the old one after it: `new,old`. Only the core holds the keys.
2. Restart the core. Everything counts as before, and the status says how much is sealed with the old key: "Sealed with a key A5S_SEAL_KEYS is moving away from".
3. Run `a5s seal-again` where the core runs, with its settings, such as `kubectl exec deploy/a5s-gateway -- a5s seal-again`. It seals again with the new key everything the old one sealed that still checks out, and retires the old key. What checks out under no key stays as it is, and counts for nothing, as before. It refuses until the core at work seals with the new key.
4. Take the old key out of `A5S_SEAL_KEYS` and restart the core.

If the key may have leaked, sealing again would make anything its holder sealed count. Run `a5s seal-again --leaked` instead at step 3: it retires the old key without sealing anything again, and says what stops counting with it. Then the settings must be approved again, graded samples must raise the caps again before an agent acts on its own, decisions still waiting are decided again, and people connect their accounts again. A key retired as leaked never comes back: the core won't start with it.

## The operators' token

**When:** setting a5s up, or when a token may have leaked.

The scheduler calls the core with the service token, `A5S_SERVICE_TOKEN`, to open runs, answer people and sweep. Operators' commands, such as `a5s status`, `a5s runs` and `a5s audit`, and the Python client, call it with a token of their own, `A5S_OPERATOR_TOKEN`. Where the core has both, each opens only its own routes: an operator's token opens no run and writes to nobody, and the scheduler's does none of an operator's work. Without an operators' token, the service token opens both, as in development.

1. Make the operators' token at random, at least 32 characters, apart from the service token, and set it on the core, the chart's `operator-token` secret, and for whoever runs operators' commands. The scheduler never holds it.
2. Reading the audit trail through the core needs the reader's own sign-in wherever people sign in: `a5s audit` sends it from `A5S_TOKEN`.
3. To change either token, set the new one on the core and on what holds it, and restart both. Each run's opening in the ledger names the token behind it by a fingerprint, so the runs a leaked token opened show.

## a5s won't start: a seal key is missing

**Shows as:** the core exiting with "A5S_SEAL_KEYS no longer holds a key the core sealed with", or "holds a key retired as leaked".

1. Someone took a key out of `A5S_SEAL_KEYS` before `a5s seal-again` retired it. What it sealed would stop counting unsaid: the approvals of the settings in force, so every run would be refused, and the caps, so no agent would act on its own.
2. Put the key back after the first, start the core, and rotate as above. If the key is lost, or leaked, put back any key you still hold and run `a5s seal-again --leaked`, which retires the keys after the first and says what stops counting.
3. A key retired as leaked is in `A5S_SEAL_KEYS` again: take it out.

## Connections to the database run out

**Shows as:** errors that a connection couldn't be had, or Postgres refusing new connections.

1. Each part keeps a pool of `A5S_DB_POOL_SIZE` connections, 10 by default, and connects afresh only as many again while they're all in use. Past that, work waits ten seconds for the pool and then fails, to be tried again. So each part uses at most twice its pool: size Postgres's limit to that, for every replica of each part.
2. Work that waits behind the ledger's lock for 30 seconds fails, and is tried again: look for what held it, such as a slow records system read inside a transaction.

## The database is away

**Shows as:** the status unreadable (`a5s.status.readable` at 0), and each part logging that it can't reach the database, as in a managed database's failover.

1. a5s waits it out. People and their chats are asked to try again in a moment: the channels app answers 503 with `Retry-After: 5` and words the web chat shows its person, and Matrix delivers its transactions again on its own. Runs at work fail, and their people are told they couldn't finish; tasks' slices fail and go on later; the scheduler listens again once it can.
2. Once it's back, a5s answers again within seconds, as the soak test checks with Postgres away for half a minute. A run whose scheduler couldn't close it meanwhile is closed at the next sweep once its lease has lapsed two minutes, and its person is told to send it again, unless they had their answer.
3. If it isn't back within a few minutes, it's the database's own incident: see its provider's status, and its failover's.

## Calls are denied

**Shows as:** many denials of one kind.

1. Read the reasons with `a5s ledger tail`. Each denial names the policy that decided it.
2. `tools-match-the-release`: a scenario's tool changed since the release pinned it. Pin the tools again with `a5s pin`, test, and release.
3. `models-see-only-data-they-are-approved-for`: the instance's model isn't approved for the class of data the settings name. Approve a model for it, or use one that is.
4. `messages-go-only-to-the-audience`: an agent tried to write to someone a5s may not write to. That's usually right: check what it was asked.
5. `settings-must-check-out`: the settings in force don't match their signatures or their rows, so every call is denied until they do. See [settings or the release don't check out](#settings-or-the-release-dont-check-out).
6. `lasting-or-outside-effects-only-on-its-own`: a tool the scenario marks as destructive, or as sending outside the organisation, was called where the agent may not act on its own. Tell the agent owner: unless an agent may act on its own, it drafts and people act.
7. `arguments-fit-the-schema` or `records-are-named-by-key`: the agent called a tool with arguments it doesn't take. Once in a while is the model's mistake. Many in a row may mean the tool's description misleads it: tell the agent owner.
8. `records-can-be-read`: a change named records a5s couldn't read just then, so nobody could decide it as they stood, and a5s asked for nothing. Its records system, or the scenario's code that reads it, is failing: the log says which records and why. The change can be asked for again once they read.
9. `a-change-names-few-records`: one call named more than 20 records to change. a5s reads each as it stands before deciding, so it reads none of so many, and asks the agent to ask for the rest apart. Many in a row may mean its instructions ask it to change records in bulk: tell the agent owner.

## An instance isn't active

**Shows as:** an instance suspended, and by whom, or retired.

1. Only the person who suspended it can resume it: on its page in the studio, `/studio/instances/<id>`, signed in afresh for that alone, or with `a5s resume`, signed in. Resuming someone else's suspension needs the release approver, from outside the team, who sees an instance while it's suspended, and resumes it on its page, signed in afresh with a second factor where the deployment asks for one. The ledger names whose suspension they lifted.
2. One suspended or resumed on its page waits for the core's next sweep, within a minute, which checks that sign-in again. If it waits longer, the status counts it among what waits to be sealed: the core is missing its seal key or can't reach the identity provider, which the log says. A request it couldn't carry out, its person hears of in their digest, with why.
3. A retired instance comes back with a version of the settings that names it again.

## Settings or the release don't check out

**Shows as:** runs refused because the settings in force aren't approved, or because the release isn't approved here.

1. Settings: the reason names whose approval is missing, such as the owner of a part. They sign the version again, with their key, or approve it on a card. If an approver left, whoever holds the role now does.
2. If the core's seal key changed, approvals made on cards need making again.
3. The release: `a5s release status` says what it still needs, and who must sign. Where Flux deploys a5s ([deploy/gitops](../deploy/gitops/README.md)), the check on the pull request that deploys it says the same, and nothing deploys until it passes; each person it still needs signs it in the environment's folder, `a5s release sign --environment`.
4. To roll a release back where Flux deploys a5s, revert the pull request that deployed it: Flux deploys the release before, whose approval the core has recorded already.

## The ledger's copies stop

**Shows as:** the copier exiting with an error, `a5s status` saying the ledger's copies stopped, or that the copier's last try failed, with `a5s.ledger.copies.stopped` or `a5s.ledger.copies.failing` at 1, the copies falling behind the ledger for more than 15 minutes, the copier's daily check of the whole ledger finding a problem, which `a5s status` and the auditors' page name, with `a5s.ledger.check.problems` above 0, or `a5s ledger verify` failing. The status says why the copier stopped in its own words; what a store answered stays in the copier's log, since it may name the store.

1. Don't restart the copier to make the error go away. It stops when the ledger no longer matches its copies, which means the history changed.
2. Run `a5s ledger verify`, and tell assurance what it says.
3. If the copier says the ledger's copies hold entries the database lacks, the database was restored from a backup: see below. If nobody restored it, someone wrote to the store with the copier's own credentials, its database role's and the store's, since only the copier marks a copy as its own: don't run `a5s restore`; change those credentials, and tell assurance.

## Restoring from a backup

**When:** the database is lost or damaged, and you restore it from a backup.

A database restored from a backup lacks what a5s did since the backup was taken: the ledger stops there, though its locked copies go on, and what a5s sent since looks unsent.

1. Stop every part of a5s, and restore the database from the backup.
2. Before any part starts, setup included, run `a5s restore` with the core's database address, as its role, and the copier's store: in the copier's container, which reaches the store, with the core's address in its place. On the container stack, `docker compose run --rm --no-deps -e A5S_DATABASE_URL=postgresql://a5s_gateway:<the core's password>@postgres:5432/postgres anchor restore`. On a cluster, install or upgrade the chart with `restore.id` set to the backup's name, such as `--set restore.id=<the backup's name>`, or in the environment's values where Flux deploys it: a job runs `a5s restore --id <the backup's name>` first, before setup, as `<release>-restore`, an account with the copier's annotations and labels, and the parts start once it's done. It runs once for each name, so the value can stay until the next restore. Setup applies the settings, which writes to the ledger, so it runs only after. If `a5s restore` says the database needs migrating, as when the image is newer than the backup, run `a5s migrate` first, as the administrator: it writes nothing to the ledger. It:
   - puts back into the ledger the entries its copies hold beyond it, each as its copy has it, from the copies the copier marked as its own alone;
   - takes as answered each message, as worked on each event, and as fired each schedule, whose run opened since the backup, as those entries say, so no agent answers or acts on one again, nor makes again a change it made;
   - erases again each person an erasure since the backup erased, whom the backup brings back, keeping nothing of theirs, not even where a5s writes to them first, which comes back once they write; and names any it can't, such as an archive erased by its name, for the data protection officer to ask again;
   - holds what a5s was to send through a chat, which waits in each person's local inbox instead, saying it may have gone already;
   - and starts each mailbox afresh from now, so mail read since the backup starts no run again.

   It says what it did, and the ledger records it. Run it after any restore, even where the copies hold nothing beyond the ledger: what a5s sent since still looks unsent.
3. Start a5s. The copier goes on from the entries put back.
4. Look through what the database lost, which the entries put back name: runs and the changes they made in other systems, held changes that were waiting for a decision, which people ask for again, conversations, approvals of the settings, and grades. Mail that came into each mailbox since the backup waits there for the team. Digests, reminders, chases, reports and the steps of tasks that fell due since the backup may come again. Entries written after the last copy are lost with the database: up to 15 minutes' of them, and a minute's of what people decided.

Until `a5s restore` runs, the copier copies nothing, saying "the ledger's copies hold entries N to M, which the database lacks", so the copies never fork, and a core given `A5S_ANCHOR_STORE` too, to read, won't start. If any part wrote to the ledger first, such as setup or a core without it, the copier, or `a5s restore`, says "the ledger no longer matches its copy": stop a5s, restore the backup again, and run `a5s restore` before any part starts.

## A request for someone's data

**Shows as:** the data protection officer asking for what a5s keeps about someone, such as for their request to see it.

1. The officer asks in the studio, `/studio/officer`, signed in afresh: export, and the person's id in the directory, or an archive's name, or, for someone outside the directory, such as a customer who wrote to a shared mailbox, their address. The page says whose the id is in the directory now, and the command to run, which takes the address in the id's place. For an address, the file says where a5s keeps it, and how much, with the changes that name them: the texts that hold it are other people's conversations, for the officer to read in the organisation's records if the request needs them.
2. Within ten minutes, someone from the team that runs a5s, whose service token reaches the core, runs `a5s export --person <id> --out <file>`. It needs both: the team can't export without the officer's request, which does nothing else and works once, nor can anyone else with a role, or the person themselves. If ten minutes have passed, the officer asks again.
3. The file holds all a5s keeps that names them, and only whoever runs the command may read it: the command writes only a new file, which goes to the officer. It gives nobody else's words, only how much they heard others say in group chats or were answered there, and names records by key and title: what records hold is the records system's to answer for.
4. If the id was archived, the command names each archive, with when its holder left. An id the directory later gave someone else exports only its new holder's, so an archive may be someone else's: the officer asks for each that's the person's by its name, `former:...`, and the team exports it the same way.
5. The ledger records the request and the export, by whom and for whom, in counts. Delete the file once it's answered.

## A request to erase someone's data

**Shows as:** the data protection officer asking a5s to erase what it keeps about someone, at their request.

1. Export it first, if the officer wants a copy of what goes (above): erasure can't be undone.
2. The officer asks on the core's page, as for an export: erase, with the id twice. The team runs `a5s erase --person <id> --confirm <id>` within ten minutes, with the id twice again, so that a mistyped one erases nobody.
3. By an id, it erases what its holder now has said since the id's last archive, and lists the archives, which it leaves: if the person asking has left, the officer asks to erase their archive by its name instead, and the team erases that the same way. Check the page's name for the id against the person asking.
4. If a5s is at work for them just then, it says so and erases nothing: try again in a minute or two, while the request lasts. For an address, it waits too while a change that names them waits for a decision, naming it: its deciders decide it first, and the request lasts through the refusal.
5. It says how much of each kind went. What's evidence of what agents did stays: the ledger, runs, the changes asked for them with their decisions and samples, and what they owe while the records owe it. If they're still here, a5s still writes to them where it did, without a word they said.
6. The ledger records the erasure, by whom and for whom, in counts, and nothing that went.

## People the directory no longer names

**Shows as:** the status saying people the directory no longer names wait to be archived.

1. a5s archives someone a day after the directory stops naming them. When more than three, and more than a third of everyone a5s keeps anything for, go missing at once, it waits a week, since that's more likely the directory than people leaving.
2. Check the directory, or the scenario's connection to it: a group emptied by mistake, or a refresh that failed. Once it names them again, they're forgotten as missing, and nothing was archived.
3. If they really did leave, nothing needs doing: a5s archives them once they've been missing a week.

## Old conversations aren't deleted

**Shows as:** the scheduler's log saying it couldn't ask the core to delete what's past its time.

1. The scheduler asks the core every hour, and the ledger records what each sweep deleted. A sweep that finds nothing to delete records nothing.
2. Check that the scheduler is running and can reach the gateway. Nothing is lost while it's stopped, but a5s keeps what it said it would delete.
3. If it stopped for more than a few days, tell the data protection officer.

## An objective is missed

**Shows as:** `missed` beside replies or chases. `Not known yet` means nothing was answered or fell due: check the runs line, since a day of failed runs answers nothing.

1. Slow replies: look at the queue and at model latency in the traces, then at the sections above.
2. Late chases: check that the scheduler sweeps every minute, and that the records can be read. While they can't, nothing owed changes.
