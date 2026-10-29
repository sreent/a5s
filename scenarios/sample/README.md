# Sample Scenario

a5s's own stand-in for a real scenario, with made-up data: a directory of nine people in two time zones, including the team that runs a5s and the people outside it who approve its releases, a records system of customer questions, each owed by its owner until it's closed, and a store for drafts. Phase 1 builds and tests against it. The code is in [`src/a5s/sample.py`](../../src/a5s/sample.py).

| File | Holds |
| --- | --- |
| [data.yaml](data.yaml) | The people and the records |
| [settings.yaml](settings.yaml) | Which instances exist, whom each serves, and how far each may act |
| [settings.sig](settings.sig) | Ana's signature over the settings. She holds the instance-approver role, so her signature makes this version count. |
| [keys/](keys/) | Made-up keys for the made-up people, so anyone can sign the sample's settings. A real scenario's private keys stay with their owners, and a5s only reads public keys. |

To change the settings, edit them, raise the serial, and sign the new version: `a5s sign --as ana`, then `a5s apply`.
