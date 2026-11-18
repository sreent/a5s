-- A person's own words in a conversation are the core's to keep, from the message as it arrived
-- (round 15, F10): the scheduler's role could write a turn into someone's conversation as
-- theirs, which later runs read as what they said. The core writes them as a run opens; the
-- scheduler writes the agent's words and a5s's own, as each run's, and a person's never.
create or replace function a5s_turns_theirs() returns trigger language plpgsql as $$
begin
  if new.role = 'person' and pg_has_role(current_user, 'a5s_scheduler', 'MEMBER')
     and not pg_has_role(current_user, 'a5s_gateway', 'MEMBER') then
    raise exception 'a person''s words are the core''s to keep, from what arrived'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end $$;
drop trigger if exists turns_theirs on turns;
create trigger turns_theirs before insert or update on turns
  for each row execute function a5s_turns_theirs();
