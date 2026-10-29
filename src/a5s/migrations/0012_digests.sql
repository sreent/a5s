-- Digests: one message a day for each person, from all the agents together, at a
-- time they choose. What agents write to someone on their own waits for it; the
-- day's digest goes once, and closes the day, so what comes later waits for the next.
-- People's typed preferences, such as their digest's time, are theirs to set.

create table if not exists preferences (
  person text not null,
  name text not null,  -- such as 'digest-time'
  value text not null,
  set_at timestamptz not null,
  set_run uuid,  -- the run that set it, in answer to their own message
  primary key (person, name)
);

create table if not exists digest_items (
  id bigserial primary key,
  person text not null,
  agent text,  -- whose words; none for a5s's own
  instance_id text,
  run_id uuid,
  text text not null,
  at timestamptz not null,
  digest_due timestamptz  -- the digest it went in, once it went
);
create index if not exists digest_items_waiting on digest_items (person) where digest_due is null;

create table if not exists digests (
  person text not null,
  due_at timestamptz not null,  -- the day's digest time, in the person's time zone
  sent_at timestamptz not null,
  items int not null,  -- none, when there was nothing to tell
  channel text,
  primary key (person, due_at)
);

alter table reminders add column if not exists in_digest boolean not null default true;

alter table preferences owner to a5s_owner;
alter table digest_items owner to a5s_owner;
alter table digests owner to a5s_owner;

grant select, insert, update on preferences to a5s_gateway;
grant select, insert, update on digest_items to a5s_gateway;
grant usage on sequence digest_items_id_seq to a5s_gateway;
grant select, insert on digests to a5s_gateway;
