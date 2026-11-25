-- Why a change kept to undo can't be undone any more, where a5s knows: such as the seal key
-- that sealed how to undo it leaked, so how to undo it can't be trusted (round 16, D7)
alter table changes_made add column if not exists void text;
