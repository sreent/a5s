-- A change a task's later run asks for again is the same change (core/counts.py): the core
-- finds it among every run of the task, by its digest.
create index if not exists action_counts_by_change on action_counts (change);
