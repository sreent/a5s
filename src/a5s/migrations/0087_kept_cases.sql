-- Test cases kept from real runs (core/run_cases.py): whose words each holds, so an export
-- lists it, erasure takes it out of every draft that holds it, and a departure archives it, as
-- it does what a5s keeps for them. The case says nothing of whom: only its token, in its
-- from_run, which this links back.
create table if not exists kept_cases (
  token text primary key,  -- the case's from_run
  agent text not null,
  name text not null,  -- the case's name, as it was kept
  run_id uuid,  -- the run it was kept from
  person text not null,  -- who said what it holds: whom the run answered
  acts_for text[] not null default '{}',  -- and everyone the run acted for
  kept_by text,  -- who kept it, in their draft: none once they're erased
  kept_at timestamptz not null default now()
);
create index if not exists kept_cases_person on kept_cases (person);
alter table kept_cases owner to a5s_owner;
grant select, insert on kept_cases to a5s_channels;  -- keeping a case, in the studio
grant select, delete, update (person, acts_for, kept_by) on kept_cases to a5s_gateway;  -- the
-- officer's exports and erasures, and departures
grant update (files, updated_at) on agent_drafts to a5s_gateway;  -- erasure takes a case out
