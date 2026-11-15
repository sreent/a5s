-- When the core sealed each grade, by its own clock (round 12, B7). Weighing counts the grades
-- sealed since a cap last changed, not those the channels app recorded since, so a grade given
-- before a cap changed but sealed after it is weighed in the next test, never lost. Only the
-- gateway writes it, as it seals.
alter table samples add column if not exists sealed_at timestamptz;
update samples set sealed_at = graded_at where grade_seal is not null and sealed_at is null;
grant update (sealed_at) on samples to a5s_gateway;

-- Everyone who decided a held change, for each part it touched, on each of its samples (round
-- 12, B8): none of them grades it, nor anyone who reports to them.
alter table samples add column if not exists deciders text[] not null default '{}';
update samples set deciders = array[decided_by] where decided_by is not null and deciders = '{}';
