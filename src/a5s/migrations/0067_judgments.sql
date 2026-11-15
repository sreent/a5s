-- The judge's verdicts: an approved model's grade of each sample of an agent's work, beside
-- people's, never instead of them (core/judging.py). Only the core writes or reads them. The
-- channels app, which serves the grading page, reads a verdict only through judged_samples,
-- once people have graded the sample, so they always grade as they would without it.
create table if not exists judgments (
  sample_id bigint primary key references samples (id) on delete cascade,
  judge text not null,  -- the model's alias
  -- none if its answer couldn't be read as a grade: such a sample isn't asked about again
  verdict text check (verdict in ('right', 'wrong', 'critical')),
  why text not null,  -- in a sentence, cut to 200 characters
  tokens integer not null default 0,
  judged_at timestamptz not null default now()
);
alter table judgments owner to a5s_owner;
grant select, insert on judgments to a5s_gateway;

-- Each sample people graded that the judge judged too: how far it agrees with them
create or replace view judged_samples as
  select s.scenario, s.definition, s.instance_id, s.part, s.action, s.grade, s.graded_at,
         j.judge, j.verdict
  from samples s join judgments j on j.sample_id = s.id
  where s.grade is not null and j.verdict is not null;
alter view judged_samples owner to a5s_owner;
grant select on judged_samples to a5s_gateway, a5s_channels;
