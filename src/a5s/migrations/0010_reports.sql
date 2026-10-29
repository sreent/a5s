-- Reports: what an agent such as the watcher tells each person it serves about
-- their own records, once a day. Each day's report goes once, whether it ran,
-- had nothing new, or fell while the instance was suspended, which isn't made
-- up. What the agent last told each person is kept, once they have it, so the
-- next report says only what changed since.

create table if not exists report_fires (
  instance_id text not null references instances (id),
  person text not null,
  source text not null,  -- the kind of record it reports on, such as 'records'
  due_at timestamptz not null,  -- the day's time, in the person's time zone
  fired_at timestamptz not null default now(),
  run_id uuid,  -- the run it opened, if it opened one
  outcome text not null,  -- 'run', 'nothing new', or why not, such as 'suspended'
  records jsonb,  -- what the run tells them about, remembered once they have it
  primary key (instance_id, person, source, due_at)
);

create table if not exists report_seen (
  instance_id text not null references instances (id),
  person text not null,
  source text not null,
  records jsonb not null,  -- each of their records as the agent last told them of it, by key
  looked_at timestamptz not null,  -- when it last looked, so it says only what fell due since
  primary key (instance_id, person, source)
);

alter table report_fires owner to a5s_owner;
alter table report_seen owner to a5s_owner;

grant select, insert on report_fires to a5s_gateway;
grant select, insert, update on report_seen to a5s_gateway;
