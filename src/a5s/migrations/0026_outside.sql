-- Content from outside the organisation: what a run has read through the extractor, kept for
-- its questions to a5s's reader until an hour after it ends, and the mark it leaves on the
-- run, which only ever goes one way.

create table if not exists run_documents (
  run_id uuid not null,
  number int not null,
  text text not null,
  primary key (run_id, number)
);
alter table run_documents owner to a5s_owner;
grant select, insert, delete on run_documents to a5s_gateway;

grant update (read_outside) on runs to a5s_gateway;

create or replace function a5s_marked_stays_marked() returns trigger
language plpgsql as $$
begin
  if old.read_outside and not new.read_outside then
    raise exception 'a run that has read outside content stays marked';
  end if;
  return new;
end $$;
alter function a5s_marked_stays_marked() owner to a5s_owner;
drop trigger if exists runs_marked_stay_marked on runs;
create trigger runs_marked_stay_marked before update of read_outside on runs
  for each row execute function a5s_marked_stays_marked();
