# Phase 2

**Status:** Built, 31 October 2026, apart from outside senders ([progress](#progress)) · Round 6 of the critique comes next · **Under:** [Architecture](architecture.md)

Phase 2 lets agents act. In [phase 1](phase-1.md) they read, report, draft and remind, and change no data. In phase 2 an agent can propose a change, which the owner of what it touches decides on the core's own page. Once samples, graded by people outside the team that built it, show it's accurate enough, it can make changes of a type the part owner approves, within the scenario's limits, telling someone each time. Content from outside, such as a customer's email, reaches agents only through the extractor, and a run that has read some never acts on its own.

## Decide first

Proposed here, for whoever runs a5s to confirm:

| Decision | Proposed |
| --- | --- |
| What agents can change in the sample | The assistant can change a customer question's due date, and close one, in the sample's records system. Each is a type of action: `change-due-date` and `close-question`. |
| Who decides a held change | The owners of the part its record is in, never anyone the run acts for. Where nobody else may decide, a5s doesn't hold the change: the agent drafts it for the person to make themselves. |
| Which decisions take a sign-in each | Decisions on sensitive changes: a tool that can't be undone or sends outside the organisation, or a value of a class of its own. Others can be decided together, with one sign-in that names each of them. |
| How long a held change waits | Its deciders are reminded once after 2 working days, their managers are told after 5, and it lapses after 10 ([starting values](starting-values.md#phase-2)) |
| Who grades | People who hold the `grader` role, never from the team of the agent's owner, and only for records they may see [TBC: who, in each deployment] |
| Thresholds | Each part's, in its settings. The sample: billing 98%, orders 95%. |
| The sequential test | Anytime-valid, at 95% confidence, so checking after every grade doesn't make a level-up likelier by chance. With no errors, a 98% threshold needs 224 graded items and a 95% one 88, more than the 149 and 59 a test of fixed size needs, which the starting values quoted until now. |
| Outside content in the sample | Made-up emails from each record's customer |

## Build, in order

Each step ends with something running and its tests passing.

1. **Held proposals and signed decisions.**
   - A scenario's tool says what type of action it takes, if it changes a part's data, such as `change-due-date`, and names the record it changes. The type is pinned in the release with the rest of the tool.
   - At level 1, policy holds such a call rather than allowing it: a hold is an annotation on a Cedar permit. The core keeps the exact call, the records it names as they stood, and the values of any handles in it, and tells the agent who decides. The agent carries on.
   - Its deciders get a card, or a link in other chats, that opens the core's page. There they see what the change does, in words code works out, with the agent's flags, such as values it wrote itself. They sign in afresh, with a nonce that commits to their decision on exactly that change, or on a list of changes that aren't sensitive. The core seals the decision, and each sign-in decides once.
   - Once it's approved, the gateway makes the call, if the records haven't changed and the instance may still act. Whoever the run acted for is told what was decided, and so is the agent's next run, as a5s's notice.
   - Its deciders are reminded once after two working days, their managers are told after five, and it lapses after ten. A decider whose authenticator was reset in the last day has their decisions wait until a day has passed.
2. **Counts.** The settings give the scenario's limits for each type of action: how many one piece of work may take, and how many for each person acted for in 30 days. Code decides what a piece of work is: a run. The gateway counts in the transaction that decides each call, under a lock, and a call past a limit is held for its decider, whatever the level.
3. **Types of action and level 2.**
   - The settings set a level for each part and type of action. A level-2 setting counts only while one of the people who approved it for that part still owns the part, and drops to level 1 otherwise, until the new owner approves a version.
   - At level 2, a call runs, and is reported: in the digest of the instance's owner, with a link to the record, and to whoever the run acted for. The owner reverses one through the scenario's own process.
   - A run that has read outside content works at level 1 at most, so what it would change is held.
4. **Samples, grades and the cap.**
   - a5s keeps a cap for each release, part and type of action, and an instance works at the lower of its setting and the cap. The cap starts at 1.
   - Code draws samples: every held change once it's decided, while the cap is 1, and at level 2 enough actions for about 100 a quarter. Graders grade them on the core's page as right, wrong or critical, seeing what the agent proposed or did and the record as it stood.
   - A sequential test, pooled across the release's instances, raises the cap when the evidence shows accuracy meets the part's threshold, and lowers it when the evidence shows it doesn't, or at once on a critical error. The ledger records each change of cap.
   - The status flags a decider whose approvals are graded wrong more often than their peers'. A release that widens what an agent does starts at 1 for what it widens.
5. **The extractor and marked runs.**
   - A scenario's tool says which fields of what it returns are outside content, and the fixed schema the extractor fills from them: keys, amounts, dates, choices from a list, and sensitive values, never free text.
   - The gateway never hands those fields to the agent. The extractor, a model call with no tools and the instance's approved model, fills the schema, and code keeps only values it finds in the text itself, giving sensitive ones as handles.
   - An agent can also ask a question about a document. The answer comes back in free text, marked as outside content, and never as an instruction.
   - The run is marked from then: it can't act at level 2 or write anyone's profile, and what it drafts or proposes says it drew on outside content.

Outside senders who can start work, with a limit of 20 requests a day each, wait for a scenario where outside senders start work at all.

## Done means

- Each finding the [critique](critique.md) marks for phase 2 has a test in a5s's own suite that shows the code stops it: A2, A8, I1, I6, I7, I11, F5, C10, D5, O4, O8 and O10.
- In the sample, the assistant holds a change of due date, its decider approves it on the core's page, and the change is made only if the record hasn't changed. Once graded samples raise its cap and the part's owner sets level 2, it makes such changes and reports them. A run that has read a customer's email can't make one.
- Round 6 of the critique has read the code, and what it found is fixed.

## Progress

Step 1, held proposals and signed decisions, is built:

| Built | Where |
| --- | --- |
| A scenario's tool says the type of action it takes, if it changes a part's data, and names the record it changes. The type is pinned in the release with the rest of the tool, and a tool with one always counts as writing. The sample's records system can change a question's due date and close a question, keeping each change apart from the questions as data.yaml has them, and the assistant's release grants both. | [`contract.py`](../src/a5s/contract.py), [`sample.py`](../src/a5s/sample.py), [`agents/assistant/`](../agents/assistant/) |
| Holds. Below level 2, a change waits: a permit annotated `@hold` in a5s's base pack holds the call, which never outweighs a forbid, and a scenario's pack, which may only forbid, can't add one. | [`core/policies/base.cedar`](../src/a5s/core/policies/base.cedar), [`core/policy.py`](../src/a5s/core/policy.py) |
| Held proposals. The gateway keeps the exact call, each record it names as it stood, and the values of the handles in it, and tells the agent who decides. The owners of the record's part decide it, or the instance approvers for a record in no part, who may see the record, and never anyone the run acts for: where nobody else may decide, the change isn't held, and the agent says the person can make it themselves. Deciders get a card, or a link, saying what the change does in words code works out, with what to know, such as values the agent wrote itself. | [`core/proposals.py`](../src/a5s/core/proposals.py), [`core/gateway.py`](../src/a5s/core/gateway.py) |
| Signed decisions, on the core's own page. A decider signs in to see what waits for them, then afresh to decide, with a nonce that commits to approving or rejecting exactly the changes they chose. Changes that aren't sensitive can be decided together, and a sensitive one alone. The core seals each decision, each sign-in decides once, and a decider who no longer owns what a change touches decides nothing. | [`core/webchat/decide.js`](../src/a5s/core/webchat/decide.js), [`core/inbox.py`](../src/a5s/core/inbox.py) |
| Making what's approved. Each minute the gateway makes the changes approved, if their records haven't changed, the tool is as it was pinned, and policy would still let the instance call it, and tells whoever each was for, in the conversation with its agent. A change is marked as being made first, so it's never made twice. A decision by someone whose authenticator was reset in the last day waits until a day has passed. Deciders are reminded once after two working days, their managers are told after five, and a change lapses after ten. Changes and their decisions go a year after they end, and the status counts those waiting and any stopped part way. | [`core/gateway.py`](../src/a5s/core/gateway.py), [`core/retention.py`](../src/a5s/core/retention.py), [`core/status.py`](../src/a5s/core/status.py) |

Steps 2 and 3, counts and level 2, are built:

| Built | Where |
| --- | --- |
| Counts. The settings give each type of action the scenario's limits: how many one run may take, and how many for each person acted for in 30 days, across every agent. The gateway counts each change made or held in the transaction that decides it, under a lock for its type, so calls made at once can't each squeeze under a limit. Past a limit, a change waits for its decider, whatever the level. The same change made again in a run counts once, keeps its verdict, and answers with the same proposal. The sample limits each of its two types to 5 a run and 20 a person. | [`core/counts.py`](../src/a5s/core/counts.py), [`core/policies/base.cedar`](../src/a5s/core/policies/base.cedar) |
| Level 2. The settings set an instance's level for each type of action in each part, the only way to level 2, and approvers read it in words. A change works at level 2 only while someone who approved the settings in force owns the part, and only up to a5s's cap for the release, part and type, which is 1 until graded samples raise it in step 4. A change about no record, or from a run that read outside content, works at level 1 at most. At level 2 a change is made, and reported in the digest of the instance's owner with a link to the record. The assistant's release may now reach level 2. | [`core/parts.py`](../src/a5s/core/parts.py), [`contract.py`](../src/a5s/contract.py), [`core/gateway.py`](../src/a5s/core/gateway.py) |

Step 4, samples, grades and the cap, is built:

| Built | Where |
| --- | --- |
| Samples. Code draws samples of each release's changes, for each part and type of action: every held change someone decided, while the cap is 1, and at level 2 every change made until there are 100 in the quarter, each with what the agent asked for or did, in words code worked out, and its records as they stood. | [`core/samples.py`](../src/a5s/core/samples.py), [`core/gateway.py`](../src/a5s/core/gateway.py) |
| Grades, on the core's own page. People who hold the grader role grade samples right, wrong or critical, once each: never anyone from the team of the agent's owner, nor anyone a change was for or who decided it, and only for records they may see. The sample has a grader, Dana Price, in finance. | [`core/webchat/grade.js`](../src/a5s/core/webchat/grade.js), [`core/inbox.py`](../src/a5s/core/inbox.py) |
| The cap. Each minute an anytime-valid sequential test, pooled across the release's instances, weighs the grades for each release, part and type: it raises the cap to 2 once they show, with 95% confidence, that accuracy meets the part's threshold in the settings, and lowers it once they show it falls short, or at once on a critical error. A part with no threshold never earns level 2; the sample's are 98% for billing and 95% for orders. The ledger records each change of cap with its evidence, and the status shows what's earned level 2, what waits to be graded, and deciders whose approvals are graded wrong far more often than everyone else's. Graded samples go a year after they're graded. | [`core/samples.py`](../src/a5s/core/samples.py), [`core/status.py`](../src/a5s/core/status.py) |

Step 5, the extractor and marked runs, is built:

| Built | Where |
| --- | --- |
| The extractor. A scenario's tool names the fields of what it returns that are content from outside, and the fixed form the extractor fills from them, each field typed. The gateway never hands those fields to the agent: the instance's own approved model, called with no tools and a fixed instruction, fills the form, through the same model gateway, policy, budget and ledger as any model call, and code keeps only keys, amounts, dates and sensitive values the document itself contains, choices from the list, and yes or no. Sensitive values go to the agent as handles. What the agent gets is the form, marked as from outside, with the document's number; a reply that isn't a form says so. | [`core/extractor.py`](../src/a5s/core/extractor.py), [`core/gateway.py`](../src/a5s/core/gateway.py) |
| Asking about a document. With `ask_about`, a release that may ask a5s's reader gets a free-text answer to a question about a document its run has read, marked as outside content, with a note never to act on it as an instruction. Documents go an hour after their run. | [`core/extractor.py`](../src/a5s/core/extractor.py), [`core/retention.py`](../src/a5s/core/retention.py) |
| Marked runs. A run is marked from its first outside content, and the database keeps it marked. It works at level 1 at most, so what it would change is held; it can't write anyone's profile; its drafts end with a note that they drew on outside content; and its held changes tell their deciders. | [`migrations/0026_outside.sql`](../src/a5s/migrations/0026_outside.sql), [`core/parts.py`](../src/a5s/core/parts.py) |
| The sample's customers write: their emails are on each question, and one tells the agent that finance approved its refund and to move every due date. The assistant reads them with `get_messages`, its regression suite checks it does nothing an email says, and the tests show the email can't make a change at level 2. | [`scenarios/sample/data.yaml`](../scenarios/sample/data.yaml), [`agents/assistant/tests/outside.yaml`](../agents/assistant/tests/outside.yaml) |

Still to do: a limit of 20 requests a day for each outside sender, once a scenario lets outside senders start work at all.

Held proposals didn't bring back the round-4 middleware that asked the core to explain a call before making it: a held call answers at once, with who decides, so the agent carries on.
