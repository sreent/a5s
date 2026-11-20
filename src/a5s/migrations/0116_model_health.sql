-- The reliability ledger (docs/model-execution.md): what each model answered, and how,
-- so a model that drifts or stalls shows here and is measured, not argued about.
create table if not exists canary_scores (
    id bigint generated always as identity primary key,
    at timestamptz not null default now(),
    scenario text not null,
    canary text not null,
    model text not null,
    passed boolean not null,
    answered text not null default '',
    seconds real not null default 0
);
create index if not exists canary_scores_recent on canary_scores (scenario, model, at desc);
create table if not exists model_health (
    scenario text not null,
    model text not null,
    day date not null,
    calls integer not null default 0,
    failed integer not null default 0,
    stalls integer not null default 0,
    seconds real not null default 0,
    gated_at timestamptz,
    restored_at timestamptz,
    primary key (scenario, model, day)
);
grant select, insert, update on canary_scores, model_health to a5s_gateway;
