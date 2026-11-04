-- Urgent messages: what a5s and its agents write to someone at once, when they aren't waiting
-- for it, such as an escalation or a reminder for a particular time. Up to five a day go at
-- once, in the person's own day, across all the agents. The rest wait, and go together once
-- the oldest has waited an hour, so urgent stays urgent without becoming noise.

create table if not exists urgent_sent (
  person text not null,
  day date not null,  -- in the person's own time zone
  sent int not null default 0,  -- urgent messages that went at once
  primary key (person, day)
);

create table if not exists urgent_held (
  id bigserial primary key,
  person text not null,
  agent text,  -- whose words; none for a5s's own
  instance_id text,
  run_id uuid,
  text text not null,
  at timestamptz not null,
  sent_at timestamptz  -- in the batch that took it
);
create index if not exists urgent_waiting on urgent_held (person) where sent_at is null;

alter table urgent_sent owner to a5s_owner;
alter table urgent_held owner to a5s_owner;

grant select, insert, update, delete on urgent_sent to a5s_gateway;
grant select, insert, update, delete on urgent_held to a5s_gateway;
grant usage on sequence urgent_held_id_seq to a5s_gateway;
