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
