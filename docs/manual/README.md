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

**The sidebar.** Every page has the same sidebar, the chat's too, with a5s's pages under four headings. It shows only the pages your roles give you, each checked as its own page checks who may use it, so no page in it turns you away; *What you may do*, below, says which of your roles gives each:

| Heading | Pages |
| --- | --- |
| Work | Home, `/studio/`; Chat, `/chat/`; Handed over, `/studio/handovers`; Tasks, `/studio/tasks`; Notebook, `/studio/notebook` |
| Build | Agents, `/studio/agents`; New agent, `/studio/new`; Map, `/studio/map` |
| Decide | Decisions, `/studio/decide`; Grading, `/studio/grade`; Shadows, `/studio/shadows`; Settings, `/studio/settings` |
| Oversee | Status, `/studio/status`; Audit trail, `/studio/audit`; Administration, `/studio/admin`; Spending, `/studio/spending`; Model health, `/studio/health`; Data protection, `/studio/officer` |

**Who you are, and what you may do.** a5s has no administrator's mode to switch into, or user mode to leave: what you see, and what you may do, follows from the roles you hold, and nothing else. The foot of every sidebar says who you're signed in as, and your roles, with each instance you run as its owner or deputy, or *No roles: you work with agents*, and leads to `/studio/you`, *What you may do*, which lists each, what it lets you do, and what gave it you: your organisation's directory, one of its groups, or, for an instance you run, the signed settings. Roles come from there, never from a5s, and a role you lose stops working the next time you sign in.

**Which deployment, and which of your roles.** A band across the top of every page, the sign-in's too, says which deployment you're on: production in a strong colour, filled, and a test, a staging or a developer's own machine in amber, so nobody does in one what they meant for the other. A page where you're about to use one of your roles' powers says so first, above its title: *Acting as Owner of billing: what you approve here, the agent that asked for it does in its records*. It's there only while the page holds something one of your roles lets you do, and names the role it counts as: changes to decide, samples or a new version's answers to grade, a version of the settings to approve, an instance you may suspend or resume, a change you may undo as a decider in its part, a conversation handed to your team, notes you may take out of a notebook, and the data protection officer's requests. A page that only shows has none, nor has one where what you do is your own, such as your tasks, or only asks, such as for a version of the settings, which its approvers approve on its own page, with the line.

**Finding anything.** In the studio, the palette opens with Ctrl+K, ⌘K on a Mac, or *Find anything* at the top of the sidebar, and finds any page, agent, instance or draft you may open, as you type, and what waits on you. The chat's sidebar has no palette: its pages are a click away.

## How far an agent may go

In each part of the business, an agent does one of three things, which the part's settings and its owner decide:

- **Reads only:** it reads, reports, reminds and chases, and changes nothing.
- **Asks first:** it drafts, raises requests and proposes changes, and a person decides each one.
- **Acts on its own:** it makes one type of change itself, tells someone, and the change can be undone for a while. It gets there only once graded samples show it's accurate enough, for that type of change, in that part, on the model it runs on.

Whatever an agent may do, it works only on records the people it's helping may see, and a change it asks for after reading something from outside, such as a supplier's email, waits for a person.
