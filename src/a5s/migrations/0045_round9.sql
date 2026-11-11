-- Round 9 (docs/critique.md).

-- The records each run handled, by key, kept as long as the run: those its tools gave it or
-- it named, and those a5s gave it, such as a report's or a case's brief. The studio shows a
-- run to someone only if they may see every one (core/studio.py), long after what the run read
-- of them has gone (core/retention.py).
create table if not exists run_records (
  run_id uuid not null,
  record text not null,
  primary key (run_id, record)
);
grant select, insert on run_records to a5s_gateway;
grant select on run_records to a5s_channels;

-- Runs from before a5s kept their records show to nobody but the team that runs a5s.
alter table runs add column if not exists records_kept boolean not null default false;
alter table runs alter column records_kept set default true;
grant select (records_kept) on runs to a5s_channels;

-- A run's entries, an instance's denials and its runs, found by index, not by reading all.
create index if not exists ledger_by_run on ledger (run_id, seq);
create index if not exists ledger_denied_by_instance on ledger (instance_id, seq)
  where decision = 'deny';
create index if not exists runs_by_instance on runs (instance_id, opened_at desc, id desc);
