-- Held proposals: a change to a part's data an agent may not make alone, waiting for a person
-- to decide it. The gateway keeps the exact call, the values of the handles in it, and each
-- record it names as it stood. Its deciders decide it on the core's page, signed in afresh for
-- that decision, and the channels app records each decision, sealed by the core. The gateway
-- makes the call once it's approved, if the records haven't changed.

create table if not exists proposals (
  id bigserial primary key,
  scenario text not null,
  digest text not null unique,  -- what a decision's sign-in commits to
  run_id uuid not null,
  instance_id text not null,
  definition text not null,
  release text not null,  -- the release whose agent proposed it
  tool text not null,
  schema_hash text not null,  -- the tool as it was pinned when the call was held
  action text not null,  -- the type of action, such as change-due-date
  args jsonb not null,  -- the exact call, as the agent made it, with its handles
  records jsonb not null,  -- each record it names, by key, and a digest of it as it stood
  parts text[] not null,
  acts_for text[] not null,  -- who the run acted for: told what's decided, and never deciders
  deciders text[] not null,
  said text not null,  -- what it does, in words code worked out
  flags jsonb not null default '[]',  -- what deciders should know, such as values the agent wrote itself
  sensitive boolean not null,  -- decided one at a time, never with others
  read_outside boolean not null,
  seq bigint not null,  -- the ledger entry that held it
  proposed_at timestamptz not null,
  reminded_at timestamptz,
  escalated_at timestamptz,
  lapses_at timestamptz not null,
  status text not null default 'waiting',  -- waiting, then made, rejected, lapsed or not made
  decided_by text,
  decided_at timestamptz,
  ended_at timestamptz,
  outcome text  -- what became of it, in words
);
create index if not exists proposals_waiting on proposals (id) where status = 'waiting';

-- The values its handles stood for, kept until it's decided or lapses, since a run's own go an
-- hour after it ends.
create table if not exists proposal_values (
  proposal_id bigint not null references proposals (id) on delete cascade,
  handle text not null,
  value text not null,
  primary key (proposal_id, handle)
);

create table if not exists proposal_decisions (
  id bigserial primary key,
  scenario text not null,
  digest text not null references proposals (digest),
  decision text not null check (decision in ('approve', 'reject')),
  person text not null,
  token text not null,  -- the sign-in, by its hash: it decides once
  nonce text not null,
  salt text not null,
  issuer text not null,
  subject text not null,
  decided_at timestamptz not null default now(),
  seal text not null,  -- the core's, over all of the above
  unique (digest, person),
  unique (token, digest)
);

alter table proposals owner to a5s_owner;
alter table proposal_values owner to a5s_owner;
alter table proposal_decisions owner to a5s_owner;

grant select, insert on proposals to a5s_gateway;
grant update (status, decided_by, decided_at, ended_at, outcome, reminded_at, escalated_at)
  on proposals to a5s_gateway;
grant usage on sequence proposals_id_seq to a5s_gateway;
grant select, insert, delete on proposal_values to a5s_gateway;
grant select on proposal_decisions to a5s_gateway;
grant delete on proposals, proposal_decisions to a5s_gateway;  -- a year after they end, by retention
grant select on proposals to a5s_channels;
grant select, insert on proposal_decisions to a5s_channels;
grant usage on sequence proposal_decisions_id_seq to a5s_channels;
