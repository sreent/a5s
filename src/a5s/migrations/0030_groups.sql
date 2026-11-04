-- Group conversations: an agent in a group chat, such as a Teams group chat or a Matrix room,
-- answering whoever mentions it there and acting for everyone in it (core/groups.py). A
-- group's conversation is keyed by its own name, group:<hex>, where a person's is keyed by
-- their id, so what a person's conversation keeps, a group's keeps the same way.

create table if not exists groups (
  id text primary key,  -- group:<hex>
  channel text not null,
  place text not null,  -- the chat's own id: a Matrix room, or a Teams conversation
  first_at timestamptz not null default now(),
  unique (channel, place)
);
alter table groups owner to a5s_owner;
grant select, insert on groups to a5s_channels;  -- where its messages arrive
grant select on groups to a5s_gateway, a5s_scheduler;

-- A message in a group: whose conversation it is, and who was in the group when it was said
alter table inbound add column if not exists conversation text;  -- a group's, or null: the sender's own
alter table inbound add column if not exists members text[];

-- A turn in a group: who said it, and who heard it, so a run gives nobody what was said before
-- they joined
alter table turns add column if not exists speaker text;
alter table turns add column if not exists heard_by text[];

-- A reminder offered in a group is kept and confirmed there, by the person who asked
alter table reminders add column if not exists conversation text;

-- Someone who leaves: what they said in a group stays there, under their archive's name
grant update (speaker, heard_by) on turns to a5s_gateway;
grant update (members) on inbound to a5s_gateway;
