-- Samples of agents' changes, which people outside the team that built each agent grade, and
-- whose grades raise or lower a5s's cap on its level (core/samples.py).

create table if not exists samples (
  id bigserial primary key,
  scenario text not null,
  kind text not null check (kind in ('proposal', 'action')),  -- a decided held change, or one made at level 2
  proposal_id bigint,
  run_id uuid not null,
  instance_id text not null,
  release text not null,
  definition text not null,
  part text not null,
  action text not null,
  said text not null,  -- what the agent asked for or did, in words code worked out
  records jsonb not null,  -- the records it named, as they stood
  acts_for text[] not null,
  decided text,  -- for a held change: approve or reject
  decided_by text,
  drawn_at timestamptz not null,
  grade text check (grade in ('right', 'wrong', 'critical')),
  graded_by text,
  graded_at timestamptz
);
create index if not exists samples_to_grade on samples (id) where grade is null;
create index if not exists samples_by_cap on samples (release, part, action);

alter table samples owner to a5s_owner;

grant select, insert on samples to a5s_gateway;
grant usage on sequence samples_id_seq to a5s_gateway;
grant insert, update on caps to a5s_gateway;
grant delete on samples to a5s_gateway;  -- a year after they're graded, by retention
grant select, update (grade, graded_by, graded_at) on samples to a5s_channels;
