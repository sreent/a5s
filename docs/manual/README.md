# The a5s manual

How to work with a5s's agents, decide what they ask for, and look after them. Each page is a set of short tasks for one kind of work, in the words a5s's own pages use. For how a5s is built, and why, the [reference docs](../../README.md#documents) say more.

## Find your page

| If you | Read |
| --- | --- |
| Ask an agent for help, in the web chat, Teams, Matrix or Slack | [Working with an agent](chatting.md) |
| Decide the changes agents ask for in your part of the business | [Deciding what agents ask for](deciding.md) |
| Grade samples of agents' work | [Grading agents' work](grading.md) |
| Approve a part's settings, or sign a release | [Approving settings and releases](approving.md) |
| Own an agent, and look after its instances | [Running an agent](running.md) |
| Build agents in the studio | [Building an agent](building.md) |
| Answer requests for someone's data | [The data protection officer](data-protection-officer.md) |
| Audit what agents did, or administer a5s | [Auditing and administering](oversight.md) |

Most people do more than one of these: a part's owner decides changes, approves settings, and may own agents too. The [glossary](glossary.md) says what a5s's words mean.

## Getting around

**Signing in.** You sign in once, through your organisation's own sign-in, for the chat and the studio. A few acts ask you to sign in again, afresh, for that act alone, with a second factor where your organisation asks for one: approving a change or a version of the settings, grading, undoing a change, and suspending an agent among them. That shows the act was yours, then and there.

**The studio's home.** `/studio/` says what waits on you, each with a link to where you do it: changes to decide, versions of the settings to approve, samples to grade, a release that needs your signature, and your tasks that wait for you.

**The sidebar.** Every page has the same sidebar, with a5s's pages under four headings. It shows only the pages your roles give you:

| Heading | Page | Who sees it |
| --- | --- | --- |
| Work | Chat, `/chat/` | Everyone |
| | Handed over, `/studio/handovers` | People in a team that agents hand conversations to |
| | Tasks, `/studio/tasks` | Everyone |
| | Notebook, `/studio/notebook` | People who look after an agent's notebook |
| Build | Studio, `/studio/` | Everyone |
| | Map, `/studio/map` | Everyone |
| Decide | Decisions, `/studio/decide` | Part owners, their delegates and instance approvers |
| | Grading, `/studio/grade` | Graders |
| | Shadows, `/studio/shadows` | Graders, and the people who watch a new version's answers |
| | Settings, `/studio/settings` | People who approve settings |
| Oversee | Audit trail, `/studio/audit` | Auditors and assurance |
| | Administration, `/studio/admin` | Administrators |
| | Spending, `/studio/spending` | People who may see an agent's spending |
| | Model health, `/studio/health` | The release approver and the team that runs a5s |
| | Data protection, `/studio/officer` | The data protection officer |

**What you may do, and why.** `/studio/you` lists each role you hold, what gave it you, your organisation's directory or one of its groups, and what it lets you do. Roles come from the directory, never from a5s: a role you lose there stops working the next time you sign in.

**Finding anything.** The palette opens with Ctrl+K, or ⌘K on a Mac, and finds any page, and any agent you may see, as you type.

## How far an agent may go

In each part of the business, an agent does one of three things, which the part's settings and its owner decide:

- **Reads only:** it reads, reports, reminds and chases, and changes nothing.
- **Asks first:** it drafts, raises requests and proposes changes, and a person decides each one.
- **Acts on its own:** it makes one type of change itself, tells someone, and the change can be undone for a while. It gets there only once graded samples show it's accurate enough, for that type of change, in that part, on the model it runs on.

Whatever an agent may do, it works only on records the people it's helping may see, and a change it asks for after reading something from outside, such as a supplier's email, waits for a person.
