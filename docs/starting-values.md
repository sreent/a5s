# Starting Values

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md)

The design marks with `[TBC]` every name or number it still needs. This page gives each one the value a5s starts from, and why. They're starting values, not decisions: each needs its owner to confirm it. As with the lean framework's own measures, the numbers are baselined in the first month and then set.

## Names

The names follow the lean scenario. Another scenario names its own.

| Who | Starting value | Why | Confirmed by |
| --- | --- | --- | --- |
| Release approver, for agents and for a5s's own enforcement | Information security [TBC: who] | Outside the data team and the platform owner's reporting line, and used to judging security risk | The GPDOs |
| Design review | Run by the release approver, with the agent owner and the attribute owners of the parts the agent touches | The owners of the parts know what the agent should do there | The GPDOs |
| Model approver, keeping the approved AI tools list | Information security, with the data protection officer for personal data | R-22 already brings in the data protection officer | The GPDOs |
| Policy pack approver | The release approver | Packs are enforcement, and change like it | The GPDOs |
| Agreement to resume an agent someone else suspended, or replace an agent owner who hasn't left | A GPDO | Business owners outside the data team | The charter's signatories |
| Sample graders | The part's delegates, never on items they decided, and internal controls for samples of sensitive changes | They know the data, and none of them built the agent | Each attribute owner |
| Pair alerts and re-performed call-backs | Internal controls | Independent of everyone in the case | Internal controls |
| Retention of conversations and profiles | The data protection officer | They hold colleagues' personal data | The data protection officer |

## Numbers

| Setting | Starting value | Why |
| --- | --- | --- |
| Call-back contact unchanged for | 90 days | A two-step fraud then needs a quarter's patience, and most suppliers' contacts change far less often |
| Mass-change size | 50 records, unless a profile sets another | R-07's own default |
| Counting window, as a backstop | 30 days, up to the mass-change size | Catches a clean-up spread over several weeks |
| Proposal timings | Chase when half the turnaround has passed, escalate when it's due, expire after 10 business days | An urgent bank change with 4 business hours is chased after 2 |
| Notebook entries | Expire after 90 days, and are renewed if their sources still hold | Long enough to learn a quarter's patterns, short enough to forget stale ones |
| Conversations | Kept for 12 months after the last message, and archived when someone leaves | Covers a yearly cycle [TBC: the data protection officer] |
| Ledger | As long as the financial records it supports [TBC: 10 years] | It's audit evidence |
| Traces | 14 days | For debugging only. It's LangSmith's own default for short-lived traces. |
| Digest | One a day per person from all the agents together, at a time they choose, 09:00 by default | One place to look, at a time that suits them |
| Urgent messages | Up to 5 per person per day across all agents, then batched hourly | Urgent stays urgent without becoming noise |
| Context per turn | 50,000 tokens | Keeps a months-long conversation affordable |
| Budgets | Set from the first month's use, with 20% kept for obligations | There's no baseline yet |
| Samples to move up a level | 50 graded items per instance and change type, at least 98% right and none critical | Matches the 98% quality threshold in the starter profiles |
| Ongoing samples | 5% of the work, and at least 20 items a month | Enough to notice a change within a month |
| Rubber-stamping flag | Over 98% accepted with a median review under 30 seconds, over a month, weighted by size | Very short reviews and almost no rejections, as the operating model warns |
| Pair alert | The same requester and confirmer on more than 3 sensitive changes in 90 days, or on more than a third of a confirmer's | Patterns that rarely happen by chance when confirmers are picked at random |
| Re-performed call-backs | 10% of confirmed bank changes, and all high-risk ones | Enough to deter, without redoing every call |
| Circuit breaker | Opens after 3 failures in a row, and retries every 5 minutes | Stops quickly, and recovers without anyone stepping in |
| Outside requests | 20 portal requests a day per supplier, then the rest wait for review | Stops a flood without blocking a busy supplier |
