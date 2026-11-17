-- The mailboxes a team's work arrives in (connectors/mailboxes.py): each message the core has
-- seen, by a key of a5s's own, which agents name it by, beside Graph's id for it, and never its
-- words; and where each inbox stood when the core last asked what's new there.
create table if not exists mail_messages (
  mailbox text not null,  -- as the scenario's mailboxes.yaml names it
  key text not null,  -- such as M-3f2a9c0d41b7e8a6
  message_id text not null,  -- Graph's id for it in the mailbox
  seen_at timestamptz not null default now(),
  primary key (mailbox, key),
  unique (mailbox, message_id)
);
alter table mail_messages owner to a5s_owner;

create table if not exists mail_state (
  mailbox text primary key,
  delta text,  -- Graph's link to what's come in since the core last asked
  polled_at timestamptz  -- when a core last asked, so only one asks a minute
);
alter table mail_state owner to a5s_owner;

grant select, insert, update, delete on mail_messages, mail_state to a5s_gateway;
-- The core keeps each new message as the mailbox's event, as the channels' endpoint keeps
-- other systems' (core/events.py)
grant insert on events to a5s_gateway;
