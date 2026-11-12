-- People's own page for their tasks, in the channels app (core/tasking.py): the core's own
-- endpoint for them, as the notebook's is for its keepers. It reads the tasks they asked
-- agents for, and cancels one at their word. It reads none of what a task's runs read.
grant select on tasks to a5s_channels;
grant update (status, lease_expires_at, last_error, not_before, updated_at) on tasks
  to a5s_channels;
