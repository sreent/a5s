-- A draft's plan for its agent's first instance (docs/studio.md#the-designer): the parts it
-- would work in, whom it would serve, and the instances it could ask, as its authors mean to ask
-- for them. Never in force: the signed settings are, which those parts' owners approve.
alter table agent_drafts add column if not exists plan jsonb not null default '{}'::jsonb;
grant update (plan) on agent_drafts to a5s_gateway;  -- for erasure: someone it named, gone
