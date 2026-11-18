-- What a seal binds (round 15, B1, B2, F3, F9). A held change keeps the nonce its digest was
-- made with, so the core makes it again from what it holds and makes nothing that isn't what its
-- deciders signed; a change kept to undo is sealed, so its undo is the one the core kept; a sample
-- is sealed when the core draws it, so only what the core drew counts; and the ledger says which
-- of a5s's parts wrote each entry, which none of them may say for itself.
alter table proposals add column if not exists nonce text;
alter table changes_made add column if not exists seal text;
alter table samples add column if not exists drawn_seal text;
grant update (drawn_seal) on samples to a5s_gateway;
alter table ledger add column if not exists writer text not null default current_user;
revoke insert on ledger from a5s_gateway, a5s_channels;
grant insert (seq, entry, prev_hash, hash) on ledger to a5s_gateway, a5s_channels;
