-- Retention: a conversation, everything one person and one agent have said to each other, is
-- kept for 12 months after the last thing either said, and then the core deletes it, with the
-- notes and reminders that ended 12 months before. The values a run was handed as handles, and
-- what it read, go once the run is over. The core sweeps every hour, and the ledger records
-- what each sweep deleted, in counts.

grant delete on turns, summaries, inbound, outbox, digest_items, profile_notes, reminders,
  run_reads, run_handles to a5s_gateway;
