-- Files people send with a message, such as a screenshot or an invoice (core/files.py): where
-- the chat keeps each, for the core to fetch as the agent's own bot, or what the web chat sent
-- with the message itself. Each is read through a5s's reader, as content from outside, only
-- once an agent asks about it, and goes a day after the message is answered.
create table if not exists inbound_files (
  inbound_id uuid not null references inbound (id) on delete cascade,
  number int not null,  -- in the order they came
  name text not null,
  media_type text not null,
  size bigint,
  origin jsonb,  -- where the chat keeps it: the chat, its address, and whose bot fetches it
  data bytea,  -- what came with the message itself
  refused text,  -- why a5s didn't keep it, which the agent hears, if it didn't
  primary key (inbound_id, number)
);
alter table inbound_files owner to a5s_owner;
grant select, insert on inbound_files to a5s_channels;
grant select, delete on inbound_files to a5s_gateway;

-- A run's documents may be the files its message came with, read only once it asks
alter table run_documents add column if not exists name text;  -- the file's, as it was sent
alter table run_documents add column if not exists media_type text;
alter table run_documents add column if not exists source jsonb;  -- {inbound, number}, until read
alter table run_documents add column if not exists image bytea;  -- an image, as it was sent
grant update (text, digest, image, source) on run_documents to a5s_gateway;
