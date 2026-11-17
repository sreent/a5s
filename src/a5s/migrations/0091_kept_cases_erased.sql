-- Round 14 (docs/critique.md): a kept case whose words someone erased stays known as erased,
-- with nothing of whose they were, not even the run, so a draft started from a release that still holds it leaves
-- it out, rather than carrying it on (core/run_cases.py). The record goes once no draft and no
-- release holds the case.
alter table kept_cases alter column person drop not null;
alter table kept_cases add column if not exists erased_at timestamptz;
grant update (erased_at, run_id) on kept_cases to a5s_gateway;
