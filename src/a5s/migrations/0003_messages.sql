-- Every message arrives at the core, which records it in `inbound`; the
-- scheduler takes each one from there. Runs expire, and the outbox belongs to
-- the core, which writes what it sends there and lets people collect it.

alter table inbound add column if not exists attempts int not null default 0;
alter table inbound add column if not exists retry_at timestamptz;  -- after a failure to open a run
alter table outbox add column if not exists inbound_id uuid;  -- the message it answers
alter table runs add column if not exists expires_at timestamptz not null
  default now() + interval '1 hour';

create index if not exists inbound_waiting on inbound (received_at) where answered_at is null;
create index if not exists outbox_by_message on outbox (inbound_id);

revoke all on outbox from a5s_scheduler;
revoke usage on sequence outbox_id_seq from a5s_scheduler;
grant update (claimed_at, attempts, retry_at) on inbound to a5s_scheduler;
grant select, update (delivered_at) on outbox to a5s_channels;
