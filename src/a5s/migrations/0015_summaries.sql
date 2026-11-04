-- Summaries: one for each topic of each person's conversation with an agent, for the turns
-- that no longer fit in a run. A run of a5s's own folds turns into it once they fall out of
-- what a run is given, and code keeps every key, amount and date they had, and none they
-- didn't. The person can see it, and have it corrected.

create table if not exists summaries (
  person text not null,
  agent text not null,
  topic text not null,
  body jsonb not null,  -- decisions, commitments, open questions, facts and corrections
  through bigint not null,  -- the last turn folded into it
  run_id uuid,  -- the run that last folded turns into it
  updated_at timestamptz not null default now(),
  primary key (person, agent, topic)
);

alter table summaries owner to a5s_owner;

grant select, insert, update on summaries to a5s_scheduler;  -- the context service keeps them
grant select, update (body, updated_at) on summaries to a5s_gateway;  -- a person's corrections
grant select on summaries to a5s_channels;  -- for the person to see
