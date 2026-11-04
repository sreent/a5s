-- Departures: someone the directory no longer names, from when a5s first missed them, and,
-- once a day has passed, the name a5s archived what it keeps for them under
-- (core/departures.py). Kept until the archive goes, 12 months on.

create table if not exists departures (
  id bigserial primary key,
  person text not null,
  missing_since timestamptz not null,
  archived_at timestamptz,
  archived_as text  -- the archive's name, such as former:3f9a0c1d2e4b5a6f
);
create unique index if not exists departures_missing on departures (person) where archived_at is null;
alter table departures owner to a5s_owner;
grant select, insert, update, delete on departures to a5s_gateway;
grant usage on sequence departures_id_seq to a5s_gateway;

-- The gateway archives what a5s keeps for someone who left, in place, under the archive's name.
grant update (person) on turns, summaries, outbox, chats, digest_items, digests, urgent_held,
  profile_notes, reminders, report_fires to a5s_gateway;
grant update (person, answered_at) on inbound to a5s_gateway;
grant update (cancelled_at) on reminders to a5s_gateway;
grant update (ended_at) on profile_notes to a5s_gateway;
grant select on turns, summaries, inbound, outbox, chats, digest_items, digests, urgent_held,
  profile_notes, reminders, report_fires to a5s_gateway;
grant delete on preferences, report_seen, digest_waits, urgent_sent to a5s_gateway;
