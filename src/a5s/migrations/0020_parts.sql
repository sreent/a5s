-- Parts: each instance works in the parts of the business its settings name, with a level in
-- each, which their owners approve. Its level is the lowest of theirs, for calls about no
-- record in particular.

alter table instances add column if not exists parts jsonb not null default '{}'::jsonb;
