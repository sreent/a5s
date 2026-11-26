---
name: check-results
description: How to tell a requester what check_request found about their change request, finding by finding, in plain words, and what happens next, without deciding anything yourself.
---

# Telling a requester what the check found

`check_request` decides; you say what it found. Go through its findings in this order, and leave out any it didn't find:

1. **Rules it fails.** Name each critical field it says is missing or wrong, in the words people use for it, and what it needs, as the check says. Ask the requester for what's missing. A value they give that isn't sensitive, you may propose with `correct_value`, exactly as they gave it.
2. **Likely duplicates.** Name each record it says may be the same one, by its key and name, and say the data object's owner decides whether it is. Never say yourself that it is or isn't.
3. **Sensitive fields.** Name each it touches, such as bank details or a VAT number, and say that the owner confirms the change in SAP: nobody can propose one through you.
4. **Where it goes next.** Say whom it waits for, by name, as the check gives them, and that a5s tells the requester what was decided.

Keep each to a sentence. If the check found nothing, say it passes, and whom it waits for.
