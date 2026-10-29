-- Each part of a5s connects as its own role, with only the rights its job needs,
-- so a service that's compromised can't write the core's records. The core's
-- tables belong to a role nobody logs in as, and no role may change, delete or
-- truncate the ledger. Setting up the schema and applying signed settings is
-- left to the database's administrator.

do $$
declare
  part text;
begin
  if not exists (select from pg_roles where rolname = 'a5s_owner') then
    create role a5s_owner nologin;
  end if;
  foreach part in array array['a5s_gateway', 'a5s_channels', 'a5s_scheduler', 'a5s_anchor'] loop
    if not exists (select from pg_roles where rolname = part) then
      execute format('create role %I login', part);
    end if;
  end loop;
end $$;

alter table instances owner to a5s_owner;
alter table runs owner to a5s_owner;
alter table settings_versions owner to a5s_owner;
alter table ledger owner to a5s_owner;
alter table inbound owner to a5s_owner;
alter table turns owner to a5s_owner;
alter table outbox owner to a5s_owner;
alter table leases owner to a5s_owner;
alter function a5s_ledger_append_only() owner to a5s_owner;

-- Truncating skips row triggers, so the ledger refuses it separately.
drop trigger if exists ledger_no_truncate on ledger;
create trigger ledger_no_truncate before truncate on ledger
  for each statement execute function a5s_ledger_append_only();

-- The owner too, as Postgres checks foreign keys with its rights.
grant usage on schema public to a5s_owner, a5s_gateway, a5s_channels, a5s_scheduler, a5s_anchor;

-- The gateway, in the core: runs, decisions, and what it sends.
grant select, update (status, suspended_by, updated_at) on instances to a5s_gateway;
grant select, insert, update (closed_at, outcome) on runs to a5s_gateway;
grant select on settings_versions to a5s_gateway;
grant select, insert on ledger to a5s_gateway;
grant select, update (answered_at, notices) on inbound to a5s_gateway;
grant select, insert, update (delivered_at) on outbox to a5s_gateway;
grant usage on sequence outbox_id_seq to a5s_gateway;

-- The channels' endpoint, in the core, where people's messages arrive.
grant select, insert on inbound to a5s_channels;
grant select, insert on ledger to a5s_channels;

-- The scheduler, a service: it reads what it needs, and writes only its own records.
grant select on instances to a5s_scheduler;
grant select, update (claimed_at) on inbound to a5s_scheduler;
grant select, insert on turns to a5s_scheduler;
grant usage on sequence turns_id_seq to a5s_scheduler;
grant select, insert, update (delivered_at) on outbox to a5s_scheduler;
grant usage on sequence outbox_id_seq to a5s_scheduler;
grant select, insert, update, delete on leases to a5s_scheduler;

-- The copier, which only reads the ledger.
grant select on ledger to a5s_anchor;
