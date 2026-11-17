-- Handing a conversation over to people (core/handover.py): an instance's settings name the
-- directory's teams it may hand one to, and its agent hands one over at the person's word, with
-- a brief. The core keeps what the person said lately, for the team to read, since the channels
-- app reads no conversation; whoever takes it answers from the studio, the core putting each
-- reply in the person's chat, until they hand it back.
alter table instances add column if not exists hands_to text[] not null default '{}';
grant select (hands_to) on instances to a5s_channels;  -- whose teams answer, for the studio

create table if not exists handovers (
  id bigserial primary key,
  person text not null,  -- whose conversation it is: their own chat with the agent
  agent text not null,
  instance_id text not null,
  run_id uuid,  -- the run that handed it over
  team text not null,
  brief text not null,  -- what the agent says they need, for whoever takes it
  said jsonb not null default '[]',  -- what the person said lately, as they said it
  started_at timestamptz not null default now(),
  told_at timestamptz,  -- when the core told the person, in their chat
  taken_by text,  -- who of the team answers it now
  taken_at timestamptz,
  ended_at timestamptz,
  ended_by text,  -- who handed it back, or nobody, if it lapsed
  back_told_at timestamptz  -- when the core told the person, and noted it for the agent
);
create unique index if not exists handovers_open on handovers (person, agent) where ended_at is null;
alter table handovers owner to a5s_owner;
grant select, update (taken_by, taken_at, ended_at, ended_by) on handovers to a5s_channels;
grant select, insert, update, delete on handovers to a5s_gateway;
grant usage on sequence handovers_id_seq to a5s_gateway;
grant select (person, agent, ended_at) on handovers to a5s_scheduler;  -- it leaves theirs alone

create table if not exists handover_replies (
  id bigserial primary key,
  handover_id bigint not null references handovers (id) on delete cascade,
  by_person text not null,
  text text not null,
  at timestamptz not null default now(),
  sent_at timestamptz  -- when the core put it in the person's chat
);
alter table handover_replies owner to a5s_owner;
grant select, insert on handover_replies to a5s_channels;
grant usage on sequence handover_replies_id_seq to a5s_channels;
grant select, update (sent_at), delete on handover_replies to a5s_gateway;
