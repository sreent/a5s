-- What the people a run answered said to it, kept with each sample of its change, for its
-- graders, masked until the officer agrees to names, and its judge: so a change made to the
-- wrong record shows (core/samples.py; round 15, C1). The core seals its digest with the
-- draw, so an erasure takes the words out and the sample still counts.
alter table samples add column if not exists asked text;
alter table samples add column if not exists asked_digest text;
grant update (asked) on samples to a5s_gateway;  -- to take it out, at an erasure
-- What a run was asked is found by its run, so a sample's draw reads its turns alone
create index if not exists turns_run on turns (run_id) where run_id is not null;
