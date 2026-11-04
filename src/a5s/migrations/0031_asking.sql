-- Agent to agent: an instance asks another a question, for the people its run acts for
-- (core/asking.py). The settings name whom each instance may ask; the core opens a run of the
-- instance asked, for the same people, and its answer goes back to the run that asked.

alter table instances add column if not exists asks text[] not null default '{}';

create table if not exists questions (
  id uuid primary key,
  asked_by_run uuid not null,  -- the run that asks
  asker text not null,  -- its instance
  asked text not null,  -- the instance asked
  acts_for text[] not null,  -- the people the run that asks acts for, as the answer must be
  text text not null,
  read_outside boolean not null,  -- the mark the run that asks has, which the run asked takes
  asked_at timestamptz not null default now(),
  claimed_at timestamptz,  -- by the scheduler
  run_id uuid,  -- the run that answers it
  answer text,
  answered_at timestamptz,
  answer_read_outside boolean,  -- the mark the run that answers has, which marks the asker's
  answer_sourced text,  -- the values in the answer that the run that answers had read
  problem text,  -- why it wasn't answered
  task jsonb not null  -- the question and its answer, as an A2A task
);
create index if not exists questions_waiting on questions (asked_at) where claimed_at is null;
alter table questions owner to a5s_owner;
grant select, insert, update on questions to a5s_gateway;
grant select, update (claimed_at, problem) on questions to a5s_scheduler;
grant delete on questions to a5s_gateway;  -- retention
