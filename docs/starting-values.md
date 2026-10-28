# Starting Values

**Status:** Draft v0.1 · **Under:** [Architecture](architecture.md)

The design marks with `[TBC]` every name or number it still needs. This page gives each one the value a5s starts from, why, and who confirms it. They're starting values, not decisions. As with the lean framework's own measures, the numbers are baselined in the first months and then set, and loosening one later needs the agreement the [independence](architecture.md#independence) rules ask for.

## Names

The names follow the lean scenario. Another scenario names its own.

| Who | Starting value | Why | Confirmed by |
| --- | --- | --- | --- |
| Release approver, for agents and for a5s's own enforcement | Information security [TBC: who] | Outside the data team and the platform owner's reporting line, and used to judging security risk | The GPDOs |
| Design review | Run by the release approver, with the agent owner and the attribute owners of the parts the agent touches | The owners of the parts know what the agent should do there | The GPDOs |
| Model approver, keeping the approved AI tools list | Information security, with the data protection officer for personal data | R-22 already brings in the data protection officer | The GPDOs |
| Policy pack approver | The release approver | Packs are enforcement, and change like it | The GPDOs |
| Raising a cap by hand | Information security, with the part owner told | It loosens what the evidence set | The GPDOs |
| Stopping a check that detects, such as the change reconciler | Internal controls | They're the ones the checks report to | The GPDOs |
| Agreement to resume an agent someone else suspended, or replace an agent owner who hasn't left | A GPDO | Business owners outside the data team | The charter's signatories |
| Sample graders | The part's delegates, never on items they decided, and internal controls for samples of sensitive changes | They know the data, and none of them built the agent | Each attribute owner |
| Measures of people | Agreed with the data protection officer and, where there are works councils, with them, before they start | They watch employees' work | The data protection officer |
| Retention of conversations and profiles | The data protection officer | They hold colleagues' personal data | The data protection officer |

## Numbers

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Mass-change size | 50 records, unless a profile sets another | R-07's own default | Each attribute owner |
| Counting backstop | 30 days, up to the mass-change size, per person acted for and change type, or per check | Catches a clean-up spread over weeks without stopping a busy assistant | Each attribute owner |
| Proposal timings | Chase in the last digest before half the turnaround, escalate when due but no sooner than a working day after the chase, expire after 10 business days | An urgent bank change with 4 business hours is chased after 2 | Each attribute owner |
| Waiting after an authenticator reset | 24 hours before the person's decisions take effect | A reset is how a stolen identity usually starts | Information security |
| Notebook entries | Expire after 90 days, and are renewed if their sources still hold | Long enough to learn a quarter's patterns, short enough to forget stale ones | The agent owner |
| Conversations | Kept for 12 months after the last message, and archived when someone leaves | Covers a yearly cycle | The data protection officer |
| Ledger | As long as the financial records it supports [TBC: 10 years] | It's audit evidence | Internal controls |
| Traces | 14 days | For debugging only. It's LangSmith's own default for short-lived traces. | The agent owner |
| Digest | One a day per person from all the agents together, at a time they choose, 09:00 by default | One place to look, at a time that suits them | Each person |
| Urgent messages | Up to 5 per person per day across all agents, then batched hourly | Urgent stays urgent without becoming noise | The agent owner |
| Context per turn | 50,000 tokens, split into a budget for each part of the context, tested at release | Keeps a months-long conversation affordable, with room for what matters | The agent owner |
| Budgets | Set from current request volumes, with 20% kept for obligations, a warning at 80%, and routine work waiting at 100% | Not from a quiet first month, such as December | The platform owner |
| Moving up a level | A sequential test showing, with 95% confidence, that accuracy meets the part's quality threshold, pooled across the release's instances. With no errors, a 98% threshold needs about 150 graded items, and a 95% one about 60. | 50 items can't tell a 98% agent from a 95% one | Each attribute owner, through the threshold |
| Moving down a level | When the evidence shows accuracy below the threshold, or at once on a critical error | One bad month of a small sample is often chance | Each attribute owner |
| Ongoing samples | About 100 items a quarter per type of action, or all of them if there are fewer | Notices a fall from 98% to 93% about four times in five, with few false alarms | Each attribute owner |
| Rubber-stamping flag | A reviewer whose accepted items fail later samples more often than their peers' accepted items do | Quick reviews of good work aren't a problem | Internal controls |
| Circuit breaker | Opens after 3 failures in a row, and retries every 5 minutes | Stops quickly, and recovers without anyone stepping in | The agent owner |
| Outside requests | 20 portal requests a day per supplier, then the rest wait for review | Stops a flood without blocking a busy supplier | Each attribute owner |
