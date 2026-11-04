# Phase 3

**Status:** Confirmed on 4 November 2026, and step 1, group conversations, under way ([progress](#progress)) · **Under:** [Architecture](architecture.md)

Phase 3 lets agents work with more than one person at a time, and with each other. In [phase 1](phase-1.md) and [phase 2](phase-2.md), each person has a conversation of their own with each agent, and a5s turns away a chat with anyone else in it. In phase 3, people can bring an agent into a group chat, an agent can ask another what it knows, and an agent can keep a notebook of what it learns from records. Each keeps the rules phase 2 ends with: a run sees only what everyone it acts for may see, authority never passes from one person or agent to another, and what's said to an agent reaches only runs for people who heard it.

## Decide first

Confirmed on 4 November 2026:

| Decision | Proposed |
| --- | --- |
| What comes first | Group conversations, then agent to agent, then the notebook. Groups are what people will ask for first, and they need little that's new: a run already acts for several people when an instance serves a team. Agent to agent builds on the same. The notebook carries the most risk, one person's words reaching everyone, so it comes last, once the others' evidence is in. |
| Which group chats | Teams group chats and Matrix rooms, of up to 20 people, each of them known to the directory. Not Teams channels, whose members are a whole team, until a deployment asks for them. The web chat stays one to one. |
| Who a group run acts for | Everyone in the chat when the message arrives, as the chat itself lists them, so it sees only what all of them may see. An agent answers in a group only when someone mentions it. |
| What reaches someone added later | Only what's said once they've joined: a run loads only the turns said while everyone now in the chat was in it. In Matrix, a5s turns away a room that shows people what was said before they joined. In Teams, whoever adds someone and shares the chat's history shares what a5s said in it too, which a5s can't stop: an accepted risk. |
| What stays one to one | Notes on how someone likes to work, digests, and agents writing first. A reminder asked for in a group is the asker's alone: only they can say yes to it, in a later message of their own, and it reaches them alone. |
| Agent to agent | Only between instances of one deployment, as each instance's settings say, which its part owners approve. The call acts for the caller's people, and the instance asked works within its own grant and what those people may see, never the caller's. An agent that's asked can't ask another. Its answer carries its run's mark, so a run that hears from one that read outside content is marked too. Agents outside a5s wait for a deployment that needs them, and what they say would be outside content. |
| The notebook | An agent notes what it learns from records and tool results alone, never from what people say or from outside content, and a marked run notes nothing. Code checks each entry against its sources, as it checks summaries, and gives it only to runs whose people may see every source. An entry expires after 90 days unless its sources still hold, and the agent's owner can read and remove entries. |
| Managed runtimes | None until a deployment needs one, since the worker runs on Kubernetes everywhere. A runtime would then only run the worker's loop: it would hold no secrets and reach only the gateway, as the worker does. |

## Build, in order

Each step ends with something running and its tests passing.

1. **Group conversations.**
   - Teams and Matrix take a message in a group chat when it mentions an agent. The core reads who's in the chat from the chat itself, at each message: from the Bot Framework in Teams, and in Matrix from the organisation's homeserver, which vouches only for its own people. A chat with anyone the directory doesn't know, or with more than 20 people, gets one message saying why, and nothing more.
   - A group conversation belongs to its chat, with topics and summaries as a person's own conversation has. Each turn records who said it, and who was in the chat.
   - A run in a group acts for everyone in the chat, so it finds, sees and says only what all of them may see, and its changes count for each of them. Its context loads only the turns said while everyone now in the chat was in it.
   - A reminder offered in a group is the asker's alone: only they can say yes to it, and it reaches them alone. Notes on how people like to work, and agents writing first, stay one to one.
   - A group conversation goes 12 months after the last thing said in it. What someone who leaves said in a group stays there, under their archive's name.
2. **Agent to agent.**
   - An instance's settings name the instances it may ask, which their part owners approve. A typed tool asks one of them a question.
   - The core opens a run of the instance asked, acting for the same people as the caller's run, with the question as a5s's notice. Its answer comes back as the tool's result, carrying its run's mark. An agent that's asked can't ask another, and the ledger links the two runs.
   - What the instance asked proposes or does, it proposes or does for those people, within its own grant and level, and nobody the call acts for decides what it holds.
   - The question and the answer take A2A's shapes for a message and a task, so agents outside a5s can come later without a second way of asking.
3. **The notebook.**
   - A typed tool notes something learned, naming the records and tool results it comes from. Code keeps the entry only if every key, amount and date in it is in those sources, and a marked run can't use the tool.
   - A run is given the entries whose every source its people may see, within a budget.
   - A sweep renews each entry whose sources still hold at 90 days, and lets the rest go. The agent's owner reads and removes entries on the core's page.
4. **Adapters for managed runtimes,** only once a deployment needs one.

## Done means

- Each finding the [critique](critique.md) marks for phase 3 has a test in a5s's own suite that shows the code stops it: A9, C1 and C9, and F6 for group chats.
- In the sample, two people in a Matrix room ask the assistant about a record only one of them may see, and it answers only from what both may see. Someone added to the room later gets nothing said before they joined. The same holds in a Teams group chat, against the fake of the Bot Framework. The assistant asks the watcher what changed on a record, for the person it's answering, and hears only what that person may see. A notebook entry holds only what its records show, and goes once they stop showing it.
- Round 7 of the critique has read the code, and what it found is fixed.

## Progress

Step 1, group conversations, is under way.
