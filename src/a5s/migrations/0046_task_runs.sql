-- Tasks as a5s runs them (core/tasking.py): a person asks an agent for work that takes more
-- than one run, the agent offers it, and it starts once they say yes in a later message. Each
-- slice of it is then a run of the agent's, which keeps what it said the slice came to until
-- the run closes, and people name a task by its number, such as T-12.
alter table tasks drop constraint if exists tasks_status_check;
alter table tasks add constraint tasks_status_check check (status in
  ('offered', 'queued', 'running', 'waiting', 'blocked', 'done', 'cancelled', 'failed'));
alter table tasks add column if not exists number bigint generated always as identity;
alter table tasks add column if not exists offered_run uuid;
alter table tasks add column if not exists asked_at timestamptz;  -- by the message that asked
create unique index if not exists tasks_by_number on tasks (number);
create index if not exists tasks_offered on tasks (owner, instance_id) where status = 'offered';
alter table runs add column if not exists task_result jsonb;
grant update (task_result) on runs to a5s_gateway;

-- What a task's runs read, with where each value came from, kept with the task for its
-- later runs: a value its agent writes is traced to wherever it came from, whichever of its
-- runs read it, and nothing an earlier run made up passes as the records'
-- (core/provenance.py). Whether any of them read content from outside, so the mark follows
-- what they drew on, and what its owner said when it needed them.
alter table tasks add column if not exists read_outside boolean not null default false;
alter table tasks add column if not exists answered jsonb;
create table if not exists task_reads (
  task_id uuid not null references tasks (id) on delete cascade,
  source text not null,
  kind text not null,
  norm text not null,
  text text not null,
  primary key (task_id, kind, norm, source)
);
alter table task_reads owner to a5s_owner;
grant select, insert on task_reads to a5s_gateway;
