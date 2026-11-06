-- What each run read from its provider's cache, and wrote to it, of the tokens it took in, which
-- providers price apart (core/budgets.py, core/measures.py).

alter table runs add column if not exists tokens_cached bigint not null default 0;
alter table runs add column if not exists tokens_cache_written bigint not null default 0;
grant update (tokens_cached, tokens_cache_written) on runs to a5s_gateway;
