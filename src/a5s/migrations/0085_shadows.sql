-- Shadow runs (core/shadows.py): a new version of an agent answers what people ask an instance,
-- beside it, sending and changing nothing, for graders to compare, once the data protection
-- officer chooses to let it. A shadow is an instance of its own, whose settings name the one it
-- answers beside; its status says it does no work of its own.
alter table instances add column if not exists shadows text;  -- the instance it answers beside
alter table instances drop constraint if exists instances_status_check;
alter table instances add constraint instances_status_check
  check (status in ('proposed', 'active', 'suspended', 'retired', 'shadow'));
grant select (shadows) on instances to a5s_channels;  -- what each shadows, for the studio

create table if not exists shadow_answers (
  id bigserial primary key,
  run_id uuid not null unique,  -- the shadow's run, which sent nothing
  live_run_id uuid not null,  -- the run whose answer was sent
  instance_id text not null,  -- the shadow
  shadows text not null,  -- the instance it answered beside
  definition text not null,  -- the shadow's agent
  person text not null,  -- whose conversation: theirs, or their group chat's
  agent text not null,  -- the agent they spoke to
  acts_for text[] not null,
  asked text not null,  -- what they said, as the instance it shadows had it
  sent text not null,  -- what that instance answered them
  answer text not null,  -- what the shadow answered, which went nowhere
  records text[] not null default '{}',  -- the records the three name, for who may grade them
  at timestamptz not null default now(),
  grade text check (grade in ('better', 'same', 'worse', 'wrong')),
  graded_by text,
  graded_at timestamptz,
  grade_noted_at timestamptz,  -- when the core put the grade in the ledger
  judged text check (judged in ('better', 'same', 'worse', 'wrong')),  -- the judge's, apart
  judged_why text,
  judged_at timestamptz
);
create unique index if not exists shadow_answers_once on shadow_answers (instance_id, live_run_id);
create index if not exists shadow_answers_waiting on shadow_answers (id) where grade is null;
alter table shadow_answers owner to a5s_owner;
grant select, insert, delete, update (judged, judged_why, judged_at, grade_noted_at, graded_by)
  on shadow_answers to a5s_gateway;  -- and erasure, which leaves a grade and forgets its grader
grant usage on sequence shadow_answers_id_seq to a5s_gateway;
grant select, update (grade, graded_by, graded_at) on shadow_answers to a5s_channels;  -- graders'
grant select (instance_id, live_run_id) on shadow_answers to a5s_scheduler;  -- answered already
