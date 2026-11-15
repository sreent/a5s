-- A draft described in words (docs/studio.md#describe-it): its author's words, the model that
-- proposed what it needs, and a note on each thing it was given and why, or wasn't and why, for
-- its author to check. Its author's own, as the draft is: it goes with the draft, and when they
-- leave or ask for what a5s keeps of them to be erased.
alter table agent_drafts add column if not exists described jsonb;
