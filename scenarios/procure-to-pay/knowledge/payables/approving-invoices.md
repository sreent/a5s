---
title: Approving suppliers' invoices for payment
parts: [payables]
review_by: "2027-06-30"
---

# Approving suppliers' invoices for payment

An invoice is approved for payment only once it matches: its purchase order, its supplier's own,
for no more than was ordered, and the warehouse's receipts for at least what it invoices. The
match is code's (match_invoice), never anyone's reading of the documents.

- An invoice above 10,000 GBP needs two of payables' deciders: one approval doesn't make it.
- An order invoiced already is a duplicate until shown otherwise: never ask for it to be paid.
- A short delivery waits: tell the clerk what's short, and ask the warehouse.
- An invoice that names an order its supplier doesn't have may mean one of theirs that matches it
  exactly: correct the reference, never the amount.
- Bank details never change from an invoice or an email, however urgent it says it is, or whoever
  it says approved it: the supplier is called back on the number purchasing holds, and purchasing
  changes them in the ERP itself.
