-- What an id owes, apart by who held it: from when a5s first owed it to them, so an export and
-- an erasure take one holder's alone (core/export.py, core/erasure.py). And what the measures
-- may count as done: not what the records handed to someone else, nor what was done after a5s
-- last read them, by when it can't know (core/measures.py).
alter table obligations add column if not exists owed_since timestamptz not null default now();
alter table obligations add column if not exists handed_on boolean not null default false;
alter table obligations add column if not exists seen_owed_at timestamptz;  -- before it was done

-- When a5s last read what each scenario's records owe.
create table if not exists record_reads (
  scenario text primary key,
  read_at timestamptz not null
);
alter table record_reads owner to a5s_owner;
grant select, insert, update on record_reads to a5s_gateway;
