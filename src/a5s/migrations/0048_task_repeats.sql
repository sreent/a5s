-- Tasks people ask agents to do again and again, such as every Monday at 09:00
-- (core/tasking.py): offered, and said yes to in a later message, as a task is. At each of
-- its times, in its owner's time zone, the core makes a task of it, once the last one it made
-- has ended, with what the run that offered it had read. People name one by its number, such
-- as E-3, and stop it at their word.
create table if not exists task_repeats (
  id uuid primary key,
  number bigint generated always as identity,
  instance_id text not null references instances (id),
  owner text not null,
  task text not null,
  days text[] not null,
  at text[] not null,
  status text not null default 'offered' check (status in ('offered', 'active', 'stopped')),
  offered_run uuid,
  asked_at timestamptz,
  reads jsonb not null default '[]',  -- what the run that offered it had read, and from where
  read_outside boolean not null default false,
  last_due timestamptz,  -- the time it last came round, whether it made a task then or not
  last_task uuid,  -- the task it last made
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists task_repeats_by_number on task_repeats (number);
create index if not exists task_repeats_owner on task_repeats (owner);
alter table task_repeats owner to a5s_owner;
grant select, insert, update, delete on task_repeats to a5s_gateway;
grant select on task_repeats to a5s_channels;  -- their page, which stops one at their word
grant update (status, updated_at) on task_repeats to a5s_channels;
alter table tasks add column if not exists repeat uuid;  -- the repeat that made it, if one did
