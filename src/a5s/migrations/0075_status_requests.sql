-- Suspending or resuming an instance from its page in the studio, signed in afresh for that
-- act alone, which the gateway checks again and carries out at its next sweep, within a minute
-- (core/suspension.py).
create table if not exists status_requests (
  id uuid primary key default gen_random_uuid(),
  instance_id text not null,
  action text not null check (action in ('suspend', 'resume')),
  person text not null,  -- who asked, as the directory knows them
  nonce text not null unique,  -- binds the sign-in to this act: it works once
  salt text not null,
  token text not null unique,  -- the sign-in, by its hash: kept, not usable
  proof text,  -- the sign-in itself, for the gateway to check again, until it's carried out
  issuer text not null,
  asked_at timestamptz not null default now(),
  ended_at timestamptz,
  outcome text  -- what became of it: made, or why not, as the gateway found
);
create index if not exists status_requests_waiting on status_requests (asked_at)
  where ended_at is null;
alter table status_requests owner to a5s_owner;

-- The channels' endpoint, where people ask, and see what they asked; the gateway, which carries
-- it out, and lets each go a day after it ends, as the ledger keeps it (core/retention.py).
grant select, insert on status_requests to a5s_channels;
grant select, update, delete on status_requests to a5s_gateway;

-- Who suspended an instance, whom its page names, and who alone may resume it from there.
grant select (suspended_by) on instances to a5s_channels;
