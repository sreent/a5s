-- The status's record is never ahead of the database's own clock, whoever writes it: a time set
-- ahead would hide the scheduler's being away from the status, the Status page and the
-- alerts for as long as it lasts (round 17, D5). One set back only makes it look away sooner.
create or replace function status_seen_now() returns trigger language plpgsql as $$
begin
  new.at := least(new.at, now());
  return new;
end
$$;
drop trigger if exists status_seen_now on status_seen;
create trigger status_seen_now before insert or update on status_seen
  for each row execute function status_seen_now();
