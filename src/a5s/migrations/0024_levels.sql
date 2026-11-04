-- Level 2: an instance's level for each type of action in each part, as the signed settings
-- set it; a5s's cap on it, for each release, part and type of action, which samples raise
-- and lower; and what's been counted against the scenario's limits.

alter table instances add column if not exists actions jsonb not null default '{}';

-- With no row, the cap is 1: a release earns level 2 for a type of action in a part on
-- graded samples (core/samples.py), and a release that widens starts again.
create table if not exists caps (
  release text not null,
  part text not null,
  action text not null,
  cap int not null check (cap between 0 and 2),
  since timestamptz not null,
  why text not null,
  primary key (release, part, action)
);

-- Each change an agent asked for, counted against the scenario's limits: one a run took, or
-- one for someone it acted for, in the last 30 days. A call made again in the same run, the
-- same change to the same records, counts once.
create table if not exists action_counts (
  id bigserial primary key,
  run_id uuid not null,
  instance_id text not null,
  action text not null,
  change text not null,  -- a digest of the change: the action, its records and its arguments
  acts_for text[] not null,
  at timestamptz not null,
  unique (run_id, change)
);
create index if not exists action_counts_by_action on action_counts (action, at);

alter table caps owner to a5s_owner;
alter table action_counts owner to a5s_owner;

grant select on caps to a5s_gateway;
grant select, insert, delete on action_counts to a5s_gateway;
grant usage on sequence action_counts_id_seq to a5s_gateway;
alter table action_counts add column if not exists over boolean not null default false;  -- held for being past a limit

-- A held change keeps the digest of the change, so the same call made again in its run
-- answers with the same proposal, and its deciders are asked once.
alter table proposals add column if not exists change text;
