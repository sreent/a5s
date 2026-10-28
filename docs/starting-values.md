# Starting Values

**Status:** Draft v0.2 · **Under:** [Architecture](architecture.md)

These are the numbers a5s starts from, by the phase that needs them. They're starting values, not decisions: each is baselined in the first months and then set, and loosening one later needs someone outside the team ([independence](architecture.md#independence)). People hold [roles](agent-model.md#roles) as each deployment assigns them, and a scenario can bring numbers of its own, such as a limit on how many records one piece of work may change.

## Phase 1

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Context per run | 50,000 tokens, with a budget for each part of the context, tested at release | Keeps a months-long conversation affordable, with room for what matters | The agent owner |
| Settings cache | At most 30 seconds, and a change clears it | A withdrawn approval takes effect within half a minute | The platform owner |
| Ledger anchor | Every hour, with assurance | A rewritten history shows within the hour | Assurance |
| Digest | One a day per person from all the agents together, at a time they choose, 09:00 by default | One place to look, at a time that suits them | Each person |
| Urgent messages | Up to 5 per person per day across all agents, then batched hourly | Urgent stays urgent without becoming noise | The platform owner |
| Chases | Routine items in the last digest before half the turnaround has passed, then escalated when due, but no sooner than a working day after the chase. Urgent items by urgent message at half the turnaround, then escalated when due. | People get a chance to act before anyone above them hears | Each part owner |
| Conversations | Kept for 12 months after the last message, and archived when someone leaves | Covers a yearly cycle | The data protection officer |
| Ledger | As long as the records it supports, which the scenario sets | It's evidence | Assurance |
| Traces | 14 days | For debugging only | The agent owner |
| Budgets | Set from current volumes, with 20% kept for obligations, a warning at 80%, and routine work waiting at 100% | Not from a quiet first month | The platform owner |
| Circuit breaker | Opens after 3 failures in a row, and retries every 5 minutes | Stops quickly, and recovers without anyone stepping in | The agent owner |

## Phase 2

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Moving up a level | A sequential test showing, with 95% confidence, that accuracy meets the part's threshold, pooled across the release's instances. With no errors, a 98% threshold needs about 150 graded items, and a 95% one about 60. | 50 items can't tell a 98% agent from a 95% one | Each part owner, through the threshold |
| Moving down a level | When the evidence shows accuracy below the threshold, or at once on a critical error | One bad month of a small sample is often chance | Each part owner |
| Ongoing samples | About 100 items a quarter per type of action at level 2, or all of them if there are fewer | Notices a fall from 98% to 93% about four times in five, with few false alarms | Each part owner |
| Counting backstop | 30 days, up to the scenario's limit, per person acted for and type of action, or per check | Catches a change spread over weeks without stopping a busy assistant | Each part owner |
| Held proposals | Chased and escalated as above, and expired after 10 business days | Nothing waits forever | Each part owner |
| Rubber-stamping flag | A reviewer whose accepted items fail later samples more often than their peers' accepted items do | Quick reviews of good work aren't a problem | Assurance |
| Outside senders | 20 requests a day per outside sender, then the rest wait for review | Stops a flood without blocking a busy supplier | Each part owner |
| After an authenticator reset | The person's decisions wait 24 hours before they take effect | A reset is how a stolen identity usually starts | The release approver |

## Phase 3

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Notebook entries | Expire after 90 days, and are renewed if their sources still hold | Long enough to learn a quarter's patterns, short enough to forget stale ones | The agent owner |
