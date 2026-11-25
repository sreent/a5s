-- The core's status, as it last found it, for the studio's Status page, which the channels app
-- serves and which can't ask the core: the core records it each minute, when the scheduler asks
-- it to, so one gone stale says the scheduler or the core is away (core/status.py,
-- docs/runbooks.md#start-with-a5s-doctor).
create table if not exists status_seen (
  only_one boolean primary key default true check (only_one),
  at timestamptz not null default now(),
  status jsonb not null
);
grant select, insert, update on status_seen to a5s_gateway;
grant select on status_seen to a5s_channels;
