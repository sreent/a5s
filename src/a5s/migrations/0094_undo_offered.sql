-- Round 14 (docs/critique.md): a5s tells whoever a change at level 2 was for how to undo it,
-- with its page's link, in its own note beside the agent's next message to them, once
-- (core/undoing.py): when it did, so it says so once.
alter table changes_made add column if not exists offered_at timestamptz;
