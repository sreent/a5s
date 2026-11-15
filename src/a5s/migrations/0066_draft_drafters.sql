-- Who drafted a draft before whoever holds it now, oldest first, each with when and how it
-- went on: handed over, or copied into a draft of someone else's (core/drafts.py). Its page
-- says it was handed over, and its pull request names everyone who drafted it, not its last
-- holder alone (round 11, E-4). The core rewrites it to erase someone it names.
alter table agent_drafts add column if not exists before jsonb not null default '[]'::jsonb;
grant update (before) on agent_drafts to a5s_gateway;
