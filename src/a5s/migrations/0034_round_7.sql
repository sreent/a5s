-- Round 7 of the critique (docs/critique.md).

-- A person's own chat with an agent that someone else joined, so it's theirs alone no more:
-- a5s writes to them first in a new one (core/chats.py)
alter table chats add column if not exists shared_at timestamptz;

-- Archiving someone who left finds them in group chats by index, not by reading every turn
create index if not exists turns_heard_by on turns using gin (heard_by) where heard_by is not null;
create index if not exists turns_speaker on turns (speaker) where speaker is not null;
create index if not exists inbound_members on inbound using gin (members) where members is not null;

-- A reminder offered in a group chat: who was there to hear it, so it's given to a run, and
-- confirmed, only while everyone in the chat heard it (core/reminders.py)
alter table reminders add column if not exists heard_by text[];

-- An answer kept back from a group chat goes to whoever asked, in a chat of their own
grant update (route) on outbox to a5s_gateway;

-- A question's A2A task is built from its row when it's needed (core/asking.py), not kept
alter table questions alter column task drop not null;

-- The notebook (core/notebook.py): every record a note's run read, all of which whoever it
-- reaches may see; its records' fingerprints, so it goes once they change; and when they were
-- last read again
alter table notebook add column if not exists read_records text[];
alter table notebook add column if not exists fingerprints jsonb;
alter table notebook add column if not exists checked_at timestamptz not null default now();
grant update (read_records, fingerprints, checked_at) on notebook to a5s_gateway;
alter table notebook add column if not exists links jsonb;  -- each record's link, for its page
grant update (links) on notebook to a5s_gateway;

-- Each part checks, as it starts, that no later release of a5s migrated the database
grant select on schema_migrations to a5s_gateway, a5s_channels, a5s_scheduler;
