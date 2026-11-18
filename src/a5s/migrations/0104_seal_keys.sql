-- The core's seal keys, by fingerprint, never the key: the core won't start without one it
-- sealed with that isn't retired, nor with one retired as leaked, and `a5s seal-again`
-- retires a key once what it sealed is sealed again with the first (core/rotation.py;
-- round 15, D2).
create table if not exists seal_keys (
  fingerprint text primary key,
  first_seen timestamptz not null default now(),
  sealing_since timestamptz,  -- while the core seals with it, as the first of its keys
  retired_at timestamptz,  -- once nothing it sealed waits on it, or it leaked
  leaked boolean not null default false
);
alter table seal_keys owner to a5s_owner;
grant select, insert, update on seal_keys to a5s_gateway;
