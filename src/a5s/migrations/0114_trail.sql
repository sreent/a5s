-- What the ledger's copier found when it last checked the whole ledger, its chain and every
-- copy, which it does when it starts and once a day, for the core's status and the auditors'
-- page, which say whether the trail checks out (round 15, E8).
alter table copier add column if not exists checked_at timestamptz;
alter table copier add column if not exists checked_through bigint;  -- how far the copies held it
alter table copier add column if not exists check_problems text[];  -- what it found, if anything
grant select on copier to a5s_channels;  -- for the auditors' page, which it serves
