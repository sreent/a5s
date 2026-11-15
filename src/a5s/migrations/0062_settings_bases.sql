-- The version in force each proposed version was written against, by its serial, or none if
-- none was (core/approvals.py): it comes into force on that version alone, so its approvers'
-- review of what it changes holds. Another in force first, and it's superseded.
alter table settings_proposals add column if not exists base bigint;
