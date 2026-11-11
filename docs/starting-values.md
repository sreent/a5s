# Starting Values

**Status:** Draft v0.3 · **Under:** [Architecture](architecture.md)

These are the numbers a5s starts from, by the phase that needs them. They're starting values, not decisions: each is baselined in the first months and then set, and loosening one later needs someone outside the team ([independence](architecture.md#independence)). People hold [roles](agent-model.md#roles) as each deployment assigns them, and a scenario can bring numbers of its own, such as a limit on how many records one piece of work may change.

## Phase 1

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Context per run | 24,000 tokens for the assistant and 16,000 for the watcher, with a budget for each part of the context, tested at release. A topic's summary takes a third of it at most, and keeps its newest 500 facts. | Each model call carries the whole context, so it sets what every call costs | The agent owner |
| Database connections | Each part keeps up to 10 (`A5S_DB_POOL_SIZE`), and a transaction that can't have one within half a second connects afresh | Connecting for each transaction took some 28 connections for each message in the soak test, and pooling takes 2, one for each model call, with answers a quarter faster. Against a managed Postgres each connection is a TLS handshake and a new server process | The platform owner |
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
| Someone who leaves | What a5s keeps for them is archived where it is, a day after the directory stops naming them, and goes on the same clock. Nothing is copied elsewhere | A day lets a directory that missed someone for a while catch up; anything longer leaves their conversation to anyone given the same id | The data protection officer |
| What people owed | Kept for 12 months after the records stopped owing it | The measures look back a month or two, and a record that opens again is owed afresh | The data protection officer |
| A person's use of a day's budget, and the log of their digests | Their last two days, and nothing once they leave | Only their day reads either | The data protection officer |
| Ledger | As long as the records it supports, which the scenario sets, with its copies locked for as long [TBC: a year until it's set] | It's evidence | Assurance |
| Traces | 14 days | For debugging only | The agent owner |
| Budgets | Set from current volumes, with 20% kept for obligations, a warning at 80%, and routine work waiting at 100%. A release's budgets must fit 6 model calls a run and 12 answers a day, of its whole context and 6,000 tokens beside it. The assistant starts at 200,000 tokens a run and 1,000,000 a person a day, the watcher at 150,000 and 700,000. | Not from a quiet first month, and never so tight that ordinary work can't fit | The platform owner |
| Circuit breaker | Opens after 3 failures in a row, and retries every 5 minutes | Stops quickly, and recovers without anyone stepping in | The agent owner |

## Phase 2

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Moving up a level | An anytime-valid sequential test showing, with 95% confidence, that accuracy meets the part's threshold, on the sealed grades given since the cap last changed, pooled across the instances of a behaviour: an agent, its model and the tools of that type it may use, as pinned. With no errors, a 98% threshold needs 224 graded items, and a 95% one 88; with one error, 340 and 134. A critical error, or a fall, means earning it again on new grades. | 50 items can't tell a 98% agent from a 95% one, and a test checked after every grade must stay valid however often it's checked | Each part owner, through the threshold |
| Moving down a level | When the grades given since the cap rose show accuracy below the threshold, at once on a critical error, or when the part's threshold rises past what the grades that earned it show. Anyone who may can lower a cap at once (`a5s caps lower`) | A fresh test after each change notices a fall that the grades which earned the level would hide | Each part owner |
| Ongoing samples | Changes made at level 2, at random, about 100 a quarter for each behaviour, part and type of action, spread through it, and every held change someone decided while the cap is 1. A sample nobody grades in a quarter lapses | Notices a fall from 98% to 93% about half the time within a quarter's 100, and four times in five within two quarters, with false alarms under one in twenty. To notice it within a quarter four times in five, sample about 200 | Each part owner |
| Counting backstop | For each type of action, a limit for one run and one for each person acted for in 30 days, as the scenario's settings set them: the sample's are 5 and 20. Past one, a change waits for a person. | Catches a change spread over weeks without stopping a busy assistant | Each part owner |
| Held proposals | Each decider reminded once after 2 working days, in their own hours; once reminded, their managers, or the instance's owner, told after 5; lapsed after 10. A decision by someone whose authenticator was reset in the last day waits until a day has passed. Kept a year after they end. | Nothing waits forever, and a reset, how a stolen identity usually starts, can't approve a change at once | Each part owner |
| Rubber-stamping flag | Off, until the data protection officer agrees, since it profiles people (O6). Then a decider with at least 3 approvals graded wrong, at over twice the rate of everyone else's, is shown in the status (`A5S_FLAG_RUBBER_STAMPS`, `officerAgrees.rubberStampFlag` in the chart) | Quick reviews of good work aren't a problem | Assurance |
| Whom the studio names | Off, until the data protection officer agrees: people's studio pages show for how many people a run was, and not whom (`A5S_STUDIO_NAMES`, `officerAgrees.studioNames` in the chart). The core's API, for the team that runs a5s, names them | Who asked an agent what, and when, is about a person even without their words | Assurance |
| a5s's reader | The first 24,000 characters of each document, at most 10 documents a call, within what's left of the run's budget, and each document read once a run | One long email can't spend a run's budget, or outlast the agent's wait for its tool | The agent owner |
| Outside senders | 20 requests a day per outside sender, then the rest wait for review | Stops a flood without blocking a busy supplier | Each part owner |
| After an authenticator reset | The person's decisions wait 24 hours before they take effect, by the time the directory says it was reset | A reset is how a stolen identity usually starts | The release approver |

## Phase 3

| Setting | Starting value | Why | Owned by |
| --- | --- | --- | --- |
| Group chats | Up to 20 people, each known to the directory | A run in a group sees only what all of them may see, so a larger group sees little, and each of them counts toward its limits | The platform owner |
| An answer from another agent | Waited for 2 minutes at most, after which the question is given up | Long enough for a run of a few tool calls, short enough that the person asking isn't left waiting | The platform owner |
| Notebook entries | The newest 50 for each instance, of 300 characters, each naming up to 10 records. Each goes once its records change, checked each day | A note is worth keeping only while the records it comes from say what it does | The agent owner |
| Questions one run asks | 3 | Enough to ask two agents and follow one up, and no more of their budgets | The agent owner |
