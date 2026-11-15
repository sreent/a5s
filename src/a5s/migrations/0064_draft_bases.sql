-- The folder a draft began from, file by file (core/drafts.py): the agent's as released, or
-- none for a new agent's. A publish merges it file by file with what's on the branch now, so a
-- draft begun before a change was merged there never takes that change back.
alter table agent_drafts add column if not exists base jsonb;
