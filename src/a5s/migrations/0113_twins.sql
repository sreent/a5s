-- One sample in five is drawn twice, its twin for a second grader, and counts toward a raise of
-- a cap once both are graded, as the worse of the two (core/samples.py; round 15, C4).
alter table samples add column if not exists twin_of bigint references samples (id)
  on delete cascade;
create index if not exists samples_twins on samples (twin_of) where twin_of is not null;
