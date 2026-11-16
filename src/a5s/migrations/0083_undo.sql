-- Undoing a change an agent made (core/undoing.py): how to reverse each change a5s made with a
-- tool that says how, for as long as the tool says, and someone asking to, signed in afresh for
-- that act alone, which the core checks again and carries out.
create table if not exists changes_made (
  id bigserial primary key,
  run_id uuid not null,
  instance_id text not null,
  definition text not null,
  release text not null,
  tool text not null,
  schema_hash text not null,  -- of the tool that made it: one changed since undoes nothing
  action text not null,
  record text not null,  -- the one record it changed
  parts text[] not null,
  said text not null,  -- what it did, in the words code worked out
  undo jsonb not null,  -- the call that reverses it, worked out as it was made
  as_left jsonb not null,  -- the fields the undo restores, as the change left them
  acts_for text[] not null,  -- whose words asked for it
  proposal_id bigint,  -- the held change it was, if it was one
  made_at timestamptz not null default now(),
  until timestamptz not null,  -- after which it can't be undone
  state text check (state in ('asked', 'undoing', 'undone', 'refused', 'failed')),
  asked_by text,
  asked_at timestamptz,
  nonce text,
  salt text,
  token text unique,  -- the sign-in's hash, so each works once
  proof text,  -- the sign-in itself, until the core has checked it
  issuer text,
  subject text,
  outcome text,
  undone_at timestamptz,
  undone_by text
);
create index if not exists changes_made_asked on changes_made (asked_at) where state = 'asked';
create index if not exists changes_made_for on changes_made using gin (acts_for);
alter table changes_made owner to a5s_owner;
grant select (id, run_id, instance_id, definition, record, parts, said, acts_for, made_at, until,
              state, asked_by, asked_at, outcome, undone_at, undone_by, token),
      update (state, asked_by, asked_at, nonce, salt, token, proof, issuer, subject, outcome)
  on changes_made to a5s_channels;
grant select, insert, update, delete on changes_made to a5s_gateway;  -- and retention, erasure
grant usage on sequence changes_made_id_seq to a5s_gateway;

-- Whether a grade is an undo's, which counts as wrong: for whoever reads the sample
alter table samples add column if not exists undone_at timestamptz;
grant update (undone_at, lapsed_at) on samples to a5s_gateway;
