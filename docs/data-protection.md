# Data Protection

**Status:** Draft, for the data protection officer · **Under:** [Architecture](architecture.md)

What the data protection officer's assessment needs to know about a5s before any of the pilot team's data reaches a model ([pilot](pilot.md), stage 2). It says what a5s keeps about people, why, where, for how long and who can see it, what models see, how a request for someone's data is answered, and what the officer decides. The design is in the architecture's [data protection](architecture.md#data-protection); this page is the inventory, from the code.

## Whose data

- **The team's people.** The directory names each of them: their id, such as Entra ID's object id, their name, roles, reporting line, working hours and time zone, and what they may see. a5s reads the directory through the scenario, and its own records name people by their id, though what a5s and the agents say to them uses their names.
- **What they and the agents say to each other,** one to one, and in the group chats they bring an agent into.
- **What the records system holds,** such as customers' questions, names and amounts. It stays in the records system: a run reads it through the scenario's tools, and a5s keeps what the table below says, such as a record's key and title for what someone owes.
- **Whoever decides, grades or approves,** by their id, with what they decided.

## What a5s keeps

| What | What it holds | Why | How long |
| --- | --- | --- | --- |
| Conversations: what each person and agent said, its summaries, the messages a5s received and sent for it, and what waited for a digest | The words, by the person's id. In a group chat, who said each turn and who heard it. What an agent wrote keeps a value it passed as a handle as the handle; the message a5s sent keeps it filled in, as the person read it | So an agent picks up where they left off, and answers about the past from what was said | 12 months after the last thing either said |
| Notes on how someone likes to work | In their own words, as an agent offered it, kept once they said yes | So agents work the way they asked | Until they ask an agent to forget it, at once. Otherwise 12 months after it ended, or after it was offered if they never said yes |
| Their preferences, such as their digest's time, what reports last told them of each of their records, and the chats a5s writes to them in | The setting, each record as last told, and each chat's own ids | So agents keep to their settings, a report says only what changed, and a5s reaches them | While they're here. When they leave, the first two go, and their chats are archived, until the record of their archive goes |
| Reminders | What, when, and for whom | To remind them | 12 months after it was given or cancelled, or offered if nobody said yes |
| What people owed | A record's key and its title from the records, whose it is, from when a5s owed it to them, when it fell due and was done or handed to someone else, whether an agent chased it or took it up the line, and what they said they're waiting on, in their words | To chase and escalate, from the records, to stop chasing while someone waits, and for the measures | While the records owe it, and 12 months after they stopped. What someone's waiting on, 12 months after they said it, and never past their leaving. What a scenario the deployment no longer runs owed, 12 months after it last changed |
| Held changes, and their decisions | The change asked for, the records as they stood, whom it was for, who decided and when | So a change waits for its decision, and the decision is evidence | 12 months after it ended |
| Samples of agents' changes | The change, the records as they stood, whom it was for, who decided it, and its grade and grader | Grading, which sets how much an agent may do | 12 months after it was graded, or drawn if nobody graded it |
| Questions agents asked each other | The question and its answer, and whom they were for | So an agent can ask another, for the same people | 12 months after it was asked |
| Tasks | What someone asked an agent to do over more than one run: the task in their words, its plan, partial results and result, whom it's for, its budget and deadline | So the work outlives any one run or worker, and its owner sees how it goes | 12 months after it and its children ended, or passed their deadline. Archived when its owner leaves, which ends what was still open |
| The notebook | What an agent learned from records, with their keys. Nobody's words, since only a run that acts for nobody notes anything | So later runs know what to check | Until its records change, checked each day, and only its instance's newest 50 |
| What a run handled: values passed as handles, what it read, and documents from outside | Sensitive values, such as contacts, and what the records and documents said | So a run can pass on values it never sees, and code can check what it says | An hour after the run ends |
| A person's use of each day's budget, and the log of their digests | Tokens used each day, and when their digest went | So a budget holds for the day, and the digest goes once a day | Their last two days, and nothing once they leave |
| Runs and the ledger | For each run and call: whom it acted for, by id, the tool or model, the keys of the records it handled, what was decided and why, and what was said only by hash and length, never the words | Evidence of what every agent did, for whom, under which settings | As long as the records it supports [TBC: the officer and assurance]. Its copies are in locked storage, where nobody can delete them before their time |
| Departures | Whose archive is which, once someone has left. The ledger records that they were archived, but not the archive's name | To answer a request for a leaver's data | Once nothing is left under the archive's name, such as what they said in a group chat that's still going, and 12 months after archiving at the soonest |
| The officer's requests | What the officer asked for, for whom, and the sign-in that asked, kept until it's carried out | So the team carries out only what the officer asked for, once | A day |
| Traces | Masked spans: no prompt, reply, message, tool argument or person | To find what's slow or failing | 14 days |
| Operators' figures | The status's counts and times, by model, tool, trigger and outcome, and by instance for those serving at least 5 people: no person, record or anything said | So the team that runs a5s sees how it's doing in its own monitoring | The monitoring's own [TBC] |
| Logs | What each service did. A few lines name a person by id, or a record by key, such as a budget's warning. Never what was said | To run a5s | The platform's [TBC] |

Someone who leaves is archived a day after the directory stops naming them, or a week, if so many go missing at once that it looks like the directory: what a5s kept for them goes under a name no person has, on the same clocks, what only served them while they were here goes, and so does what they said they were waiting on. A group chat's summary that held anything they said goes too, and the group's next run makes it again from its turns, where the archive's name stands for them ([`core/departures.py`](../src/a5s/core/departures.py)). The retention sweep runs every hour and records in the ledger, in counts, what it deleted ([`core/retention.py`](../src/a5s/core/retention.py)).

## Where it is

- **a5s's database,** a managed Postgres in the deployment's region [TBC: which], and nowhere else. Nothing is copied out, apart from the ledger.
- **The ledger's copies,** in locked object storage in the same region, which the copier writes and nobody can delete before their time.
- **The models,** each in the region its approved entry names ([`config/models.yaml`](../config/models.yaml)). The model gateway refuses any model not on the list, and a failover to one.
- **Traces, operators' figures and logs,** in the platform's telemetry, which the deployment names [TBC: which, and where].

## What models see

- **A run's context:** the conversation it continues, what the records it read hold, its notes, and its instructions. Only what everyone it acts for may see.
- **Not classified values.** The settings classify fields, such as a customer's name as personal, and a model sees only classes its approved entry allows. Others it sees as tokens. Values the agent shouldn't retype, such as contacts and bank accounts, it sees only as handles.
- **Not outside content,** such as an email's body, which only the extractor reads, filling a fixed form.
- **Cached for minutes.** A provider may keep what a run sent for a few minutes, so its next call reads it from a cache, for less. Deep Agents asks Anthropic models to, at the points it marks, and the model gateway asks for the shortest time a provider keeps it, whatever the worker asked. DeepSeek does it of itself. [TBC: the approved provider's terms for what it caches.]
- **For the pilot,** one model on the organisation's approved list for the class of the team's data, such as one it runs in its own subscription. Models hosted by DeepSeek and Qwen see synthetic data only. [TBC: the approved model's provider keeps no prompt, and trains on none, under its terms.]

## Who can see it

- **Each person,** signed in: their own conversations, summaries and inbox, and in a group chat what everyone there heard.
- **An agent's run:** only what everyone it acts for may see, as the directory says.
- **Deciders:** the changes they may decide, on the core's page, signed in afresh for each decision.
- **Graders:** samples of records they may see, on the core's page. Never from the team that built the agent, nor anyone a change was for or who decided it.
- **An instance's owner:** its notes whose records they may see, on the core's page.
- **The people who run an instance, own its agent, own or decide for one of its parts, or approve instances:** on the studio's page, `/studio/`, its figures, which count people and never name them, and the runs whose every record they may see: when each ran, what kind of thing started it, for how many people, the keys of the records it handled, which a5s keeps with the run, and its tool calls with the policy's decisions and their ids. Nothing anyone said, not even by its hash, which a short text can be guessed back from. Whom each run acted for, by name, only once the officer agrees, as deciders and graders see whom a change was for: until then it's off (`A5S_STUDIO_NAMES`). [TBC: the officer, before the pilot's stage 1.]
- **The team that runs a5s:** the status and the measures, which count people and never name them; the held changes that wait, by whom they're for (`a5s proposals`); the ledger, by ids and hashes; and every instance's runs, with whom each acted for and its entries in the ledger (`a5s runs`).
- **Anyone with access to the database itself** sees everything a5s keeps. [TBC: who, with the cloud's access reviews, and its audit log of who connected.]
- **The data protection officer:** the record of whose archive is which, and for a request to see someone's data, all a5s keeps about them, which someone from the team that runs a5s carries out for them.

## A request for someone's data

- **How the officer asks.** On the core's page, `/officer/`, signed in afresh for that request alone: to export, or erase, all a5s keeps about one person. Someone from the team that runs a5s carries it out, once, within ten minutes, with the core's service token: `a5s export --person <id> --out <file>`, or `a5s erase --person <id> --confirm <id>`. Neither can do it alone: the team can't without the officer's request, and the officer's sign-in does nothing else, for nobody else, and only once. The ledger records the request, with the sign-in by its hash, and what was done ([`core/officer.py`](../src/a5s/core/officer.py)).
- **To see it:** all a5s keeps that names them, as the table above lists it, one holder at a time. Since the directory may give a leaver's id to someone new, an export by id gives what's its holder's since its last archive, and lists its archives, each of which may be someone else's who held the id before: the officer exports each that's the person's by its own name. It gives nobody else's words: in a group chat, what they said, and their corrections to its summary, and how much they heard others say or were answered there, and of a question agents asked for others too, only that it was. It names records by key and title, and changes by what they do, never what records held, which is the records system's to answer for, nor whom else a change was for. What the ledger and runs hold, which is what was said only by hash, it counts, by what each entry records. The ledger records each export, by whom and for whom, in counts ([`core/export.py`](../src/a5s/core/export.py)). It gives the tasks they asked agents to do, in their words, with what each did, and counts those someone else asked for them.
- **To forget a note** on how they like to work: they ask an agent, and it goes at once, leaving no words in the ledger.
- **To correct a summary:** they ask the agent, which corrects it, as they see it.
- **To erase it:** as for an export, one holder at a time. By an id, a5s erases what's its holder's since its last archive: their conversations and summaries, notes, preferences and reminders, what reports told them, their days' budget and digests, what they said in group chats, and each group's summary that held any of it, which the group's next run makes again from what's left, the questions agents asked for them alone, what they said they were waiting on, and what they owed that the records no longer owe. While they're still here, it keeps where a5s writes to them, without a word they said, so what's for them, such as a decision's card, still reaches them. An archive of the id may be someone else's, so it stays, and is listed: the officer erases each that's the person's by its name, which erases it with the record of whose it was. It keeps what's evidence of what agents did, for as long as retention keeps it: the ledger, which keeps what was said only by hash, runs, which name whom they acted for, the changes asked for them with their decisions and samples, and what they owe while the records owe it. Where they were in a group chat, a name no person has stands in their place, and only the runs kept as evidence link it back to them; the agents' answers there are the group's and stay. While a run is at work for them, which might write what it read of them after they're gone, it waits: the team tries again in a minute or two. The id, sent twice, guards against a mistyped one, and the ledger records each erasure, by whom and for whom, in counts ([`core/erasure.py`](../src/a5s/core/erasure.py)). It erases the tasks they asked agents to do, with what each did, and waits, as for a run, while a task's slice is at work for them.
- **What the records system holds** is the records system's to answer for.

## Measures

`a5s measures` and the status count people and never name them. Measures of individual people judge outcomes, not speed, and they're agreed with the officer, and with works councils where there are any, before they start ([assurance](architecture.md#assurance)). The flag for deciders who approve what graders find wrong profiles people, so it's off until the officer agrees ([starting values](starting-values.md)).

## What the officer decides

- The lawful basis for each use above. [TBC]
- The retention periods: 12 months for conversations and what goes with them, and how long the ledger and runs are kept as evidence. [TBC]
- The approved model for the class of the team's data, and its provider's terms. [TBC]
- Who may reach the database itself, and how that's reviewed. [TBC]
- What erasure keeps as evidence of what agents did, and for how long. [TBC]
- How long the platform keeps logs. [TBC]
- The measures, and the flag for deciders. [TBC]
- Whether a works council must agree. [TBC]
