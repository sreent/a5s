-- What the data protection officer asks for on the core's page, signed in afresh for that
-- request alone: to export, or erase, what a5s keeps about one person, which someone from the
-- team that runs a5s then carries out, once, within ten minutes (core/officer.py).
create table if not exists officer_requests (
  id uuid primary key default gen_random_uuid(),
  action text not null check (action in ('export', 'erase')),
  person text not null,  -- whose data
  officer text not null,  -- who asked, as the directory knows them
  nonce text not null unique,  -- binds the sign-in to this request: it works once
  salt text not null,
  token text not null unique,  -- the sign-in, by its hash: kept, not usable
  proof text,  -- the sign-in itself, for the gateway to check again, until it's used
  issuer text not null,
  asked_at timestamptz not null default now(),
  used_at timestamptz
);
create index if not exists officer_requests_waiting on officer_requests (action, person, asked_at)
  where used_at is null;
alter table officer_requests owner to a5s_owner;

-- The channels' endpoint, where the officer asks; the gateway, which carries it out, and lets
-- the requests go a day after they're asked (core/retention.py).
grant select, insert on officer_requests to a5s_channels;
grant select, update, delete on officer_requests to a5s_gateway;
