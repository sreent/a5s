-- Model fallbacks: when a message's run ends with its model not answering, the scheduler
-- tries the message again on the next model its release names, and its row keeps which models
-- those attempts already tried, so each is tried once (services/scheduler.py,
-- core/gateway.py's model_for).
alter table inbound add column if not exists tried_models text[] not null default '{}';
grant update (tried_models) on inbound to a5s_scheduler;
