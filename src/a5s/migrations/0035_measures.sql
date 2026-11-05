-- The measures a5s's first users baseline (core/measures.py, docs/pilot.md): each run's tokens
-- in and out apart, as providers price them, beside the total its budgets count.

alter table runs add column if not exists tokens_in bigint not null default 0;
alter table runs add column if not exists tokens_out bigint not null default 0;
grant update (tokens_in, tokens_out) on runs to a5s_gateway;
