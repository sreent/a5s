-- a5s schema. Every statement is idempotent, so it's safe to run on every start.

-- Trusted core data: instances, runs and the ledger.

create table if not exists instances (
  id text primary key,
  definition text not null,
  release text not null,
  status text not null default 'active'
    check (status in ('proposed', 'active', 'suspended', 'retired')),
  level int not null default 1 check (level between 0 and 2),
  grants text[] not null default '{}',
  model text not null,
  serves text[] not null default '{}',
  owner text,
  deputy text,
  pins jsonb not null default '{}',
  settings_version text,
  suspended_by text,
  updated_at timestamptz not null default now()
);

create table if not exists runs (
  id uuid primary key,
  instance_id text not null references instances (id),
  token_hash bytea not null unique,
  trigger jsonb not null,
  acts_for text[] not null default '{}',
  read_outside boolean not null default false,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  outcome text
);

-- Signed versions of each scenario's settings. Serials only ever rise.
create table if not exists settings_versions (
  scenario text not null,
  serial bigint not null,
  version text not null,
  signers text[] not null,
  applied_at timestamptz not null default now(),
  primary key (scenario, serial)
);

-- Each entry is canonical JSON, chained to the one before by its hash.
create table if not exists ledger (
  seq bigint primary key,
  entry text not null,
  prev_hash bytea not null,
  hash bytea not null,
  kind text generated always as ((entry::jsonb) ->> 'kind') stored,
  action text generated always as ((entry::jsonb) ->> 'action') stored,
  decision text generated always as ((entry::jsonb) ->> 'decision') stored,
  run_id text generated always as ((entry::jsonb) ->> 'run') stored,
  instance_id text generated always as ((entry::jsonb) ->> 'instance') stored
);

create or replace function a5s_ledger_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'the ledger is append-only';
end;
$$;

drop trigger if exists ledger_append_only on ledger;
create trigger ledger_append_only before update or delete on ledger
  for each row execute function a5s_ledger_append_only();

-- Messages the core received from a channel that signs them, such as Teams,
-- with the sender it checked. A run answering one names it, and uses it once.
create table if not exists inbound (
  id uuid primary key,
  channel text not null,
  source_id text not null,  -- the channel's own id for it, so a resent message counts once
  person text not null,
  agent text not null,
  text text not null,
  reply_to jsonb not null,  -- where answers go
  received_at timestamptz not null default now(),
  claimed_at timestamptz,  -- by the scheduler
  answered_at timestamptz,  -- when a run opened for it
  notices int not null default 0,  -- a5s's own notices sent in answer to it
  unique (channel, source_id)
);

-- Services: conversations, the outbox and leases.

create table if not exists turns (
  id bigserial primary key,
  person text not null,
  agent text not null,
  topic text not null default 'general',
  role text not null check (role in ('person', 'agent')),
  content text not null,
  run_id uuid,
  at timestamptz not null default now()
);
create index if not exists turns_conversation on turns (person, agent, topic, id);

create table if not exists outbox (
  id bigserial primary key,
  run_id uuid,
  instance_id text,
  person text not null,
  channel text not null,
  text text not null,
  at timestamptz not null default now(),
  delivered_at timestamptz
);

create table if not exists leases (
  key text primary key,
  holder text not null,
  expires_at timestamptz not null
);

-- The sample scenario's own system, kept apart from a5s's tables.

create schema if not exists sample;

create table if not exists sample.drafts (
  id bigserial primary key,
  title text not null,
  body text not null,
  created_for text not null,
  at timestamptz not null default now()
);
