# The data protection officer

For the data protection officer: answering requests for someone's data, and the choices about people's data that are yours. What a5s keeps about people, why, where and for how long is in [data protection](../data-protection.md).

## Ask for someone's data to be exported

1. Open **Data protection** in the sidebar, `/studio/officer`: *A request for someone's data*.
2. Choose to **export** all a5s keeps about someone, and say who: their id in the directory, an archive's name, such as *former:9c1e2b7a4d3f0e65*, for someone who has left, or an email address, for a customer who wrote to a shared mailbox.
3. Choose **Sign in and ask**, and sign in again, for this request alone, with your second factor where your organisation asks for one.

The page then gives the command, `a5s export`, for someone in the team that runs a5s to carry it out, once, within ten minutes; after that, the request lapses.

The export holds their conversations and summaries, their messages, notes, preferences, reminders, tasks and drafts, the accounts they connected but never their tokens, the changes asked for them, their decisions and the samples of them, and test cases holding their words. Other people's words in it are only counted, records appear by their key and title, and the ledger and runs as counts. For a customer, it says where a5s keeps their address, and how much.

## Ask for someone to be erased

Choose **erase** instead, and type their id again, since an erasure can't be undone. As for an export, someone in the team that runs a5s carries it out, with `a5s erase`.

- **What goes:** what a5s keeps of them, their words in conversations among it. In a group chat, a name no person has takes theirs, and the agents' answers there stay.
- **What stays, and why:** the ledger, runs, the changes asked for them, and what they owe while the records still owe it, as evidence of what agents did.
- **A customer** who wrote to a shared mailbox: each text holding their address keeps *[an address a5s erased]* in its place, and what runs held of their address, and what was read from their mail, goes. Changes that name them, and their samples, stay as evidence.
- **When it waits:** an erasure is refused while a run is working for them, or holds a customer's address, or while a change naming the customer waits for a decision: try again shortly.
- **Not reached:** the database's backups, so restoring one means erasing again, and the sandbox's own disk.

## One holder of an id at a time

When someone leaves, a5s keeps what it held of them under an archive's name, such as *former:9c1e2b7a4d3f0e65*. If the same id is later given to someone else, an export or erasure of the id reaches only its present holder: an earlier holder's archive is listed apart, and you ask for it by its own name.

## The choices that are yours

A deployment's settings hold seven choices about people's data, which only you approve:

| Choice | What it does | As it starts |
| --- | --- | --- |
| `kept_for` | How long a5s keeps what's said after a conversation's last message, and what goes with it, such as summaries, reminders, held changes and samples: from a day to ten years | 12 months |
| `fewest_people` | The fewest people an instance serves before its runs show one by one, and its figures go to the team's dashboards, since with fewer they'd say what one person did | 5, and never fewer than 3 |
| `studio_names` | Whether the studio's pages name whom each run acted for, rather than how many | Off |
| `audit_names` | Whether the auditors' page names whom agents acted for, and exports the trail | Off |
| `flag_rubber_stamps` | Whether a5s's status names deciders whose approvals are graded wrong far more often than others': profiling people | Off |
| `cases_from_runs` | Whether an agent's authors may keep real runs as test cases | Off |
| `shadow_runs` | Whether new versions may answer beside the instances they'd replace, sending and changing nothing | Off |

There's no form for them. To change one, open **Settings**, choose **Ask for a change**, then **Edit the text**, **Review** and **Ask its approvers**. The version then waits for your approval, which you give as for [any version](approving.md#read-and-approve-a-version), signed in afresh. Letting shadows run is marked as widening what agents do.

For how a5s works this out, see [data protection](../data-protection.md) and [what the officer decides](../data-protection.md#what-the-officer-decides).
