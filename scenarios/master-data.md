# SAP Master Data Governance Scenario

**Status:** An MVP is implemented for local development and tests: synthetic SAP master data and change requests, critical-field rules, duplicate checks and data quality measured by code, a governance handbook in a Markdown vault, an assistant that proposes corrections for each data object's owner to decide, and a watcher that reports to each owner every working morning. It follows the data objects, owners, critical fields, sensitive changes and turnaround of the LEAN data governance framework.

A data team governs the master data an organisation runs on, in SAP MDG: suppliers, their bank and payment data, customers and materials. Each data object has one named owner, who reports to a global process data owner. People raise change requests; code checks them; a sensitive change, a new record or a likely duplicate waits for the data object's owner to confirm it in SAP. It tests a5s where the records are an organisation's controls against fraud and error, where a supplier's letter may be an attack, and where each data object's owner, not the agent, is the one who decides.

## The contract

| Interface | In master data governance |
| --- | --- |
| Directory | The identity provider: requesters, data stewards, each data object's owner, and the global process data owners they report to; and the team that runs a5s, who own its agents, with the people from outside it who approve its releases |
| Settings | a5s's own settings store. The parts are the data objects, each owned by its data object's owner, who signs the settings and decides what an agent proposes there |
| Tools | SAP's change requests and master records, read only, with bank details as handles; change requests checked, and each data object's quality measured, by code; suppliers' letters through a5s's reader; the governance handbook; drafts; and corrections to a request's values, held for the data object's owner |
| Records | Change requests, each owed by whoever has its next step, and each data object's quality, owed by its owner while it's below target or has likely duplicates |
| Governed process | SAP MDG's own workflow: the data object's owner confirms sensitive changes, new records and likely duplicates there. a5s approves, rejects and posts nothing in SAP |
| Decision surface | SAP MDG, and a5s's decision page for the corrections an agent proposes |
| Tests | [`tests/test_master_data.py`](../tests/test_master_data.py), against a fake SAP MDG, and live on a real model; and on a5s's containers, through Matrix, with its release approved by its own people ([`deploy/smoke-scenario.sh`](../deploy/smoke-scenario.sh)) |

## What code decides

The model never validates. Code does, the same way each time, and the agent tells people what code found:

- **Critical-field rules.** A supplier or customer has a name, country and postcode, and a VAT number in its country's form where its country requires one. Payment terms are one of the approved terms. An IBAN has a valid form and check digits. A material has a description, a base unit and a material type from their lists.
- **Likely duplicates.** The same VAT number; a similar name in the same country and postcode; a bank account another supplier already uses; a similar material description.
- **Sensitive fields.** A supplier's name, country, postcode and VAT number; a supplier's bank account, payment terms, and the supplier its bank record belongs to; a customer's country, VAT number and payment terms. A country is sensitive since it decides which VAT rule its number is checked by, so an agent never proposes one.
- **Where a request goes.** Back to its requester if a rule fails; to its data object's owner if it's new, touches a sensitive field or looks like an existing record; otherwise through SAP's workflow with no owner's confirmation.
- **Data quality.** The share of each data object's records that pass every rule, against its owner's target, which records fail and why, and its likely duplicates.

## Coordinating with each data object's owner

- **Confirmations.** A request waiting for its owner is the owner's to confirm, by its due date, two working days after the step before. a5s reminds them halfway, and when it's late, tells their global process data owner, a working day at a time up the line, in each person's hours.
- **Quality.** While a data object is below its target, or has likely duplicates, its owner owes the fix by the date set when it was measured, and a5s chases it the same way.
- **Reports.** The watcher tells each owner, each working morning, how their data object stands and what changed since, and each person what changed in the requests that wait on them. Code works out the facts, so a morning with nothing new starts no model.
- **Corrections.** When a requester or steward gives a missing value that isn't sensitive, such as a base unit, the assistant proposes it. It waits for the data object's owner on a5s's decision page, signed in afresh, and a5s makes it once they approve, if the request hasn't changed since. A sensitive field can't be proposed at all: the tool's schema has no such argument, so policy refuses it before anything is held.

## Who sees what

- A data object's records are its owner's team's and the data team's to see, and the teams that work with them: procurement and accounts payable see suppliers, accounts payable sees supplier bank data, sales sees customers, and the plant sees materials.
- A change request is the data team's and its owner's team's, and its requester's.
- A data object's quality is its owner's team's and the data team's.
- Bank details reach an agent only as handles, which a5s fills in where people see them, so the message a person got keeps the value as they read it, for as long as their conversation ([data protection](../docs/data-protection.md)). What suppliers send reaches it only as a5s's reader fills a fixed form from it: what it asks for, the dates and keys it names, and whether it says it's urgent, asks to skip the callback, or says someone approved it already, the handbook's warning signs. The assistant never asks the reader about a letter in words of its own, whose answer could carry a bank account's number.

## The agents

| Agent | Works for | Starts at | Does |
| --- | --- | --- | --- |
| Master data assistant (`mdg-assistant`) | Requesters, data stewards and each data object's owner | Level 1 | Checks requests and quality by code, answers from SAP and the handbook, proposes corrections for the owner to decide, drafts notes and quality reports, and chases each request's next step and each owner's quality fix |
| Data quality watcher (`mdg-watcher`) | Each data object's owner, and the data stewards | Level 0 | Tells each owner every working morning how their data object stands against its target and what changed, and each person what changed in the requests that wait on them |

Neither approves, rejects or posts anything in SAP, and neither ever sees a bank account's number.
