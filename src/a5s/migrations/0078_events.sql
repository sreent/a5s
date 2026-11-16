-- What other systems say happened, such as a ticket opened (core/events.py): checked by the
-- channels' endpoint against the sending system's signing secret, kept once by its own id, and
-- worked on by the agent whose release takes it, in a run the core opens at its next sweep.
-- An event names its records and the person it's about, if any, and nothing else.
create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  source text not null,  -- the system that sent it, as the deployment names it
  event_id text not null,  -- its own id there: what makes a second delivery the same event
  type text not null,  -- such as ticket-opened
  records text[] not null default '{}',  -- the keys of the records it's about
  person text,  -- whom it's about, as the directory knows them, if anyone
  received_at timestamptz not null default now(),
  taken_at timestamptz,  -- once the core opened a run for it, or found nothing to
  instance_id text,
  run_id uuid,
  outcome text,  -- run, or why there was none
  unique (source, event_id)
);
create index if not exists events_waiting on events (received_at) where taken_at is null;
alter table events owner to a5s_owner;

-- The channels' endpoint records them; the gateway opens their runs and records what came of
-- them, and lets them go as it lets messages go (core/retention.py); the export reads them.
grant select, insert on events to a5s_channels;
grant select, update, delete on events to a5s_gateway;
