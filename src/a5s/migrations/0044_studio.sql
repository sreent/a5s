-- The studio's pages (core/studio.py): the channels app shows people the instances they may
-- watch, how each is doing and what its runs did, read only. It reads the columns those
-- figures count and each run's own record, and never what people said, what a reminder or an
-- obligation is about, what a question asked, or a run's token.
grant select (id, definition, release, status, level, model, serves, owner, deputy, parts,
              actions, asks) on instances to a5s_channels;
grant select (id, instance_id, trigger, acts_for, read_outside, opened_at, closed_at, outcome,
              tokens, tokens_in, tokens_out, tokens_cached, tokens_cache_written, model,
              notes_given) on runs to a5s_channels;
grant select (run_id, source) on run_reads to a5s_channels;
grant select (scenario, instance_id, due_at, done_at, seen_owed_at, chased_at, escalations,
              handed_on) on obligations to a5s_channels;
grant select (instance_id, due_at, in_digest, confirmed_at, reminded_at, cancelled_at)
  on reminders to a5s_channels;
grant select (asked, asked_at, answered_at, problem) on questions to a5s_channels;
grant select (instance_id, source, fired_at, outcome) on report_fires to a5s_channels;
