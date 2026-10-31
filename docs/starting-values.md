# Starting Values

**Status:** Draft v0.3 · **Under:** [Architecture](architecture.md)

These are the numbers a5s starts from, by the phase that needs them. They're starting values, not decisions: each is baselined in the first months and then set, and loosening one later needs someone outside the team ([independence](architecture.md#independence)). People hold [roles](agent-model.md#roles) as each deployment assigns them, and a scenario can bring numbers of its own, such as a limit on how many records one piece of work may change.

## Phase 1

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Context per run | 24,000 tokens for the assistant and 16,000 for the watcher, with a budget for each part of the context, tested at release. A topic's summary takes a third of it at most, and keeps its newest 500 facts. | Each model call carries the whole context, so it sets what every call costs | The agent owner |
| Settings cache | None: the settings in force are checked at every call | A withdrawn approval takes effect at the next call, and settings that stop checking out stop every call | The platform owner |
| Settings requests | 5 a day per person in the settings app, with one waiting at a time, and 64 KB at most | Approvers aren't asked again and again | The platform owner |
| Ledger anchor | Every hour, with assurance | A rewritten history shows within the hour | Assurance |
| Digest | One a day per person, by their own date, from all the agents together, at a time they choose, 09:00 by default. It waits 30 minutes at most for its agents' work. | One place to look, at a time that suits them, and never held all day by work that can't be done | Each person |
| Deliveries | 5 tries for a chat, after 1, 2, 4 and 8 minutes, then the person's local inbox | A chat that's down for a while loses nothing | The platform owner |
| Urgent messages | Up to 5 per person per day across all agents, then batched hourly in their working hours. Reminders people asked for at a particular time don't count. | Urgent stays urgent without becoming noise | The platform owner |
| Chases | Routine items in the last digest before half the turnaround has passed, then escalated when due, but no sooner than a working day after the chase. Urgent items by urgent message at half the turnaround, then escalated when due. | People get a chance to act before anyone above them hears | Each part owner |
| Working hours | From the directory, and otherwise 09:00 to 17:00, Monday to Friday, in each person's time zone. Hours that end before they start cross midnight, as a night shift's do. Chases and escalations wait for them. | Nobody is chased off shift | Each person, through the directory |
| Missed schedules | A time more than an hour past is let go, and one that falls while the instance is suspended isn't made up | No backlog of stale work after an outage or a suspension | The agent owner |
| Conversations | Kept for 12 months after the last message, and archived when someone leaves | Covers a yearly cycle | The data protection officer |
| Ledger | As long as the records it supports, which the scenario sets, with its copies locked for as long [TBC: a year until it's set] | It's evidence | Assurance |
| Traces | 14 days | For debugging only | The agent owner |
| Budgets | Set from current volumes, with 20% kept for obligations, a warning at 80%, and routine work waiting at 100%. A release's budgets must fit 6 model calls a run and 12 answers a day, of its whole context and 6,000 tokens beside it. The assistant starts at 200,000 tokens a run and 1,000,000 a person a day, the watcher at 150,000 and 700,000. | Not from a quiet first month, and never so tight that ordinary work can't fit | The platform owner |
| Circuit breaker | Opens after 3 failures in a row, and retries every 5 minutes | Stops quickly, and recovers without anyone stepping in | The agent owner |

## Phase 2

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Moving up a level | An anytime-valid sequential test showing, with 95% confidence, that accuracy meets the part's threshold, pooled across the release's instances. With no errors, a 98% threshold needs 224 graded items, and a 95% one 88; with one error, 340 and 134. | 50 items can't tell a 98% agent from a 95% one, and a test checked after every grade must stay valid however often it's checked | Each part owner, through the threshold |
| Moving down a level | When the evidence shows accuracy below the threshold, or at once on a critical error | One bad month of a small sample is often chance | Each part owner |
| Ongoing samples | Every change made at level 2 until there are 100 in the quarter for its release, part and type of action, and every held change someone decided while the cap is 1 | Notices a fall from 98% to 93% about four times in five, with few false alarms | Each part owner |
| Counting backstop | For each type of action, a limit for one run and one for each person acted for in 30 days, as the scenario's settings set them: the sample's are 5 and 20. Past one, a change waits for a person. | Catches a change spread over weeks without stopping a busy assistant | Each part owner |
| Held proposals | Their deciders reminded once after 2 working days, their managers told after 5, and lapsed after 10. A decision by someone whose authenticator was reset in the last day waits until a day has passed. Kept a year after they end. | Nothing waits forever, and a reset, how a stolen identity usually starts, can't approve a change at once | Each part owner |
| Rubber-stamping flag | A decider with at least 3 approvals graded wrong, at over twice the rate of everyone else's, shown in the status | Quick reviews of good work aren't a problem | Assurance |
| Outside senders | 20 requests a day per outside sender, then the rest wait for review | Stops a flood without blocking a busy supplier | Each part owner |
| After an authenticator reset | The person's decisions wait 24 hours before they take effect, by the time the directory says it was reset | A reset is how a stolen identity usually starts | The release approver |

## Phase 3

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Notebook entries | Expire after 90 days, and are renewed if their sources still hold | Long enough to learn a quarter's patterns, short enough to forget stale ones | The agent owner |
