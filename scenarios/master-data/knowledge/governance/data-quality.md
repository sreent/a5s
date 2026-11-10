---
title: How data quality is measured and reported
parts: [supplier, supplier-bank, customer, material]
review_by: 2027-06-30
---

# How data quality is measured and reported

- A data object's quality is the share of its records that pass every critical-field rule. Code measures it, the same way each time.
- Each data object has a target, set by its owner: 98% for supplier general data, supplier bank and payment data, and customer data, and 95% for material data.
- Likely duplicates are counted beside it, by the same match rules a change request is checked by: the same VAT number, a similar name in the same country and postcode, the same bank account for another supplier, or a similar material description.
- When a data object is below its target, or has likely duplicates, its owner brings it back by the date set when it was measured. The data stewards help, and the watcher tells the owner each working morning how it stands.
- The quality report for a month names each data object, its share against its target, the records that fail and why, and its likely duplicates.
