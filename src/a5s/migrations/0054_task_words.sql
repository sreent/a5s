-- Round 10: what tasks keep, and who may change them.
--
-- A slice's run keeps only what it said the slice came to, its status, once the slice ends:
-- what it found and what it needed of its owner are the task's, and go with it, in its export,
-- erasure and retention (core/tasking.py's end). Runs ended before this keep the same.
update runs set task_result = jsonb_build_object('status', task_result -> 'status')
 where task_result is not null and closed_at is not null
   and exists (select 1 from jsonb_object_keys(task_result) k where k <> 'status');

-- The channels app's role cancels a task, and stops a repeat, at its owner's word on their
-- page, and does nothing else to either: whatever its grants on their columns, it never sets
-- an offer going, a stopped repeat going again, or a lease to lapse (the page is the part
-- people reach, so a5s reckons with it being broken into).
create or replace function a5s_only_cancels() returns trigger language plpgsql as $$
begin
  if pg_has_role(current_user, 'a5s_channels', 'MEMBER')
     and not pg_has_role(current_user, 'a5s_gateway', 'MEMBER') then
    if tg_table_name = 'tasks' and not (new.status = 'cancelled'
        and old.status not in ('done', 'cancelled', 'failed')) then
      raise exception 'the channels app only cancels a task still open'
        using errcode = 'insufficient_privilege';
    end if;
    if tg_table_name = 'task_repeats' and not (new.status = 'stopped'
        and old.status <> 'stopped') then
      raise exception 'the channels app only stops a repeat'
        using errcode = 'insufficient_privilege';
    end if;
  end if;
  return new;
end $$;
drop trigger if exists tasks_only_cancelled on tasks;
create trigger tasks_only_cancelled before update on tasks
  for each row execute function a5s_only_cancels();
drop trigger if exists task_repeats_only_stopped on task_repeats;
create trigger task_repeats_only_stopped before update on task_repeats
  for each row execute function a5s_only_cancels();

-- And it reads none of what the run that offered a repeat read, every person's: only how each
-- stands, for its owner's page.
revoke select on task_repeats from a5s_channels;
grant select (id, number, instance_id, owner, task, days, at, status, offered_run, asked_at,
              read_outside, last_due, last_task, created_at, updated_at, replaces)
  on task_repeats to a5s_channels;

-- A read of the audit trail through the core's API records whom it asked about as a stand-in,
-- under the deployment's own key, as the auditors' page does (core/audit.py's noted).
grant select, insert on audit_key to a5s_gateway;
