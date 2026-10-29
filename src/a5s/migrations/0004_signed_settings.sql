-- The core checks the signed settings itself, at every run: it keeps exactly
-- the bytes that were signed, and their signatures, beside each version. And it
-- checks an instance's status against the last change the ledger records.

alter table settings_versions add column if not exists raw bytea;
alter table settings_versions add column if not exists signatures jsonb;

create index if not exists ledger_admin on ledger (instance_id, seq) where kind = 'admin';
