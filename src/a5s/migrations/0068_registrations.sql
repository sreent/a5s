-- Each instance a5s registered in the Microsoft tenant's agent registry, and its Entra agent
-- identity, if it has one (core/registration.py): what it last registered, by its hash, so it
-- registers only what changed, and what the tenant last refused, if it did. The core alone.
create table if not exists registrations (
  instance_id text primary key,
  registration text,  -- the registry's id for it
  identity text,  -- its Entra agent identity's id, if it has one
  said_sha text,  -- what a5s last registered of it, by its hash: none, to register it again
  first_registered timestamptz not null default now(),
  registered_at timestamptz,
  problem text  -- what the tenant last answered that a5s couldn't use, if it did
);
alter table registrations owner to a5s_owner;
grant select, insert, update, delete on registrations to a5s_gateway;
