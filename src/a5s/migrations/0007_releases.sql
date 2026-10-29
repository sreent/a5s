-- The releases of a5s this deployment has recorded, each with exactly the manifest
-- its people signed, and their signatures. The core checks them again itself
-- before it opens a run, so changing a record approves nothing.

create table if not exists releases (
  digest text primary key,  -- the manifest's sha256
  version text not null,
  manifest bytea not null,  -- exactly what was signed
  previous text references releases (digest),  -- the approved release it's weighed against
  signatures jsonb not null default '[]',
  advisory text,  -- the security advisory it fixes, if it's recorded as fixing one
  recorded_at timestamptz not null default now(),
  approved_at timestamptz
);

alter table releases owner to a5s_owner;
grant select on releases to a5s_gateway;
