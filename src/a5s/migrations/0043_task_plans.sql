-- A task's plan: its steps, each with its content and whether it's pending, in progress or
-- completed, in the shape of LangChain's todos, which its runs keep at their checkpoints, the
-- next run is shown, and its owner sees (core/tasks.py).
alter table tasks add column if not exists plan jsonb not null default '[]';
