-- How the ledger's copier is doing, as it records it each time it copies or can't, for the
-- core's status and the operators' figures, which read no copies themselves (round 15, D8).
create table if not exists copier (
  only_one boolean primary key default true check (only_one),
  through bigint,           -- the last entry its copies hold, as it last copied them
  copied_at timestamptz,    -- when it last copied, or found nothing new to copy
  problem text,             -- why it couldn't, the last time it tried and couldn't
  problem_at timestamptz,
  stopped boolean not null default false  -- it stopped, until someone acts on its problem
);
grant select, insert, update on copier to a5s_anchor;
grant select on copier to a5s_gateway;
