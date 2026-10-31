-- The settings app: someone who approves instances asks there for a new version of the
-- settings. The core's endpoint records what they asked for, signed in, and the gateway
-- proposes it to everyone it needs, as it does any version, so only the gateway proposes.

create table if not exists settings_requests (
  id bigserial primary key,
  scenario text not null,
  person text not null,  -- who asked, signed in at the settings app
  raw bytea not null,  -- the version they asked for
  asked_at timestamptz not null default now(),
  digest text,  -- the version the gateway proposed, once it has
  outcome text,  -- proposed, or why it couldn't be
  decided_at timestamptz
);
create index if not exists settings_requests_waiting on settings_requests (id) where outcome is null;

alter table settings_requests owner to a5s_owner;

grant select, insert on settings_requests to a5s_channels;
grant usage on sequence settings_requests_id_seq to a5s_channels;
grant select, update (digest, outcome, decided_at) on settings_requests to a5s_gateway;
