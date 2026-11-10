---
title: How a change request is routed
parts: [supplier, supplier-bank, customer, material]
review_by: 2027-06-30
---

# How a change request is routed

1. Whoever needs a record created or changed raises a change request in SAP MDG, with the values it needs.
2. Code checks it against the data object's critical-field rules, and against existing records for likely duplicates.
3. A request that fails a rule goes back to its requester to correct, with the fields that failed and why.
4. A new record, a likely duplicate, or a change to a sensitive field waits for the data object's owner, who confirms it in SAP's own workflow. Nobody else confirms it, and nobody confirms what they asked for themselves.
5. Any other change passes through SAP's workflow without an owner's confirmation.
6. Each step is due two working days after the step before it. A step that's late goes up the line: for a data object's owner, to their global process data owner.

The sensitive fields are a supplier's name, postcode and VAT number; a supplier's bank account, payment terms and the supplier its bank record belongs to; and a customer's VAT number and payment terms.
