-- Round 14 (docs/critique.md): the parts a version only narrows, if that's all it did, so
-- the approvals of the versions before it stand for every other part, and level 2 counts there
-- still (core/registry.py, core/gateway.py): null for a version that needed every approval
alter table settings_versions add column if not exists narrows text[];
