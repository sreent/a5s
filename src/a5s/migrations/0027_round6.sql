-- Round 6's fixes to phase 2.

-- A document a run read again keeps its number and the form a5s's reader filled from it, so
-- it isn't sent to the model twice.
alter table run_documents add column if not exists digest text;
alter table run_documents add column if not exists form jsonb;
create index if not exists run_documents_by_digest on run_documents (run_id, digest);

-- Counts: how many records each change touches, each of which counts, and what became of it,
-- so the same change made again in its run is answered without being made again. A change
-- the records system didn't take isn't counted. Counts go once their 30 days are past.
alter table action_counts add column if not exists records int not null default 1;
alter table action_counts add column if not exists state text not null default 'made';
alter table action_counts drop constraint if exists action_counts_state;
alter table action_counts add constraint action_counts_state
  check (state in ('making', 'made', 'held'));
grant update (state) on action_counts to a5s_gateway;
create index if not exists action_counts_by_instance on action_counts (instance_id, action, at);
create index if not exists action_counts_by_time on action_counts (at);

-- What decides how a release acts on a type of action: its model, and the tools of that type
-- it may use, as pinned. a5s's caps are kept for that, not for the release, so a release that
-- changes only instructions keeps the level its grades earned, and one that changes a tool or
-- the model starts again at 1 for what it widens.
create table if not exists behaviours (
  release text not null,
  action text not null,
  behaviour text not null,
  primary key (release, action)
);
alter table behaviours owner to a5s_owner;
grant select, insert on behaviours to a5s_gateway;
grant select on behaviours to a5s_channels;

-- Caps: kept for a behaviour, with the threshold they were earned under and when the grades
-- that earned them began, and sealed by the core with the ledger entry that set them, so a
-- row written straight into the database, or an old one put back, doesn't count.
alter table caps add column if not exists behaviour text;
alter table caps add column if not exists threshold double precision;
alter table caps add column if not exists window_from timestamptz;
alter table caps add column if not exists seq bigint;
alter table caps add column if not exists seal text;
alter table caps drop constraint if exists caps_pkey;
alter table caps alter column release drop not null;
create unique index if not exists caps_by_behaviour on caps (behaviour, part, action);
grant select on caps to a5s_channels;
create index if not exists ledger_caps on ledger (seq) where kind = 'cap';

-- Samples: what deciders were told, and the records as they stood when the change was asked
-- for; a grade sealed by the core, from a sign-in to give exactly those grades; and samples
-- nobody graded in a quarter lapse, and go a year after they were drawn.
alter table samples add column if not exists flags jsonb not null default '[]';
alter table samples add column if not exists lapsed_at timestamptz;
alter table samples add column if not exists grade_token text;
alter table samples add column if not exists grade_nonce text;
alter table samples add column if not exists grade_salt text;
alter table samples add column if not exists grade_issuer text;
alter table samples add column if not exists grade_subject text;
alter table samples add column if not exists grade_seal text;
grant update (grade, graded_by, graded_at, grade_token, grade_nonce, grade_salt, grade_issuer,
              grade_subject, grade_seal) on samples to a5s_channels;
grant update (lapsed_at) on samples to a5s_gateway;
-- The graders' page leaves out graders from the teams of each instance's owner and deputy.
grant select (id, owner, deputy) on instances to a5s_channels;
create index if not exists samples_waiting on samples (scenario, id)
  where grade is null and lapsed_at is null;

-- Held changes: who was asked and reminded, each in their own hours; when each step falls
-- due, so the sweep reads only what's due; the last decision it weighed; and the records as
-- they stood when it was asked for, for graders and for the report.
alter table proposals add column if not exists remind_at timestamptz;
alter table proposals add column if not exists escalate_at timestamptz;
alter table proposals add column if not exists asked text[] not null default '{}';
alter table proposals add column if not exists reminded text[] not null default '{}';
alter table proposals add column if not exists escalated text[] not null default '{}';
alter table proposals add column if not exists weighed bigint not null default 0;
alter table proposals add column if not exists standing jsonb;
update proposals set remind_at = proposed_at, escalate_at = proposed_at
  where remind_at is null and status = 'waiting';  -- worked out again at the next sweep
grant update (remind_at, escalate_at, asked, reminded, escalated, weighed) on proposals to a5s_gateway;
create index if not exists proposals_by_change on proposals (instance_id, change)
  where status = 'waiting';
create index if not exists proposals_due on proposals (scenario, least(remind_at, escalate_at, lapses_at))
  where status = 'waiting';

-- A decider may say why they reject a change, in a few words, sealed with their decision.
alter table proposal_decisions add column if not exists reason text;
