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

-- A task and the children it made are a tree, which shares its root's budget; a slice that
-- fails leaves its task waiting longer each time; and only the core writes a task, as phase 4
-- says, so the scheduler no longer may (core/tasks.py).
alter table tasks add column if not exists root uuid;
alter table tasks add column if not exists failures int not null default 0;
alter table tasks add column if not exists not_before timestamptz;
with recursive tree as (
  select id, id as root from tasks where parent is null
  union all
  select t.id, tree.root from tasks t join tree on t.parent = tree.id)
update tasks set root = tree.root from tree where tasks.id = tree.id and tasks.root is null;
alter table tasks alter column root set not null;
create index if not exists tasks_root on tasks (root);
create index if not exists tasks_owner on tasks (owner);
revoke insert, update on tasks from a5s_scheduler;
grant delete on tasks to a5s_gateway;  -- retention and erasure
