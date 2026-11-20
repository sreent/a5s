-- A message has at most one run still at work. A crashed scheduler's replacement waits for
-- the old run's sweep, rather than overlap it; closed model-fallback attempts stay allowed.
create unique index if not exists one_open_run_per_message
  on runs ((trigger->>'inbound'))
  where trigger->>'kind' = 'message' and closed_at is null;
