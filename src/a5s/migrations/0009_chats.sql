-- Conversations in a chat a5s writes to itself, such as Matrix or Teams, that a
-- person didn't start by writing to the agent: ones an agent's bot started, and
-- ones a person let it write in, such as by adding the agent's app in Teams.
-- Also when a person left a conversation with an agent's bot, so a5s doesn't
-- keep writing where they won't see it, or ask them in again.

create table if not exists chats (
  channel text not null,
  place text not null,  -- the chat's own id for it: a Matrix room, or a Teams conversation
  person text not null,
  agent text not null,
  reply_to jsonb not null,  -- where to send to it
  started_at timestamptz,  -- when the agent's bot started it, or was let in
  left_at timestamptz,  -- when the person left it
  primary key (channel, place)
);
create index if not exists chats_by_person on chats (person, agent);

alter table chats owner to a5s_owner;

grant select, insert, update on chats to a5s_gateway;  -- it starts them
grant select, insert, update on chats to a5s_channels;  -- where people add and leave them
