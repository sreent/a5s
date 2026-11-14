-- Asking for an agent (core/asks.py, docs/studio.md): someone who knows of an agent, from the
-- studio's catalogue, asks to be served by it. Only those who approve versions of the settings
-- propose one, so an ask is a request for them, not a version: the agent's owners and its
-- instances' approvers see it waiting, and answer it with a version that serves the asker, or
-- decline it. Nothing anyone wrote: who asked, for which agent, when, and how it ended.
create table if not exists agent_asks (
    id uuid primary key,
    scenario text not null,
    person text not null,
    agent text not null,
    asked_at timestamptz not null default now(),
    ended_at timestamptz,
    outcome text check (outcome in ('served', 'withdrawn', 'declined', 'lapsed')),
    ended_by text,  -- who declined it, or withdrew it
    check ((ended_at is null) = (outcome is null))
);
-- One open ask for each person and agent
create unique index if not exists agent_asks_open on agent_asks (scenario, person, agent)
    where ended_at is null;
grant select, insert, update on agent_asks to a5s_channels;
grant select, update, delete on agent_asks to a5s_gateway;  -- the sweep, exports, erasure and departures
