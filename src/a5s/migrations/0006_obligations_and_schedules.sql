-- Obligations and schedules, both the core's own records.
--
-- The core works obligations out from the scenario's records, one for each
-- record and person, naming the instance that acts on it, and escalates them
-- itself. Each time a schedule is due, the core records whether it fired, so it
-- fires once, and a time missed while its instance was suspended isn't made up.

create table if not exists obligations (
  id bigserial primary key,
  scenario text not null,
  source text not null,  -- the kind of record it comes from, such as 'records'
  record text not null,  -- the record's key
  person text not null,  -- who owes it
  title text not null,
  link text,
  opened_at timestamptz not null,
  due_at timestamptz not null,
  instance_id text references instances (id),  -- the instance that acts on it, if any
  chased_at timestamptz,  -- when a run opened to remind its person
  escalations int not null default 0,  -- how far up the chain it has gone
  escalated_at timestamptz,
  escalated_to text,
  done_at timestamptz,  -- when the records stopped owing it
  updated_at timestamptz not null default now(),
  unique (scenario, source, record, person)
);
create index if not exists obligations_open on obligations (due_at) where done_at is null;

create table if not exists schedule_fires (
  instance_id text not null references instances (id),
  schedule text not null,
  due_at timestamptz not null,
  fired_at timestamptz not null default now(),
  run_id uuid,  -- the run it opened, if it opened one
  outcome text not null,  -- 'run', or why not, such as 'suspended'
  primary key (instance_id, schedule, due_at)
);

alter table obligations owner to a5s_owner;
alter table schedule_fires owner to a5s_owner;

grant select, insert, update on obligations to a5s_gateway;
grant usage on sequence obligations_id_seq to a5s_gateway;
grant select, insert on schedule_fires to a5s_gateway;

-- a5s's tasks for an agent, such as reminding someone of what falls due, join
-- the person's conversation beside the agent's reply.
alter table turns drop constraint if exists turns_role_check;
alter table turns add constraint turns_role_check
  check (role in ('person', 'agent', 'notice', 'task'));

-- Messages a run sends without answering one, such as a reminder, which people
-- collect from the local channel's inbox.
create index if not exists outbox_unanswered on outbox (person) where inbound_id is null;
