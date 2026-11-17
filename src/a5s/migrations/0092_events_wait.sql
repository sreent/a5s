-- Round 14 (docs/critique.md): an event that can't be worked on now, such as while the
-- instance that takes it is suspended, its release waits for approval, or its person's day is
-- spent, waits and is tried again, rather than being turned away for good (core/events.py).
alter table events add column if not exists not_before timestamptz;  -- when it's next tried
