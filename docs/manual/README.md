# The a5s manual

How to work with a5s's agents, decide what they ask for, and look after them. Each page is a set of short tasks for one kind of work, in the words a5s's own pages use. For how a5s is built, and why, the [reference docs](../../README.md#documents) say more.

## Find your page

| If you | Read |
| --- | --- |
| Ask an agent for help, in the web chat, Teams, Slack or Matrix | [Working with an agent](chatting.md) |
| Decide the changes agents ask for in your part of the business | [Deciding what agents ask for](deciding.md) |
| Grade samples of agents' work | [Grading agents' work](grading.md) |
| Approve a version of the settings, or sign a release | [Approving settings and releases](approving.md) |
| Own an agent, or run its instances | [Running an agent](running.md) |
| Build agents in the studio | [Building an agent](building.md) |
| Answer requests for someone's data | [The data protection officer](data-protection-officer.md) |
| Audit what agents did, or look after who holds which role | [Auditing and administering](oversight.md) |

Most people do more than one of these: a part's owner decides changes, approves settings, and may own agents too. The [glossary](glossary.md) says what a5s's words mean.

## Getting around

**Signing in.** You sign in with your organisation's own sign-in, in the chat and in the studio. What counts asks you to sign in again, afresh, for that act alone, with a second factor where your organisation asks for one, such as approving a change or a version of the settings, grading, or undoing a change. That shows the act was yours, then and there ([which acts ask](oversight.md#second-factors-and-signing-in-afresh)).

**Home.** `/studio/`, first in the sidebar, says the roles you hold, and what waits on you, each with why it's yours and a link to where you do it: changes to decide, versions of the settings to approve, samples to grade, a release that needs your signature, people asking for your agent, and your tasks that wait for you. Its *Build an agent* shows the way from a new agent to one at work, with **Start a new agent**, if you may start one, or else who may, and how to become one of them.

**The sidebar.** Every page has the same sidebar, with a5s's pages under four headings. It shows only the pages your roles give you:

| Heading | Page | Who sees it |
| --- | --- | --- |
| Work | Home, `/studio/` | Everyone |
| | Chat, `/chat/` | Everyone |
| | Handed over, `/studio/handovers` | People in a team that agents may hand conversations to |
| | Tasks, `/studio/tasks` | Everyone |
| | Notebook, `/studio/notebook` | An agent's owners, and the people who run its instances |
| Build | Agents, `/studio/agents` | Everyone: the agents you may know of |
| | New agent, `/studio/new` | Agents' owners and engineers, who may start one |
| | Map, `/studio/map` | Everyone: what depends on what |
| Decide | Decisions, `/studio/decide` | Part owners, their delegates and instance approvers |
| | Grading, `/studio/grade` | Graders |
| | Shadows, `/studio/shadows` | Graders, and the people who follow a new version answering beside an instance |
| | Settings, `/studio/settings` | Part owners, instance approvers, agents' owners, the data protection officer and assurance |
| Oversee | Audit trail, `/studio/audit` | Auditors and assurance |
| | Administration, `/studio/admin` | Those who own, approve, decide or oversee: owners, delegates, approvers, assurance, auditors, the data protection officer and the team that runs a5s |
| | Spending, `/studio/spending` | Owners of agents, instances and parts, delegates, and instance approvers |
| | Model health, `/studio/health` | The release approver and the team that runs a5s |
| | Data protection, `/studio/officer` | The data protection officer |

**Who you are, and what you may do.** a5s has no administrator's mode to switch into, or user mode to leave: what you see, and what you may do, follows from the roles you hold, and nothing else. The foot of every sidebar says who you're signed in as, and your roles, or *No roles: you work with agents*, and leads to `/studio/you`, *What you may do*, which lists each role you hold, what it lets you do, and what gave it you: your organisation's directory, or one of its groups. Roles come from there, never from a5s, and a role you lose stops working the next time you sign in.

**Finding anything.** The palette opens with Ctrl+K, ⌘K on a Mac, or *Find anything* at the top of the sidebar, and finds any page, agent, instance or draft you may open, as you type, and what waits on you.

## How far an agent may go

In each part of the business, an agent does one of three things, which the part's settings and its owner decide:

- **Reads only:** it reads, reports, reminds and chases, and changes nothing.
- **Asks first:** it drafts, raises requests and proposes changes, and a person decides each one.
- **Acts on its own:** it makes one type of change itself, tells someone, and the change can be undone for a while. It gets there only once graded samples show it's accurate enough, for that type of change, in that part, on the model it runs on.

Whatever an agent may do, it works only on records the people it's helping may see, and a change it asks for after reading something from outside, such as a supplier's email, waits for a person.
