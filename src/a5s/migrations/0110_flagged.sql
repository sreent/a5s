-- What a held change's deciders are told to know of it, and its sample's graders, as a5s's own
-- words with what changes in each, so each reads them in the language they read (round 15,
-- B6). The English stays in `flags`, as before, for the record and the judge.
alter table proposals add column if not exists flagged jsonb;
alter table samples add column if not exists flagged jsonb;
