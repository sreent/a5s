-- The auditors' own page, in the channels app (core/audit.py): it reads the ledger as the core's
-- API does, and puts each read in it. Until the data protection officer agrees to names, whom
-- agents acted for shows there as a stand-in, the same one each time, made with a key that
-- only the database holds: made once, at random, and never shown to anyone.
create table if not exists audit_key (
  one boolean primary key default true check (one),
  key bytea not null check (length(key) >= 32)
);
grant select, insert on audit_key to a5s_channels;
