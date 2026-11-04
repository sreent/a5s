# Sample Scenario

a5s's own stand-in for a real scenario, with made-up data: a directory of nine people in two time zones, including the team that runs a5s and the people outside it who approve its releases, a records system of customer questions, each in a part of the business and owed by its owner until it's closed, and a store for drafts. Phase 1 builds and tests against it. The code is in [`src/a5s/sample.py`](../../src/a5s/sample.py).

It has two parts. Billing, the finance team's invoices, refunds and billing contacts, is Ana's: she holds `part-owner:billing`. Orders, the operations team's deliveries, is Omar's. A part's team may see its records, and so may each record's owner and whoever is above them, so Ana and Ben see billing's records, and Chen and Omar see orders'.

| File | Holds |
| --- | --- |
| [data.yaml](data.yaml) | The people, the parts and the records |
| [settings.yaml](settings.yaml) | Which instances exist, whom each serves, the parts each works in, and how far each may act there |
| [settings.sig](settings.sig) | Ana's signature over the settings. Both instances work in billing, which she owns, so her signature makes this version count. One that has an instance work in orders needs Omar's too. |
| [keys/](keys/) | Made-up keys for the made-up people, so anyone can sign the sample's settings. A real scenario's private keys stay with their owners, and a5s only reads public keys. |

To change the settings, edit them, raise the serial, and sign the new version: `a5s sign --as ana`, and `a5s sign --as omar` too if it reaches orders, then `a5s apply`. Or ask its approvers to approve it where they work, with `a5s propose`: each gets a card, and the core applies it once everyone it needs has approved.
