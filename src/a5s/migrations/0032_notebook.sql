-- The notebook: what an agent learns from records, kept for its instance's later runs
-- (core/notebook.py). Only a run that acts for nobody notes anything, so nobody's words are in
-- it; each entry names the records it comes from, and goes after 90 days unless they still
-- hold everything it says.

create table if not exists notebook (
  id bigserial primary key,
  instance_id text not null,
  agent text not null,
  text text not null,
  sources text[] not null,  -- the records it comes from, by their keys
  written_run uuid not null,
  written_at timestamptz not null default now(),
  renewed_at timestamptz not null default now(),
  unique (instance_id, text)
);
alter table notebook owner to a5s_owner;
grant select, insert, update (sources, renewed_at), delete on notebook to a5s_gateway;
grant usage on sequence notebook_id_seq to a5s_gateway;
grant select, delete on notebook to a5s_channels;  -- where the agent's owner removes entries
grant select (id, definition, owner, deputy, status) on instances to a5s_channels;  -- whose they are
