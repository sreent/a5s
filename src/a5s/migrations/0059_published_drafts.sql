-- Where a draft was published (core/publishing.py, docs/studio.md, step 2): the pull request
-- its author opened from it, as themselves, the last time they published it. A draft stays once
-- it's published, so its author can publish it again, adding a commit to that pull request, as
-- reviews ask, until they drop it.
alter table agent_drafts add column if not exists published text;
