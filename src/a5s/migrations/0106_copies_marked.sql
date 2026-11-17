-- What marks a copy of the ledger as the copier's own (core/anchor.py; round 15, D1): a secret
-- made once, which the database alone keeps. After a restore from a backup, only the copies the
-- copier marked stand for entries the database lacks: never one planted in the store by
-- someone who could make a chain of hashes, but not this.
create table if not exists copy_secret (
  only_one boolean primary key default true check (only_one),
  secret text not null default gen_random_uuid()::text || gen_random_uuid()::text
);
insert into copy_secret default values on conflict do nothing;
alter table copy_secret owner to a5s_owner;
grant select on copy_secret to a5s_anchor, a5s_gateway;
