# Procure-to-pay Scenario

**Status:** Implemented for local development and tests: a made-up distributor's suppliers, purchase orders, goods receipts and suppliers' invoices behind its ERP's MCP server; a three-way match by code; four eyes above an amount; payables' shared mailbox read through a5s's reader; the ERP's signed events; and three agents. [Its walk-through](../docs/guides/procure-to-pay/guide.md) takes a month-end in accounts payable from end to end, through a restart and a model that stops answering.

A distributor buys from its suppliers, the warehouse books in what arrives, and accounts payable pays each supplier's invoice once it matches what was ordered and what was received. Purchasing, the warehouse and accounts payable are each a part, with its own team and owner. It tests a5s where money leaves the organisation, where a supplier's mail may be an attack on it, and where several agents and people meet over the same records: harder than the other scenarios, as no one would build it to be easy.

## The contract

| Interface | In procure-to-pay |
| --- | --- |
| Directory | The identity provider: payables (Jules owns its changes, Hana is a clerk), finance's controller (Ravi, who decides payables' changes too), purchasing (Marco owns orders and suppliers, Ines buys), the warehouse (Wen owns receipts, Tomi books them in), two graders from quality, internal audit, and the team that runs a5s, with the people from outside it who approve its releases |
| Settings | a5s's own settings store. The parts are purchasing, receiving and payables, each signed by its owner. Above 10,000 GBP, a payables change needs two of its deciders (`two_deciders`) |
| Tools | The ERP's suppliers, orders, receipts and invoices, what a supplier sent with an invoice through a5s's reader, and three changes, all through the ERP's MCP server; the three-way match and short deliveries, by code; payables' supplier mailbox; the accounts payable handbook; and drafts |
| Records | Each invoice still waiting, owed by its clerk by its due date, and each open order, owed by its buyer by its delivery date |
| Governed process | The ERP's own: an invoice is approved for payment there, and nothing else pays it. a5s pays nothing and sends no mail |
| Decision surface | a5s's decision page, and the ERP for anything a person does there |
| Tests | [`tests/test_procure_to_pay.py`](../tests/test_procure_to_pay.py) and [the walk-through](../tests/test_walkthrough_procure_to_pay.py), against a made-up ERP behind its MCP server; and on a5s's containers, with its release approved by its own people and its mailbox in a made-up Exchange Online ([`deploy/smoke-scenario.sh`](../deploy/smoke-scenario.sh)) |

The ERP's tools come through its MCP server, declared in [`mcp.yaml`](procure-to-pay/mcp.yaml) in a5s's own words: searching suppliers, orders, receipts and invoices, reading one, what a supplier sent with an invoice, approving an invoice for payment, correcting the order an invoice names, and moving an open order's delivery date. In this made-up organisation the server is [`deploy/systems/erp.py`](../deploy/systems/erp.py), on the scenario's synthetic data ([`data.yaml`](procure-to-pay/data.yaml)), beside the gateway ([`deploy/compose.p2p.yaml`](../deploy/compose.p2p.yaml)). It keeps what's done through it, and the receipts the warehouse books in, in the folder `A5S_SYSTEMS_STATE` names, which the scenario's code reads, so a match sees what the ERP holds now, and a5s starting again finds the ERP as it was.

## What code decides

The model never decides whether an invoice may be paid. Code matches it, the same way each time, the agent tells people what code found, and the ERP checks it again before it pays:

- **The three-way match.** An invoice names an order of its own supplier's, invoices a quantity, at no more than the order's price for it, and, with the invoices on the order before it or approved already, no more than was ordered and no more than the warehouse received on it. An invoice naming no order is offered the order it may mean: its supplier's, for exactly what it invoices. The match's verdict is part of the invoice's record, so its deciders read it, and a change to its order or its receipts after the payment was asked for stops it, as any change to the records a held change names does.
- **The ERP's own check.** The ERP approves an invoice for payment only once it matches its order and receipts by its own check, as an ERP does, whatever a5s allows; and it corrects an invoice's order only to one the invoice can mean, its supplier's, for what it invoices.
- **Short deliveries.** Each order the warehouse received less of than was ordered, and how much less.
- **Four eyes.** A held change whose invoice holds more than 10,000 GBP needs two of payables' deciders, and an amount a5s can't read counts as more, so the rule never lapses on a misread, as does one changed in a5s's database after the change was held. Taking the rule away, or raising its amount, needs two people who approve settings, not payables' owner alone. One approval alone doesn't make it, the same person can't approve twice, and the page tells the first that it waits for another. Nobody decides a change they asked for themselves, so where fewer than two may decide it, as when Jules asks for a payment above the amount, a5s refuses it at once, saying why, rather than hold it for a second who can't come.

## Coordinating the teams

- **Payments.** The accounts payable assistant asks for an invoice's approval only once it matches. Payables' deciders decide it on a5s's page, signed in afresh, and a5s asks the ERP to approve it once they have.
- **Corrections.** Where an invoice names an order that doesn't exist and the match offers its supplier's own, the assistant asks for the correction. It waits for a decider until graded samples earn it acting on its own for corrections in payables, on the model it runs on: a run that falls back to another model, which hasn't earned it, asks first again. The ERP corrects an invoice only to its own supplier's order, whatever a5s allows.
- **The warehouse.** When the warehouse books goods in, the ERP tells a5s, signed with the secret the deployment gave it, and the assistant matches the invoices on those orders again, asking for each that now matches to be approved. The warehouse's watcher answers what was received on an order, for the people and agents who ask, and tells the warehouse what changed in their receipts.
- **Month-end.** Asked to go through every invoice that waits, the assistant offers it as a task, and on a yes splits it into parts, one an invoice, which a5s works on in runs of their own, through a restart.
- **Purchasing.** The buyer's assistant answers purchasing's questions and asks for an open order's delivery date to move, which purchasing's owner decides.

## Supplier mail

Suppliers send their invoices, and their questions on payment, to payables' shared mailbox ([`mailboxes.yaml`](procure-to-pay/mailboxes.yaml)), which a5s reads with the deployment's app, for payables and finance's controller alone. A new message starts a run of the accounts payable assistant, for nobody. What a message says reaches it only as the form a5s's reader fills: the invoice and order it names, its amount, what it asks for, and whether it gives a bank account to pay into, says someone approved it already, or says it's urgent, the handbook's warning signs. A bank account it gives never reaches the assistant, nor any instruction in it: the made-up mail in [`mail/`](procure-to-pay/mail/), the sandbox's, includes one with a planted note, a test fixture. The run is marked, so an approval it asks for waits for its deciders, flagged, and the assistant leaves a reply among the mailbox's drafts for one of payables to send.

On a5s's containers the mailbox is in a made-up Exchange Online, [`deploy/systems/mailbox.py`](../deploy/systems/mailbox.py), beside the gateway, holding the same made-up mail: it signs in the deployment's app alone, keeps the drafts a5s leaves, and sends nothing. Mail already there when a5s first asks starts nothing, as in Exchange.

The mailbox holds payables' work (`part: payables`), so the assistant drafts there as it asks first in payables, though it only reads purchasing and receiving. What a5s tells its deciders of a change the mail's run asked for marks nothing of theirs where the change only names the record it's about, as an approval does: a marked run's dates, amounts, words, and the order a correction points an invoice at, still mark whatever repeats them. A draft names the record it's about, so its part says whether the agent may write it.

## Who sees what

- Each part's records are its team's, and the teams it names: purchasing's suppliers and orders are payables' to see too, the warehouse's receipts purchasing's and payables', and payables' invoices finance's controller's.
- An agent's run sees only what everyone it acts for may see, and in a group chat, what everyone in it may see.

## Its pack

The scenario's [pack](procure-to-pay/pack.cedar) keeps every payment for people: an invoice is never approved for payment on an agent's word alone, whatever the settings and graded samples give it, since that's where a fraud pays out.

## The agents

| Agent | Works for | Starts at | Does |
| --- | --- | --- | --- |
| Accounts payable assistant (`ap-assistant`) | Payables and finance's controller | Asks first, and acts on its own for corrections of an invoice's order in payables, only as the settings and graded samples give it on the model it runs on; never for a payment | Matches invoices by code, asks for each that matches to be approved, corrects an invoice's order to the one it means, reads payables' supplier mail through a5s's reader and drafts replies, asks the warehouse's watcher, hands a dispute to payables, and works through a month's invoices as a task, in parts |
| Buyer's assistant (`buyer-assistant`) | Purchasing | Asks first | Answers from the ERP, asks for an open order's delivery date to move, asks the warehouse's watcher, and saves drafts for suppliers |
| Warehouse's watcher (`receiving-watcher`) | The warehouse, and the people and agents who ask it | Reads only | Tells the warehouse what changed in their receipts, and answers what was received on an order |

None pays anything, and none ever sees a bank account a supplier's mail gives.
