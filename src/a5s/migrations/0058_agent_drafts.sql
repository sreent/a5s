-- Drafts of agents, which the studio keeps for the people who author them (core/drafts.py,
-- docs/studio.md, step 2): an agent's folder, file by file, until its author publishes it or
-- drops it. A draft is never in force: no run uses it, and nothing about it is signed. It
-- serves its author while they're here, so it goes when they leave, and when they ask for what
-- a5s keeps of them to be erased; what a5s exports for them shows it.
create table if not exists agent_drafts (
  id uuid primary key default gen_random_uuid(),
  person text not null,         -- its author, by their id in the directory
  agent text not null,          -- a new agent's name, or the agent it changes
  based_on text not null,       -- the template, or the agent's release, it began as
  files jsonb not null,         -- each file of the agent's folder, by its path in it
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (person, agent)
);
grant select, insert, update, delete on agent_drafts to a5s_channels;
grant select, delete on agent_drafts to a5s_gateway;  -- for exports, erasure and departures
