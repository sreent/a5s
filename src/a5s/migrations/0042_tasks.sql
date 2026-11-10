-- Durable, resumable tasks. Workers hold only their current lease; the task's state is here.
create table if not exists tasks (
  id uuid primary key,
  instance_id text not null references instances (id),
  owner text not null,
  audience text[] not null,
  task text not null,
  status text not null default 'queued' check (status in
    ('queued', 'running', 'waiting', 'blocked', 'done', 'cancelled', 'failed')),
  step int not null default 0,
  progress double precision not null default 0 check (progress between 0 and 1),
  partial jsonb not null default '[]',
  result jsonb,
  tokens bigint not null default 0,
  token_budget bigint not null check (token_budget > 0),
  deadline timestamptz not null,
  parent uuid references tasks (id),
  depth int not null default 0,
  lease_id uuid,
  lease_expires_at timestamptz,
  last_heartbeat_at timestamptz,
  attempts int not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists tasks_ready on tasks (status, lease_expires_at);
create index if not exists tasks_parent on tasks (parent);
alter table tasks owner to a5s_owner;
grant select, insert, update on tasks to a5s_gateway, a5s_scheduler;
