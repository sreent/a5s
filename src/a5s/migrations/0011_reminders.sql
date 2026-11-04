-- Reminders: what people ask an agent to remind them of, and what agents promise to
-- follow up, kept in a5s's own records. An agent offers one, and it counts only once
-- the person confirms it, in a later message of their own. Each is its person's alone.
--
-- A person can also say what they're waiting on for one of their records, and until
-- when, which pauses chases to them about it until then.

create table if not exists reminders (
  id bigserial primary key,
  person text not null,  -- whose it is: the person who asked, or whom the agent promised
  agent text not null,
  instance_id text not null references instances (id),
  about text not null,  -- what to remind them of, in words
  record text,  -- the record it's about, if any
  due_at timestamptz not null,
  offered_at timestamptz not null,
  offered_run uuid not null,
  asked_at timestamptz not null,  -- when the core received the message it was offered in answer to
  confirmed_at timestamptz,  -- once they said yes, in a later message of theirs
  confirmed_run uuid,
  reminded_at timestamptz,
  cancelled_at timestamptz
);
create index if not exists reminders_due on reminders (due_at)
  where confirmed_at is not null and reminded_at is null and cancelled_at is null;

alter table obligations add column if not exists waiting_on text;
alter table obligations add column if not exists waiting_until timestamptz;
alter table obligations add column if not exists waiting_noted_at timestamptz;

alter table reminders owner to a5s_owner;

grant select, insert, update on reminders to a5s_gateway;
grant usage on sequence reminders_id_seq to a5s_gateway;
