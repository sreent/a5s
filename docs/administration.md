# Administration and audit: who runs a5s, how they sign in, and how it's checked

**Status:** Draft, for confirmation. Step 1, a second factor for what counts, is built, and so is step 2's first half, the audit trail's API and command line · **Under:** [Architecture](architecture.md)

An enterprise asks three things of a system like a5s before it trusts it with people's work. Who can change what, and can that be narrowed to a part of the business? How do people sign in, and is a second factor asked for where it matters? And can someone independent see what happened, and show that the record of it is whole? a5s answers most of this already, in its core, though not yet in pages an administrator or an auditor would use. This page says what's there, what isn't, and what to build, in order.

## Who administers what, today

There's no administrator over everything. Each power is a role with a scope, and anything that loosens a5s needs someone outside the team that runs it and that team's line of managers ([architecture](architecture.md)). What the team can do alone only makes a5s safer.

| Role | Scope | May | How |
| --- | --- | --- | --- |
| The platform owner and the team that runs a5s | The deployment | Run it, and make it safer alone: suspend an instance, lower a cap, withdraw a release. Never loosen it. | The command line and the chart |
| Instance approver | Instances that work in no part | Approve them and set their level | The settings app, signed |
| Part owner, `part-owner:<part>` | One part of the business, such as billing | Approve the instances that work in their part, and how far each may act there | The settings app, each approval a fresh sign-in |
| Part delegate, `part-delegate:<part>` | One part | Decide the changes agents ask for there, beside its owner, such as while they're away. They approve no settings. | Approval cards and the held changes' page |
| Agent owner, `agent-owner:<agent>`, and their deputy | One agent | Own its definition and releases, watch its runs in the studio, and suspend it | The agents' repository and the studio |
| Release approver | Each release | Approve it. Never someone from the team that runs a5s, nor above it. | `a5s release sign` |
| Assurance | The evidence | Hold the ledger's locked copies, test releases, and agree before an agent the scenario marks as a check is stopped | Their storage account and tests |
| Data protection officer | Requests for someone's data | Export or erase what a5s keeps about one person, one request at a time | The officer's page, signed in for that request alone |
| Grader | Samples | Grade agents' work, never their own team's | The grading page, each grade a fresh sign-in |
| Auditor, `auditor`, and assurance | The ledger | Read it all: find a period's entries, export a period with what proves it's the ledger's own, and report who holds each role and who did what. Change nothing. | `a5s audit` (step 2) |

So the "sub-administrators" an enterprise asks about are the scoped roles: a part's owner administers what agents may do in their part of the business, and an agent's owner their agent, and neither gets more. Every change they make is a new settings version or release, signed by the people it needs, and in the ledger.

People are found by their identity provider's id, such as Entra ID's object id. Their roles come from the directory in the deployment's scenario folder, which the deployment's release covers, so giving someone a role is a reviewed and approved change. That's safe, but it isn't how an enterprise manages access: it does that in its identity provider, with joiners and leavers, access reviews and time-bound elevation.

## How people sign in, today

- **Single sign-on.** Every page, the web chat, the settings app, the studio, the notebook, people's tasks and the officer's page, signs people in through the organisation's identity provider with OpenID Connect: Entra ID, Okta, Keycloak or any other. a5s holds no passwords. In Teams and Matrix, a5s knows senders by their accounts there, which the directory maps to people.
- **A fresh sign-in for what counts.** Approving settings, deciding a held change, grading and the officer's requests each need a sign-in made in the last ten minutes, for that one thing: its nonce commits to exactly what was approved. The core, which nobody outside reaches, checks the sign-in again against the provider's keys, and only then seals it ([`core/sealing.py`](../src/a5s/core/sealing.py)). So breaking into the channels app, which people reach, makes nothing count.
- **A second factor.** The identity provider asks for it, by its own policies, such as Conditional Access in Entra ID. Until step 1, a5s trusted that it had: if a policy was changed or left out, an approval made with a password alone counted. Now the deployment names the claim that shows one, and a5s checks it itself (step 1, below).

## How it's audited, today

- **The ledger** records every policy decision, tool call, message, notice, approval, decision, grade, release, settings version, suspension, export and erasure, in the same transaction as the act. Each entry is chained to the last by its hash, and keeps what anyone said only by hash. Every hour, the entries since the last copy go to object-lock storage that assurance owns, which nobody can change or delete until its retention ends. `a5s ledger verify` checks the chain against those copies, so a rewritten history shows ([architecture](architecture.md)).
- **Who sees it.** The studio shows each run's ledger entries to the people who may see the run. `a5s ledger tail`, `a5s measures` and `a5s status` show the rest, to whoever can run the command line.
- **What's missing.** There's no auditor's role or page. Reading the ledger needs the database or the command line, with no way to find entries by period, person, instance, action or decision. An auditor can't take a period away in a form they can check against the locked copies themselves, and nothing reports who held which role, or who approved, decided, released, suspended, exported or erased what.

## Decide first

| Decision | Proposed |
| --- | --- |
| A second factor | a5s checks it itself, for what counts, by a claim the deployment names (`A5S_OIDC_MFA`): `amr` holding `mfa` for Entra ID, which puts `amr` in its OpenID Connect tokens, or `acr` or `acrs` for a provider's step-up level or authentication context. What counts is refused without it, when people sign in and again when the core seals it. It's on in the chart, and off in the development stack, where `a5s status` says so. |
| Who audits | Someone with the `auditor` role, from outside the team that runs a5s. Auditors read every entry the ledger holds: what was done and decided, by and for whom, never what anyone said, which the ledger doesn't keep. Whom an entry acted for shows as a stand-in name until the data protection officer agrees, as on the studio's pages (`A5S_STUDIO_NAMES`). |
| What auditors get | Entries found by period, kind, action, decision, instance, agent and person. A period exported as a file of its entries, with what proves they're the ledger's own: the chain's hashes, and the locked copy that holds its last entry. And a report of who held which role, and who approved, decided, released, suspended, exported or erased what. The API and the command line first, then a page in the studio. |
| Where roles come from | The identity provider's groups, which the signed settings map to a5s's roles. The organisation manages who's in each group with its own tools, such as access reviews and Entra ID's Privileged Identity Management, and a5s's settings, which the roles' owners sign, decide what each group may do. A sign-in shows its groups, so a role someone loses stops working at their next sign-in. The directory's roles stay for deployments without groups. |
| Security monitoring | Later: the ledger's entries, as an auditor sees them, to the organisation's security monitoring, such as Microsoft Sentinel or Splunk. |

## Build, in order

1. **A second factor for what counts.** Built. The deployment names the claim and the values that show one (`A5S_OIDC_MFA`, such as `amr:mfa`, the chart's `people.oidcMfa`). An approval, a decision, a grade or an officer's request whose sign-in doesn't show one is refused when it arrives, and again when the core seals it, so a channels app broken into can't make one count. Resuming an instance and ending a held change need one too; suspending one and lowering a cap, which only make a5s safer, don't, so nobody waits for a second factor in an emergency. `a5s status` says whether it's checked, the chart checks `amr` for `mfa` unless told otherwise, and the first-day guide asks Entra ID for `amr` and names the Conditional Access policy that requires the second factor (`tests/test_mfa.py`).
2. **The audit trail, for auditors.** The `auditor` role. The core's API, behind its service token, and the channels app's, for auditors signed in, from the same module, with `a5s audit` on the core's: entries by period and filters, a period's export with its proof, and the report of roles and acts. Then a page in the studio. Every search and export an auditor makes is itself in the ledger.
   - Built: the core's API, `/audit/entries`, `/audit/export` and `/audit/report`, for someone the directory names as an auditor or assurance, and the command line on it ([`core/audit.py`](../src/a5s/core/audit.py)). `a5s audit entries` finds a period's entries, a page at a time, by kind, action, decision, instance and person. `a5s audit export --out <file>` writes a period exactly as the ledger holds it, each entry with its hash and the one before, as the locked copies hold them, and `a5s audit verify <file>` checks that it holds together and, where `A5S_ANCHOR_STORE` names the locked copies, that it's the ledger's own. So an auditor needn't trust whoever ran the export: an entry changed after export, or one taken out from between others or put in, doesn't check out, and each entry's time shows the stretch of the period the export covers. `a5s audit report` says who holds each role now, and who approved, decided, released, suspended, exported or erased what. Each read is itself in the ledger, with whom it asked about by hash alone (`tests/test_audit.py`).
   - Next: the channels app's API and a page in the studio, for auditors signed in, with stand-in names until the data protection officer agrees.
3. **Roles from the identity provider, and a page for administrators.** Settings map groups to roles. The page shows who holds each role and by which group, what waits for whom, such as settings versions, releases and held changes, and the latest changes to each, from the audit trail. It shows; the settings app and the command line still change.
4. **Later, with evidence.** The ledger's entries to the organisation's security monitoring, and the settings app folded into the studio ([studio](studio.md), step 3).

## Tests

- With `A5S_OIDC_MFA` set, an approval, a decision, a grade or an officer's request whose sign-in shows no second factor never counts, and one whose sign-in does counts, as before. Without it, nothing changes, and `a5s status` says it isn't checked.
- An auditor finds every entry of a period, filtered as asked, and nothing anyone said. Someone without the role finds none.
- A period an auditor exports checks out against the locked copies, and one changed after export doesn't.
- The report names who approved each settings version, release and held change in a period, as the ledger records them.
- With roles from groups, someone taken out of a group loses the role's powers at their next sign-in, and a group the signed settings don't name gives none.

## What this doesn't change

Nobody gets a power through a page that they wouldn't have at the command line, and no administrator can loosen a5s alone. The ledger stays the one record: audit reads it, and changes nothing in it.
