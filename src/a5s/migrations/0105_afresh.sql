-- Someone starts their conversation with an agent afresh: no run is given what came before,
-- nor marked by it, and its summaries go (core/afresh.py; round 15, A4)
create table if not exists fresh_starts (
  person text not null,  -- the conversation's: someone's own, or a group chat's
  agent text not null,
  through bigint not null,  -- its last turn before it
  at timestamptz not null default now(),
  primary key (person, agent)
);
alter table fresh_starts owner to a5s_owner;
grant select, insert, update, delete on fresh_starts to a5s_gateway;  -- and archiving, erasure
grant select on fresh_starts to a5s_scheduler;  -- what a run is given starts after it
-- which turns a summary folds none of: those a marked run wrote (services/context.py)
grant select (id, read_outside) on runs to a5s_scheduler;
-- A summary that holds what a run wrote after it read outside content marks a run given it.
-- From now, a summary folds none of it (services/scheduler.py)
alter table summaries add column if not exists outside boolean not null default false;
update summaries s set outside = true where exists (
  select 1 from turns t left join runs r on r.id = t.run_id
  where t.person = s.person and t.agent = s.agent and t.topic = s.topic and t.id <= s.through
  and (t.marked or (r.read_outside and t.role <> 'person')));
