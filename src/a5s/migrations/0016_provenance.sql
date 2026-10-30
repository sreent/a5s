-- Provenance: the keys, amounts and dates each run has read, and where from, so the ones an
-- agent writes can be matched exactly against them. What it writes that matches none is
-- flagged as its own. And handles: sensitive values a tool returns, such as a contact, which
-- the agent gets as a handle and passes on without seeing.

create table if not exists run_reads (
  run_id uuid not null,
  source text not null,  -- such as a tool's name, or the case's brief
  kind text not null,  -- key, amount or date
  norm text not null,  -- how it's matched, such as GBP 1240.50
  text text not null,  -- as it was written
  primary key (run_id, kind, norm, source)
);

alter table run_reads owner to a5s_owner;

grant select, insert on run_reads to a5s_gateway;

create table if not exists run_handles (
  run_id uuid not null,
  handle text not null,  -- such as 7f3a9c2b, which the agent writes as [h:7f3a9c2b]
  field text not null,  -- the field it came in, such as contact
  value text not null,
  source text not null,  -- the tool that returned it
  primary key (run_id, handle)
);

alter table run_handles owner to a5s_owner;

grant select, insert on run_handles to a5s_gateway;
